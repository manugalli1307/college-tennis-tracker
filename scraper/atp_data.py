"""
atp_data.py -- ATP Challenger and ATP Tour events, read from atptour.com.

Used by build_data.py. For each event in the date window it records:
  * the event itself (name, dates, category, link)
  * entries: roster players on the draw (main draw and qualifying), from the Draws page
  * matches: singles matches with roster players, from the Results page

The ATP calendar pages list every event with its dates and its Draws / Results
links, so we never have to guess an address.
"""
import re
from datetime import date, timedelta

BASE = "https://www.atptour.com"
LOG = []   # diagnostics, saved to data/scrape_log.json by build_data.py
CALENDARS = [
    ("Challenger", BASE + "/en/atp-challenger-tour/calendar"),
    ("ATP", BASE + "/en/tournaments"),
]

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}

_DATE_RE = re.compile(
    r"(\d{1,2})(?:\s+([A-Za-z]+))?\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})")

_CAL_JS = """() => Array.from(document.querySelectorAll('ul.events > li')).map(li => {
  const tx = s => ((li.querySelector(s) || {}).textContent || '').replace(/\\s+/g, ' ').trim();
  const link = li.querySelector('a.tournament__page-link');
  return {
    name: tx('.name'), venue: tx('.venue'), date: tx('.Date'), mid: tx('.mid-section'),
    overview: link ? (link.getAttribute('href') || '') : '',
    links: Array.from(li.querySelectorAll('.cta-holder a')).map(a => a.getAttribute('href') || '')
  };
})"""

_RESULTS_JS = """() => Array.from(document.querySelectorAll('.match')).filter(m => m.querySelector('.stats-item')).map(m => ({
  header: ((m.querySelector('.match-header strong') || {}).textContent || '').trim(),
  note: ((m.querySelector('.match-notes') || {}).textContent || '').trim(),
  sides: Array.from(m.querySelectorAll('.stats-item')).map(si => ({
    names: Array.from(si.querySelectorAll('.name a')).map(a => a.textContent.trim()),
    tag: ((si.querySelector('.name span') || {}).textContent || '').trim(),
    winner: !!si.querySelector('.winner'),
    scores: Array.from(si.querySelectorAll('.scores .score-item')).map(it =>
      Array.from(it.querySelectorAll('span')).map(s => s.textContent.trim()))
  }))
}))"""

_DRAW_JS = """() => {
  const seen = new Set(), out = [];
  document.querySelectorAll('select option[data-first]').forEach(o => {
    const key = o.dataset.first + '|' + o.dataset.last;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({first: o.dataset.first, last: o.dataset.last, country: o.dataset.countryCode || ''});
  });
  return out;
}"""


def _fail_note(page):
    try:
        body = page.inner_text("body")[:200].replace("\n", " ")
        return f"title={page.title()!r} body={body!r}"
    except Exception as e:
        return f"(could not read page: {str(e)[:60]})"


def parse_dates(text: str):
    """'2 - 8 November, 2026' / '26 October - 1 November, 2026' -> (start, end) or None."""
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    d1, m1, d2, m2, yr = m.groups()
    end_month = MONTHS.get(m2.lower())
    start_month = MONTHS.get(m1.lower()) if m1 else end_month
    if not end_month or not start_month:
        return None
    try:
        end = date(int(yr), end_month, int(d2))
        start = date(int(yr) - 1 if start_month > end_month else int(yr), start_month, int(d1))
    except ValueError:
        return None
    return (start, end) if start <= end else None


def _score(parts) -> str:
    """['6', '3'] (6 games, 3-point tiebreak) -> '6(3)'."""
    parts = [p for p in parts if p]
    if not parts:
        return ""
    return parts[0] + (f"({parts[1]})" if len(parts) > 1 else "")


def read_calendar(page, tour: str, url: str, today, back_days, ahead_days, classify):
    """Return a list of event dicts inside the date window."""
    print(f"Loading ATP calendar: {tour} ...")
    try:
        page.goto(url, timeout=45000)
        page.wait_for_selector("ul.events > li", state="attached", timeout=30000)
        page.wait_for_timeout(2000)
        raw = page.evaluate(_CAL_JS)
    except Exception as e:
        print(f"  [!] could not read the {tour} calendar: {str(e)[:150]}")
        LOG.append({"step": f"calendar {tour}", "error": str(e)[:120], "page": _fail_note(page)})
        return []
    events = []
    for r in raw:
        rng = parse_dates(r["date"])
        m = re.search(r"/tournaments/([^/]+)/(\d+)/", r["overview"] or "")
        if not rng or not m:
            continue
        status = classify(rng[0], rng[1], today, ahead_days, back_days)
        if status is None:
            continue
        slug, eid = m.group(1), m.group(2)
        city, _, country = r["name"].partition(",")
        cat = re.search(r"Challenger\s*\d+", r["mid"])
        if tour == "Challenger":
            category = cat.group(0) if cat else "Challenger"
            name = f"{city.strip()} Challenger"
        else:
            category = "ATP Masters 1000" if "masters-1000" in " ".join(r["links"]) else "ATP Tour"
            name = f"{city.strip()} ATP"
        links = r["links"]
        events.append({
            "id": f"atp-{eid}-{rng[0].year}",
            "name": name,
            "category": category,
            "tour": "ATP Challenger" if tour == "Challenger" else "ATP Tour",
            "country": country.strip(),
            "start": rng[0], "end": rng[1], "status": status,
            "url": BASE + r["overview"],
            "draws": next((l for l in links if re.search(r"/draws/?$", l)), ""),
            "results": next((l for l in links if re.search(r"/results/?$", l)), ""),
        })
    print(f"  {len(events)} {tour} event(s) in the window")
    return events


