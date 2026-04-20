#!/usr/bin/env python3
"""
fetch_scholar.py
Fetches research metrics and enriched publication data using:
  1. scholarly       → Google Scholar: citation counts, h-index, i10-index
  2. OpenAlex API    → DOI, Open Access status, journal source metrics
                       (2-year mean citedness ≈ Impact Factor, CiteScore)
  3. Scimago/OpenAlex → Quartile (Q1–Q4) per journal

No API keys required. Run: python scripts/fetch_scholar.py
"""

import json, os, sys, time, re
from datetime import datetime, timezone

SCHOLAR_ID  = "udy6g1kAAAAJ"    # Google Scholar user ID
ORCID_ID    = "0000-0003-0127-9982"
EMAIL       = "mushfiqul.siraji@northsouth.edu"  # polite OpenAlex header
OA_HEADERS  = {"User-Agent": f"AcademicWebsite/1.0 (mailto:{EMAIL})"}

# ── Helpers ──────────────────────────────────────────────────────────────────

def get_json(url, retries=3, delay=5):
    import urllib.request, urllib.error
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=OA_HEADERS)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            print(f"  ⚠ GET failed ({url[:80]}…): {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    return None


def normalize_title(t):
    return re.sub(r'[^a-z0-9]', '', t.lower())[:60]


# ── Step 1: Google Scholar (scholarly) ───────────────────────────────────────

def fetch_scholar_metrics(scholar_id, retries=3):
    from scholarly import scholarly as sc
    for attempt in range(retries):
        try:
            print(f"  Attempt {attempt+1}: fetching Scholar profile…")
            author = sc.search_author_id(scholar_id)
            sc.fill(author, sections=["basics", "indices", "publications"])
            return author
        except Exception as e:
            print(f"  Error: {e}")
            if attempt < retries - 1:
                time.sleep((attempt + 1) * 20)
    raise RuntimeError("Scholar fetch failed after retries")


# ── Step 2: OpenAlex – works by ORCID ────────────────────────────────────────

def fetch_openalex_works(orcid):
    print("  Fetching OpenAlex works…")
    url = (
        f"https://api.openalex.org/works"
        f"?filter=author.orcid:{orcid}"
        f"&per-page=100"
        f"&select=id,doi,title,publication_year,cited_by_count,"
        f"open_access,primary_location,authorships,best_oa_location"
    )
    data = get_json(url)
    if not data:
        return []
    works = data.get("results", [])
    print(f"  Found {len(works)} works on OpenAlex")
    return works


# ── Step 3: OpenAlex – journal/source metrics ─────────────────────────────────

_source_cache = {}

def fetch_source_metrics(source_id):
    """Returns dict with if_approx, cite_score, quartile, issn."""
    if not source_id:
        return {}
    if source_id in _source_cache:
        return _source_cache[source_id]

    data = get_json(f"https://api.openalex.org/sources/{source_id}")
    if not data:
        _source_cache[source_id] = {}
        return {}

    # 2yr_mean_citedness is OpenAlex's approximation of Impact Factor
    result = {
        "if_approx":   round(data.get("2yr_mean_citedness", 0) or 0, 3),
        "cite_score":  round(data.get("cited_by_count", 0) /
                             max(data.get("works_count", 1), 1) * 2, 2),
        "h_index":     data.get("h_index", None),
        "issn":        (data.get("issn_l") or
                        (data.get("issn") or [None])[0]),
        "publisher":   data.get("host_organization_name", ""),
        "quartile":    None,  # filled below
        "is_oa_venue": data.get("is_oa", False),
    }

    # Derive quartile from OpenAlex topic rankings (best available free source)
    topics = data.get("topics", [])
    if topics:
        # Use the top topic's subfield percentile rank
        top = topics[0]
        rank = top.get("subfield", {})
        # OpenAlex doesn't expose quartile directly; derive from count rank if available
        # Fall back to CiteScore-based heuristic
        pass

    # Quartile heuristic: based on 2yr_mean_citedness against known thresholds
    # These are rough cross-discipline thresholds (Q1 > 2.5 is conservative)
    if_val = result["if_approx"]
    if if_val >= 5.0:
        result["quartile"] = "Q1"
    elif if_val >= 2.0:
        result["quartile"] = "Q1"
    elif if_val >= 1.0:
        result["quartile"] = "Q2"
    elif if_val > 0:
        result["quartile"] = "Q3"
    else:
        result["quartile"] = None   # unknown

    _source_cache[source_id] = result
    return result


# ── Step 4: Scimago quartile via ISSN ────────────────────────────────────────

_scimago_cache = {}

def fetch_scimago_quartile(issn):
    """Scrapes Scimago for the best quartile of a journal by ISSN."""
    if not issn:
        return None
    clean = issn.replace("-", "")
    if clean in _scimago_cache:
        return _scimago_cache[clean]

    import urllib.request
    url = f"https://www.scimagojr.com/journalsearch.php?q={clean}&tip=issn&clean=0"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; AcademicBot/1.0)"
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="ignore")

        # Extract quartile from HTML (e.g. "Q1" badge)
        matches = re.findall(r'<span[^>]*class="[^"]*quartile[^"]*"[^>]*>\s*(Q\d)\s*</span>', html)
        if not matches:
            matches = re.findall(r'\b(Q[1-4])\b', html[:3000])

        quartile = matches[0] if matches else None
        _scimago_cache[clean] = quartile
        time.sleep(1.5)  # polite delay
        return quartile
    except Exception as e:
        print(f"  ⚠ Scimago fetch failed for {issn}: {e}")
        _scimago_cache[clean] = None
        return None


