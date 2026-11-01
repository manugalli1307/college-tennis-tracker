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


def roster_ids_for(name: str, prepared, id_by_key):
    """Roster ids matching a name from a draw or entry list ([] if none)."""
    out = []
    for rp, kind in itf.find_players(name, prepared):
        pid = id_by_key.get((rp.school, rp.player))
        if pid and pid not in out:
            out.append((pid, kind))
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


def read_draw(page):
    """Return {round title: [raw matches]} for the draw currently on screen,
    clicking the 'next' arrow so every round gets loaded."""
    rounds = {}
    order = []
    for _ in range(8):
        try:
            data = page.evaluate(_DRAW_JS)
        except Exception:
            data = []
        grew = False
        for r in data:
            title = r["round"] or f"Round {len(order) + 1}"
            if title not in rounds or len(r["matches"]) > len(rounds[title]):
                if title not in rounds:
                    order.append(title)
                rounds[title] = r["matches"]
                grew = True
        try:
            nxt = page.locator("button.btn--chevron-next, .btn--chevron-next").first
            if not nxt.count() or not nxt.is_visible():
                break
            nxt.click(timeout=3000)
            page.wait_for_timeout(1200)
        except Exception:
            break
        if not grew and _ >= 2:
            break
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
        return [], 0

    out, seen = [], 0
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
                        "roster": [pid for pid, kind in roster_ids_for(full, prepared, id_by_key)],
                    })
                if not any(s and s["roster"] for s in sides):
                    continue
                p1, p2 = m["p1"] or {"scores": []}, m["p2"] or {"scores": []}
                n = max(len(p1["scores"]), len(p2["scores"]))
                sets = []
                for i in range(n):
                    a = norm_score(p1["scores"][i]) if i < len(p1["scores"]) else ""
                    b = norm_score(p2["scores"][i]) if i < len(p2["scores"]) else ""
                    sets.append([a, b])
                winner = 1 if sides[0] and sides[0]["winner"] else 2 if sides[1] and sides[1]["winner"] else 0
                out.append({
                    "tournament": tid,
                    "draw": draw_name,
                    "round": round_title,
                    "p1": sides[0],
                    "p2": sides[1],
                    "winner": winner,
                    "sets": sets,
                    "live": bool(m["live"]),
                })
    return out, seen


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
    roster = tt.load_roster(args.roster)
    prepared = itf.prepare_roster(roster)
    id_by_key = {(p["school"], p["name"]): p["id"] for p in players}
    print(f"{len(players)} roster players. Today {today}; {args.back_days} days back, {args.ahead_days} ahead.\n")

    old_t = {t["id"]: t for t in load_json("tournaments.json", [])}
    old_e = load_json("entries.json", [])
    old_m = load_json("matches.json", [])

    new_t, read_ok = {}, {}
    entries_by_t, matches_by_t = {}, {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=itf.USER_AGENT)

        base = args.base_url
        cal = base + "/en/tournament-calendar/mens-world-tennis-tour-calendar/?categories=All"
        a1, b1 = (today + timedelta(days=1)).isoformat(), (today + timedelta(days=args.ahead_days)).isoformat()
        a2, b2 = (today - timedelta(days=args.back_days)).isoformat(), (today - timedelta(days=1)).isoformat()
        windows = [
            ("today", cal),
            ("ahead", f"{cal}&startdate={a1}&enddate={b1}"),
            ("past", f"{cal}&startdate={a2}&enddate={b2}"),
        ]
        found = {}
        for label, url in windows:
            for t in itf.fetch_calendar_month(page, base, url, today.year, today.month, args.debug, label):
                old = found.get(t.url)
                if old is None or (old.start is None and t.start is not None):
                    found[t.url] = t

        if not found:
            browser.close()
            raise SystemExit("The ITF calendar returned no tournaments (site down or blocking us). Keeping the existing data.")

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
                    ms, seen = collect_matches(page, t, tid, prepared, id_by_key, args.debug)
                    print(f"    {seen} players on draw sheet, {len(ms)} roster match(es)")
                    if seen:
                        matches_by_t[tid] = ms
                        read_ok[tid] = True
            except Exception as e:
                print(f"    [!] problem: {e}")
        browser.close()

    # Merge with previous data: re-read tournaments replace their old records,
    # tournaments that weren't (or couldn't be) re-read keep what we had.
    cutoff = (today - timedelta(days=args.back_days)).isoformat()
    tournaments = dict(new_t)
    for tid, rec in old_t.items():
        if tid not in tournaments and rec["end"] >= cutoff and not args.only:
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

    tlist = sorted(tournaments.values(), key=lambda r: (r["start"], r["name"]))
    save_json("players.json", players)
    save_json("tournaments.json", tlist)
    save_json("entries.json", entries)
    save_json("matches.json", matches)
    save_json("meta.json", {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": {"back_days": args.back_days, "ahead_days": args.ahead_days},
        "counts": {"players": len(players), "tournaments": len(tlist), "entries": len(entries), "matches": len(matches)},
    })
    print(f"\nSaved to {DATA_DIR}: {len(tlist)} tournaments, {len(entries)} entries, {len(matches)} matches.")


if __name__ == "__main__":
    main()
