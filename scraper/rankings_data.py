"""
rankings_data.py -- current ATP singles ranking for every roster player.

Tennis Explorer's player search (/list-players/?search-text-pl=<surname>) lists
"Surname, Given" with the ATP rank, so brothers with the same surname stay apart.
Results are cached in data/rank_lookup.json and refreshed weekly.
"""
import re
import time
from datetime import date, timedelta

from bs4 import BeautifulSoup

import tennis_tracker as tt

BASE = "https://www.tennisexplorer.com"
LOG = []
MAX_PER_RUN = 400          # first fill takes two runs, then it is only the weekly refresh
REFRESH_DAYS = 7


def toks(s):
    return re.sub(r"[^a-z ]", " ", tt.strip_accents(s or "").lower()).split()


def same_person(roster_name, found_name):
    """found_name is 'Surname, Given' from the site."""
    if "," in found_name:
        sur, given = [x.strip() for x in found_name.split(",", 1)]
        f = toks(given + " " + sur)
    else:
        f = toks(found_name)
    r = toks(roster_name)
    if not f or not r:
        return False
    if sorted(f) == sorted(r):
        return True
    # same first name and same last name, one side has an extra middle name
    return f[0] == r[0] and f[-1] == r[-1] and len(set(f) & set(r)) >= 2


def search_query(name):
    """The longest word after the first name, hyphens kept ('Dedura-Palomero')."""
    words = re.sub(r"[^A-Za-z\- ]", " ", tt.strip_accents(name or "")).split()
    rest = words[1:] or words
    return max(rest, key=len)


def parse_results(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tb in soup.select("table.result"):
        head = tb.select_one("thead")
        if not head or "Name - men" not in head.get_text(" ", strip=True):
            continue
        for tr in tb.select("tbody tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            a = tds[1].find("a", href=True)
            if not a or "/player/" not in a["href"]:
                continue
            rk = re.match(r"\s*(\d+)\.", tds[0].get_text(" ", strip=True))
            flag = tds[1].find("span", title=True)
            out.append({"name": a.get_text(" ", strip=True), "slug": a["href"].split("/player/")[1].strip("/"),
                        "rank": int(rk.group(1)) if rk else None, "country": flag["title"] if flag else ""})
    return out


def lookup(page, players, cache, ranks_out, today=None):
    """players: roster dicts with id + name. Fills cache and ranks_out {pid: {...}}."""
    today = today or date.today()
    todo = []
    for p in players:
        c = cache.get(p["id"])
        # ATP rankings change on Mondays: a lookup is stale once a newer Monday has passed (and never older than a week)
        monday = today - timedelta(days=today.weekday())
        asof = date.fromisoformat(c.get("asof", "2000-01-01")) if c else None
        if c and asof >= monday and (today - asof).days < REFRESH_DAYS:
            continue
        todo.append(p)
    print(f"Ranking lookup: {len(players) - len(todo)} fresh, {len(todo)} to look up (max {MAX_PER_RUN} this run).")
    done = found = 0
    for p in todo[:MAX_PER_RUN]:
        q = search_query(p["name"])
        try:
            page.goto(f"{BASE}/list-players/?search-text-pl={q}", timeout=45000, wait_until="domcontentloaded")
            page.wait_for_selector("table.result", state="attached", timeout=15000)
            hits = [h for h in parse_results(page.content()) if same_person(p["name"], h["name"])]
        except Exception as e:
            LOG.append({"step": "rank search", "player": p["name"], "error": str(e)[:100]})
            continue
        done += 1
        if hits:
            found += 1
            h = sorted(hits, key=lambda x: (x["rank"] is None, x["rank"] or 0))[0]
            cache[p["id"]] = {"found": True, "slug": h["slug"], "rank": h["rank"], "country": h["country"], "asof": today.isoformat()}
        else:
            cache[p["id"]] = {"found": False, "asof": today.isoformat()}
        time.sleep(0.4)
    print(f"Ranking lookup: searched {done}, matched {found}.")
    LOG.append({"step": "rank lookup", "searched": done, "matched": found})
    for p in players:
        c = cache.get(p["id"])
        if not c or not c.get("found"):
            continue
        info = {"country": c.get("country", ""), "asof": c.get("asof", "")}
        if c.get("rank"):
            info["rank"] = c["rank"]
        else:
            info["unranked"] = True
        old = ranks_out.get(p["id"], {})
        old.update(info)
        ranks_out[p["id"]] = old
