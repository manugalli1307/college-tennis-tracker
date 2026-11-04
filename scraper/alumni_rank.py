"""
alumni_rank.py -- one-time cleanup of the alumni list.

Looks every former player up on Tennis Explorer. Anyone with an ATP singles ranking stays
(with the ranking and country saved); anyone without one is removed.
  data/alumni_all.csv   the full list before the cleanup (kept for reference, not shown on the site)
  data/alumni.csv       only the ranked former players
  data/rank_lookup.json the ranking lookups (also used by the daily update)
"""
import csv, json, re, sys, time
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rankings_data as rd          # noqa: E402
import tennis_tracker as tt        # noqa: E402

DATA = HERE.parent / "data"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", tt.strip_accents(s).lower()).strip("-")


def main():
    src = DATA / "alumni_all.csv"
    if not src.exists():
        src = DATA / "alumni.csv"
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    print(f"{len(rows)} former players to check.")
    cache_path = DATA / "rank_lookup.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    today = date.today().isoformat()
    kept, dropped, errors = [], 0, 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA)
        for i, r in enumerate(rows, 1):
            name, school = r["Player"].strip(), r["School"].strip()
            pid = slug(f"alumni {school} {name}")
            hit = None
            try:
                page.goto(f"{rd.BASE}/list-players/?search-text-pl={rd.search_query(name)}", timeout=45000, wait_until="domcontentloaded")
                page.wait_for_selector("table.result", state="attached", timeout=15000)
                hits = [h for h in rd.parse_results(page.content()) if rd.same_person(name, h["name"])]
                ranked = [h for h in hits if h["rank"]]
                hit = sorted(ranked, key=lambda h: h["rank"])[0] if ranked else None
            except Exception as e:
                errors += 1
                print(f"  [!] {name}: {str(e)[:80]}")
                r["_error"] = True
                kept.append(r)          # unknown: keep for now, the next run checks again
                continue
            if hit:
                cache[pid] = {"found": True, "slug": hit["slug"], "rank": hit["rank"], "country": hit["country"], "asof": today}
                r["ATP rank"] = hit["rank"]
                kept.append(r)
            else:
                dropped += 1
            if i % 50 == 0:
                print(f"  {i}/{len(rows)} checked, {len(kept)} kept so far")
            time.sleep(0.4)
        browser.close()
    # keep the full list for reference, then write the cleaned one
    if not (DATA / "alumni_all.csv").exists():
        (DATA / "alumni_all.csv").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    fields = [f for f in rows[0].keys() if not f.startswith("_")]
    if "ATP rank" not in fields:
        fields.append("ATP rank")
    with open(DATA / "alumni.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(kept)
    cache_path.write_text(json.dumps(cache, indent=0), encoding="utf-8")
    print(f"\nKept {len(kept)} ranked former players, removed {dropped}, {errors} lookups failed (kept, will be checked again).")


if __name__ == "__main__":
    main()
