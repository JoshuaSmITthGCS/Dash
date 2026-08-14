# ValueSignal — fundamentals-first investment research

ValueSignal is a static React research dashboard backed by a Python data pipeline. It ranks a
configurable ~900-company equity universe using company fundamentals first, then adds price behavior,
market context, news sentiment, and corporate-insider activity. Congressional trading is not an
input to the advisor score.

> General research only—not individualized financial advice. A high score is a prompt for deeper
> research, not a buy order or return forecast.

## Scoring model

Weights follow the strength of the published evidence for each signal, not the convenience of the
data. They live in `pipeline/config/settings.json`, so changing the model is a config edit.

The overall research score is:

- **78% fundamentals**
- **18% market behavior**: 12-1 momentum (twelve-month return skipping the most recent month, to
  avoid the short-term reversal that runs against it), Sortino and Sharpe ratios on the stock's own
  returns, 20-day relative strength versus SPY, one-year maximum drawdown, volume confirmation, and
  a low-beta reward. This uses the same `risk_metrics` functions as the ETF model, so a Sharpe means
  the same thing on both screens.
- **4% company news sentiment**, aggregated over seven days. Headline sentiment largely mean-reverts
  within days, so it is a tilt rather than a component.

### Acceleration versus the market

Momentum asks whether a stock has been beating the market. `relative_acceleration`
(`pipeline/risk_metrics.py`) asks the second-derivative question: whether it is beating the market
by *more than it recently was*. It is the cumulative beta-adjusted excess return over the last 63
sessions minus the same over the 63 before that, divided by its own standard error, with the most
recent week skipped because that is where short-term reversal lives.

Two construction choices carry the whole measure:

- **Beta-adjusting is what makes it market-relative.** A raw stock-minus-index difference subtracts
  the same number from every row on a given day, and subtracting a constant cannot change a
  cross-sectional ranking — that is why the older `relative_strength_20d` measured +1.00 Spearman
  against `return_20d` across 877 rows and no longer carries weight. Scaling the market leg by each
  name's own beta means a high-beta stock that only rose because the index rose does not read as
  accelerating.
- **Dividing by its own tracking noise** puts a quiet utility and a volatile biotech on one scale.
  The published reading is a t-statistic, so `+1.0` is a pickup one standard error larger than that
  stock's ordinary wobble, not one percent.

It is computed for every scored name, published on `technical_detail`, and shown on the company
detail view — but it has **no entry in `market_behavior.weights` and contributes nothing to the
score**. Weighting a second market-relative term on a plausible mechanism alone is the mistake the
first one made; it stays a measurement until the validation harness has prospective evidence for it.
Horizons are config (`market_behavior.relative_acceleration`). Basis: Gettleman & Marks (2006) on
acceleration, Blitz, Huij & Martens (2011) on residual construction.

The fundamental score:

- **28% valuation**: EV/EBITDA and EV/EBIT lead — the enterprise multiple is the best-validated
  single value measure available. Plus EV/FCF, EV/Sales (falling back to P/S), sector-aware forward
  P/E, and trimmed book multiples. PEG is a minor sanity check; it ignores the time value of money,
  risk, and cost of capital. Price-to-tangible-book is scored only in the sectors it describes.
- **26% profitability and cash**: ROIC, gross profits-to-assets, FCF yield, margin, cash conversion.
- **15% financial health**: interest coverage, net debt/EBITDA, debt/equity, current ratio, and an
  Altman Z computed with the variant fitted for the filer's sector — suppressed entirely for
  financials.
- **11% growth**: revenue, earnings, three-year FCF growth, operating-margin direction, and earnings
  surprise against expectations.
- **10% capital allocation**: net buyback yield, stock comp, capex/depreciation, total asset growth.
- **10% accounting quality**: Piotroski F-score leads; the accruals ratio is retained at a small
  weight because its predictive power has largely decayed in US data since the early 2000s.

Metrics are reweighted only within their category when unavailable, then missing coverage reduces
the final confidence. Metrics that do not apply to a sector leave the coverage denominator rather
than counting as missing evidence. Suspiciously low P/E values receive a possible value-trap penalty.

Bounded post-blend modifiers refine the score without replacing it: sector-relative valuation (±3),
short interest (up to −6), insider activity (+5/−3), liquidity (−3), analyst expectations (±3), and
macro regime (±3), with a hard ±15 combined cap.

### Insider activity

SEC Form 4 open-market trades are split into **routine** (same calendar month across years — a
schedule, and historically uninformative) and **opportunistic**. Only opportunistic activity scores.
Clusters of independent buyers count for more than one large buyer, buys count for more than sells,
and the signal decays over one to three months.

### Theme exposure

`pipeline/themes/*.yaml` declares structural trends; adding one is a config file, not a code change.
Exposure is measured from segment revenue, the trend in how a company describes itself in its own
filings, disclosed customer ties to confirmed spenders, and the capex of the companies doing the
spending. Two guardrails are enforced in code and re-checked by `validate_data.py`: **price momentum
contributes exactly zero**, and names already in the top valuation decile of their sector are flagged
rather than promoted. The result is published as an independent screen and never folded into the
research score — blending a forward-looking thematic bet into the fundamentals score would make that
score impossible to interpret.

### ETFs

The ~125-fund ETF watchlist is scored separately on performance, risk, total cost of ownership, liquidity, and structure.
Percentiles are computed **within peer groups** (broad equity, sector, thematic, fixed income,
commodity, crypto), never across the whole batch — ranking a bond fund's Sharpe against an equity
fund's measures batch composition, not fund quality. Cost includes tracking difference against the
fund's index proxy and NAV premium/discount, not just the expense ratio; where a fund declares a
Rule 6c-11 disclosure endpoint in `universe.json`, the mandated median 30-day bid-ask spread is used
instead of an estimate.

