"""
alumni.py -- builds data/alumni.csv: men's tennis players who were on a top-30 team's roster
in the last 10 seasons but are not on this season's roster (no repeats).

Reads each school's public roster pages (/sports/mens-tennis/roster/<season>), season by season.
Writes data/alumni.csv and data/alumni_log.json (one line per page, so gaps are easy to see).
"""
import asyncio, csv, json, os, re, sys, unicodedata
from pathlib import Path
from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
SEASONS = [f"{y}-{str(y + 1)[2:]}" for y in range(2016, 2026)]   # 2016-17 ... 2025-26
SPORT_SLUGS = ["mens-tennis", "mten", "mtennis", "m-tennis"]

# school (as written in roster.csv) -> website
SITES = {
    "University of Virginia": "virginiasports.com",
    "University of Texas at Austin": "texassports.com",
    "Wake Forest": "godeacs.com",
    "TCU": "gofrogs.com",
    "Ohio State": "ohiostatebuckeyes.com",
    "Mississippi State": "hailstate.com",
    "University of Arizona": "arizonawildcats.com",
    "LSU": "lsusports.net",
    "University of Oklahoma": "soonersports.com",
    "Baylor University": "baylorbears.com",
    "Texas A&M University": "12thman.com",
    "University of Georgia": "georgiadogs.com",
    "UCF": "ucfknights.com",
    "University of Illinois at Urbana-Champaign": "fightingillini.com",
    "University of South Carolina": "gamecocksonline.com",
    "Stanford": "gostanford.com",
    "University of San Diego": "usdtoreros.com",
    "Michigan State": "msuspartans.com",
    "UCLA": "uclabruins.com",
    "USC": "usctrojans.com",
    "Pepperdine": "pepperdinewaves.com",
    "University of Florida": "floridagators.com",
    "Vanderbilt": "vucommodores.com",
    "University of Notre Dame": "fightingirish.com",
    "Auburn": "auburntigers.com",
    "Cornell": "cornellbigred.com",
    "Columbia": "gocolumbialions.com",
    "NC State": "gopack.com",
    "SMU": "smumustangs.com",
    "Clemson": "clemsontigers.com",
}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CLASS_RE = re.compile(r"^(?:R-|RS-|Redshirt\s*)?(Fr|So|Jr|Sr|Gr|Grad|Freshman|Sophomore|Junior|Senior|Graduate|5th|5Y)\b", re.I)

EXTRACT_JS = """() => {
  const out = [];
  const clean = s => (s || '').replace(/\\s+/g, ' ').trim();
  // A) tables with a Name column and a class/year column
  document.querySelectorAll('table').forEach(tb => {
    const rows = Array.from(tb.querySelectorAll('tr'));
    if (rows.length < 2) return;
    const heads = Array.from(rows[0].querySelectorAll('th,td')).map(c => clean(c.textContent).toLowerCase());
    const ni = heads.findIndex(h => /^(full )?name$|^player$/.test(h));
    const ci = heads.findIndex(h => /^(yr|cl|class|academic year|year|eligibility)\\.?$/.test(h));
    const hi = heads.findIndex(h => /hometown/.test(h));
    if (ni < 0 || ci < 0) return;
    rows.slice(1).forEach(r => {
      const c = Array.from(r.querySelectorAll('th,td')).map(x => clean(x.textContent));
      if (c[ni]) out.push({name: c[ni], cls: c[ci] || '', home: hi >= 0 ? (c[hi] || '') : '', how: 'table'});
    });
  });
  if (out.length) return out;
  // B) "person cards"
  document.querySelectorAll('.s-person-card, .sidearm-roster-player').forEach(card => {
    const t = clean(card.textContent);
    const m = /Academic Year\\s+(\\S+)/.exec(t) || /\\b(Fr|So|Jr|Sr|Gr)\\.?\\b/.exec(t);
    if (!m) return;
    const nm = card.querySelector('.s-person-details__personal-single-line, h3, h2, .sidearm-roster-player-name a, a');
    const h = /Hometown\\s+(.+?)(?:\\s+(?:Last School|High School|Major|Full Bio|Previous)|$)/.exec(t);
    out.push({name: clean(nm ? nm.textContent : ''), cls: m[1], home: h ? h[1] : '', how: 'card'});
  });
  return out;
}"""


