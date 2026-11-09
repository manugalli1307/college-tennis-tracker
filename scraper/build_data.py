#!/usr/bin/env python3
"""
build_data.py -- collects everything the website needs and saves it as JSON
files in ../data/.

  tournaments.json  every M15/M25 event in the window (past / current / upcoming)
  entries.json      roster players on an entry list (main draw / qualifying)
  matches.json      singles matches that involve at least one roster player
  players.json      the roster (id, name, school, ...)
  meta.json         when the data was last refreshed

Run it from the scraper/ folder:

    python3 build_data.py                  # normal run (2 weeks back, 3 weeks ahead)
    python3 build_data.py --max-tournaments 5   # quick test

If one tournament page fails, the previous data for it is kept, so a bad run
never wipes out what the site already shows.
"""
import argparse
import csv
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

import rankings_data
import te_data
import itf_scraper as itf
import tennis_tracker as tt

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"


def slug(text: str) -> str:
    text = tt.strip_accents(text or "").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def tournament_id(url: str) -> str:
    parts = [p for p in url.rstrip("/").split("/") if p]
    return parts[-1] if parts else slug(url)


def country_from_url(url: str) -> str:
    m = re.search(r"/en/tournament/[^/]+/([a-z]{3})/", url)
    return m.group(1).upper() if m else ""


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------

def load_players(path: Path):
    players = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("Player") or "").strip()
            if not name:
                continue
            school = (row.get("School") or "").strip()
            players.append(
                {
                    "id": slug(f"{school} {name}"),
                    "name": name,
                    "school": school,
                    "team_rank": (row.get("Rank") or "").strip(),
                    "class": (row.get("Class") or "").strip(),
                    "hometown": (row.get("Hometown") or "").strip(),
                }
            )
    return players


ALUMNI_IDS = set()


def roster_ids_for(name: str, prepared, id_by_key, strict: bool = False):
    """Ids (current players and alumni) matching a name from a draw or entry list.
    Alumni only count on a full-name match, since there are many more of them."""
    out = []
    for rp, kind in itf.find_players(name, prepared, strict):
        pid = id_by_key.get((rp.school, rp.player))
        if not pid or any(o[0] == pid for o in out):
            continue
        if pid in ALUMNI_IDS and kind != "full name":
            continue
        out.append((pid, kind))
    return out


def load_alumni(path: Path, current_names):
    """Former players from data/alumni.csv, minus anyone on a current roster
    (transfers) and with each person listed once (latest school)."""
    if not path.exists():
        return []
    best = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("Player") or "").strip()
            school = (row.get("School") or "").strip()
            k = re.sub(r"[^a-z ]", "", tt.strip_accents(name).lower()).strip()
            if not name or len(k.split()) < 2 or k in current_names:
                continue
            if k not in best or (row.get("Last season") or "") > (best[k].get("Last season") or ""):
                best[k] = row
    out = []
    for row in best.values():
        name, school = row["Player"].strip(), row["School"].strip()
        out.append({
            "id": slug(f"alumni {school} {name}"),
            "name": name,
            "school": school,
            "team_rank": "",
            "class": (row.get("Last class") or "").strip(),
            "hometown": (row.get("Hometown") or "").strip(),
            "alumni": True,
            "grad": (row.get("Graduation year") or "").strip(),
            "last_season": (row.get("Last season") or "").strip(),
            "colleges": (row.get("Colleges") or "").strip(),
        })
    return out


# ---------------------------------------------------------------------------
# Draw sheets (results)
# ---------------------------------------------------------------------------

_DRAW_JS = """() => {
  const T = (e, s) => ((e.querySelector(s) || {}).innerText || '').trim();
  return Array.from(document.querySelectorAll('.drawsheet-round-container')).map(rc => ({
    round: T(rc, '.drawsheet-round-container__round-title'),
    matches: Array.from(rc.querySelectorAll('.drawsheet-widget')).map(w => {
      const side = k => {
        const ti = w.querySelector('.drawsheet-widget__team-info--team-' + k);
        if (!ti) return null;
        return {
          first: T(ti, '.drawsheet-widget__first-name'),
          last: T(ti, '.drawsheet-widget__last-name'),
          country: T(ti, '.drawsheet-widget__nationality'),
          seed: T(ti, '.drawsheet-widget__seeding'),
          winner: ti.classList.contains('is-winner'),
          scores: Array.from(ti.querySelectorAll('.drawsheet-widget__score')).map(x => x.innerText.trim())
        };
      };
      return {live: w.classList.contains('is-live'), p1: side(1), p2: side(2)};
    })
  }));
}"""


