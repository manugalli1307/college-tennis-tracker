"""
tennis_tracker.py

Scrapes tennisexplorer.com's weekly men's tennis calendar (ATP, Challenger,
ITF M15/M25 all show up on the same page) and checks which tournaments have
entrants matching a roster of tracked players.

WHAT THIS DOES:
  1. Fetch this week's tournament list from tennisexplorer.com.
  2. Fetch the entry list / draw for each tournament.
  3. Fuzzy-match entrant names against your roster.csv.
  4. Write matches to matches_<date>.csv and print a summary.

WHAT THIS DOES NOT DO (yet):
  - Run on a schedule (use cron / Task Scheduler / GitHub Actions for that).
  - Handle live scores or in-progress matches.
  - Guarantee it keeps working forever -- tennisexplorer can change its HTML
    at any time with no notice, since this isn't an official API.

HONEST CAVEAT ON THE FIRST RUN:
  I verified the WEEKLY CALENDAR page renders as plain HTML. I could NOT
  verify the exact HTML structure of individual tournament entry-list pages
  from my side -- I kept hitting a redirect loop that's most likely a
  cookie-consent wall, which a real browser (and a requests.Session() that
  persists cookies, which this script uses) should get past fine, but I
  can't promise the CSS selectors below are pixel-perfect on the first try.

  If TOURNAMENT SCRAPING comes back empty:
    1. Run with --debug to dump the raw HTML of one tournament page to
       debug_page.html, open it, and look for the table that lists players.
    2. Adjust `parse_entrants()` below to match what you see -- the comments
       mark exactly where to look.

Usage:
    pip install -r requirements.txt
    python tennis_tracker.py                  # this week, all levels
    python tennis_tracker.py --debug           # also saves debug_page.html
    python tennis_tracker.py --roster my.csv   # use a different roster file
"""

import argparse
import csv
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    from rapidfuzz import fuzz
    HAVE_RAPIDFUZZ = True
except ImportError:
    HAVE_RAPIDFUZZ = False
    import difflib

BASE_URL = "https://www.tennisexplorer.com"
CALENDAR_YEAR = date.today().year
CALENDAR_URL = f"{BASE_URL}/calendar/atp-men/{CALENDAR_YEAR}/"
REQUEST_DELAY_SECONDS = 2.0  # be polite -- don't hammer their server
MATCH_THRESHOLD = 85         # 0-100, fuzzy name-match confidence cutoff

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class Tournament:
    name: str
    url: str
    level: str  # "ATP", "Challenger", "ITF (M15/M25)", "UTR/Other"


@dataclass
class RosterPlayer:
    rank: str
    school: str
    player: str
    normalized: str = field(default="")


# ---------------------------------------------------------------------------
# Roster loading + name normalization
# ---------------------------------------------------------------------------

