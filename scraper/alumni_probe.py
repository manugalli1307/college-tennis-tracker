"""Why are semifinals and finals missing from ITF draws? Page through a finished draw and log what is on screen."""
import re
from playwright.sync_api import sync_playwright

PAGES = {
    "hilton_head": "https://www.itftennis.com/en/tournament/m15-hilton-head-island-sc/usa/2026/m-itf-usa-2026-048/draws-and-results/",
    "guadalajara": "https://www.itftennis.com/en/tournament/m25-guadalajara/mex/2026/m-itf-mex-2026-010/draws-and-results/",
}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
JS = """() => Array.from(document.querySelectorAll('.drawsheet-round-container')).map(rc => [
  (rc.querySelector('.drawsheet-round-container__round-title') || {}).innerText || '?',
  rc.querySelectorAll('.drawsheet-widget').length,
  Array.from(rc.querySelectorAll('.drawsheet-widget__last-name')).map(x => x.innerText.trim()).slice(0, 4).join('/')])"""
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(user_agent=UA, viewport={"width": 1280, "height": 900})
    for name, url in PAGES.items():
        print("=====", name)
        try:
            pg.goto(url, timeout=45000, wait_until="domcontentloaded")
            pg.wait_for_timeout(5000)
            try:
                pg.wait_for_selector(".drawsheet-widget", timeout=15000)
            except Exception:
                print("no widgets")
            for step in range(8):
                print(f"step {step}:", pg.evaluate(JS))
                nxt = pg.locator(".btn--chevron-next").first
                n = pg.locator(".btn--chevron-next").count()
                vis = nxt.is_visible() if n else None
                dis = nxt.get_attribute("disabled") if n else None
                print(f"   next buttons={n} visible={vis} disabled={dis}")
                if not n or not vis:
                    break
                nxt.click(timeout=3000)
                pg.wait_for_timeout(1500)
            print("titles on page:", pg.evaluate("() => Array.from(document.querySelectorAll('[class*=round-title]')).map(e => e.innerText.trim())"))
            print("dropdowns:", pg.evaluate("() => Array.from(document.querySelectorAll('.drawsheet-dropdowns *')).map(e => e.innerText.trim()).filter(x => x && x.length < 40).slice(0, 12)"))
        except Exception as e:
            print("FAIL", str(e)[:150])
    b.close()
