# College Tennis on Tour

Tracks men from the top-30 Division I college tennis teams at ITF M15/M25 events: who is entered, who is playing now, and how they did over the last two weeks.

- `scraper/` collects entry lists and results from the public ITF pages (`build_data.py`) and writes JSON to `data/`.
- `site/` is the website (plain HTML/CSS/JS). It reads `data/*.json`.
- `.github/workflows/update.yml` runs the scraper twice a day and publishes the site to GitHub Pages.

To refresh by hand: GitHub, Actions tab, "Update data and publish site", Run workflow.