def strip_accents(text: str) -> str:
    """Turn 'Jangjun Kim' / 'Kučera' / 'García' into plain ASCII for matching."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_name(name: str) -> str:
    """Lowercase, strip accents/punctuation, sort tokens.

    Sorting tokens means 'Kim Jangjun' and 'Jangjun Kim' compare equal --
    draw sheets and rosters don't always order first/last name the same way.
    """
    name = strip_accents(name).lower()
    name = re.sub(r"[^a-z\s]", " ", name)
    tokens = sorted(name.split())
    return " ".join(tokens)


def load_roster(csv_path: str) -> list[RosterPlayer]:
    players = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("Player", "").strip()
            if not name:
                continue
            players.append(
                RosterPlayer(
                    rank=row.get("Rank", "").strip(),
                    school=row.get("School", "").strip(),
                    player=name,
                    normalized=normalize_name(name),
                )
            )
    return players


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------

def similarity(a: str, b: str) -> float:
    """Return 0-100 similarity score between two normalized names."""
    if HAVE_RAPIDFUZZ:
        return fuzz.token_sort_ratio(a, b)
    # Fallback if rapidfuzz isn't installed: stdlib difflib (slower, cruder).
    return difflib.SequenceMatcher(None, a, b).ratio() * 100


def find_roster_match(entrant_name: str, roster: list[RosterPlayer]):
    """Return (RosterPlayer, score) for the best match above MATCH_THRESHOLD,
    or (None, best_score_seen) if nothing clears the bar."""
    target = normalize_name(entrant_name)
    best_player, best_score = None, 0.0
    for rp in roster:
        score = similarity(target, rp.normalized)
        if score > best_score:
            best_player, best_score = rp, score
    if best_score >= MATCH_THRESHOLD:
        return best_player, best_score
    return None, best_score


# ---------------------------------------------------------------------------
# Calendar scraping
# ---------------------------------------------------------------------------

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def parse_row_date(row) -> "date | None":
    """Extract the tournament start date from a calendar row.

    Real HTML looks like:
        <td class="first shortdate" rowspan="2">22.06.<br>2026</td>
    i.e. "DD.MM." then a <year> after a <br>. get_text(separator) joins
    those with a space so we can regex it out reliably.
    """
    cell = row.find("td", class_="shortdate")
    if not cell:
        return None
    text = cell.get_text(separator=" ", strip=True)  # e.g. "22.06. 2026"
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.\D*(\d{4})", text)
    if not m:
        return None
    day, month, year = (int(x) for x in m.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def fetch_weekly_calendar(session: requests.Session, debug: bool = False) -> list[Tournament]:
    """Parse tournaments from the calendar page and filter to the current week.

    IMPORTANT: the raw HTML tennisexplorer serves contains the ENTIRE
    season's tournaments, not just "this week" -- the "This week's
    tournaments" heading you see in a browser is produced by their own
    JavaScript filtering the same table down client-side. Since we're
    reading raw HTML (no JS), we do that filtering ourselves here using
    each row's own start date instead.

    Each tournament row carries a data-type attribute -- "main" or "lower"
    -- which is a more reliable level signal than the section headings
    (confirmed against real site HTML on 2026-09-11).
    """
    resp = session.get(CALENDAR_URL, timeout=20)
    resp.raise_for_status()
    if debug:
        Path("debug_calendar.html").write_text(resp.text, encoding="utf-8")
        print("Saved raw calendar HTML to debug_calendar.html")

    soup = BeautifulSoup(resp.text, "html.parser")

    today = date.today()
    week_start = today - timedelta(days=today.weekday())       # this week's Monday
    week_end = week_start + timedelta(days=6)                  # this week's Sunday

    tournaments: list[Tournament] = []
    seen_urls = set()

    for row in soup.find_all("tr", attrs={"data-type": True}):
        link = row.find("a", href=True)
        if not link:
            continue
        href = link["href"]
        if not re.match(r"^/[\w\-]+/\d{4}/[\w\-]+/?$", href):
            continue

        row_date = parse_row_date(row)
        # Rows using rowspan only carry the date on the FIRST of their two
        # <tr>s -- if this row has no date cell of its own, fall back to
        # not filtering it out (better to show an extra tournament than
        # silently drop a real one because of a rowspan quirk).
        if row_date is not None and not (week_start <= row_date <= week_end):
            continue

        name = link.get_text(strip=True)
        section = "Main tournaments" if row.get("data-type") == "main" else "Lower level tournaments"
        level = classify_level(name, section)
        url = urljoin(BASE_URL, href)
        if url not in seen_urls:
            seen_urls.add(url)
            tournaments.append(Tournament(name=name, url=url, level=level))

    return tournaments


def classify_level(name: str, section: str) -> str:
    lower = name.lower()
    if "challenger" in lower or re.search(r"\bchall\.?\b", lower):
        return "Challenger"
    if "utr" in lower:
        return "UTR/Other"
    if "itf" in lower or section == "Lower level tournaments":
        return "ITF (M15/M25 -- check tournament page for exact level)"
    if section == "Main tournaments":
        return "ATP"
    return "Unknown"


# ---------------------------------------------------------------------------
# Entry list / draw scraping
# ---------------------------------------------------------------------------

def fetch_entrants(session: requests.Session, tournament: Tournament, debug: bool = False) -> list[str]:
    """Fetch a tournament page and pull out player names.

    tennisexplorer usually links player names to a profile page shaped like
    /player/some-name/. We treat any such link inside the page body as an
    entrant. This will also catch names in results/H2H boxes, which is fine
    for matching purposes (a name that shows up anywhere on the tournament
    page is a name worth checking against your roster) but may produce a
    few extra hits beyond just the main draw -- worth a sanity check on
    your first run.
    """
    try:
        resp = session.get(tournament.url, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [!] Could not fetch {tournament.name}: {e}")
        return []

    if debug:
        Path("debug_page.html").write_text(resp.text, encoding="utf-8")
        print(f"  Saved raw HTML for '{tournament.name}' to debug_page.html")

    soup = BeautifulSoup(resp.text, "html.parser")
    names = []
    for link in soup.find_all("a", href=True):
        if re.match(r"^/player/[\w\-]+/?$", link["href"]) or "/player/" in link["href"]:
            name = link.get_text(strip=True)
            if name:
                names.append(name)

    # de-duplicate while preserving order
    seen = set()
    unique_names = []
    for n in names:
        if n not in seen:
            seen.add(n)
            unique_names.append(n)
    return unique_names


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", default="roster.csv", help="Path to roster CSV")
    parser.add_argument("--out", default=None, help="Output CSV path (default: matches_<date>.csv)")
    parser.add_argument("--debug", action="store_true", help="Save raw HTML for inspection")
    parser.add_argument(
        "--max-tournaments",
        type=int,
        default=None,
        help="Limit how many tournaments to check (useful for a quick test run)",
    )
    args = parser.parse_args()

    if not HAVE_RAPIDFUZZ:
        print(
            "[!] rapidfuzz isn't installed -- falling back to a slower, cruder "
            "matcher. Run: pip install rapidfuzz\n"
        )

    roster = load_roster(args.roster)
    print(f"Loaded {len(roster)} players from {args.roster}\n")

    session = make_session()

    print("Fetching this week's tournament calendar...")
    tournaments = fetch_weekly_calendar(session, debug=args.debug)
    print(f"Found {len(tournaments)} tournaments this week.\n")

    if args.max_tournaments:
        tournaments = tournaments[: args.max_tournaments]

    all_matches = []
    for i, t in enumerate(tournaments, 1):
        print(f"[{i}/{len(tournaments)}] {t.name} ({t.level})")
        entrants = fetch_entrants(session, t, debug=(args.debug and i == 1))
        if not entrants:
            print("  (no entrant names found -- see caveats in the file header)")
        for entrant in entrants:
            match, score = find_roster_match(entrant, roster)
            if match:
                print(f"  MATCH: {entrant}  ->  {match.player} ({match.school}) [{score:.0f}%]")
                all_matches.append(
                    {
                        "tournament": t.name,
                        "level": t.level,
                        "tournament_url": t.url,
                        "entrant_name_on_site": entrant,
                        "matched_roster_player": match.player,
                        "matched_school": match.school,
                        "match_confidence": f"{score:.0f}%",
                    }
                )
        time.sleep(REQUEST_DELAY_SECONDS)

    out_path = args.out or f"matches_{date.today().isoformat()}.csv"
    if all_matches:
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_matches[0].keys()))
            writer.writeheader()
            writer.writerows(all_matches)
        print(f"\nWrote {len(all_matches)} match(es) to {out_path}")
    else:
        print(
            "\nNo matches found this run. If this is your first run, "
            "re-run with --debug and check debug_page.html to confirm "
            "the entry-list HTML looks like what parse logic expects."
        )


if __name__ == "__main__":
    sys.exit(main())
