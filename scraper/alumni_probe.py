"""Second look at the schools whose roster pages could not be read."""
import os, re
from playwright.sync_api import sync_playwright

HOSTS = ["clemsontigers.com", "fightingirish.com", "gamecocksonline.com", "virginiasports.com",
         "vucommodores.com", "lsusports.net", "uclabruins.com", "12thman.com", "auburntigers.com",
         "cornellbigred.com", "usdtoreros.com", "ucfknights.com"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
os.makedirs("alumni_html", exist_ok=True)
CLEAN = lambda h: re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", "", h, flags=re.S)
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(user_agent=UA)
    for host in HOSTS:
        print("==", host)
        try:
            pg.goto(f"https://{host}/", timeout=45000, wait_until="domcontentloaded")
            pg.wait_for_timeout(2500)
            links = pg.eval_on_selector_all("a[href*='tennis']", "els => els.map(e => [e.getAttribute('href'), e.textContent.trim().slice(0,30)])")
            seen = []
            for href, txt in links:
                if href and href not in seen and "women" not in href and "wten" not in href and "wtennis" not in href:
                    seen.append(href)
            print("  tennis links:", seen[:8])
            base = next((h for h in seen if "/sports/" in h), None)
            cands = []
            if base:
                m = re.search(r"/sports/([^/]+)", base)
                if m:
                    cands.append(f"/sports/{m.group(1)}/roster/2019-20")
            cands += ["/sports/mens-tennis/roster/2019-20", "/sports/mens-tennis/roster"]
            for c in dict.fromkeys(cands):
                r = pg.goto(f"https://{host}{c}", timeout=45000, wait_until="domcontentloaded")
                pg.wait_for_timeout(3000)
                n_tab = pg.locator("table").count(); n_card = pg.locator(".s-person-card, .sidearm-roster-player").count()
                print(f"  {c}: status {r.status if r else '?'}, title={pg.title()[:60]!r}, tables={n_tab}, cards={n_card}")
                if r and r.status == 200 and "tennis" in pg.title().lower():
                    open(f"alumni_html/{host}.html", "w", encoding="utf-8").write(CLEAN(pg.content())[:250000])
                    break
        except Exception as e:
            print("  FAIL", str(e)[:100])
    b.close()
