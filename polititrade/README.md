# PolitiTrade — Signal Terminal

Personal financial-intelligence dashboard. Tracks congressional trades + executive/policy
catalysts, layers a valuation screen (P/S, Forward P/E, PEG), and ranks everything into a
daily watchlist and three research buckets (short-term / long-term / retirement-broad).

**Runs at ~$0/month.** No server or paid database. GitHub Actions runs Python on a
schedule → writes JSON into `site/public/data/` → commits → Netlify redeploys → the static
React site reads local JSON.

> Informational only. Not financial advice. STOCK Act disclosures lag trades 30–45 days, so
> nothing here front-runs anyone. The edge is pattern detection. Output labels are research
> tiers (HIGH CONVICTION / WATCH / NEUTRAL / COOLING), never "buy."

## Quick start

### Pipeline (Python)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r pipeline/requirements.txt

# Live run (needs open network — works on GitHub Actions / your machine):
python pipeline/fetch_congress.py  # -> append-only history + recent trades.json
python pipeline/fetch_prices.py    # -> prices.json + politicians.json
python pipeline/fetch_news.py      # -> news.json + per-feed health
python pipeline/scorer.py          # -> signals.json
python pipeline/rank_picks.py      # -> picks.json
python pipeline/validate_data.py --production

# Offline demo (no network — fills every JSON with realistic mock data):
python pipeline/seed_mock_data.py && python pipeline/scorer.py && python pipeline/rank_picks.py
```

### Site (React + Vite)
```bash
cd site
npm ci
npm run dev      # local preview at localhost:5173
npm run build    # -> site/dist (Netlify publishes this)
```

## How the score works
Each disclosed **buy** gets a 0–100 political signal from six weighted factors
(track record 25, committee relevance 20, cluster detection 20, trade size 15,
direction+recency 10, policy catalyst 10). Separately, each single stock gets a 0–100
**valuation score** from PEG (45%), Forward P/E (35%), P/S (20%).

The three buckets blend those two scores differently:
| Bucket | Signal | Valuation | Third factor |
|---|---|---|---|
| Short term | 70% | 15% | 15% momentum |
| Long term | 40% | 45% | 15% quality (PEG/growth) |
| Retirement/broad | 15% | 20% | 65% stability (ETF diversification anchors) |

All weights and thresholds live in `pipeline/config/settings.json` — tune without touching code.

## Config
- `config/settings.json` — weights, valuation bands, bucket blends, feature flags
- `config/committees.json` — politician → committee → sector map
- `config/policy_map.json` — news keyword → sector → tickers
- `config/universe.json` — ETF classification + retirement core holdings

## Data reliability

- Congressional disclosures come from the Bargo Congress API, which normalizes House Clerk and
  Senate eFD filings and preserves the official filing-portal URL. `pipeline/data/trades_history.json`
  is append-only across successful runs; `trades.json` is only the recent 90-day UI/scoring view.
- A source response with fewer than the configured minimum records, failed pagination, or an
  unhealthy news-feed quorum fails the job and preserves the last known-good public file.
- Every public payload declares `data_mode`. Demo fixtures display a persistent warning, and
  `validate_data.py --production` rejects them.
- `status.json` exposes source/stage health. The site marks data stale after 36 hours.

## Deploy
1. Push the repository to GitHub and enable Actions. Both workflows declare their contents
   permission explicitly; the scheduled workflow needs repository **Workflow permissions → Read
   and write permissions** to push generated data.
2. Create a free Bargo key and add it as the Actions repository secret `BARGO_API_KEY`. Anonymous
   runs safely accumulate the newest page, but an authenticated run is required to backfill enough
   history for the 90-day leaderboard. Production validation enforces a minimum 95-day span.
3. Netlify → **Add new site → Import an existing project** → choose this repository. The root
   `netlify.toml` sets base `polititrade/site`, publish `dist`, and Node 22.
4. Run **Refresh data and score** manually once. Confirm its bot commit appears on `main`, then
   confirm Netlify creates a deploy for that commit. Do not mark the site production-ready until
   this end-to-end check succeeds.

The schedule is `11:17 UTC` on weekdays. GitHub schedules are fixed in UTC, so this runs at
**6:17 a.m. Eastern Standard Time** and **7:17 a.m. Eastern Daylight Time**; it does not remain at
one Eastern wall-clock time across daylight-saving changes.

## Feature flags without implementations

The Haiku morning brief and webhook alert flags are placeholders only. Enabling them currently
does nothing. There is no paper-trade backtester yet.

## Roadmap
- Parse official House Clerk / Senate eFD filings directly instead of relying on a normalizing API.
- Backtester to validate whether the scoring weights are actually predictive.

Recharts 2 was unused and has been removed. See `docs/RECHARTS_3.md` for the adoption plan if a
chart is added later.
