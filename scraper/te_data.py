"""
te_data.py -- ATP Challenger and ATP Tour events, read from tennisexplorer.com.

(atptour.com blocks GitHub's computers, tennisexplorer.com does not.)

Tennis Explorer only shows surnames, e.g. "Santamarta Roig". So we:
  1. keep only names whose surname appears somewhere on the roster,
  2. open that player's profile once to get the full name ("Andres Santamarta Roig"),
  3. match the full name against the roster, and remember the answer in
     data/te_players.json so each profile is only opened once.
"""
import re
from datetime import date, timedelta

from bs4 import BeautifulSoup

import tennis_tracker as tt

BASE = "https://www.tennisexplorer.com"
CALENDAR = BASE + "/calendar/atp-men/{year}/"
LOG = []
MAX_PROFILES_PER_RUN = 250

ROUNDS = {"1R": "1st Round", "2R": "2nd Round", "3R": "3rd Round", "R128": "Round of 128",
          "R64": "Round of 64", "R32": "Round of 32", "R16": "Round of 16",
          "QF": "Quarterfinals", "SF": "Semifinals", "F": "Final"}


def _note(page):
    try:
        return f"title={page.title()!r} body={page.inner_text('body')[:150]!r}".replace("\n", " ")
    except Exception as e:
        return f"(could not read page: {str(e)[:60]})"


def _get(page, url, wait_for=None):
    page.goto(url, timeout=45000, wait_until="domcontentloaded")
    if wait_for:
        page.wait_for_selector(wait_for, state="attached", timeout=15000)
    return BeautifulSoup(page.content(), "html.parser")


def _key(s: str) -> str:
    return re.sub(r"[^a-z ]", "", tt.strip_accents(s).lower()).strip()


# ---------------------------------------------------------------- calendar
def read_calendar(page, today, back_days, ahead_days, classify):
    events = {}
    for year in sorted({today.year, (today - timedelta(days=back_days)).year, (today + timedelta(days=ahead_days)).year}):
        try:
            soup = _get(page, CALENDAR.format(year=year), "tr[data-type]")
        except Exception as e:
            print(f"  [!] could not read the {year} calendar: {str(e)[:120]}")
            LOG.append({"step": f"calendar {year}", "error": str(e)[:120], "page": _note(page)})
            continue
        for tr in soup.select("tr[data-type]"):
            a = tr.select_one("th.t-name a")
            cell = tr.select_one("td.shortdate")
            if not a or not cell:
                continue
            m = re.search(r"(\d{1,2})\.(\d{1,2})\.\D*(\d{4})", cell.get_text(" ", strip=True))
            href = a.get("href", "")
            hm = re.match(r"^/([\w\-]+)/(\d{4})/atp-men/?$", href)
            if not m or not hm:
                continue
            try:
                start = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                continue
            name = a.get_text(" ", strip=True)
            main = tr.get("data-type") == "main"
            if not main and "challenger" not in name.lower():
                continue  # ITF / UTR events come from the ITF site
            end = start + timedelta(days=6)
            status = classify(start, end, today, ahead_days, back_days)
            if status is None:
                continue
            city = re.sub(r"\s*challenger\s*$", "", name, flags=re.I).strip()
            slug = hm.group(1)
            events[f"te-{slug}-{hm.group(2)}"] = {
                "id": f"te-{slug}-{hm.group(2)}",
                "name": f"{city} ATP" if main else f"{city} Challenger",
                "category": "ATP Tour" if main else "ATP Challenger",
                "tour": "ATP Tour" if main else "ATP Challenger",
                "country": "", "start": start, "end": end, "status": status,
                "path": href,
            }
    print(f"  {len(events)} Challenger/ATP event(s) in the window")
    return sorted(events.values(), key=lambda e: (e["start"], e["name"]))


# ---------------------------------------------------------------- event pages
def _name_cell(td):
    """-> (surname text, profile slug, seed) from a <td class=t-name>."""
    a = td.find("a", href=re.compile(r"^/player/"))
    if not a:
        return None
    sd = re.search(r"\((\d+)\)", td.get_text(" ", strip=True))
    return {"surname": a.get_text(" ", strip=True), "slug": a["href"].split("/player/")[1].strip("/"),
            "seed": sd.group(1) if sd else ""}


