# ValueSignal — fundamentals-first investment research

ValueSignal is a static React research dashboard backed by a Python data pipeline. It ranks a
configurable 120-company equity universe using company fundamentals first, then adds price behavior,
market context, news sentiment, and corporate-insider activity. Congressional trading is not an
input to the advisor score.

> General research only—not individualized financial advice. A high score is a prompt for deeper
> research, not a buy order or return forecast.

## Scoring model

The overall research score is:

- 75% fundamentals
- 15% market behavior: trend, volatility, drawdown, and 20-day relative strength versus SPY
- 10% company news sentiment

The fundamental score implements this framework:

- 40% valuation: PEG, sector-aware forward P/E, sector-aware P/S, and P/B
- 25% profitability and cash: ROE, free-cash-flow yield, and profit margin
- 20% financial health: debt-to-equity and current ratio
- 15% growth: year-over-year revenue and earnings growth

Metrics are reweighted only within their category when unavailable, then missing coverage reduces
the final confidence. Suspiciously low P/E values receive a possible value-trap penalty. Banks do
not use industrial-company leverage cutoffs. PEG is taken from a provider-consistent calculation
rather than combining trailing and forward periods.

## Data sources

One scheduled refresh uses the Alpha Vantage free allowance deliberately (up to 25 calls): company overview,
100-day daily history, company news sentiment, corporate-insider transactions, SPY history, global
market status, 10-year Treasury yield, federal-funds rate, and inflation. Yahoo Finance fills deeper
fundamental fields that are absent from the overview response. Raw provider responses are cached
locally and never published.

The direct major-index endpoints in the supplied documentation are premium-only. SPY serves as the
free benchmark instead. Alpha Vantage documents the free key as limited to 25 calls per day and one
request per second; the client centrally enforces 1.1 seconds between uncached requests.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r pipeline/requirements.txt
cp .env.example .env.local
# Put the real ALPHA_VANTAGE_API_KEY in .env.local; this file is ignored by Git.
python pipeline/fetch_advisor.py
python pipeline/validate_data.py

npm ci
npm test
npm run build
npm run dev
```

`pipeline/config/advisor_universe.json` defines the default 120-stock candidate universe and the
pipeline publishes its top 20. `ADVISOR_SYMBOLS` can override it without imposing an application
hard cap. To respect the free plan, `ALPHA_ENRICH_LIMIT` caps Alpha Vantage company/news/insider enrichment at five;
Yahoo Finance supplies the full-universe fundamentals and history. The committed `advisor.json`
contains derived public data only; it never contains the API key.

## Deployment

The app lives at the repository root. Netlify should leave its base directory empty; root
`netlify.toml` builds with `npm run build` and publishes `dist`.

For scheduled refreshes, add `ALPHA_VANTAGE_API_KEY` under GitHub repository
**Settings → Secrets and variables → Actions**. `refresh-advisor.yml` fetches, scores, validates,
and commits data in one job. It has explicit `contents: write`, shared push concurrency, and three
push retries.

The weekday cron is fixed at 11:00 UTC. That is 07:00 Eastern during daylight time and 06:00
Eastern during standard time; GitHub cron does not automatically follow daylight-saving changes.

## Quality controls

```bash
python -m unittest discover -s pipeline/tests -v
python pipeline/validate_data.py
npm run lint
npm test
npm run build
```

The UI exposes provider health and marks research stale after 36 hours. CI runs Python tests, JSON
contract validation, React tests, linting, and a production build on every push.
