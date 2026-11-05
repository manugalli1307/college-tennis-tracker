"""One-time merge of a hand-copied list of ATP-ranked former college players
(rank, name, colleges with years) into data/alumni.csv and data/rank_lookup.json.
No network. Run: python scraper/pro_list.py"""
import csv, json, re, sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tennis_tracker as tt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "pro_college_list_raw.txt"
SEG = re.compile(r"^(.*\S)\s+(\d{4})(?:-(\d{2}|\*))?$")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", tt.strip_accents(text or "").lower()).strip("-")


def key(name):
    s = re.sub(r"[^a-z]+", " ", tt.strip_accents(name).lower()).split()
    return " ".join(sorted(s))


def norm_school(s):
    s = s.lower()
    s = re.sub(r"\b(the|university|of)\b", " ", s)
    s = re.sub(r"\bat (austin|urbana[- ]champaign)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_stints(text):
    out = []
    for seg in [x.strip() for x in text.split(", ")]:
        m = SEG.match(seg)
        if not m:
            return None
        school, a, b = m.group(1), int(m.group(2)), m.group(3)
        if b == "*":
            end, current = None, True
        elif b:
            end, current = (a // 100) * 100 + int(b), False
            if end < a:
                end += 100
        else:
            end, current = a, False
        out.append({"school": school, "start": a, "end": end, "current": current})
    return out


def read_list():
    rows = []
    for line in RAW.read_text(encoding="utf-8").splitlines():
        p = line.split("\t")
        if len(p) < 4 or not p[0].strip().isdigit():
            continue
        st = parse_stints(p[3].strip())
        if st is None:
            print("could not read:", line)
            continue
        rows.append({"rank": int(p[0]), "name": p[1].strip(), "colleges": p[3].strip(), "stints": st})
    return rows


def main():
    rows = read_list()
    roster = list(csv.DictReader(open(ROOT / "scraper" / "roster.csv", encoding="utf-8")))
    roster_keys = {key(r["Player"]) for r in roster}
    alum_path = ROOT / "data" / "alumni.csv"
    old = list(csv.DictReader(open(alum_path, encoding="utf-8")))
    known = {r["School"] for r in roster} | {r["School"] for r in old}
    by_norm = {norm_school(s): s for s in known}
    top30_norm = {norm_school(r["School"]) for r in roster}

    def key2(name):  # first + last word, to catch "Theo"/"Theodore" style variants
        w = re.sub(r"[^a-z]+", " ", tt.strip_accents(name).lower()).split()
        return (w[0], w[-1]) if w else ("", "")

    list_key2 = {key2(r["name"]) for r in rows}
    existing = {key(r["Player"]): r for r in old}
    # the list wins when an old row is the same person under a slightly different name
    for k in [k for k, r in existing.items() if key2(r["Player"]) in list_key2 and k not in {key(x["name"]) for x in rows}]:
        print("dropping old duplicate:", existing[k]["Player"])
        del existing[k]
    new_rows, current_missing, stats = {}, [], {"former": 0, "current": 0, "on_roster": 0, "updated": 0, "added": 0}
    for r in rows:
        k = key(r["name"])
        if k in roster_keys:
            stats["on_roster"] += 1
            continue
        cur = [s for s in r["stints"] if s["current"]]
        if cur:  # still playing college tennis: a current player, not a former one
            stats["current"] += 1
            if any(norm_school(s["school"]) in top30_norm for s in cur):
                current_missing.append(f'{r["name"]} ({", ".join(s["school"] for s in cur)}) ATP #{r["rank"]}')
            continue
        stats["former"] += 1
        last = sorted(r["stints"], key=lambda s: (s["end"], s["start"]))[-1]
        school = by_norm.get(norm_school(last["school"]), last["school"])
        first_start = min(s["start"] for s in r["stints"])
        # a single year ("Virginia 2019") is one season starting that fall, except spring-2026 entries
        single = len(r["stints"]) == 1 and last["start"] == last["end"]
        last_end = (last["end"] + 1 if last["end"] < 2026 else last["end"]) if single else last["end"]
        if single and last["end"] >= 2026:
            first_start = last["end"] - 1
        ex = existing.get(k, {})
        row = {
            "School": school,
            "Player": r["name"],
            "Hometown": ex.get("Hometown", ""),
            "First season": f"{first_start}-{str(first_start + 1)[2:]}",
            "Last season": f'{last_end - 1}-{str(last_end)[2:]}',
            "Last class": ex.get("Last class", "") if ex.get("School") == school else "",
            "Graduation year": ex.get("Graduation year", "") if ex.get("School") == school else "",
            "ATP rank": r["rank"],
            "Colleges": r["colleges"],
        }
        new_rows[k] = row
        stats["updated" if k in existing else "added"] += 1

    # keep the old rows that this list doesn't mention
    merged = dict(new_rows)
    kept_old = 0
    for k, r in existing.items():
        if k not in merged:
            r = dict(r)
            r["Colleges"] = r.get("Colleges", "")
            merged[k] = r
            kept_old += 1
    fields = ["School", "Player", "Hometown", "First season", "Last season", "Last class", "Graduation year", "ATP rank", "Colleges"]
    out = sorted(merged.values(), key=lambda r: (int(r["ATP rank"]) if str(r.get("ATP rank", "")).isdigit() else 99999, r["Player"]))
    with open(alum_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in out:
            w.writerow({k: r.get(k, "") for k in fields})

    # seed ranks so the site shows them right away (TE lookup refreshes them weekly)
    cache_path = ROOT / "data" / "rank_lookup.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    today = date.today().isoformat()
    seeded = 0
    for r in out:
        if str(r.get("ATP rank", "")).isdigit() and r["School"]:
            pid = slug(f'alumni {r["School"]} {r["Player"]}')
            if key(r["Player"]) in new_rows:
                cache[pid] = {"found": True, "slug": cache.get(pid, {}).get("slug", ""), "rank": int(r["ATP rank"]),
                              "country": cache.get(pid, {}).get("country", ""), "asof": today}
                seeded += 1
    cache_path.write_text(json.dumps(cache, indent=1, ensure_ascii=False))

    schools = sorted({r["School"] for r in out})
    new_schools = [s for s in schools if s not in known]
    print(stats, "kept_old_only", kept_old, "total alumni now", len(out), "seeded ranks", seeded)
    print("new schools:", len(new_schools), new_schools)
    print("current college players at top-30 schools not on roster:", len(current_missing))
    for x in current_missing:
        print("  ", x)


if __name__ == "__main__":
    main()
