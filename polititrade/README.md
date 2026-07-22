# PolitiTrade — Signal Terminal

Personal financial-intelligence dashboard. Tracks congressional trades + executive/policy
catalysts, layers a valuation screen (P/S, Forward P/E, PEG), and ranks everything into a
daily watchlist and three research buckets (short-term / long-term / retirement-broad).

**Runs at ~$0/month.** No server, no database, no paid APIs. GitHub Actions runs Python on a
schedule → writes JSON into `site/public/data/` → commits → Netlify redeploys → the static
React site reads local JSON.

> Informational only. Not financial advice. STOCK Act disclosures lag trades 30–45 days, so
> nothing here front-runs anyone. The edge is pattern detection. Output labels are research
> tiers (HIGH CONVICTION / WATCH / NEUTRAL / COOLING), never "buy."

## Quick start

### Pipeline (Python)
```bash
cd pipeline
pip install -r requirements.txt

# Live run (needs open network — works on GitHub Actions / your machine):
python fetch_congress.py      # -> trades.json
python fetch_prices.py        # -> prices.json (+ valuation metrics) + politicians.json
python fetch_news.py          # -> news.json
python scorer.py              # -> signals.json
python rank_picks.py          # -> picks.json + prints the ranked buckets

# Offline demo (no network — fills every JSON with realistic mock data):
python seed_mock_data.py && python scorer.py && python rank_picks.py
```

### Site (React + Vite)
```bash
cd site
npm install
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

## Deploy
1. Push this repo to GitHub.
2. Netlify → New site → pick the repo (`netlify.toml` is preconfigured: base `site`, publish `dist`).
3. Actions tab → enable workflows. They commit fresh JSON on schedule and Netlify auto-redeploys.

## Optional (feature-flagged in settings.json)
- Daily Haiku morning brief (~$0.30/mo)
- Webhook alert when a signal scores 80+
- Paper-trade backtester (build before ever acting on signals)

## Roadmap
- Phase 3 stretch: parse official House Clerk / Senate eFD PDFs as ground truth.
- Backtester to validate whether the scoring weights are actually predictive.