def _games(td):
    sup = td.find("sup")
    if sup:
        tb = sup.get_text(strip=True)
        sup.extract()
        g = td.get_text(strip=True)
        return f"{g}({tb})" if g else ""
    t = td.get_text(strip=True)
    return t


def parse_event(soup):
    """-> (draw players [name dicts], finished matches [dict])"""
    draw = []
    seen = set()
    dr = soup.select_one("#draw")
    if dr:
        for a in dr.select('a[href^="/player/"]'):
            slug = a["href"].split("/player/")[1].strip("/")
            if slug not in seen:
                seen.add(slug)
                draw.append({"surname": a.get_text(" ", strip=True), "slug": slug, "seed": ""})
    matches = []
    for tr in soup.select("table.result tr[id]"):
        mid = tr.get("id", "")
        if not re.fullmatch(r"r\d+", mid):
            continue
        tr2 = tr.find_next_sibling("tr")
        if not tr2 or tr2.get("id") != mid + "b":
            continue
        c1, c2 = tr.select_one("td.t-name"), tr2.select_one("td.t-name")
        if not c1 or not c2:
            continue
        p1, p2 = _name_cell(c1), _name_cell(c2)
        if not p1 or not p2:
            continue
        rnd = tr.find("td", attrs={"title": True, "rowspan": True})
        rtxt = rnd.get_text(strip=True) if rnd else ""
        w1 = tr.select_one("td.result")
        w2 = tr2.select_one("td.result")
        s1 = int(w1.get_text(strip=True) or 0) if w1 and w1.get_text(strip=True).isdigit() else 0
        s2 = int(w2.get_text(strip=True) or 0) if w2 and w2.get_text(strip=True).isdigit() else 0
        a_sc = [_games(td) for td in tr.select("td.score")]
        b_sc = [_games(td) for td in tr2.select("td.score")]
        sets = [[a, b] for a, b in zip(a_sc, b_sc) if a or b]
        matches.append({"round": ROUNDS.get(re.sub(r"^Q-?", "", rtxt), re.sub(r"^Q-?", "", rtxt) or "Round"), "p1": p1, "p2": p2,
                        "winner": 1 if s1 > s2 else 2 if s2 > s1 else 0, "sets": sets})
    return draw, matches


# ---------------------------------------------------------------- player names
class Names:
    def __init__(self, page, cache, roster_tokens):
        self.page, self.cache, self.tokens = page, cache, roster_tokens
        self.fetched = 0

    def possible(self, surname):
        toks = _key(surname).split()
        return bool(toks) and all(t in self.tokens for t in toks)

    def full(self, p, force=False):
        """Full 'Given Surname' for a player dict, or None if not known."""
        slug = p["slug"]
        if slug not in self.cache:
            if not force and not self.possible(p["surname"]):
                return None
            if self.fetched >= MAX_PROFILES_PER_RUN:
                return None
            self.fetched += 1
            try:
                soup = _get(self.page, f"{BASE}/player/{slug}/", "table.plDetail, h3")
                h = soup.select_one("table.plDetail h3") or soup.select_one("h3")
                raw = h.get_text(" ", strip=True) if h else ""
                cm = re.search(r"Country:\s*(.+?)\s+Age:", soup.get_text(" ", strip=True))
                self.cache[slug] = {"raw": raw, "country": cm.group(1) if cm else ""}
            except Exception as e:
                LOG.append({"step": "profile", "slug": slug, "error": str(e)[:100], "page": _note(self.page)})
                return None
        raw = self.cache[slug].get("raw", "")
        if not raw:
            return None
        sn = p["surname"].strip()
        if raw.lower().startswith(sn.lower() + " "):
            given = raw[len(sn):].strip()
            return f"{given} {sn}".strip()
        return raw


