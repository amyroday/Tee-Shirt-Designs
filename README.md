# Whimsical Ember Apparel — Weekly Trend Research Pipeline

Automated weekly research + reporting for a Printify/Etsy tee & sweatshirt business.
Runs every Monday via GitHub Actions, writes a report to `weekly_reports/`, and
updates the dashboard at `index.html` (enable GitHub Pages to browse it live).

## How it works

- **Printify catalog + costs** (official API) — real brand/model/color/base-cost data.
- **Etsy shop sales** (official Etsy Open API v3, OAuth) — this shop's actual last-60-day
  sales, not guesswork.
- **Google Trends** (pytrends) — search-interest signal for candidate niches.
- **Anthropic API (web search)** — the one part no API can give you: reads public trend
  blogs and Etsy's own trend pages to synthesize design concepts, political/seasonal
  angles, and forecasts, grounded in the real data above.
- **Manual ListingView export (optional)** — drop a CSV in `data/manual/` before a run
  if you want to fold in ListingView's competitive numbers (no public API exists for it,
  so this is a manual step, not automated).

See `pipeline/` for the individual modules and `.github/workflows/weekly-report.yml`
for the schedule.

## One-time setup

1. **Printify**: generate a Personal Access Token (Printify account → Connections → API).
   Also grab your Shop ID from the Printify dashboard URL.
2. **Etsy**:
   - Register a free app at [developer.etsy.com](https://www.etsy.com/developers/your-apps) — note the **Keystring** (`ETSY_API_KEY`) and **Shared secret** (`ETSY_SHARED_SECRET`).
   - Copy `.env.example` to `.env` and fill in `ETSY_API_KEY`, `ETSY_SHARED_SECRET`, and `ETSY_SHOP_ID`.
   - Run `python scripts/etsy_oauth_setup.py` and follow the prompts — you'll approve access in
     your own browser, then get back an `ETSY_REFRESH_TOKEN` to store as a secret.
   - **Etsy rotates the refresh token every time it's used.** The pipeline persists the new
     one back to the `ETSY_REFRESH_TOKEN` GitHub secret automatically each run — this needs a
     GitHub Personal Access Token with this repo's "Secrets: write" permission, stored as
     `GH_PAT_FOR_SECRETS`.
3. **Anthropic**: create an API key at [console.anthropic.com](https://console.anthropic.com)
   (billed separately from a Claude subscription — this is pay-per-use API spend, a few
   cents per weekly run).
4. **GitHub repo secrets** (Settings → Secrets and variables → Actions): add
   `PRINTIFY_TOKEN`, `PRINTIFY_SHOP_ID`, `ETSY_API_KEY`, `ETSY_SHARED_SECRET`, `ETSY_SHOP_ID`,
   `ETSY_REFRESH_TOKEN`, `ANTHROPIC_API_KEY`, `GH_PAT_FOR_SECRETS`.
5. **GitHub Pages** (optional, for the browsable dashboard): Settings → Pages → Deploy from
   branch → `main` / root.

## Local testing

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your values
python pipeline/run_weekly_report.py --dry-run
```

`--dry-run` writes the report files and updates `index.html` locally without committing
or pushing. Open `Tee_Research_Report_<date>.html` or run `python -m http.server` from
the repo root and browse to `index.html` to check the rendering.

## Manually triggering the GitHub Actions run

Once secrets are set, go to the **Actions** tab → **Weekly Tee Trend Report** →
**Run workflow** to test the full path (including the git commit) before relying on
the Monday cron.

## Manual competitive data (ListingView)

ListingView (listingview.io) has real cross-shop sales data but only through its browser
extension — no public API. To fold a week's worth of it into the report, export whatever
you need from ListingView and drop it as a CSV in `data/manual/` (e.g.
`data/manual/listingview_2026-08-04.csv`) before the run. Suggested columns: `keyword`,
`listing_title`, `shop_name`, `estimated_sales`, `price`, `tags` — extra columns are kept,
just not specially parsed.