### Validating a change

`pipeline/evaluation.py` measures whether a score predicts forward returns cross-sectionally — rank
information coefficient and ICIR, quantile spread and monotonicity — rather than reading one equity
curve. Results are deflated for the number of configurations tried (deflated Sharpe ratio) and the
probability of backtest overfitting is estimated by combinatorially-symmetric cross-validation. A
change ships only if it improves out-of-sample IC *after* deflation.

`pipeline/pit_store.py` appends a timestamped observation of every tracked metric on each run, with
restatements kept in a separate revision log, plus a point-in-time universe membership record that
includes departed names. Neither can be reconstructed retroactively — the providers only ever serve
today's restated numbers for today's survivors — so the store starts accumulating before any
backtest needs it. Its contents are committed, because scheduled runs happen on ephemeral runners.

Published factor premia are historical, in-sample estimates. They indicate which signals have
mattered; they are not forecasts.

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
# Put the real ALPHA_VANTAGE_API_KEY, MARKETAUX_API_TOKEN, and FRED_API_KEY in .env.local.
# This file is ignored by Git.
python pipeline/fetch_news.py
python pipeline/fetch_advisor.py
python pipeline/build_etf_comparisons.py
python pipeline/validate_data.py

npm ci
npm test
npm run build
npm run dev
```

`pipeline/config/advisor_universe.json` defines the ~900-stock candidate universe and the
pipeline publishes its top 40. Breadth is deliberate: a signal's information ratio scales
with the square root of the number of independent bets, so a wider cross-section tightens
every rank-IC estimate. Alpha Vantage enrichment is capped at five symbols regardless of
universe size, so growing the list spends only free Yahoo requests. `ADVISOR_SYMBOLS` can override it without imposing an application
hard cap. To respect the free plan, `ALPHA_ENRICH_LIMIT` caps Alpha Vantage company and insider
enrichment at five. Marketaux supplies entity-level news sentiment for that shortlist and the
market-pulse feed. FRED supplies a six-series macro regime that is reduced to a sector-sensitive
±3-point modifier; raw FRED observations are not published or cached. Yahoo Finance supplies the
full-universe fundamentals and history. The committed `advisor.json`
contains derived public data only; it never contains the API key.

## Deployment

The app lives at the repository root. Netlify should leave its base directory empty; root
`netlify.toml` builds with `npm run build` and publishes `dist`.

For scheduled refreshes, add `ALPHA_VANTAGE_API_KEY`, `MARKETAUX_API_TOKEN`, `FRED_API_KEY`, and
`SEC_USER_AGENT` under GitHub repository **Settings → Secrets and variables → Actions**.
`SEC_USER_AGENT` must be a real application and contact string (for example
`ValueSignal research admin@example.com`); SEC fair-access policy requires it, and without it the
Form 4 insider layer and the theme-exposure screen both report themselves unavailable rather than
spoofing a client. `refresh-advisor.yml` fetches news and research, scores, validates, and commits
data in one job. It has explicit `contents: write`, shared push concurrency, and three push retries.

The workflow refreshes shortly after 07:00, 12:00, and 15:00 Eastern on weekdays. It gates paired UTC cron
times against `America/New_York`, so daylight-saving changes do not shift the local schedule.
Only the morning run spends Alpha Vantage quota; the later runs refresh the other providers.

### Manual data refresh

Authenticated users can start a fast data-only refresh from the Overview page. It refreshes the
prior top 100 plus submitted portfolio/watchlist symbols and carries the rest forward from the
morning full sweep. Configure these
server-only environment variables in Netlify:

- `GITHUB_REFRESH_TOKEN`: fine-grained token with Actions read/write access to this repository
- `REFRESH_GITHUB_REPOSITORY`: repository in `owner/name` form
- `REFRESH_ALLOWED_EMAILS`: comma-separated Firebase account emails allowed to start a run
- `FIREBASE_SERVICE_ACCOUNT_JSON`: complete Firebase service-account JSON

The browser sends a Firebase ID token to the Netlify function. The GitHub token and service-account
credential remain server-side. The function refuses duplicate runs and always dispatches
`data-only`; Alpha Vantage can only be selected from the GitHub Actions manual form.

Netlify also runs `portfolio-price-snapshots` every five minutes. During the regular U.S. market
session it reads only saved portfolio positions, requests their current prices, and writes a
complete account-value point to each user's private `intradaySnapshots` collection. It runs on the
published production deploy even when no browser is open and uses the same server-only
`FIREBASE_SERVICE_ACCOUNT_JSON` credential. A portfolio is skipped rather than storing a misleading
partial value when any holding is unpriced.
The chart keeps those raw points for its Today view, derives one average per trading day for Week
and Month, then rolls daily averages into weekly points for 3 Months and monthly points for Year.

See [Configure manual refresh on Netlify](docs/MANUAL_REFRESH_SETUP.md) for step-by-step instructions
to create each value, add the variables safely, verify the live function, and troubleshoot errors.

## Quality controls

```bash
PYTHONPATH=pipeline python -m pytest pipeline/tests -q
python pipeline/validate_data.py
npm run lint
npm test
npm run build
```

The UI exposes provider health and marks research stale after 36 hours. CI runs Python tests, JSON
contract validation, React tests, linting, and a production build on every push.
