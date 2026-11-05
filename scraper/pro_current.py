"""One-time merge of a hand-copied list of ATP-ranked CURRENT college players
into scraper/roster.csv (new teams get no team ranking) and data/rank_lookup.json.
No network. Run: python scraper/pro_current.py"""
import csv, json, re, sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pro_list as pl  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "pro_current_list_raw.txt"
THIS_SEASON = 2026  # fall 2026 starts the 2026-27 season


def standing(first_start):
    n = THIS_SEASON - first_start + 1
    return {1: "Freshman", 2: "Sophomore", 3: "Junior", 4: "Senior"}.get(n, "Grad" if n >= 5 else "Freshman")


def main():
    rows = pl.read_list(RAW)
    path = ROOT / "scraper" / "roster.csv"
    roster = list(csv.DictReader(open(path, encoding="utf-8")))
    have = {pl.key(r["Player"]) for r in roster}
    have2 = set()
    for r in roster:
        w = re.sub(r"[^a-z]+", " ", pl.tt.strip_accents(r["Player"]).lower()).split()
        if w:
            have2.add((w[0], w[-1]))
    by_norm, team_rank = {}, {}
    for r in roster:
        by_norm[pl.norm_school(r["School"])] = r["School"]
        if r.get("Rank"):
            team_rank[r["School"]] = r["Rank"]

    added, skipped, new_schools, seeded = [], 0, set(), 0
    cache_path = ROOT / "data" / "rank_lookup.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    today = date.today().isoformat()
    for r in rows:
        cur = [s for s in r["stints"] if s["current"]]
        if not cur:
            continue
        w = re.sub(r"[^a-z]+", " ", pl.tt.strip_accents(r["name"]).lower()).split()
        if pl.key(r["name"]) in have or (w[0], w[-1]) in have2:
            skipped += 1
            continue
        school = by_norm.get(pl.norm_school(cur[-1]["school"]), cur[-1]["school"])
        if school not in team_rank:
            new_schools.add(school)
        first = min(s["start"] for s in r["stints"])
        row = {"Rank": team_rank.get(school, ""), "School": school, "Player": r["name"],
               "Class": standing(first), "Hometown": ""}
        roster.append(row)
        added.append((row, r["rank"]))
        cache[pl.slug(f"{school} {r['name']}")] = {"found": True, "slug": "", "rank": r["rank"], "country": "", "asof": today}
        seeded += 1
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=["Rank", "School", "Player", "Class", "Hometown"])
        wr.writeheader()
        wr.writerows(roster)
    cache_path.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
    top = [a for a in added if a[0]["Rank"]]
    print(f"list rows {len(rows)}; already on roster {skipped}; added {len(added)} ({len(top)} at top-30 teams, {len(added)-len(top)} at {len(new_schools)} other schools)")
    print("other schools:", sorted(new_schools))
    for row, rk in top:
        print("  top-30:", row["School"], "|", row["Player"], row["Class"], "ATP", rk)


if __name__ == "__main__":
    main()