def collect(page, today, back_days, ahead_days, classify, roster_ids_for, prepared, id_by_key,
            cache, only=None, limit=None):
    """Returns (tournament records, read_ok ids, entries by tournament, matches by tournament)."""
    tokens = set()
    for rp in tt_roster(prepared):
        tokens.update(_key(rp).split())
    names = Names(page, cache, tokens)

    events = [e for e in read_calendar(page, today, back_days, ahead_days, classify)
              if not only or only.lower() in e["name"].lower()]
    if limit:
        events = events[:limit]

    records, read_ok, entries_by_t, matches_by_t = {}, {}, {}, {}
    for i, ev in enumerate(events, 1):
        tid = ev["id"]
        print(f"[ATP {i}/{len(events)}] {ev['name']} ({ev['category']}, {ev['status']}, {ev['start']} to {ev['end']})")
        try:
            sections = [("Main Draw", ev["path"]), ("Qualifying", ev["path"] + "?phase=qualification")]
            ents, ms, any_data = [], [], False
            for section, path in sections:
                try:
                    soup = _get(page, BASE + path, "table.result, #draw")
                except Exception as e:
                    if section == "Main Draw":
                        LOG.append({"step": "event", "id": tid, "error": str(e)[:100], "page": _note(page)})
                    continue
                draw, finished = parse_event(soup)
                if not draw and not finished:
                    continue
                any_data = True
                if ev["status"] in ("upcoming", "current"):
                    for p in draw:
                        full = names.full(p)
                        if not full:
                            continue
                        for pid, kind in roster_ids_for(full, prepared, id_by_key):
                            if not any(e["player"] == pid and e["section"] == section for e in ents):
                                ents.append({"tournament": tid, "player": pid, "section": section, "match": kind})
                if ev["status"] in ("current", "past"):
                    for m in finished:
                        sides, hit = [], False
                        for k, p in enumerate((m["p1"], m["p2"]), 1):
                            full = names.full(p)
                            roster = [pid for pid, kind in roster_ids_for(full, prepared, id_by_key)] if full else []
                            hit = hit or bool(roster)
                            sides.append({"p": p, "full": full, "roster": roster, "winner": m["winner"] == k})
                        if not hit:
                            continue
                        for s in sides:  # opponents get a full name too
                            if not s["full"]:
                                s["full"] = names.full(s["p"], force=True) or s["p"]["surname"]
                        ms.append({
                            "tournament": tid, "draw": section, "round": m["round"],
                            "p1": {"name": sides[0]["full"], "country": names.cache.get(m["p1"]["slug"], {}).get("country", ""),
                                   "seed": m["p1"]["seed"], "winner": sides[0]["winner"], "roster": sides[0]["roster"]},
                            "p2": {"name": sides[1]["full"], "country": names.cache.get(m["p2"]["slug"], {}).get("country", ""),
                                   "seed": m["p2"]["seed"], "winner": sides[1]["winner"], "roster": sides[1]["roster"]},
                            "winner": m["winner"], "sets": m["sets"], "live": False,
                        })
            print(f"    {len(ents)} roster entr(ies), {len(ms)} roster match(es)")
            LOG.append({"step": "event", "id": tid, "name": ev["name"], "status": ev["status"],
                        "entries": len(ents), "matches": len(ms), "data": any_data})
            if any_data:
                records[tid] = {
                    "id": tid, "name": ev["name"], "category": ev["category"], "tour": ev["tour"],
                    "country": ev["country"], "start": ev["start"].isoformat(), "end": ev["end"].isoformat(),
                    "status": ev["status"], "url": BASE + ev["path"],
                }
                read_ok[tid] = True
                if ents:
                    entries_by_t[tid] = ents
                if ms:
                    matches_by_t[tid] = ms
        except Exception as e:
            print(f"    [!] problem: {str(e)[:150]}")
            LOG.append({"step": "event", "id": tid, "error": str(e)[:120]})
    LOG.append({"step": "profiles opened", "count": names.fetched})
    return records, read_ok, entries_by_t, matches_by_t


def tt_roster(prepared):
    """Roster names as plain strings, whatever shape build_data's 'prepared' has."""
    out = []
    for item in prepared:
        rp = item[0] if isinstance(item, (tuple, list)) else item
        out.append(getattr(rp, "player", None) or str(rp))
    return out
