#!/usr/bin/env python3
"""
fetch_scholar.py
Primary source: OpenAlex API (via ORCID) — reliable, no rate limits, no key needed
Secondary source: Google Scholar (scholarly) — metrics only (citations, h-index, i10)
Also fetches: DOI, OA status, IF approx, CiteScore, Quartile from OpenAlex + Scimago

Run locally:  python scripts/fetch_scholar.py
GitHub Action runs this every morning at 06:00 UTC automatically.
"""

import json, os, sys, time, re
from datetime import datetime, timezone

# ── Identity — verify these match YOUR profiles ──────────────────────────────
SCHOLAR_ID = "udy6g1kAAAAJ"          # from scholar.google.com/citations?user=THIS
ORCID_ID   = "0000-0003-0127-9982"   # from orcid.org/THIS
EMAIL      = "mushfiqul.siraji@northsouth.edu"
OA_HEADERS = {
    "User-Agent": f"AcademicWebsite/1.0 (mailto:{EMAIL})",
    "Accept":     "application/json"
}

# ── HTTP helper ───────────────────────────────────────────────────────────────
def get_json(url, retries=3, delay=6):
    import urllib.request, urllib.error
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=OA_HEADERS)
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8", errors="replace"))
        except Exception as e:
            print(f"  ⚠ [{attempt+1}/{retries}] GET failed: {e}  ({url[:80]})")
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    return None

def normalize(t):
    return re.sub(r'[^a-z0-9]', '', (t or "").lower())[:60]

# ── Step 1: OpenAlex author profile (ORCID) ───────────────────────────────────
def fetch_oa_author(orcid):
    print(f"  Querying OpenAlex for ORCID {orcid}…")
    url = f"https://api.openalex.org/authors?filter=orcid:{orcid}"
    data = get_json(url)
    if not data or not data.get("results"):
        print("  ⚠ OpenAlex author not found")
        return None
    author = data["results"][0]
    print(f"  ✓ Found: {author.get('display_name')} (OA id: {author.get('id')})")
    return author

# ── Step 2: OpenAlex works (ORCID filter, paginated) ─────────────────────────
def fetch_oa_works(orcid):
    print("  Fetching works from OpenAlex…")
    all_works, page, per_page = [], 1, 100
    while True:
        url = (
            f"https://api.openalex.org/works"
            f"?filter=author.orcid:{orcid}"
            f"&per-page={per_page}&page={page}"
            f"&select=id,doi,title,publication_year,cited_by_count,"
            f"open_access,primary_location,authorships,best_oa_location,"
            f"counts_by_year"
        )
        data = get_json(url)
        if not data: break
        results = data.get("results", [])
        all_works.extend(results)
        meta = data.get("meta", {})
        if len(all_works) >= meta.get("count", 0) or len(results) < per_page:
            break
        page += 1
        time.sleep(1)
    print(f"  ✓ {len(all_works)} works found on OpenAlex")
    return all_works

# ── Step 3: Google Scholar — metrics only ─────────────────────────────────────
def fetch_scholar_metrics(scholar_id, retries=4):
    print(f"  Fetching Google Scholar metrics for ID: {scholar_id}…")
    try:
        from scholarly import scholarly as sc
    except ImportError:
        print("  ⚠ scholarly not installed — skipping Scholar metrics")
        return None

    for attempt in range(retries):
        try:
            # search_author_id is more reliable than search_author
            author = sc.search_author_id(scholar_id)
            # Only fill basics+indices — avoid filling publications (slow + unreliable)
            sc.fill(author, sections=["basics", "indices"])

            # Verify we got the right person
            name = author.get("name", "")
            scholar_url = author.get("scholar_id", "")
            print(f"  ✓ Scholar: {name} (id: {scholar_url})")
            if "siraji" not in name.lower() and "mushfiqul" not in name.lower():
                print(f"  ⚠ WARNING: Scholar returned unexpected author: {name}")
                print(f"     Expected Mushfiqul Anwar Siraji — skipping Scholar metrics")
                return None

            return {
                "citations":  author.get("citedby",   0),
                "hIndex":     author.get("hindex",     0),
                "i10Index":   author.get("i10index",   0),
                "citations5": author.get("citedby5y",  0),
                "hIndex5":    author.get("hindex5y",   0),
                "i10Index5":  author.get("i10index5y", 0),
            }
        except Exception as e:
            print(f"  ⚠ Scholar attempt {attempt+1}: {e}")
            if attempt < retries - 1:
                time.sleep(20 * (attempt + 1))
    print("  ⚠ Scholar metrics unavailable after retries — using OpenAlex counts")
    return None

