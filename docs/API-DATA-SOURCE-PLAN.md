# API / Data Source Plan

Verified against actual code (`docs/AUDIT-VERIFICATION-RESULTS.md` §14), not aspirational —
this supersedes anything in the merged audit prompt that assumed a provider was wired in without
checking. All entries below are as of this pass (2026-08-20); provider terms and free-tier
limits drift, so re-verify before relying on any of them, per this repo's own standing caveat
in `TODO.md`.

## Providers actually wired into `pipeline/` today

| Provider | File(s) | Used for |
|---|---|---|
| yfinance (Yahoo, unofficial wrapper) | `pipeline/providers.py` (`YahooAdapter`), `fetch_prices.py`, `yahoo_estimates.py`, `yahoo_news.py`, `fetch_advisor.py` | Primary price history/adjusted close, live quotes, statement fallback, analyst estimates/revisions, per-symbol news |
| Alpha Vantage | `pipeline/alpha_vantage.py` | Statement-level fundamentals enrichment, small symbol subset per refresh (hard-capped at 5/refresh, `fetch_advisor.py:1530`; also rate-limited 5/min, `cache.py:34`) |
| Marketaux | `pipeline/marketaux.py` | News sentiment, entity-matched articles |
| FRED | `pipeline/fred.py` | Macro-regime factor scores; terms/attribution embedded and published (`fred.py:15-16,191-193`) |
| SEC EDGAR | `pipeline/sec_edgar.py`, `edgar_facts.py`, `edgar_filing_signals.py`, `edgar_sue.py`, `edgar_enrichment.py`, `xbrl_dimensions.py` | Form 4 insider transactions, 13F institutional filings, XBRL company-facts fundamentals fallback (subordinate to Yahoo, fills gaps only) |
| OpenFIGI | `pipeline/openfigi_client.py` | CUSIP→ticker resolution for 13F rows; redistribution restriction documented in-file |
| Marketstack | `pipeline/marketstack.py`, `collect_marketstack.py`, `resort_marketstack_screens.py` | Batched EOD/intraday price snapshots |
| Financial Modeling Prep, Senate eFD, a House-mirror dataset | `pipeline/congress_trades.py` | Congressional STOCK Act disclosures |
| Kenneth R. French Data Library | `pipeline/fetch_factors.py` | Factor regression inputs (market/size/value/profitability/investment/momentum + risk-free), monthly |

## Providers named in the merged audit prompt but NOT wired in

Tiingo, Twelve Data, Polygon/Massive, BLS, U.S. Treasury, BEA, CFTC, GDELT, FINRA. "Polygon"
appears only as an unused rate-limit config key (`cache.py`'s `DEFAULT_RATE_LIMITS`) with no
client file behind it — treat as an unimplemented placeholder, not a wired provider.

## Corrections to specific numeric claims

- **Universe size**: static config is 910 stocks + 126 ETFs (`pipeline/config/advisor_universe.json`,
  `universe.json`), matching `TODO.md`'s already-documented "343→910, 40→126" expansion. The
  "926 configured / 40 published" figure from the merged audit prompt is a **live run-artifact**
  number (`public/data/advisor.json`), not the static config: 926 = 910 config names + up to 21
  portfolio-holding symbols, deduped; 40 = the leaderboard's `publish_limit`. Conflating
  "published on the leaderboard" with "enriched" understates real coverage — the same snapshot
  shows `statement_enriched_count: 148` (~16%) and `polled_count: 272` (~29%), and even those
  reflect one intraday "fast" refresh scope, not the daily full sweep.
- **Alpha Vantage cap**: "25 requests/day" is real (Alpha Vantage's current published free-tier
  limit) but exists only as descriptive commentary in this codebase (`providers.py:20-21`,
  `cache.py:6-7`, root `PRODUCT.md:37`), never enforced by code. What **is** hardcoded is a
  5-symbols-per-refresh cap (`fetch_advisor.py:1530`, clamped regardless of env override) and a
  5-request/minute rate limiter (`cache.py:34`) — a different mechanism achieving a similar
  practical effect.
- **Tiered A/B/C/D refresh scheduler**: not built under that name or that structure anywhere.
  The real scheduler is two scopes, not four tiers: one daily full sweep (~910 names, 07:00 ET)
  plus two intraday "fast" refreshes (prior top-100 + portfolio holdings + a rotation slice)
  (`.github/workflows/refresh-advisor.yml`, `fetch_advisor.py:1559-1567`), plus an on-demand
  `focus_symbols` mode for ad hoc re-ranking.

## Recommended stack (unchanged from the merged prompt's proposal — proposal only, T3/T4)

The merged audit prompt's recommended source stack (Massive for EOD prices, SEC EDGAR as
accession-level fundamentals spine, an independent corporate-action ledger cross-checked against
SEC filings, OpenFIGI+CIK for identifiers, FRED vintage/realtime parameters for backtest-safe
macro, FINRA for short interest, SEC for 13F/Form 4, issuer data + SEC N-PORT for ETF holdings)
remains a reasonable target and is **not contradicted by anything found in this pass** — it was
simply never checked against code before being proposed, and this pass confirms none of it is
built yet except the pieces already listed above (SEC EDGAR for Form 4/13F/XBRL fallback,
OpenFIGI, FRED). Implementing any of it beyond what already exists is T3/T4 work requiring
sign-off per the audit's own authorization tiers — this document records the target, not a plan
to build it autonomously.

## Data-license matrix — confirmed absent, not built this session

No centralized license/terms-of-use tracking table exists (`docs/AUDIT-VERIFICATION-RESULTS.md`
§14.4). Per-provider notes exist scattered in code (FRED's `TERMS_URL`/attribution string,
SEC's user-agent requirement, OpenFIGI's redistribution restriction) but are not consolidated.
Before monetizing or exposing ValueSignal beyond personal use, build the matrix the merged prompt
specifies (provider / dataset / endpoint / commercial-use allowed / display allowed /
redistribution allowed / derived-values allowed / attribution required / retention allowed /
current contract version) — flagged as T4, not started.
