# A3 — Enrichment Selection Bias

## The defect

`fetch_advisor.py::select_enrichment_priority` (line ~820) seeds the statement-enrichment
queue with the previous refresh's top 20 published names (`INCUMBENT_ENRICH_LIMIT = 20`) and
admits only 5 new challengers (`CHALLENGER_ENRICH_LIMIT = 5`). Statement-derived metrics —
EV/EBITDA, ROIC, interest coverage, Piotroski F, everything that feeds the
`capital_allocation` and `accounting_quality` fundamental categories — exist only for names a
weaker prior model already liked. A name that never cracked the top 20-25 can never earn the
categories that make up roughly a third of the fundamentals score, regardless of how strong
its actual statements are.

## What was fixed (code)

`FULL_UNIVERSE_RESEARCH=true` (new env var, default off) makes
`select_enrichment_priority` ignore `previous_top` entirely and enriches every preliminary
candidate — see `pipeline/fetch_advisor.py`. Two tests in
`pipeline/tests/test_fetch_advisor.py` lock this down:

- `test_full_universe_research_cannot_let_previous_rank_leak_in` — a populated
  `previous_top` (including a name that was never in the preliminary set at all) produces a
  byte-identical priority ordering to an empty `previous_top`.
- `test_full_universe_research_lifts_the_challenger_cap` — every preliminary candidate
  becomes a challenger, not just 5.

This is **not** the default production path — one full-universe statement sweep is far more
Yahoo requests per refresh than the standard incumbent+5 shortlist, and is meant for a
dedicated research run, potentially spread across the GitHub Actions time budget over
multiple invocations (the existing per-provider `cache.py` layer already avoids re-fetching a
symbol enriched in an earlier run within the same day).

## What was measured (offline, from the committed universe)

`pipeline/enrichment_bias.py` → `pipeline/reports/enrichment_bias.json`, computed entirely
from `public/data/advisor.json` as committed — no network calls. Run it with
`python pipeline/enrichment_bias.py`.

### Coverage by category

| Category | `research` (40) | `screen_universe` (374) |
|---|---|---|
| `capital_allocation` | 40 / 40 | **84 / 374** |
| `accounting_quality` | 40 / 40 | **84 / 374** |
| `financial_health` | 39 / 40 | 335 / 374 |
| `growth` | 40 / 40 | 372 / 374 |
| `valuation` | 40 / 40 | 372 / 374 |
| `profitability` | 40 / 40 | 372 / 374 |

`growth`/`valuation`/`profitability`/`financial_health` come from the cheap first pass every
candidate gets. `capital_allocation` and `accounting_quality` require the statement fetch —
and only 84 of 374 screen-universe names (the ones that were once incumbents or challengers)
have ever cleared that bar. The other 290 are structurally locked out under the current
selection rule, no matter how they'd actually score if enriched.

### Enriched vs. non-enriched population (124 vs. 290 names)

| | n | mean score | median score | stdev |
|---|---|---|---|---|
| Enriched (`capital_allocation` + `accounting_quality` populated) | 124 | 66.31 | 66.80 | 8.94 |
| Non-enriched | 290 | 41.77 | 43.15 | 6.30 |

A ~24.5-point gap. **This is not, by itself, evidence that enrichment causes higher scores.**
`select_enrichment_priority` chooses its enrichment targets partly from the same preliminary
fundamentals score being compared here — a name has to look decent on the cheap pass to earn
a statement fetch in the first place. Part of the gap is selection-on-the-outcome. Separating
"enrichment reveals real quality" from "enrichment targets were pre-selected for quality"
requires scoring the full universe on equal footing, which is the blocked comparison below.

Sector distribution shifts in the enriched population toward Technology and Financial
Services and away from Industrials — consistent with, but not proof of, a selection effect
rather than a sector-driven one.

Market-cap comparison is marked `not_measurable`: `market_cap` is populated only on the 40
published research rows in this dataset. The screen universe — where the entire
non-enriched population lives — does not carry it at all, so any enriched-vs-non-enriched
market-cap comparison from committed data would mean fabricating the missing side.

## What remains blocked

| Measure | Status | Resolver |
|---|---|---|
| Full-universe top-40 overlap vs. production top-40 | `blocked_network_policy` | `FULL_UNIVERSE_RESEARCH=true python pipeline/fetch_advisor.py` |
| Spearman rank correlation, full-universe-enriched vs. production score | `blocked_network_policy` | same |
| Forward-return delta of full-universe-only discoveries | `blocked_network_policy` | same, plus 63 sessions of subsequent price history |

Registered in `pipeline/reports/experiment_registry.json` as `pending_data` with this exact
reproduction command — see `docs/ALGORITHM-RESEARCH-RESULTS.md`.