# ── Step 4: Journal source metrics ───────────────────────────────────────────
_src_cache = {}

def get_source_metrics(source_id):
    if not source_id: return {}
    if source_id in _src_cache: return _src_cache[source_id]
    data = get_json(f"https://api.openalex.org/sources/{source_id}")
    if not data:
        _src_cache[source_id] = {}
        return {}
    if2yr = round(data.get("2yr_mean_citedness") or 0, 3)
    works  = max(data.get("works_count") or 1, 1)
    cites  = data.get("cited_by_count") or 0
    issn   = data.get("issn_l") or ((data.get("issn") or [None])[0])
    result = {
        "if_approx":  if2yr if if2yr > 0 else None,
        "cite_score": round(cites / works * 2, 2) if cites else None,
        "issn":       issn,
        "publisher":  data.get("host_organization_name", ""),
        "is_oa":      data.get("is_oa", False),
        "quartile":   _quartile_from_if(if2yr),
    }
    _src_cache[source_id] = result
    return result

def _quartile_from_if(if_val):
    if not if_val: return None
    if if_val >= 5.0: return "Q1"
    if if_val >= 2.0: return "Q1"
    if if_val >= 1.0: return "Q2"
    return "Q3"

# ── Step 5: Scimago quartile via ISSN (best available free source) ────────────
_scimago_cache = {}

def scimago_quartile(issn):
    if not issn: return None
    key = issn.replace("-", "")
    if key in _scimago_cache: return _scimago_cache[key]
    import urllib.request
    url = f"https://www.scimagojr.com/journalsearch.php?q={key}&tip=issn&clean=0"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="ignore")
        m = re.findall(r'<span[^>]*quartile[^>]*>\s*(Q\d)\s*</span>', html)
        if not m: m = re.findall(r'\b(Q[1-4])\b', html[:4000])
        q = m[0] if m else None
        _scimago_cache[key] = q
        time.sleep(1.5)
        return q
    except Exception as e:
        print(f"  ⚠ Scimago error for {issn}: {e}")
        _scimago_cache[key] = None
        return None

# ── Step 6: Build enriched publication list ───────────────────────────────────
def build_publications(oa_works):
    publications = []
    for w in oa_works:
        title = (w.get("title") or "").strip()
        if not title: continue

        doi_raw = w.get("doi") or ""
        doi     = doi_raw.replace("https://doi.org/", "").strip() if doi_raw else None

        oa_info = w.get("open_access") or {}
        best    = w.get("best_oa_location") or {}
        oa_url  = best.get("pdf_url") or best.get("landing_page_url")

        # Authors — mark Siraji
        auths = w.get("authorships") or []
        author_names = []
        for a in auths:
            name = a.get("author", {}).get("display_name", "")
            if name: author_names.append(name)
        authors_str = ", ".join(author_names)

        # Journal metrics
        loc    = w.get("primary_location") or {}
        source = loc.get("source") or {}
        src_id = source.get("id")
        sm     = get_source_metrics(src_id)
        issn   = sm.get("issn")
        q      = scimago_quartile(issn) if issn else sm.get("quartile")

        pub = {
            "title":        title,
            "year":         str(w.get("publication_year") or ""),
            "journal":      source.get("display_name", ""),
            "authors":      authors_str,
            "doi":          doi,
            "citations":    w.get("cited_by_count", 0),
            "open_access":  oa_info.get("is_oa", False),
            "oa_url":       oa_url,
            "if_approx":    sm.get("if_approx"),
            "cite_score":   sm.get("cite_score"),
            "quartile":     q or sm.get("quartile"),
            "issn":         issn,
            "publisher":    sm.get("publisher", ""),
        }
        publications.append(pub)

    publications.sort(key=lambda p: (
        -(int(p["year"]) if p["year"].isdigit() else 0),
        -p["citations"]
    ))
    return publications