def key(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", "", s).strip()


def class_rank(c):
    m = CLASS_RE.match(c.strip())
    if not m:
        return None
    w = m.group(1).lower()[:2]
    return {"fr": 1, "so": 2, "jr": 3, "sr": 4, "gr": 5, "5t": 5, "5y": 5}.get(w)


async def fetch_season(ctx, host, season, log):
    page = await ctx.new_page()
    try:
        for slug in SPORT_SLUGS:
            url = f"https://{host}/sports/{slug}/roster/{season}"
            try:
                r = await page.goto(url, timeout=45000, wait_until="domcontentloaded")
                status = r.status if r else 0
                if status >= 400:
                    continue
                try:
                    await page.wait_for_selector("table, .s-person-card, .sidearm-roster-player", state="attached", timeout=12000)
                except Exception:
                    pass
                await page.wait_for_timeout(1200)
                title = await page.title()
                if "tennis" not in title.lower():
                    continue
                if "women" in title.lower():
                    continue
                rows = await page.evaluate(EXTRACT_JS)
                log.append({"host": host, "season": season, "url": url, "status": status, "n": len(rows),
                            "how": rows[0]["how"] if rows else "", "title": title[:70]})
                if not rows:
                    html = await page.content()
                    return [], re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", "", html, flags=re.S)
                return rows, None
            except Exception as e:
                log.append({"host": host, "season": season, "url": url, "error": str(e)[:80]})
        log.append({"host": host, "season": season, "n": 0, "note": "no working address"})
        return [], None
    finally:
        await page.close()


async def main():
    only = sys.argv[1].lower() if len(sys.argv) > 1 else None
    current = {}
    with open(HERE / "roster.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            current.setdefault(r["School"], set()).add(key(r["Player"]))
    log, found, fails = [], {}, {}
    sem = asyncio.Semaphore(5)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA)

        async def one(school, host, season):
            async with sem:
                rows, html = await fetch_season(ctx, host, season, log)
            if html and school not in fails:
                fails[school] = html
            for r in rows:
                name = re.sub(r"\s+", " ", r["name"]).strip()
                rk = class_rank(r["cls"])
                if not name or rk is None or len(name.split()) < 2:
                    continue
                k = (school, key(name))
                e = found.setdefault(k, {"School": school, "Player": name, "seasons": [], "cls": {}, "home": r["home"]})
                e["seasons"].append(season)
                e["cls"][season] = r["cls"]
                if r["home"]:
                    e["home"] = r["home"]

        jobs = [one(s, h, y) for s, h in SITES.items() if not only or only in s.lower() for y in SEASONS]
        await asyncio.gather(*jobs)
        await browser.close()

    out = []
    for (school, k), e in found.items():
        if k in current.get(school, set()):
            continue  # still on the team
        seasons = sorted(set(e["seasons"]))
        last = seasons[-1]
        last_cls = e["cls"][last]
        rk = class_rank(last_cls)
        end_year = int("20" + last.split("-")[1])
        grad = end_year if rk and rk >= 4 else ""
        out.append({"School": school, "Player": e["Player"], "Hometown": e["home"],
                    "First season": seasons[0], "Last season": last, "Last class": last_cls,
                    "Graduation year": grad})
    out.sort(key=lambda r: (r["School"], r["Last season"], r["Player"]))
    DATA.mkdir(exist_ok=True)
    with open(DATA / "alumni.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["School", "Player", "Hometown", "First season", "Last season", "Last class", "Graduation year"])
        w.writeheader()
        w.writerows(out)
    log.sort(key=lambda r: (r["host"], r["season"]))
    (DATA / "alumni_log.json").write_text(json.dumps(log, indent=0), encoding="utf-8")
    os.makedirs(HERE.parent / "probes" / "alumni_fail", exist_ok=True)
    for school, html in fails.items():
        (HERE.parent / "probes" / "alumni_fail" / (key(school).replace(" ", "_") + ".html")).write_text(html[:250000], encoding="utf-8")
    per = {}
    for r in log:
        per.setdefault(r["host"], []).append(r.get("n", 0))
    for h, ns in sorted(per.items()):
        print(f"{h}: pages with players {sum(1 for n in ns if n)}/{len(ns)}, players seen {sum(ns)}")
    print(f"\nAlumni rows: {len(out)}")


asyncio.run(main())
