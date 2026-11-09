"""Run the real read_draw on finished ITF draws and show what it returns."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from playwright.sync_api import sync_playwright
import itf_scraper as itf
import build_data as bd

PAGES = {
    "hilton_head": "https://www.itftennis.com/en/tournament/m15-hilton-head-island-sc/usa/2026/m-itf-usa-2026-048/draws-and-results/",
    "guadalajara": "https://www.itftennis.com/en/tournament/m25-guadalajara/mex/2026/m-itf-mex-2026-010/draws-and-results/",
}
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(user_agent=itf.USER_AGENT)
    for name, url in PAGES.items():
        print("=====", name)
        try:
            pg.goto(url, timeout=45000)
            itf.settle(pg, 3000)
            pg.wait_for_selector(".drawsheet-widget", timeout=15000)
            print("titles at start:", bd._titles(pg))
            print("next count:", pg.locator(".btn--chevron-next").count(), "visible:", pg.locator(".btn--chevron-next").first.is_visible())
            res = bd.read_draw(pg)
            print("read_draw ->", [(t, len(m)) for t, m in res])
            print("titles after:", bd._titles(pg))
            print("next count after:", pg.locator(".btn--chevron-next").count())
        except Exception as e:
            print("FAIL", str(e)[:200])
    b.close()