# ── Step 7: Citations by year (from OpenAlex author profile) ──────────────────
def build_citations_by_year(oa_author):
    counts = (oa_author or {}).get("counts_by_year") or []
    result = {}
    for c in counts:
        yr = str(c.get("year", ""))
        if yr and int(yr) >= 2022:
            result[yr] = c.get("cited_by_count", 0)
    return result

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "="*60)
    print("Academic Website — Scholar Data Fetch")
    print(f"ORCID:  {ORCID_ID}")
    print(f"Scholar ID: {SCHOLAR_ID}")
    print("="*60)

    # 1. OpenAlex author
    print("\n🌐 Step 1: OpenAlex author profile…")
    oa_author = fetch_oa_author(ORCID_ID)

    # 2. OpenAlex works
    print("\n📄 Step 2: OpenAlex works…")
    oa_works = fetch_oa_works(ORCID_ID)

    # 3. Google Scholar metrics
    print("\n📊 Step 3: Google Scholar metrics…")
    scholar_metrics = fetch_scholar_metrics(SCHOLAR_ID)

    # Build metrics — prefer Scholar for citation metrics (more up-to-date)
    # Fall back to OpenAlex if Scholar fails or returns wrong person
    oa_citations = (oa_author or {}).get("cited_by_count", 0)
    oa_hindex    = (oa_author or {}).get("summary_stats", {}).get("h_index", 0)
    oa_i10       = sum(1 for w in oa_works if (w.get("cited_by_count") or 0) >= 10)

    if scholar_metrics:
        metrics = scholar_metrics
        print(f"  Using Scholar metrics: {metrics['citations']} citations, h={metrics['hIndex']}")
    else:
        metrics = {
            "citations":  oa_citations,
            "hIndex":     oa_hindex,
            "i10Index":   oa_i10,
            "citations5": 0,
            "hIndex5":    0,
            "i10Index5":  0,
        }
        print(f"  Using OpenAlex metrics: {metrics['citations']} citations, h={metrics['hIndex']}")

    # 4. Publications
    print("\n🔬 Step 4: Enriching publications with journal metrics…")
    publications = build_publications(oa_works)
    with_doi  = sum(1 for p in publications if p.get("doi"))
    with_oa   = sum(1 for p in publications if p.get("open_access"))
    with_q    = sum(1 for p in publications if p.get("quartile"))
    print(f"  ✓ {len(publications)} pubs | DOI: {with_doi} | OA: {with_oa} | Quartile: {with_q}")

    # 5. Citations by year
    print("\n📈 Step 5: Citations by year…")
    citations_by_year = build_citations_by_year(oa_author)
    print(f"  ✓ Years: {sorted(citations_by_year.keys())}")

    # 6. Save
    output = {
        "_meta": {
            "updated":    datetime.now(timezone.utc).isoformat(),
            "scholar_id": SCHOLAR_ID,
            "orcid":      ORCID_ID,
            "sources":    ["OpenAlex (primary)", "Google Scholar (metrics)", "Scimago (quartile)"]
        },
        "metrics":           metrics,
        "citations_by_year": citations_by_year,
        "publications":      publications,
    }

    os.makedirs("data", exist_ok=True)
    out_path = "data/scholar_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    total_cites = sum(p["citations"] for p in publications)
    print(f"\n✅ Saved {len(publications)} publications to {out_path}")
    print(f"   Total citations across works: {total_cites}")
    print(f"   Last updated: {output['_meta']['updated']}")
    print("="*60)

if __name__ == "__main__":
    main()
