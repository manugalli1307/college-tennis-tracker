"""Look at the #draw block of some Tennis Explorer events: where every cell sits and what it says
(byes, qualifier spots, ...)."""
import os, re
from playwright.sync_api import sync_playwright

PAGES = {
    "draw_paris": "https://www.tennisexplorer.com/paris/2026/atp-men/",
    "draw_stockholm": "https://www.tennisexplorer.com/stockholm/2026/atp-men/",
    "draw_brisbane": "https://www.tennisexplorer.com/brisbane-4-challenger/2026/atp-men/",
}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
os.makedirs("alumni_html", exist_ok=True)
JS = """() => { const d = document.querySelector('#draw'); if (!d) return null;
  return [...d.querySelectorAll('div')].map(e => { const s = e.getAttribute('style') || '';
    const l = (s.match(/left:\\s*(-?\\d+)/) || [])[1], t = (s.match(/top:\\s*(-?\\d+)/) || [])[1];
    return [l, t, e.className, (e.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 70), e.querySelectorAll('a[href^="/player/"]').length]; }); }"""
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(user_agent=UA)
    for name, url in PAGES.items():
        try:
            r = pg.goto(url, timeout=45000, wait_until="domcontentloaded")
            pg.wait_for_timeout(2500)
            cells = pg.evaluate(JS)
            if not cells:
                print(f"{name}: no #draw (status {r.status if r else '?'})")
                continue
            print(f"\\n=== {name}: {len(cells)} cells")
            for l, t, cls, txt, n in cells:
                if l in ("10", None) or (l is not None and int(l) < 40):  # first column only, plus anything odd
                    print(f"left={l} top={t} cls={cls!r} anchors={n} text={txt!r}")
        except Exception as e:
            print(f"{name}: FAIL {str(e)[:100]}")
    b.close()
