"""Save a few old roster pages so the alumni reader can be written against real HTML."""
import os, re
from playwright.sync_api import sync_playwright

SAMPLES = [
    ("texas", "https://texassports.com/sports/mens-tennis/roster/2018-19"),
    ("texas_new", "https://texassports.com/sports/mens-tennis/roster/2024-25"),
    ("virginia", "https://virginiasports.com/sports/mens-tennis/roster/2017-18"),
    ("tcu", "https://gofrogs.com/sports/mens-tennis/roster/2019-20"),
    ("stanford", "https://gostanford.com/sports/mens-tennis/roster/2018-19"),
    ("cornell", "https://cornellbigred.com/sports/mens-tennis/roster/2018-19"),
    ("ohiostate", "https://ohiostatebuckeyes.com/sports/mens-tennis/roster/2020-21"),
    ("sc", "https://gamecocksonline.com/sports/mens-tennis/roster/2019-20"),
]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
os.makedirs("alumni_html", exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(user_agent=UA)
    for name, url in SAMPLES:
        try:
            r = pg.goto(url, timeout=45000, wait_until="domcontentloaded")
            pg.wait_for_timeout(4000)
            html = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", "", pg.content(), flags=re.S)
            open(f"alumni_html/{name}.html", "w", encoding="utf-8").write(html[:300000])
            print(f"{name}: status {r.status if r else '?'}, {len(html)} chars, title={pg.title()!r}")
        except Exception as e:
            print(f"{name}: FAIL {str(e)[:100]}")
    b.close()