def norm_score(raw: str) -> str:
    """'6\\n5' (a 6 with a 5-point tiebreak) -> '6(5)'."""
    parts = raw.split()
    if len(parts) >= 2:
        return f"{parts[0]}({parts[1]})"
    return parts[0] if parts else ""


def _titles(page):
    try:
        return page.evaluate("() => Array.from(document.querySelectorAll('.drawsheet-round-container__round-title')).map(e => e.innerText.trim()).join('|')")
    except Exception:
        return ""


def read_draw(page):
    """Return {round title: [raw matches]} for the draw currently on screen,
    clicking the 'next' arrow until the last round (the Final) has been read."""
    rounds = {}
    order = []

    def grab():
        try:
            data = page.evaluate(_DRAW_JS)
        except Exception:
            data = []
        for r in data:
            title = r["round"] or f"Round {len(order) + 1}"
            if title not in rounds or len(r["matches"]) > len(rounds[title]):
                if title not in rounds:
                    order.append(title)
                rounds[title] = r["matches"]

    for _ in range(10):
        grab()
        try:
            nxt = page.locator(".btn--chevron-next").first
            if not nxt.count() or not nxt.is_visible():
                page.wait_for_timeout(1500)  # may just be re-rendering
                if not nxt.count() or not nxt.is_visible():
                    break
            before = _titles(page)
            try:
                nxt.click(timeout=3000)
            except Exception:
                nxt.evaluate("e => e.click()")  # something (a banner) may cover the arrow; click it directly
            for _w in range(12):  # wait (up to ~6s) for the new rounds to appear
                page.wait_for_timeout(500)
                if _titles(page) != before:
                    break
            page.wait_for_timeout(700)
        except Exception:
            break
    grab()
    return [(t, rounds[t]) for t in order]


def switch_draw(page, pattern: str) -> bool:
    """Try to select another draw (e.g. 'Qualifying') in the page's dropdown."""
    try:
        opt = page.locator(".drawsheet-dropdowns").get_by_text(re.compile(pattern, re.I)).first
        if opt.count():
            opt.click(timeout=3000)
            page.wait_for_timeout(2500)
            return True
    except Exception:
        pass
    return False


def collect_matches(page, t, tid, prepared, id_by_key, debug):
    """Open the draws page and return (matches involving roster players, number of
    players seen)."""
    url = t.url.rstrip("/") + "/draws-and-results/"
    page.goto(url, timeout=45000)
    itf.settle(page, 3000)
    try:
        page.wait_for_selector(".drawsheet-widget", timeout=15000)
    except Exception:
        print("    no draw sheet on this page (draw not published yet?)")
        return [], 0, []

    out, seen, allm = [], 0, []
    draws = [("Main Draw", read_draw(page))]
    if switch_draw(page, r"^\s*qualifying"):
        draws.append(("Qualifying", read_draw(page)))
        switch_draw(page, r"^\s*main\s*draw")
    for draw_name, rounds in draws:
        for round_title, matches in rounds:
            for m in matches:
                sides = []
                for k in ("p1", "p2"):
                    p = m.get(k)
                    if not p:
                        sides.append(None)
                        continue
                    full = f"{p['first']} {p['last']}".strip()
                    seen += 1 if full else 0
                    sides.append({
                        "name": full,
                        "country": p["country"],
                        "seed": p["seed"].strip("[]"),
                        "winner": bool(p["winner"]),
                        "roster": [pid for pid, kind in roster_ids_for(full, prepared, id_by_key, strict=True)],
                    })
                if not any(s and (s["name"] or s["roster"]) for s in sides):
                    continue  # empty slot in a later round
                p1, p2 = m["p1"] or {"scores": []}, m["p2"] or {"scores": []}
                n = max(len(p1["scores"]), len(p2["scores"]))
                sets = []
                for i in range(n):
                    a = norm_score(p1["scores"][i]) if i < len(p1["scores"]) else ""
                    b = norm_score(p2["scores"][i]) if i < len(p2["scores"]) else ""
                    sets.append([a, b])
                winner = 1 if sides[0] and sides[0]["winner"] else 2 if sides[1] and sides[1]["winner"] else 0
                item = {
                    "tournament": tid,
                    "draw": draw_name,
                    "round": round_title,
                    "p1": sides[0],
                    "p2": sides[1],
                    "winner": winner,
                    "sets": sets,
                    "live": bool(m["live"]),
                }
                allm.append(item)
                if any(s and s["roster"] for s in sides):
                    out.append(item)
    return out, seen, allm


