#!/usr/bin/env python3
"""
fetch_scholar.py
Fetches research metrics and publication data from Google Scholar
using the `scholarly` library. Writes to data/scholar_data.json.

Run locally:  python scripts/fetch_scholar.py
GitHub Action runs this automatically on a schedule.
"""

import json
import os
import time
import sys
from datetime import datetime, timezone

SCHOLAR_ID = "udy6g1kAAAAJ"  # From Google Scholar URL: ?user=udy6g1kAAAAJ

def fetch_with_retry(scholar_id, max_retries=3):
    from scholarly import scholarly

    for attempt in range(max_retries):
        try:
            print(f"Attempt {attempt + 1}/{max_retries}: fetching author profile...")
            author = scholarly.search_author_id(scholar_id)
            scholarly.fill(author, sections=["basics", "indices", "publications"])
            return author
        except Exception as e:
            print(f"  Error: {e}")
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 15
                print(f"  Waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                raise

def extract_coauthors(publications):
    """Extract unique co-author names from publication author strings."""
    from collections import Counter
    coauthor_counts = Counter()

    for pub in publications:
        authors_str = pub.get("authors", "")
        # Split by comma or " and "
        authors = [a.strip() for a in authors_str.replace(" and ", ", ").split(",")]
        for author in authors:
            author = author.strip()
            # Skip self (Siraji) and very short strings
            if author and len(author) > 3 and "Siraji" not in author:
                coauthor_counts[author] += 1

    return [{"name": name, "papers": count} for name, count in coauthor_counts.most_common(50)]

def main():
    try:
        from scholarly import scholarly
    except ImportError:
        print("ERROR: scholarly not installed. Run: pip install scholarly")
        sys.exit(1)

    print(f"Fetching Google Scholar data for ID: {SCHOLAR_ID}")

    try:
        author = fetch_with_retry(SCHOLAR_ID)
    except Exception as e:
        print(f"FATAL: Could not fetch author after retries: {e}")
        sys.exit(1)

    # ── Metrics ──────────────────────────────────────────────
    metrics = {
        "citations":  author.get("citedby", 0),
        "hIndex":     author.get("hindex", 0),
        "i10Index":   author.get("i10index", 0),
        "citations5": author.get("citedby5y", 0),
        "hIndex5":    author.get("hindex5y", 0),
        "i10Index5":  author.get("i10index5y", 0),
    }
    print(f"  Metrics: {metrics['citations']} citations, h={metrics['hIndex']}, i10={metrics['i10Index']}")

    # ── Publications ─────────────────────────────────────────
    publications = []
    pubs_raw = author.get("publications", [])
    print(f"  Found {len(pubs_raw)} publications on Scholar")

    for pub in pubs_raw:
        bib = pub.get("bib", {})
        title = bib.get("title", "").strip()
        if not title:
            continue

        entry = {
            "title":    title,
            "year":     bib.get("pub_year", ""),
            "journal":  bib.get("journal", bib.get("booktitle", bib.get("conference", ""))),
            "authors":  bib.get("author", ""),
            "volume":   bib.get("volume", ""),
            "pages":    bib.get("pages", ""),
            "citations": pub.get("num_citations", 0),
            "scholar_url": pub.get("author_pub_id", ""),
        }
        publications.append(entry)

    # Sort by year desc, then citations desc
    publications.sort(key=lambda p: (-(int(p["year"]) if str(p["year"]).isdigit() else 0), -p["citations"]))

    # ── Co-authors (from publication strings) ────────────────
    coauthors_auto = extract_coauthors(publications)

    # ── Output ───────────────────────────────────────────────
    output = {
        "_meta": {
            "updated":    datetime.now(timezone.utc).isoformat(),
            "scholar_id": SCHOLAR_ID,
            "source":     "Google Scholar via scholarly"
        },
        "metrics":      metrics,
        "publications": publications,
        "coauthors_auto": coauthors_auto
    }

    os.makedirs("data", exist_ok=True)
    out_path = "data/scholar_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Saved {len(publications)} publications to {out_path}")
    print(f"  Last updated: {output['_meta']['updated']}")

if __name__ == "__main__":
    main()
