"""
itf_scraper.py  (version 3)

Finds your tracked college players in ITF M15/M25 events, two ways:

  UPCOMING events (start within --ahead-days, default 21)
      Reads the tournament's ACCEPTANCE LIST (the entry list). The ITF only
      keeps this list up before an event starts.

  CURRENT / RECENT events (ended within --back-days, default 14)
      Opens the tournament page and follows "Draws and Results" to see who
      is or was in the draw. Once an event starts, players show up there
      instead of on the acceptance list.

The ITF site is a JavaScript app, so this uses Playwright (a real background
Chrome) instead of plain requests.

HONEST CAVEATS
  * I can't reach itftennis.com from where I write and test this code. The
    browser logic was tested against a local mock site only. The first real
    run is the real test, so use --debug and send me what you see.
  * The "Draws and Results" page layout is the least certain part. If it
    comes back with no players, the debug files will show me what it is.
  * Matches labelled "verify" are weaker (initial + surname, or a name shown
    without its first name). Check them by hand.

USAGE
    python3 itf_scraper.py --scope upcoming          # entry lists only (start here)
    python3 itf_scraper.py --scope recent            # current + recently finished
    python3 itf_scraper.py                           # both
    python3 itf_scraper.py --only "ann arbor" --back-days 40 --find bonding --debug
"""

import argparse
import csv
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

import tennis_tracker as tt  # roster loading + accent stripping

