# Audit Roadmap

Sequenced plan from `docs/AUDIT-VERIFICATION-RESULTS.md`, produced after that verification pass
settled which of the merged master-audit prompt's claims are real. Per that document's overlap
check, this roadmap sits **behind, not instead of**, the pre-existing `docs/P0-VERDICT.md` work
order — P0's recommendation #1 (fix metric-availability flicker, the dominant driver of 64.9%
monthly turnover) remains the single highest-priority open item in this repository and is not
duplicated or reordered by anything below.

Severity/tier keys: **T1** = copy/label fix, already implemented this session. **T2** = touches
scoring/confidence/champion model — documented + failing test only, no production change without
sign-off. **T3** = new work, moderate scope, proposal only. **T4** = new pipeline/ledger/IA
architecture, multi-week, requires explicit sign-off per the audit's §21 authorization tiers.

---

## P0 — correctness/trust (carried over, unchanged priority)

1. **Fix metric-availability flicker** (`docs/P0-VERDICT.md` recommendation #1) — still the
   top item in this repository. Nothing in this audit pass changes its priority or its blocker
   status. Not re-litigated here.
2. **Reframe the product against RSP/IWM, not just SPY** (`docs/P0-VERDICT.md` recommendation #2)
   — cheap, still open.

## P0 — this audit's contribution (already done this session)

3. ✅ **T1 — alpha t-stat language.** Docs and one dead script said "statistically meaningless"
   below t=2; the live UI already used t>3 and non-"meaningless" language. Fixed the doc/script
   drift to match the live behavior — see `docs/AUDIT-VERIFICATION-RESULTS.md` §4.1.
4. ✅ **T1 — `/hud-demo` gated to dev builds.** Was a live, ungated route serving randomized fake
   data. Now behind `import.meta.env.DEV`, same pattern as this codebase's other dev-only
   affordances.
5. ✅ **T1 — `/market` vs `/markets` naming collision resolved.** `/market` (news feed) renamed to
   `/news` (matches its own nav label and content); `/market` kept as a redirect for existing
   links; `/markets` (live index/sector data) unchanged.
6. ✅ **T1 — "Inside Information" renamed to "Disclosed positioning"** across all user-visible
   text (page title, nav entries, Dashboard card, `StockDetailModal`), confirmed as public
   13F+Congressional data only, no actual nonpublic information. Route path and backing JSON
   filename left unchanged (bigger blast radius than a label fix).
7. ✅ **T1 — `advisor_engine.py`'s technical-weight comment corrected.** Was claiming the six
   non-extended weights sum to 0.94 (they sum to 1.00; the full seven sum to 1.06). Comment now
   states the actual sum and explains why the live renormalization in
   `technical_score_from_parts()` already neutralizes the effect — no weight values changed.

## P0 — this audit's new open findings

8. **T2 — the fundamentals-category confidence multiplier still drives enrichment-priority
   selection, corrected from an earlier overstatement.** A prior pass of this audit claimed the
   `0.65+0.35×coverage` multiplier inside `_band_valuation_score` (`pipeline/scorer.py`) was
   "still live in the champion score," the same way the retired top-level `0.8+0.2×coverage`
   multiplier once was. That was wrong: `build_research()` reads `fundamental_parts["raw_score"]`
   (pre-multiplier) for the champion's `components["fundamentals"]`, never the multiplied value —
   confirmed this session by `test_champion_carries_no_completeness_multiplier` (pre-existing)
   and a new regression test. The multiplier's one real live consumer is
   `fetch_advisor.py::enrich()`'s shortlist-priority sort key, which ranks statement-enrichment
   candidates by the multiplied value before any row is published — a real effect on *which
   names get enriched*, not on the score of an already-published name. Documented and tested
   this session (`pipeline/tests/test_round4_remediation.py::TestFundamentalsCategoryMultiplierScope`);
   an additive `apply_confidence_multiplier` parameter was added to `scorer.py::valuation_score`
   (default preserves all existing behavior) so a future measured comparison of `enrich()`'s sort
   key is a small diff, not a new formula. **Do not change `enrich()`'s sort key without measuring
   its effect on shortlist composition first** — this changes upstream data availability for the
   whole pipeline, the same category of risk as the already-known shortlist-gating bias.
9. ✅ **T1, small — options r=0 Black-Scholes disclosure.** Options screens already disclosed IV/
   spread/OI staleness prominently but not that delta/probability/EV use a zero-risk-free-rate
   Black-Scholes simplification. Added one line next to the existing staleness notice in both
   `src/pages/OptionsScreen.jsx` and `src/pages/StrategyScreen.jsx`.
10. **T3 — effective-weight publishing for the 1.06 technical-weight sum.** The comment fix (item
    7) documents the issue; publishing the *effective* post-renormalization weights next to the
    declared config (so a reader doesn't have to know `short_horizon_treatment: "neutral"` drops
    `relative_strength` and the rest renormalizes) is separate follow-up UI/methodology work.
11. **T1-adjacent — `docs/MODEL-CARD.md` doc drift on the confidence label and a nonexistent
    file.** `MODEL-CARD.md:57` claims the UI labels the completeness metric "Evidence
    confidence"; the live UI uses "Data coverage" and a test explicitly asserts the old phrase
    does *not* appear. `MODEL-CARD.md:49` also cites `pipeline/confidence.py`, which does not
    exist (the real files are `score_calibration.py`/`experiment_registry.py`). Flagged, not
    edited this session — `MODEL-CARD.md` needed a full read before any edit and that was out of
    this pass's scope; a targeted follow-up should fix both lines.

## P1 — analytical edge, portfolio analytics

All items below are detailed with file:line evidence in `docs/METRIC-GAP-MATRIX.md`. Several are
markedly cheaper than the original merged-audit prompt assumed, because the underlying
computation already exists in `src/lib/portfolioAnalytics.js` and is simply not wired into any
page — those are called out as **wiring-only** below.

12. **T3, wiring-only — MWR/XIRR.** `solveXirr`/`moneyWeightedAccountReturn` are implemented and
    unit-tested but never imported by any page. Add to `Performance.jsx`.
13. **T3, wiring-only — Performance reconciliation / P&L bridge.** `trackedAllTimeEarnings` is
    implemented and tested but never called outside its own test. Needs an FX/tax line to become
    a true bridge, but the base math exists.
14. **T3, bug fix — user portfolio turnover shows "Insufficient" always.** `executionStatistics()`
    is called with no arguments (`portfolioAnalyticsModel.js:115`), so it always evaluates an
    empty rebalance list. This is a wiring bug, not a missing metric — needs a real rebalance
    ledger to pass in, which is the actual gap.
15. **T3, wiring-only — days-to-liquidate, transaction-cost drag, current-drawdown duration.**
    All either fully computed and buried in a composite score, or a thin addition given all
    inputs already exist. See gap matrix for specifics. (Weighted ETF expense ratio, the fourth
    item originally grouped here, is ✅ done — see gap matrix.)
16. **T3 — rolling metric stability beyond Sharpe.** Only rolling Sharpe (60/120d) exists; no
    rolling vol/beta/tracking-error/correlation/drawdown, and not at the requested 63/126/252d
    windows.
17. ✅ **T3 — benchmark policy (constructed multi-asset benchmark).** Was single-index best-fit
    among 4 fixed candidates only. Added `constructedBenchmarkFit()` — non-negative weights across
    the same 4 candidates summing to 1, fit to minimize tracking error against the portfolio's own
    returns — surfaced as new rows in the existing Benchmark Fit metric group, alongside (not
    replacing) the single best-fit index.
18. **T4 — full performance attribution (Brinson-style).** Existing `portfolioAttribution.js` is
    explicitly self-documented as single-factor CAPM-style, not sector/style decomposition —
    needs daily sector-index returns this codebase doesn't fetch anywhere.
19. **T4, requires sign-off — tax-lot ledger.** Does not exist; positions carry one aggregate
    cost basis only. Multi-week architectural commitment per §21.
20. **T4, blocked on #19 — wash-sale warning engine.** Does not exist anywhere in the codebase.

## P1 — data integrity (proposals, not built)

21. **T4 — independent corporate-action event ledger.** Confirmed absent; system relies solely on
    Yahoo-adjusted close. Schema and sign-off requirement per the verification doc §7.2.
22. **T4 — invert EDGAR/Yahoo precedence for fundamentals.** EDGAR XBRL ingestion already exists
    (`pipeline/edgar_enrichment.py`) but as a fallback subordinate to Yahoo; making it the
    accounting spine means inverting that precedence, not building new ingestion — still a
    meaningful architectural change requiring sign-off.
23. **T3 — clarify 926/40 vs. 910/126 in published docs.** Both numbers are real but answer
    different questions (static config size vs. one live run-artifact snapshot conflating
    "published" with "enriched"). One-line clarification, not implemented this session to avoid
    touching generated-artifact-adjacent prose without a full read of every consumer.
24. **T3/T4 — tiered A/B/C/D refresh scheduler.** Confirmed not built under that name; the
    existing two-scope (daily-full + intraday-fast) + on-demand scheduler is a real but
    differently-structured analog. Full four-tier design is new work.
25. **T4 — centralized data-license matrix.** Per-provider terms exist scattered (FRED, SEC,
    OpenFIGI); no single tracked source of truth.

## P2 — usability/advanced, after P0/P1 stable

26. **T3 — Planning gauge/assumption adjacency.** The 15% return-target percentage is not
    "buried in settings" as the merged prompt feared — it's the very next section below the
    success-probability gauge, same page, same scroll. Still worth merging into (or overlaying
    directly on) the gauge card itself to remove residual ambiguity, at zero data-model cost.
27. **T3 — reconcile or disclose the dual `momentum_12_1` implementations** (champion: daily
    offset; standalone Momentum screen: calendar-month-end resample). Not a bug — arguably
    intentional per the selection/timing separation principle — but the divergence should be
    either reconciled or explicitly disclosed on both screens.
28. **T3 — ingest the `research/audit/round3-6/` ablation results into `pipeline/experiment_registry.json`**
    so they're not orphaned in a separate tree with hardcoded machine-specific paths, and run
    the ablations confirmed never-attempted (market-behavior-only, no-news, no-valuation,
    no-profitability standalone, no-analyst-modifier, equal-weight-*categories* [distinct from
    the existing equal-weight-*universe* baseline], reduced-redundant-metric, sector-neutralized).

## Explicitly not scheduled (wait, don't build)

- **Anything premised on the IC harness having eligible periods.** It has observed 0 of 24, and
  that means the clock hasn't accumulated enough calendar time yet (~15 days of PIT history
  against a ~24-month bar) — not that 24 periods ran and failed. This resolves with calendar
  time per `docs/TODO.md` §3, already correctly self-reported in `docs/MODEL-CARD.md`'s
  Classification B. No roadmap item should be gated on "fix validation" — there is nothing broken
  to fix here.
- **The swing model.** All seven claims this audit checked (legs, renormalization, coverage
  floor, sector cap, hysteresis, short-interest/ADV caps, momentum independence) were confirmed
  already correctly built and already correctly documented in `docs/MASTER-METHODOLOGY.md` §10.7.
  No action item.
- **The options screens' real-vs-theoretical data split.** Already honestly labeled (staleness
  disclosure exists); only the smaller r=0 disclosure (item 9) is a genuine gap.
