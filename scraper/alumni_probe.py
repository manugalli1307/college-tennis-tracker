"""Look at Tennis Explorer's player search and ranking pages (how to find every roster player's ranking)."""
import os, re
from playwright.sync_api import sync_playwright

PAGES = {
    "search_dedura": "https://www.tennisexplorer.com/list-players/?search-text-pl=Dedura",
    "search_brooksby": "https://www.tennisexplorer.com/list-players/?search-text-pl=Brooksby",
    "rank_1": "https://www.tennisexplorer.com/ranking/atp-men/2026/",
    "rank_p2": "https://www.tennisexplorer.com/ranking/atp-men/2026/?page=2",
    "rank_p20": "https://www.tennisexplorer.com/ranking/atp-men/2026/?page=20",
    "profile_mariano": "https://www.tennisexplorer.com/player/dedura-palomero-ca7e6/",
}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
os.makedirs("alumni_html", exist_ok=True)
CLEAN = lambda h: re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", "", h, flags=re.S)
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(user_agent=UA)
    for name, url in PAGES.items():
        try:
            r = pg.goto(url, timeout=45000, wait_until="domcontentloaded")
            pg.wait_for_timeout(2500)
            html = CLEAN(pg.content())
            open(f"alumni_html/{name}.html", "w", encoding="utf-8").write(html[:300000])
            print(f"{name}: status {r.status if r else '?'}, {len(html)} chars, title={pg.title()[:70]!r}, rows={pg.locator('tr').count()}")
        except Exception as e:
            print(f"{name}: FAIL {str(e)[:100]}")
    b.close()
