# Changelog — Quant Upgrade

Branch `claude/valuesignal-quant-upgrade-1ngvp5`. This is the authoritative record of what
changed in this upgrade; other docs that reference "current status" point here.

## What prompted this

Two live complaints: confidence sitting at 0.39-0.48 across every published stock, and
visible rank churn between refreshes. Plus two feature requests: explain why the portfolio
moved on refresh, and a watchlist wishlist button with dip/good-buy price targets. Full scope
tracked against a 23-section quant-research upgrade brief.

## Phase 0 — Baseline

Recorded pre-upgrade test/lint/build output and the champion config hash
(`docs/BASELINE-2026-08-06.md`). Root-caused both live complaints to one bug (see Phase 1).

## Phase 1 — Fixed the enrichment failure

`yahoo_extended()` fetched Yahoo's statement frames and `.info` inside one shared
try/except; a broken `.info` call discarded already-fetched statement data, collapsing
`statement_enriched_count` to 0 and fundamental coverage to 0.21-0.35. Decoupled the two
calls so a company still enriches on statement-only metrics when `.info` fails. Added
diagnostics (`enrichment_diagnostics`) and a hard `validate_data.py` gate so a repeat can't
ship silently. Pinned `yfinance` to a tested version.

## Phase 2 — Confidence breakdown

`pipeline/confidence.py`: publishes completeness/freshness/source_reliability/peer_sample/
model_agreement components alongside the existing confidence scalar (unchanged), plus the
unshrunk `raw_score` that was previously computed but discarded before publication.

## Phase 3 — Rank-turnover diagnostics

`pipeline/stability_report.py`, run against the real committed PIT store: confirmed the
Phase 1 bug was the dominant churn cause (10-60x turnover/availability-change spike exactly
at the broken run). Wired into `refresh-advisor.yml` so a repeat is visible immediately.

## Phase 4 — ETF/stock separation

`Picks.jsx` sorted stocks (fundamentals-scored) and ETFs (separately-scored fund model)
in one mixed pool. Split into independent pools with independent sorting and bucket
allocation; `researchScreens.js`'s stock-only screens now defensively exclude ETF rows.

## Phase 5 — Research contract, feature registry, sleeve interface

`pipeline/config/research_contract.json` / `docs/RESEARCH-CONTRACT.md`: centralizes universe/
target/execution-assumption thresholds already scattered across the codebase, and states
plainly where the contract and the code disagree (trading-day vs calendar-day horizons; no
sector-residual target implemented yet). `pipeline/config/feature_registry.json` (generated
by `build_feature_registry.py`, 58 features): usage classification derived from existing
config, not hand-maintained. `pipeline/sleeves/`: the sleeve result interface plus one worked
example (`value.py`).

## Phase 6 — Sleeves, technical indicators, emerging-growth screen

Added `quality.py` and `growth.py` sleeves. Added a bounded 4-indicator technical family
(`technical_indicators.py`: moving-average slope, RSI, Bollinger %B, OBV slope) weighted at
~1% of the total composite score — declined the broader indicator zoo as mostly
data-snooping evidence, per direct instruction to keep it well below fundamentals. Renamed
`rankFastGrowth` to `rankBreakoutInProgress` (it detects a move already underway) and added
`rankEmergingGrowth`, explicitly labeled `prospective_unvalidated`, built only from
measurables this codebase can honestly compute.

## Phase 7 — Costs, screen presets, portfolio construction

`pipeline/costs.py`: liquidity-tiered, scenario-based transaction cost model (not yet wired
into the IC harness, which still uses a flat rate). `pipeline/config/screen_presets.json`:
all 16 presets from the brief, 7 wired to a real implementation, 9 honestly marked
specification-only. `shrinkCovarianceMatrix()`: covariance shrinkage utility; only 1 of the
brief's 6 portfolio-construction methods exists (score-weighted).

## Phase 8 — Portfolio move explanation

`src/lib/portfolioAttribution.js`: splits each holding's daily return into a market
component (beta × benchmark return) and a stock-specific component, reconciling exactly to
the total by construction. Rendered on `/portfolio` after every refresh. No sector-index
attribution (not fetched anywhere in this pipeline) and no catalyst/news attribution
(needs the event classification this phase did not build) — both stated explicitly rather
than approximated.

## Phase 9 — Watchlist with price targets

Migrated the watchlist from localStorage to Firestore (`useWatchlist.js`, matching
`useFirebasePortfolio.js`'s pattern). Added dip-buy and good-buy price target suggestions
(`watchlistPriceTargets.js`), both explicit bounded heuristics with a stated derivation, not
predictions. Added a watchlist star toggle to the research library and stock detail modal.
Wired an optional one-click price-cross alert through the existing alert infrastructure.

## Phase 10 — Docs, security, cleanup

`docs/DEPLOYMENT.md`, `docs/SECURITY.md`: consolidated authoritative runbooks. Fixed
`ci.yml`'s unnecessary `contents: write`. Marked 11 contradictory/stale root-level status and
report docs as superseded rather than deleting them. Moved a misplaced Claude Code skill file
out of the repo root into `.claude/skills/`.

## Phase 11 — Final verification, and a second bug-fix round

Full verification run recorded in `docs/FINAL-VERIFICATION-REPORT.md` (625 Python tests,
337/337 JS tests, clean lint, clean build, `validate_data.py` and the IC harness both run
against real published data). Also found: PR #41 merged this branch one commit before the
actual watchlist/search silent-failure fixes landed, so those fixes never reached `main`.
Rebased them forward and added a second round: a watchlist star on every search result (not
just rows with published research), Watchlist added to the mobile bottom nav (it had no
mobile entry point at all), and a mobile-reachable link to the existing widget-reorder panel
(it existed already but its only entry point sits in a header region CSS hides below 620px).

## What did not change

The champion scoring model, its weights, and every published number's formula are unchanged
except the two additive fields (confidence components, raw_score) and the new 0.06-weighted
`technical_extended` factor inside `market_behavior`. No promotion occurred — see
`docs/RESEARCH-CONTRACT.md`'s governance section. Every new sleeve, screen, and challenger
ships `research_only` / `specification_only` where it isn't a direct wrap of existing,
already-production code.