# ── Step 5: Merge Scholar + OpenAlex data ─────────────────────────────────────

def merge_publications(scholar_pubs, oa_works):
    """Match Scholar publications with OpenAlex works and enrich."""

    # Build OA lookup by normalized title
    oa_by_title = {}
    for w in oa_works:
        key = normalize_title(w.get("title") or "")
        if key:
            oa_by_title[key] = w

    enriched = []
    for pub in scholar_pubs:
        bib   = pub.get("bib", {})
        title = bib.get("title", "").strip()
        if not title:
            continue

        entry = {
            "title":     title,
            "year":      bib.get("pub_year", ""),
            "journal":   bib.get("journal", bib.get("booktitle", bib.get("conference", ""))),
            "authors":   bib.get("author", ""),
            "volume":    bib.get("volume", ""),
            "pages":     bib.get("pages", ""),
            "citations_scholar": pub.get("num_citations", 0),
            # enriched fields (filled below)
            "doi":          None,
            "citations_oa": None,
            "open_access":  False,
            "oa_url":       None,
            "if_approx":    None,
            "cite_score":   None,
            "quartile":     None,
            "issn":         None,
            "publisher":    None,
        }

        # Match with OpenAlex
        key = normalize_title(title)
        oa  = oa_by_title.get(key)
        if oa:
            # DOI
            doi_raw = oa.get("doi") or ""
            entry["doi"] = doi_raw.replace("https://doi.org/", "") if doi_raw else None

            # Citations
            entry["citations_oa"] = oa.get("cited_by_count", 0)

            # Open Access
            oa_info = oa.get("open_access", {})
            entry["open_access"] = oa_info.get("is_oa", False)
            best = oa.get("best_oa_location") or {}
            entry["oa_url"] = best.get("pdf_url") or best.get("landing_page_url")

            # Journal metrics via source
            loc    = oa.get("primary_location") or {}
            source = loc.get("source") or {}
            src_id = source.get("id")

            if src_id:
                metrics = fetch_source_metrics(src_id)
                entry.update({
                    "if_approx":  metrics.get("if_approx"),
                    "cite_score": metrics.get("cite_score"),
                    "quartile":   metrics.get("quartile"),
                    "issn":       metrics.get("issn"),
                    "publisher":  metrics.get("publisher"),
                })

                # Try Scimago for more accurate quartile
                if entry["issn"]:
                    sq = fetch_scimago_quartile(entry["issn"])
                    if sq:
                        entry["quartile"] = sq

        # Use best citation count
        entry["citations"] = max(
            entry["citations_scholar"] or 0,
            entry["citations_oa"] or 0
        )

        enriched.append(entry)

    # Sort by year desc, citations desc
    enriched.sort(key=lambda p: (
        -(int(p["year"]) if str(p["year"]).isdigit() else 0),
        -p["citations"]
    ))
    return enriched


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        from scholarly import scholarly as _
    except ImportError:
        print("ERROR: scholarly not installed. Run: pip install scholarly")
        sys.exit(1)

    print("\n📚 Step 1: Google Scholar…")
    author = fetch_scholar_metrics(SCHOLAR_ID)

    metrics = {
        "citations":   author.get("citedby",   0),
        "hIndex":      author.get("hindex",     0),
        "i10Index":    author.get("i10index",   0),
        "citations5":  author.get("citedby5y",  0),
        "hIndex5":     author.get("hindex5y",   0),
        "i10Index5":   author.get("i10index5y", 0),
    }
    print(f"  ✓ Citations: {metrics['citations']}, h={metrics['hIndex']}, i10={metrics['i10Index']}")

    print("\n🌐 Step 2: OpenAlex enrichment…")
    oa_works = fetch_openalex_works(ORCID_ID)

    print("\n🔬 Step 3: Merging + enriching journal metrics…")
    scholar_pubs = author.get("publications", [])
    publications = merge_publications(scholar_pubs, oa_works)
    print(f"  ✓ Enriched {len(publications)} publications")

    # Summary stats
    with_doi  = sum(1 for p in publications if p.get("doi"))
    with_oa   = sum(1 for p in publications if p.get("open_access"))
    with_if   = sum(1 for p in publications if p.get("if_approx"))
    with_q1   = sum(1 for p in publications if p.get("quartile") == "Q1")
    print(f"  DOI: {with_doi} | OA: {with_oa} | IF data: {with_if} | Q1: {with_q1}")

    # ── Output ────────────────────────────────────────────────────────────────
    output = {
        "_meta": {
            "updated":    datetime.now(timezone.utc).isoformat(),
            "scholar_id": SCHOLAR_ID,
            "orcid":      ORCID_ID,
            "sources":    ["Google Scholar (scholarly)", "OpenAlex API", "Scimago"]
        },
        "metrics":      metrics,
        "publications": publications,
    }

    os.makedirs("data", exist_ok=True)
    out_path = "data/scholar_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved to {out_path}")
    print(f"   Last updated: {output['_meta']['updated']}")


if __name__ == "__main__":
    main()
