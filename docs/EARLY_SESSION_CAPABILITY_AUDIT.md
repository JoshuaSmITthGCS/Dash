# Early-session capability audit

Audited against the repository on 2026-08-03. The outcome is intentionally conservative:
both live early-session screens are killed until the collection layer supplies the required
point-in-time market data.

| Capability | Available | Provider | Granularity | Freshness | Verdict |
|---|---:|---|---|---|---|
| Premarket / after-hours OHLCV | No | None | Daily regular-session history only | Not collected | Kill premarket screen |
| First-hour bars | No | None | Daily | Not collected or retained | Kill first-hour screen |
| Stock bid/ask, spread, quote timestamp, halt flags | No | None | Current price snapshot only | Fetch time, not exchange time | No execution-quality score |
| Earnings and mapped, timestamped news | Conditional | Marketaux + PIT earnings events | Event/article | News cache up to 4 hours | Context only when timestamp and primary ticker are present |
| Sector/industry and SPY context | Yes | Yahoo Finance | Classification + daily prices | Pipeline refresh cadence | Daily context only |
| Support-zone engine / structural score | Partial | Internal | Daily | Pipeline refresh cadence | Structural score exists; support zones do not |
| Shadow-trade store / PIT snapshots | Partial | Internal | Per refresh | Append-only | PIT fundamentals exist; intraday shadow ledger does not |

Evidence lives in `pipeline/fetch_advisor.py`, `pipeline/providers.py`,
`pipeline/marketaux.py`, `pipeline/estimate_snapshots.py`, and `pipeline/pit_store.py`.
ETF spread disclosure is deliberately not treated as common-stock quote coverage.

The published gate artifact is `public/data/screens/early-session.json`. Daily closes,
cached snapshots, and heuristic RSS mappings must not be substituted for missing
extended-hours or first-hour observations.
