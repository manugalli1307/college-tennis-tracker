"""Look at a Tennis Explorer event page's #draw block (is it in bracket order?)."""
import os, re
from playwright.sync_api import sync_playwright

PAGES = {
    "draw_bratislava": "https://www.tennisexplorer.com/bratislava-challenger/2026/atp-men/",
}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
os.makedirs("alumni_html", exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(user_agent=UA)
    for name, url in PAGES.items():
        try:
            r = pg.goto(url, timeout=45000, wait_until="domcontentloaded")
            pg.wait_for_timeout(2500)
            html = pg.content()
            d = pg.locator("#draw")
            block = d.first.inner_html() if d.count() else "NO #draw"
            block = re.sub(r"<script.*?</script>|<svg.*?</svg>", "", block, flags=re.S)
            open(f"alumni_html/{name}.html", "w", encoding="utf-8").write(block[:400000])
            print(f"{name}: status {r.status if r else '?'}, draw block {len(block)} chars, players={pg.locator('#draw a[href^=\"/player/\"]').count()}")
            print(pg.locator("#draw").first.inner_text()[:1500] if d.count() else "")
        except Exception as e:
            print(f"{name}: FAIL {str(e)[:100]}")
    b.close()
