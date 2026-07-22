# PolitiTrade — Signal Terminal

Personal financial-intelligence dashboard. Tracks congressional trades + executive/policy
catalysts, layers a valuation screen (P/S, Forward P/E, PEG), and ranks everything into a
daily watchlist and three research buckets (short-term / long-term / retirement-broad).

**Runs at ~$0/month.** No server or paid database. The static React site reads versioned JSON
from `public/data/` and Netlify builds directly from the repository root.

> Informational only. Not financial advice. STOCK Act disclosures lag trades 30–45 days, so
> nothing here front-runs anyone. The edge is pattern detection. Output labels are research
> tiers (HIGH CONVICTION / WATCH / NEUTRAL / COOLING), never "buy."

## Quick start

### Pipeline (Python)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r pipeline/requirements.txt

# Offline demo (no network — fills every JSON with realistic mock data):
python pipeline/seed_mock_data.py && python pipeline/scorer.py && python pipeline/rank_picks.py
python pipeline/validate_data.py
```

### Site (React + Vite)
```bash
npm ci
npm run dev      # local preview at localhost:5173
npm run build    # -> dist (Netlify publishes this)
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
- `pipeline/config/settings.json` — weights, valuation bands, bucket blends, feature flags
- `pipeline/config/committees.json` — politician → committee → sector map
- `pipeline/config/policy_map.json` — news keyword → sector → tickers
- `pipeline/config/universe.json` — ETF classification + retirement core holdings

## Data reliability

- Live congressional ingestion is paused while provider access is under review. Actions do not
  call the live adapter and there is no scheduled production refresh.
- Every public payload declares `data_mode`. Demo fixtures display a persistent warning, and
  `validate_data.py --production` rejects them.
- `status.json` exposes source/stage health. The site marks data stale after 36 hours.

## Deploy
1. Netlify → **Add new site → Import an existing project** → choose this repository.
2. Leave the base directory empty. The root `netlify.toml` runs `npm run build`, publishes `dist`,
   and selects Node 22.
3. Deploy. `index.html`, `package.json`, `src/`, and `public/` are all at the repository root, so
   no monorepo or nested-folder settings are required.
4. GitHub Actions CI runs on every push. **Rebuild demo data** is manual only and retains the
   visible demo-data guard.

## Feature flags without implementations

The Haiku morning brief and webhook alert flags are placeholders only. Enabling them currently
does nothing. There is no paper-trade backtester yet.

## Roadmap
- Select and integrate the live congressional data source after provider access is approved.
- Parse official House Clerk / Senate eFD filings directly instead of relying on a normalizing API.
- Backtester to validate whether the scoring weights are actually predictive.

Recharts 2 was unused and has been removed. See `docs/RECHARTS_3.md` for the adoption plan if a
chart is added later.
