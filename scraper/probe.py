"""Quick check: can this machine load the pages we'd need for ATP Challengers?
Prints one line per page. Used by the 'Probe Challenger sources' workflow."""
from playwright.sync_api import sync_playwright

PAGES = [
    ("ATP site: Challenger draw", "https://www.atptour.com/en/scores/current-challenger/charlottesville/6055/draws", "Player draw"),
    ("ATP site: calendar", "https://www.atptour.com/en/atp-challenger-tour/calendar", "Calendar"),
    ("Tennis Explorer: calendar", "https://www.tennisexplorer.com/calendar/atp-men/2026/", "challenger"),
    ("Tennis Explorer: draw", "https://www.tennisexplorer.com/charlottesville-challenger/2026/atp-men/?draw=1", "Tournament draw"),
    ("Tennis Explorer: player", "https://www.tennisexplorer.com/player/santamarta-roig/", "Santamarta Roig"),
]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(user_agent=UA)
    for label, url, expect in PAGES:
        try:
            r = pg.goto(url, timeout=45000)
            pg.wait_for_timeout(5000)
            text = pg.inner_text("body")
            ok = expect.lower() in text.lower()
            blocked = any(w in text.lower() for w in ("access denied", "captcha", "verify you are human", "forbidden"))
            print(f"{'OK  ' if ok and not blocked else 'FAIL'} {label}: status {r.status if r else '?'}, {len(text)} characters, "
                  f"expected text {'found' if ok else 'MISSING'}{', BLOCK PAGE' if blocked else ''}")
        except Exception as e:
            print(f"FAIL {label}: {str(e)[:120]}")
    b.close()

# ---- Save sample pages so the Tennis Explorer reader can be written against real HTML ----
import os, re
os.makedirs("probe_html", exist_ok=True)
SAMPLES = {
    "calendar": "https://www.tennisexplorer.com/calendar/atp-men/2026/",
    "event": "https://www.tennisexplorer.com/charlottesville-challenger/2026/atp-men/",
    "event_draw": "https://www.tennisexplorer.com/charlottesville-challenger/2026/atp-men/?draw=1",
    "event_qual": "https://www.tennisexplorer.com/charlottesville-challenger/2026/atp-men/?phase=qualification",
    "player": "https://www.tennisexplorer.com/player/santamarta-roig/",
}
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(user_agent=UA)
    for name, url in SAMPLES.items():
        try:
            pg.goto(url, timeout=45000)
            pg.wait_for_timeout(3000)
            html = pg.content()
            html = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
            open(f"probe_html/{name}.html", "w", encoding="utf-8").write(html[:400000])
            print("saved", name, len(html))
        except Exception as e:
            print("could not save", name, str(e)[:100])
    b.close()