def read_draw_players(page, draws_url: str, matchtype: str):
    """Players listed on a draw page (singles main draw or qualifying)."""
    try:
        page.goto(f"{BASE}{draws_url}?matchtype={matchtype}", timeout=45000)
        page.wait_for_selector("select option[data-first]", state="attached", timeout=15000)
        return page.evaluate(_DRAW_JS)
    except Exception as e:
        LOG.append({"step": "draw", "url": f"{draws_url}?matchtype={matchtype}", "error": str(e)[:100], "page": _fail_note(page)})
        return []


def read_results(page, results_url: str):
    """All singles matches on a results page (every day, qualifying included)."""
    try:
        page.goto(f"{BASE}{results_url}?matchtype=singles", timeout=45000)
        page.wait_for_selector(".match .stats-item", state="attached", timeout=20000)
        page.wait_for_timeout(1500)
        return page.evaluate(_RESULTS_JS)
    except Exception as e:
        LOG.append({"step": "results", "url": results_url, "error": str(e)[:100], "page": _fail_note(page)})
        return []


def collect(page, today, back_days, ahead_days, classify, roster_ids_for, prepared, id_by_key,
            only=None, limit=None):
    """Returns (tournament records, read_ok ids, entries by tournament, matches by tournament)."""
    events = []
    seen_ids = set()
    for tour, url in CALENDARS:
        for ev in read_calendar(page, tour, url, today, back_days, ahead_days, classify):
            if ev["id"] in seen_ids:
                continue
            seen_ids.add(ev["id"])
            if only and only.lower() not in ev["name"].lower():
                continue
            events.append(ev)
    events.sort(key=lambda e: (e["start"], e["name"]))
    if limit:
        events = events[:limit]

    records, read_ok, entries_by_t, matches_by_t = {}, {}, {}, {}
    for i, ev in enumerate(events, 1):
        tid = ev["id"]
        records[tid] = {
            "id": tid, "name": ev["name"], "category": ev["category"], "tour": ev["tour"],
            "country": ev["country"], "start": ev["start"].isoformat(), "end": ev["end"].isoformat(),
            "status": ev["status"], "url": ev["url"],
        }
        print(f"[ATP {i}/{len(events)}] {ev['name']} ({ev['category']}, {ev['status']}, {ev['start']} to {ev['end']})")
        LOG.append({"step": "event", "id": tid, "name": ev["name"], "status": ev["status"], "draws": ev["draws"], "results": ev["results"]})
        try:
            # Entries: everyone on the draw sheets
            if ev["draws"] and ev["status"] in ("upcoming", "current"):
                ents, total = [], 0
                for section, mt in (("Main Draw", "singles"), ("Qualifying", "qualifiersingles")):
                    plist = read_draw_players(page, ev["draws"], mt)
                    total += len(plist)
                    for p in plist:
                        for pid, kind in roster_ids_for(f"{p['first']} {p['last']}", prepared, id_by_key):
                            ents.append({"tournament": tid, "player": pid, "section": section, "match": kind})
                print(f"    {total} players on the draw sheets, {len(ents)} roster entr(ies)")
                LOG.append({"step": "draw summary", "id": tid, "players": total, "roster": len(ents)})
                if total:
                    entries_by_t[tid] = ents
                    read_ok[tid] = True
                    for e in ents:
                        print(f"    ENTRY: {e['player']} - {e['section']}")
            # Matches
            if ev["results"] and ev["status"] in ("current", "past"):
                raw = read_results(page, ev["results"])
                ms = []
                for r in raw:
                    if len(r["sides"]) != 2 or any(len(s["names"]) != 1 for s in r["sides"]):
                        continue  # doubles or incomplete
                    sides = []
                    for s in r["sides"]:
                        full = s["names"][0]
                        sd = re.search(r"\((\d+)", s["tag"])
                        sides.append({
                            "name": full, "country": "", "seed": sd.group(1) if sd else "",
                            "winner": s["winner"],
                            "roster": [pid for pid, kind in roster_ids_for(full, prepared, id_by_key)],
                        })
                    if not any(s["roster"] for s in sides):
                        continue
                    n = max(len(r["sides"][0]["scores"]), len(r["sides"][1]["scores"]))
                    sets = []
                    for k in range(n):
                        a = _score(r["sides"][0]["scores"][k]) if k < len(r["sides"][0]["scores"]) else ""
                        b = _score(r["sides"][1]["scores"][k]) if k < len(r["sides"][1]["scores"]) else ""
                        if a or b:
                            sets.append([a, b])
                    winner = 1 if sides[0]["winner"] else 2 if sides[1]["winner"] else 0
                    rnd = r["header"].split(" - ")[0].strip() or "Round"
                    ms.append({
                        "tournament": tid,
                        "draw": "Qualifying" if re.search(r"qualif", rnd, re.I) else "Main Draw",
                        "round": rnd,
                        "p1": sides[0], "p2": sides[1],
                        "winner": winner, "sets": sets,
                        "live": winner == 0 and bool(sets) and ev["status"] == "current",
                    })
                print(f"    {len(raw)} singles matches on the results page, {len(ms)} with roster players")
                LOG.append({"step": "results summary", "id": tid, "matches": len(raw), "roster": len(ms)})
                if raw:
                    matches_by_t[tid] = ms
                    read_ok[tid] = True
        except Exception as e:
            print(f"    [!] problem: {str(e)[:150]}")
    # Only keep events we actually read; empty shells would wrongly look like "no college players here".
    records = {k: v for k, v in records.items() if k in read_ok}
    return records, read_ok, entries_by_t, matches_by_t