# ---------------------------------------------------------------------------
# Entry lists
# ---------------------------------------------------------------------------

def collect_entries(page, t, tid, prepared, id_by_key):
    text, final_url = itf.open_acceptance_list(page, t)
    if "acceptance-list" not in final_url:
        print("    no entry list published")
        return None
    out = []
    pieces = itf.split_entry_sections(text)
    if not pieces:
        print("    entry list has no Main Draw / Qualifying section")
        return []
    for section, body in pieces:
        for pid, kind in roster_ids_for(body, prepared, id_by_key):
            out.append({"tournament": tid, "player": pid, "section": section, "match": kind})
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_json(name, default):
    try:
        return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(name, obj):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")


def _k(name):
    return re.sub(r"[^a-z]+", " ", tt.strip_accents(name or "").lower()).split()[-1] if name else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ahead-days", type=int, default=21)
    ap.add_argument("--back-days", type=int, default=14)
    ap.add_argument("--roster", default=str(HERE / "roster.csv"))
    ap.add_argument("--max-tournaments", type=int, default=None)
    ap.add_argument("--only", default=None, help="only tournaments whose name contains this text")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--base-url", default=itf.DEFAULT_BASE_URL, help=argparse.SUPPRESS)
    args = ap.parse_args()

    today = date.today()
    players = load_players(Path(args.roster))
    current_names = {re.sub(r"[^a-z ]", "", tt.strip_accents(p["name"]).lower()).strip() for p in players}
    alumni = load_alumni(DATA_DIR / "alumni.csv", current_names)
    ALUMNI_IDS.update(a["id"] for a in alumni)
    players = players + alumni
    print(f"{len(alumni)} alumni loaded.")
    roster = tt.load_roster(args.roster) + [tt.RosterPlayer(rank="", school=a["school"], player=a["name"]) for a in alumni]
    prepared = itf.prepare_roster(roster)
    id_by_key = {(p["school"], p["name"]): p["id"] for p in players}
    print(f"{len(players)} roster players. Today {today}; {args.back_days} days back, {args.ahead_days} ahead.\n")

    old_t = {t["id"]: t for t in load_json("tournaments.json", [])}
    old_e = load_json("entries.json", [])
    old_m = load_json("matches.json", [])

    new_t, read_ok = {}, {}
    entries_by_t, matches_by_t, draws_by_t = {}, {}, {}
    old_d = load_json("draws.json", {})
    old_r = load_json("rankings.json", {})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=itf.USER_AGENT, viewport={"width": 1280, "height": 900})

        base = args.base_url
        cal = base + "/en/tournament-calendar/mens-world-tennis-tour-calendar/?categories=All"
        a1, b1 = (today + timedelta(days=1)).isoformat(), (today + timedelta(days=args.ahead_days)).isoformat()
        a2, b2 = (today - timedelta(days=args.back_days)).isoformat(), (today - timedelta(days=1)).isoformat()
        # The calendar page can't look backwards (it always starts at today),
        # but the results page shows a week at a time, so past weeks come from there.
        results = base + "/en/tournament-calendar/results/?startdate="
        windows = [
            ("today", cal),
            ("ahead", f"{cal}&startdate={a1}&enddate={b1}"),
        ]
        for k in range(7, args.back_days + 7, 7):
            windows.append((f"past-{k}d", results + (today - timedelta(days=k)).isoformat()))
        found = {}
        for label, url in windows:
            for t in itf.fetch_calendar_month(page, base, url, today.year, today.month, args.debug, label):
                old = found.get(t.url)
                if old is None or (old.start is None and t.start is not None):
                    found[t.url] = t

        if not found:
            print("[!] The ITF calendar returned no tournaments (site down or blocking us). Keeping the existing ITF data.")

        todo = []
        for t in found.values():
            if args.only and args.only.lower() not in t.name.lower():
                continue
            if t.start is None:
                continue  # can't place it in time; skip rather than guess
            status = itf.classify(t.start, t.end, today, args.ahead_days, args.back_days)
            if status is None:
                continue
            t.status = status
            todo.append(t)
        todo.sort(key=lambda t: (t.start, t.name))
        print(f"\n{len(todo)} tournament(s) in the window.")
        if args.max_tournaments:
            todo = todo[: args.max_tournaments]

        for i, t in enumerate(todo, 1):
            tid = tournament_id(t.url)
            name = re.sub(r"\s*\n.*$", "", t.name).strip()
            name = re.sub(r"\s*\([A-Z]{3}\)\s*$", "", name)  # results page adds "(GBR)"
            rec = {
                "id": tid,
                "name": name,
                "category": t.category,
                "tour": "ITF",
                "country": country_from_url(t.url),
                "start": t.start.isoformat(),
                "end": t.end.isoformat(),
                "status": t.status,
                "url": t.url,
            }
            new_t[tid] = rec
            print(f"[{i}/{len(todo)}] {name} ({t.category}, {t.status}, {t.start} to {t.end})")
            try:
                if t.status == "upcoming":
                    ents = collect_entries(page, t, tid, prepared, id_by_key)
                    if ents is not None:
                        entries_by_t[tid] = ents
                        read_ok[tid] = True
                        for e in ents:
                            print(f"    ENTRY: {e['player']} - {e['section']}")
                else:
                    ms, seen, allm = collect_matches(page, t, tid, prepared, id_by_key, args.debug)
                    print(f"    {seen} players on draw sheet, {len(ms)} roster match(es)")
                    if seen:
                        matches_by_t[tid] = ms
                        draws_by_t[tid] = allm
                        read_ok[tid] = True
            except Exception as e:
                print(f"    [!] problem: {e}")

        # ATP Challengers and ATP Tour (tennisexplorer.com). A failure here never affects the ITF data.
        print("\n" + "=" * 50 + "\nATP Challenger and ATP Tour\n" + "=" * 50)
        try:
            te_cache = load_json("te_players.json", {})
            try:
                recs, ok, ents, ms, drw = te_data.collect(
                    page, today, args.back_days, args.ahead_days, itf.classify, roster_ids_for, prepared, id_by_key,
                    te_cache, only=args.only, limit=args.max_tournaments)
            finally:
                save_json("te_players.json", te_cache)
            new_t.update(recs)
            read_ok.update(ok)
            entries_by_t.update(ents)
            matches_by_t.update(ms)
            draws_by_t.update(drw)
        except Exception as e:
            print(f"[!] ATP section failed: {e}")

        # Current ATP ranking for every roster player (cached, refreshed weekly)
        print("\n" + "=" * 50 + "\nATP rankings for roster players\n" + "=" * 50)
        rank_cache = load_json("rank_lookup.json", {})
        try:
            rankings_data.lookup(page, players, rank_cache, te_data.RANKS)
        except Exception as e:
            print(f"[!] ranking lookup failed: {e}")
        finally:
            save_json("rank_lookup.json", rank_cache)
        browser.close()

    if not read_ok:
        raise SystemExit("Nothing could be read from either site. Keeping the existing data.")

    # Merge with previous data: re-read tournaments replace their old records,
    # tournaments that weren't (or couldn't be) re-read keep what we had.
    cutoff = (today - timedelta(days=args.back_days)).isoformat()
    tournaments = dict(new_t)
    for tid, rec in old_t.items():
        st = itf.classify(date.fromisoformat(rec["start"]), date.fromisoformat(rec["end"]), today, 999, 999)
        if rec.get("tour", "ITF") != "ITF" and tid not in tournaments and st != "past":
            continue  # unfinished ATP events only stay if they were read successfully this run
        if tid not in tournaments and not args.only and (st == "past" or rec["end"] >= cutoff):
            # Finished events are kept for good so the site builds up a full season.
            # Recompute status from dates so old records age correctly
            st = itf.classify(date.fromisoformat(rec["start"]), date.fromisoformat(rec["end"]), today, 999, 999)
            rec["status"] = st or rec["status"]
            tournaments[tid] = rec

    entries = [e for e in old_e if e["tournament"] in tournaments and e["tournament"] not in read_ok]
    matches = [m for m in old_m if m["tournament"] in tournaments and m["tournament"] not in read_ok]
    for lst in entries_by_t.values():
        entries += lst
    for lst in matches_by_t.values():
        matches += lst

    # Current events: players on the draw are "in" the event even without an entry list
    ent_keys = {(e["tournament"], e["player"]) for e in entries}
    for m in matches:
        for k in ("p1", "p2"):
            s = m.get(k)
            if s:
                for pid in s["roster"]:
                    if (m["tournament"], pid) not in ent_keys:
                        entries.append({"tournament": m["tournament"], "player": pid, "section": m["draw"], "match": "draw"})
                        ent_keys.add((m["tournament"], pid))

    draws = {t: v for t, v in old_d.items() if t in tournaments and t not in read_ok}
    draws.update({t: v for t, v in draws_by_t.items() if t in tournaments})
    ranks = {k: dict(v) for k, v in old_r.items()}
    for pid, info in te_data.RANKS.items():
        cur = ranks.setdefault(pid, {})
        cur.update(info)
        if info.get("unranked"):
            cur.pop("rank", None)
        elif info.get("rank"):
            cur.pop("unranked", None)

    # Drop anything that points at players who are no longer on the lists (e.g. former players without an ATP ranking)
    valid = {x["id"] for x in players}
    entries = [e for e in entries if e["player"] in valid]
    kept_m = []
    for m in matches:
        for k in ("p1", "p2"):
            if m.get(k):
                m[k]["roster"] = [i for i in m[k]["roster"] if i in valid]
        if any(m.get(k) and m[k]["roster"] for k in ("p1", "p2")):
            kept_m.append(m)
    matches = kept_m
    for ms_ in draws.values():
        for m in ms_:
            for k in ("p1", "p2"):
                if m.get(k):
                    m[k]["roster"] = [i for i in m[k]["roster"] if i in valid]
    ranks = {k: v for k, v in ranks.items() if k in valid}
    # older runs saved quarter-finals as "Final"; repair what is already stored
    for tid, ms_ in draws.items():
        if tid.startswith("te-"):
            te_data.fix_labels(ms_)
    by_t = {}
    for m in matches:
        by_t.setdefault(m["tournament"], []).append(m)
    for tid, ms_ in by_t.items():
        if tid.startswith("te-") and tid in draws:
            # use the repaired draw as the reference for roster matches
            ref = {(frozenset((_k(x["p1"]["name"]), _k(x["p2"]["name"]))), x["draw"]): x["round"] for x in draws[tid]}
            for m in ms_:
                r = ref.get((frozenset((_k(m["p1"]["name"]), _k(m["p2"]["name"]))), m["draw"]))
                if r:
                    m["round"] = r

    tlist = sorted(tournaments.values(), key=lambda r: (r["start"], r["name"]))
    save_json("scrape_log.json", {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "atp": te_data.LOG, "ranks": rankings_data.LOG})
    save_json("players.json", players)
    save_json("tournaments.json", tlist)
    save_json("entries.json", entries)
    save_json("matches.json", matches)
    save_json("draws.json", draws)
    save_json("rankings.json", ranks)
    save_json("meta.json", {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": {"back_days": args.back_days, "ahead_days": args.ahead_days},
        "counts": {"players": len(players) - len(alumni), "alumni": len(alumni), "tournaments": len(tlist), "entries": len(entries), "matches": len(matches)},
    })
    print(f"\nSaved to {DATA_DIR}: {len(tlist)} tournaments, {len(entries)} entries, {len(matches)} matches.")


if __name__ == "__main__":
    main()