DEFAULT_BASE_URL = "https://www.itftennis.com"
CALENDAR_PATH = (
    "/en/tournament-calendar/mens-world-tennis-tour-calendar/"
    "?categories=All&startdate={year}-{month:02d}"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

MONTH_LOOKUP = {}
for _i, _names in enumerate(
    [
        ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
        ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
        ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
        ("dec", "december"),
    ],
    start=1,
):
    for _n in _names:
        MONTH_LOOKUP[_n] = _i


@dataclass
class ItfTournament:
    name: str
    category: str  # "M15" or "M25"
    url: str
    start: "date | None" = None
    end: "date | None" = None
    status: str = ""  # upcoming / current / past / unknown


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_RANGE_RE = re.compile(
    r"(\d{1,2})(?:\s+([A-Za-z]{3,9}))?\s*(?:[-–—]|\bto\b)\s*(\d{1,2})\s+([A-Za-z]{3,9})(?:\s+(\d{4}))?"
)


def parse_date_range(text: str, default_year: "int | None" = None):
    """Find a date range like '28 Sep - 04 Oct 2026' (or '07 - 13 Sep 2026').
    Returns (start, end) as dates, or None."""
    for m in _RANGE_RE.finditer(text or ""):
        d1, m1, d2, m2, yr = m.groups()
        end_month = MONTH_LOOKUP.get(m2.lower())
        start_month = MONTH_LOOKUP.get(m1.lower()) if m1 else end_month
        if not end_month or not start_month:
            continue
        year = int(yr) if yr else default_year
        if not year:
            continue
        try:
            end = date(year, end_month, int(d2))
            start = date(year - 1 if start_month > end_month else year, start_month, int(d1))
        except ValueError:
            continue
        if start <= end:
            return start, end
    return None


def year_from_url(url: str) -> "int | None":
    m = re.search(r"/(20\d{2})/", url or "")
    return int(m.group(1)) if m else None


def classify(start: date, end: date, today: date, ahead_days: int, back_days: int):
    """Return 'upcoming', 'current' or 'past', or None if outside the window."""
    if end < today:
        return "past" if (today - end).days <= back_days else None
    if start <= today <= end:
        return "current"
    return "upcoming" if (start - today).days <= ahead_days else None


def months_in_window(today: date, ahead_days: int, back_days: int):
    months = []
    d = today - timedelta(days=back_days)
    last = today + timedelta(days=ahead_days)
    while d <= last:
        if (d.year, d.month) not in months:
            months.append((d.year, d.month))
        d += timedelta(days=1)
    return months


# ---------------------------------------------------------------------------
# Finding roster players in page text
# ---------------------------------------------------------------------------

def norm_words(text: str) -> list[str]:
    """Lowercase, strip accents, keep letters only. 'Kucera' == 'Kučera';
    'BONDING\\nOliver' -> ['bonding', 'oliver']."""
    text = tt.strip_accents(text or "").lower()
    return re.sub(r"[^a-z]+", " ", text).split()


def prepare_roster(roster):
    prepared = []
    for rp in roster:
        toks = norm_words(rp.player)
        if len(toks) >= 2:
            prepared.append((rp, toks))
    return prepared


def _window_exact(words: list[str], target_sorted: list[str]) -> bool:
    size = len(target_sorted)
    tokset = set(target_sorted)
    for i in range(len(words) - size + 1):
        if words[i] in tokset and sorted(words[i : i + size]) == target_sorted:
            return True
    return False


def _match_kind(words: list[str], toks: list[str]):
    # 1) full name, any order, on one line or split across lines
    if _window_exact(words, sorted(toks)):
        return "full name"
    # 2) site omits the first given name ('Kohlmann de Freitas')
    if len(toks) >= 3 and _window_exact(words, sorted(toks[1:])):
        return "partial name - verify"
    # 3) initial + surname ('O. Bonding' / 'BONDING O')
    if _window_exact(words, sorted(toks[1:] + [toks[0][0]])):
        return "initial + surname - verify"
    return None


def find_players(text: str, prepared):
    words = norm_words(text)
    if not words:
        return []
    hits = []
    for rp, toks in prepared:
        kind = _match_kind(words, toks)
        if kind:
            hits.append((rp, kind))
    return hits


# ---------------------------------------------------------------------------
# Browser helpers
# ---------------------------------------------------------------------------

def safe_label(text: str) -> str:
    return re.sub(r"[^\w\-]+", "_", text).strip("_")[:60]


def save_debug(page, label: str):
    stem = f"debug_itf_{safe_label(label)}"
    try:
        Path(stem + ".html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=stem + ".png", full_page=True)
        print(f"    Saved {stem}.html/.png")
    except Exception as e:
        print(f"    (could not save debug files: {e})")


def settle(page, extra_ms: int = 3000):
    """Wait for a JS page to finish loading, then scroll to trigger lazy rows."""
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(extra_ms)
    for _ in range(4):
        try:
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(600)
        except Exception:
            break


_TEXT_JS = """() => {
    const out = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
        const text = node.textContent.trim();
        if (!text) continue;
        const el = node.parentElement;
        if (!el) continue;
        const tag = el.tagName;
        if (tag === "SCRIPT" || tag === "STYLE" || tag === "NOSCRIPT") continue;
        if (el.checkVisibility && !el.checkVisibility()) continue;
        out.push(text);
    }
    return out.join("\\n");
}"""


def visible_text(page) -> str:
    """Visible page text with every text element on its own line. (Plain
    inner_text can glue neighbouring elements together, e.g. a surname and a
    first name in separate <span>s become 'BONDINGOliver'.)"""
    try:
        text = page.evaluate(_TEXT_JS)
        if text:
            return text
    except Exception:
        pass
    try:
        return page.locator("body").inner_text(timeout=8000)
    except Exception:
        return ""


def show_find(text: str, term: str):
    hits = [m.start() for m in re.finditer(re.escape(term), text, flags=re.IGNORECASE)]
    if not hits:
        print(f"    '{term}' is NOT in the page text ({len(text)} characters loaded)")
        return
    s = max(0, hits[0] - 60)
    e = hits[0] + len(term) + 60
    print(f"    '{term}' appears {len(hits)}x. Raw text around the first hit:")
    print("      " + repr(text[s:e]))


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

_LINK_SELECTOR = 'a[href*="/en/tournament/"]'

_COLLECT_JS = """els => els.map(e => {
    let row = "";
    let n = e;
    for (let i = 0; i < 6 && n && n.parentElement; i++) {
        n = n.parentElement;
        const hrefs = new Set(
            Array.from(n.querySelectorAll('a[href*="/en/tournament/"]')).map(a => a.getAttribute("href"))
        );
        if (hrefs.size > 1) break;
        row = n.innerText || "";
    }
    return {text: (e.innerText || "").trim(), href: e.getAttribute("href") || "", row: row};
})"""


def expand_list(page, max_rounds: int = 10):
    """The calendar may only show the first batch of events. Scroll and click
    any 'load more' / 'show more' button until the list stops growing."""
    last = -1
    for _ in range(max_rounds):
        count = page.locator(_LINK_SELECTOR).count()
        if count == last:
            break
        last = count
        try:
            page.mouse.wheel(0, 6000)
        except Exception:
            pass
        page.wait_for_timeout(1500)
        try:
            btn = page.get_by_text(re.compile(r"^\s*(load|show|view)\s+more\s*$", re.I)).first
            if btn.count():
                btn.evaluate("e => (e.closest('button,a') || e).click()")
                page.wait_for_timeout(2000)
        except Exception:
            pass


def fetch_calendar_month(page, base_url: str, template: str, year: int, month: int, debug: bool, label: str = ""):
    url = template.format(year=year, month=month)
    label = label or f"{year}-{month:02d}"
    print(f"Loading calendar: {label} ...")
    try:
        page.goto(url, timeout=45000)
    except Exception as e:
        print(f"  [!] could not load calendar: {e}")
        return []
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        print("  (page didn't reach full network-idle -- continuing)")

    for attempt in range(3):
        try:
            page.wait_for_selector(_LINK_SELECTOR, timeout=20000)
            break
        except Exception:
            if attempt < 2:
                print(f"  (tournament list not rendered yet -- reloading, attempt {attempt + 2}/3)")
                try:
                    page.reload(timeout=45000)
                except Exception:
                    pass
            else:
                print("  (tournament list never rendered)")
    if "/results/" in url:
        page.wait_for_timeout(5000)
    else:
        try:
            page.wait_for_selector("tr.whatson-table__tournament", timeout=20000)
            page.wait_for_timeout(4000)  # let the full list finish filling in
        except Exception:
            pass
    page.wait_for_timeout(1500)
    expand_list(page)

    if debug:
        save_debug(page, f"calendar_{label}")

    found = []
    for item in page.eval_on_selector_all(_LINK_SELECTOR, _COLLECT_JS):
        text = " ".join((item.get("text") or "").split())
        cat = re.search(r"\bM(15|25)\b", text)
        if not cat:
            continue
        href = item.get("href") or ""
        full = href if href.startswith("http") else base_url + href
        rng = parse_date_range(item.get("row") or "", year_from_url(full))
        t = ItfTournament(name=text, category="M" + cat.group(1), url=full)
        if rng:
            t.start, t.end = rng
        found.append(t)
    print(f"  {len(found)} M15/M25 tournament(s) listed")
    return found


# ---------------------------------------------------------------------------
# Reading one tournament
# ---------------------------------------------------------------------------

def open_overview(page, t: ItfTournament) -> str:
    page.goto(t.url, timeout=45000)
    settle(page, 2000)
    return visible_text(page)


def open_acceptance_list(page, t: ItfTournament):
    page.goto(t.url.rstrip("/") + "/acceptance-list/", timeout=45000)
    settle(page, 4000)
    return visible_text(page), page.url


def open_draws(page, t: ItfTournament):
    if page.url.rstrip("/") != t.url.rstrip("/"):
        page.goto(t.url, timeout=45000)
        settle(page, 2000)
    tile = page.get_by_text(re.compile(r"draws\s+and\s+results", re.I)).first
    try:
        tile.wait_for(timeout=10000)
    except Exception:
        print("    couldn't find a 'Draws and Results' link on the tournament page")
        return "", page.url
    # Follow the link's address directly (avoids cookie banners covering it).
    href = ""
    try:
        href = tile.evaluate("e => { const a = e.closest('a'); return a ? a.href : ''; }")
    except Exception:
        pass
    try:
        if href:
            page.goto(href, timeout=45000)
        else:
            tile.evaluate("e => (e.closest('a,button') || e).click()")
    except Exception as e:
        print(f"    couldn't open Draws and Results: {e}")
        return "", page.url
    settle(page, 5000)
    return visible_text(page), page.url


_SKIP_SECTION = re.compile(r"^(alternates?|withdrawals?|withdrawn)\b", re.I)
_KEEP_SECTION = re.compile(r"^(main\s+draw|qualifying)\b", re.I)


def split_entry_sections(text: str):
    """Split an acceptance list into (section name, text) pieces.
    Keeps MAIN DRAW ... and QUALIFYING ... sections; drops ALTERNATES and
    WITHDRAWALS (players who did not get into the event)."""
    sections = []
    name, buf = "other", []
    for line in text.splitlines():
        h = line.strip()
        is_heading = h.isupper() and len(h) > 5 and not any(c.isdigit() for c in h)
        if is_heading and (_SKIP_SECTION.match(h) or _KEEP_SECTION.match(h)):
            sections.append((name, "\n".join(buf)))
            name, buf = h.title(), []
        else:
            buf.append(line)
    sections.append((name, "\n".join(buf)))
    keep = []
    for nm, body in sections:
        if _SKIP_SECTION.match(nm) or nm == "other":
            continue
        keep.append((nm, body))
    return keep


def scan_text(text, source, page, t, status, prepared, args, debug_state):
    """Print what was found on a page and return result rows."""
    print(f"  {source}: {len(text)} characters of page text  ({page.url})")
    if args.find:
        show_find(text, args.find)
    if args.debug and not debug_state.get(source):
        save_debug(page, f"{source}_{t.name}")
        debug_state[source] = True

    by_name = {}
    if source == "acceptance list":
        pieces = split_entry_sections(text)
        if not pieces:
            print("  (no Main Draw / Qualifying section found on this page)")
        else:
            print("  sections counted: " + ", ".join(nm for nm, _ in pieces))
    else:
        pieces = [("Draw", text)]
    for section, body in pieces:
        for rp, kind in find_players(body, prepared):
            entry = by_name.setdefault(rp.player, {"kind": kind, "schools": [], "section": section})
            if rp.school not in entry["schools"]:
                entry["schools"].append(rp.school)

    rows = []
    for name, info in by_name.items():
        schools = " / ".join(info["schools"])
        print(f"  MATCH: {name} ({schools}) [{info['kind']}] - {info['section']}")
        rows.append(
            {
                "tournament": t.name,
                "category": t.category,
                "status": status,
                "dates": f"{t.start} to {t.end}" if t.start else "",
                "source": source,
                "player": name,
                "school": schools,
                "section": info["section"],
                "match_type": info["kind"],
                "url": page.url,
            }
        )
    if not rows:
        print("  (no roster players found)")
    return rows


def check_tournament(page, t, status, args, prepared, debug_state):
    want_accept = status == "upcoming" or (status == "unknown" and args.scope != "recent")
    want_draws = status in ("current", "past") or (status == "unknown" and args.scope != "upcoming")
    rows = []

    if want_accept:
        text, final_url = open_acceptance_list(page, t)
        if "acceptance-list" not in final_url:
            print(f"  acceptance list: redirected to {final_url} (no entry list published)")
        rows += scan_text(text, "acceptance list", page, t, status, prepared, args, debug_state)

    if want_draws:
        text, _ = open_draws(page, t)
        rows += scan_text(text, "draws and results", page, t, status, prepared, args, debug_state)
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def in_scope(status: str, scope: str) -> bool:
    if scope == "both" or status == "unknown":
        return True
    if scope == "upcoming":
        return status == "upcoming"
    return status in ("current", "past")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scope", choices=["upcoming", "recent", "both"], default="both",
                        help="upcoming = entry lists; recent = current + recently finished events")
    parser.add_argument("--ahead-days", type=int, default=21, help="how far ahead to look (default 21)")
    parser.add_argument("--back-days", type=int, default=14, help="how far back to look (default 14)")
    parser.add_argument("--roster", default="roster.csv", help="Path to roster CSV")
    parser.add_argument("--out", default="itf_tournaments.csv", help="Tournament list CSV path")
    parser.add_argument("--matches-out", default=None, help="Matches CSV path")
    parser.add_argument("--only", default=None, help='Only check tournaments whose name contains this, e.g. "ann arbor"')
    parser.add_argument("--find", default=None, help='Diagnostic: show how this text (e.g. "bonding") appears on each page')
    parser.add_argument("--debug", action="store_true", help="Save page HTML + screenshots for inspection")
    parser.add_argument("--max-tournaments", type=int, default=None, help="Limit how many tournaments to read (quick test)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=argparse.SUPPRESS)
    parser.add_argument("--calendar-url", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    today = date.today()
    template = args.calendar_url or (args.base_url + CALENDAR_PATH)
    roster = tt.load_roster(args.roster)
    prepared = prepare_roster(roster)
    print(f"Loaded {len(roster)} players from {args.roster}")
    print(f"Today is {today}. Window: {args.back_days} days back, {args.ahead_days} days ahead. Scope: {args.scope}\n")

    all_rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)

        # 1) Collect tournaments from every calendar month in the window
        by_url = {}
        cal_base = args.base_url + "/en/tournament-calendar/mens-world-tennis-tour-calendar/?categories=All"
        if args.calendar_url:
            windows = [(f"{y}-{m:02d}", template, y, m) for y, m in months_in_window(today, args.ahead_days, args.back_days)]
        else:
            # The ITF calendar only lists a day or a range when given real dates.
            # With no dates it shows just today's events (the ones already running).
            windows = [("today", cal_base, today.year, today.month)]
            if args.scope in ("upcoming", "both"):
                a = (today + timedelta(days=1)).isoformat()
                b = (today + timedelta(days=args.ahead_days)).isoformat()
                windows.append(("ahead", f"{cal_base}&startdate={a}&enddate={b}", today.year, today.month))
            if args.scope in ("recent", "both"):
                a = (today - timedelta(days=args.back_days)).isoformat()
                b = (today - timedelta(days=1)).isoformat()
                windows.append(("past", f"{cal_base}&startdate={a}&enddate={b}", today.year, today.month))
        for label, tmpl, year, month in windows:
            for t in fetch_calendar_month(page, args.base_url, tmpl, year, month, args.debug, label):
                old = by_url.get(t.url)
                if old is None or (old.start is None and t.start is not None):
                    by_url[t.url] = t
        tournaments = list(by_url.values())
        if args.only:
            tournaments = [t for t in tournaments if args.only.lower() in t.name.lower()]
            print(f"\n--only '{args.only}': {len(tournaments)} tournament(s) match")

        # 2) Sort into upcoming / current / past using dates, drop the ones outside the window
        todo = []
        skipped = 0
        for t in tournaments:
            if t.start:
                status = classify(t.start, t.end, today, args.ahead_days, args.back_days)
                if status is None or not in_scope(status, args.scope):
                    skipped += 1
                    continue
            else:
                status = "unknown"
            t.status = status
            todo.append(t)
        todo.sort(key=lambda t: (t.start or today))
        counts = {s: sum(1 for t in todo if t.status == s) for s in ("upcoming", "current", "past", "unknown")}
        print(f"\n{len(todo)} tournament(s) to read ({counts}); {skipped} skipped as outside the window/scope.")

        if args.max_tournaments:
            todo = todo[: args.max_tournaments]

        if todo:
            with open(args.out, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["name", "category", "status", "start", "end", "url"])
                for t in todo:
                    w.writerow([t.name, t.category, t.status, t.start or "", t.end or "", t.url])
            print(f"Wrote tournament list to {args.out}")

        # 3) Read each one
        debug_state = {}
        for i, t in enumerate(todo, 1):
            dates = f"{t.start} to {t.end}" if t.start else "dates unknown"
            print(f"\n[{i}/{len(todo)}] {t.name} ({t.category}, {t.status}, {dates})")
            status = t.status
            try:
                if t.start is None:
                    text = open_overview(page, t)
                    rng = parse_date_range(text, year_from_url(t.url))
                    if rng:
                        t.start, t.end = rng
                        status = classify(t.start, t.end, today, args.ahead_days, args.back_days)
                        if status is None or not in_scope(status, args.scope):
                            print("  skipped: outside the date window/scope")
                            continue
                        t.status = status
                        print(f"  dates from tournament page: {t.start} to {t.end} ({status})")
                all_rows += check_tournament(page, t, status, args, prepared, debug_state)
            except Exception as e:
                print(f"  [!] problem reading this tournament: {e}")
        browser.close()

    out_path = args.matches_out or f"itf_matches_{today.isoformat()}.csv"
    print("\n" + "=" * 60)
    if all_rows:
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            w.writeheader()
            w.writerows(all_rows)
        print(f"{len(all_rows)} match(es) written to {out_path}:")
        for r in all_rows:
            print(f"  {r['player']} ({r['school']}) - {r['tournament']} [{r['status']}, {r['match_type']}]")
    else:
        print("No roster players found. If you expected some, run again with")
        print("--only \"<tournament name>\" --find <surname> --debug and send me the output.")


if __name__ == "__main__":
    main()
