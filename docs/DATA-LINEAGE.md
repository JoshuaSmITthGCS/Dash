# Data Lineage

## Providers

| Provider | What | Key requirement | Status |
|---|---|---|---|
| Yahoo Finance (`yfinance`) | Price/quote/statements | none | Primary; restated only, no as-reported history |
| Alpha Vantage | Overview, earnings, macro | `ALPHA_VANTAGE_API_KEY` | Max 5 symbols/refresh (quota) |
| Marketaux | Entity-level news sentiment | `MARKETAUX_API_TOKEN` | Optional |
| FRED | Macro regime (6 series) | `FRED_API_KEY` | Optional |
| SEC EDGAR | Form 4 insider, theme signals | `SEC_USER_AGENT` | Free, needs fair-access header |
| Financial Modeling Prep | Congressional STOCK Act disclosures (needs a plan covering the Congressional endpoints; answers HTTP 402 otherwise) | (see `congress_trades.py`) | Weekly |
| House/Senate stock-watcher datasets | Congressional STOCK Act disclosures, keyless mirror of the same Clerk and eFD filings | (see `congress_trades.py`) | Weekly |

## Point-in-time stores

Three separate append-only stores — see `pipeline/pit_store.py` module docstring for the raw
one; do not conflate the three, they have different schemas and purposes:

1. **Raw fundamentals PIT** (`pipeline/data/pit/observations.jsonl`, `revisions.jsonl`,
   `universe.jsonl`) — every observed value, its source, and its observation timestamp; a
   restatement log; a universe-membership log (added/removed per observation, survivorship
   defense). `as_of()` never returns a value observed after a given cutoff.
2. **Scored validation PIT** (`pipeline/pit_store/YYYY-MM-DD.jsonl`) — one immutable row per
   (refresh, ticker), champion + challenger scores, `config_hash`, realized forward returns
   once the horizon elapses. This is what `pipeline/stability_report.py` and
   `pipeline/validation/ic_harness.py` read.
3. **Shadow portfolios** (`pipeline/shadow_store/{strategy}/YYYY-MM-DD-<sha12>.json`) —
   content-addressed, refuses a duplicate snapshot for the same strategy/date.

All three are deliberately committed to the repository (not gitignored): the CI/scheduled
runner is ephemeral, and providers only ever serve today's restated numbers — history only
exists if each run appends to it and the result is pushed.

## Timestamps carried on every observation (where the raw PIT store applies)

`observed_at` (full ISO timestamp), `observation_date`, `source`, plus (on scored rows)
`recorded_at`, `data_as_of`, `model_version`, `config_hash`, `universe_membership`,
`published_research` (bool), `quality_flags`.

## Availability lag

Statement-derived metrics: typically 1-3 months after fiscal period end (provider-restated,
not as-filed). Price/quote: same session. Congressional disclosures: STOCK Act allows up to
45 days between transaction and disclosure — `docs/SCREEN-PRESETS.md`'s Congressional
Disclosure Activity preset ranks on disclosure date, not transaction date, for exactly this
reason.

## Corporate actions

Handled entirely at the provider layer (Yahoo-adjusted price series). No independent
corporate-action event log exists in this pipeline.
