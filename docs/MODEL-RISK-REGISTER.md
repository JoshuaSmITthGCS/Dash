# Model Risk Register

Model / assumption / failure mode / severity / mitigation / monitoring metric, compiled from the
verification pass in `docs/AUDIT-VERIFICATION-RESULTS.md`. Severity follows that document's P0/P1/
P2 convention (P0 = can make a user act on a materially wrong number; P1 = materially weakens
analysis; P2 = quality/usability). This register tracks *risks*, including ones already mitigated
— an entry being here is not itself a call to action; see `docs/AUDIT-ROADMAP.md` for what's
actually scheduled.

---

### 1. Fundamentals-category confidence multiplier is directional, not neutral-shrinking

- **Model**: `pipeline/scorer.py` `_band_valuation_score`/`_cross_sectional_valuation_score`
  (production `normalization_mode: "bands"`).
- **Assumption**: `confidence_multiplier = 0.65 + 0.35 × coverage` was inherited from an earlier
  design that treated missing evidence as a reason to score lower, not a reason to defer judgment.
- **Failure mode**: a company with genuinely strong fundamentals but thin statement coverage
  (e.g. recently added to the enrichment shortlist) scores lower than its actual evidence
  supports, and the effect compounds with the shortlist-gating bias already described in
  `docs/CONSOLIDATED-ASSESSMENT.md` §2.2 — thin coverage both keeps a name off the shortlist *and*
  penalizes it further once it's scored.
- **Severity**: P0 by the same standard the top-level version of this formula was judged against
  (already retired for that reason on 2026-08-12) — but currently undiscovered/unaddressed at
  this layer.
- **Mitigation**: documented with a passing regression test
  (`pipeline/tests/test_round4_remediation.py::TestFundamentalsCategoryMultiplierStillDirectional`)
  that will need to start failing before this is fixed. Per audit tier-2 authorization, no
  production change without registering `_fixed_feature_valuation_score`'s already-existing
  no-multiplier pattern as a challenger and measuring its rank effect by coverage decile first.
- **Monitoring metric**: rank correlation between bands-mode and fixed-feature-mode scores,
  segmented by coverage decile, once the challenger comparison runs.

### 2. Enrichment-shortlist selection bias (pre-existing, largest structural risk in the system)

- **Model**: `select_enrichment_priority()` in `pipeline/fetch_advisor.py`.
- **Assumption**: a cheap preliminary (price-multiples-only) score is a good enough proxy to
  decide which ~150 of ~910 names get statement-derived metrics computed at all.
- **Failure mode**: a company with an unattractive trailing multiple but excellent capital
  returns and balance sheet can never surface, because it never enters the shortlist. Measured
  historical consequence: restoring statement enrichment after an outage reordered the published
  board at rank correlation 0.820, mean absolute shift 114 ranks — i.e. the ranking during that
  window was substantially a map of data availability, not methodology (`docs/AUDIT-ROUND-4-FINDINGS.md:244`,
  carried into `docs/MASTER-METHODOLOGY.md:467-468`).
- **Severity**: P0, already disclosed as a permanent methodology note.
- **Mitigation**: EDGAR XBRL fallback (`pipeline/edgar_enrichment.py`) already reduces the
  practical exposure by filling gaps Yahoo leaves after outages; the underlying shortlist-gating
  design is unchanged and out of this pass's scope (multi-week, WO-6 in `docs/P0-VERDICT.md`,
  explicitly deprioritized there since no validated edge exists yet to protect).
- **Monitoring metric**: `docs/CONSOLIDATED-ASSESSMENT.md`-style coverage counts
  (`capital_allocation`/`accounting_quality` scored fraction of the published universe), and the
  rank-drift-vs-previous-run metric already proposed in the merged audit's §16 (not yet built).

### 3. No independent corporate-action ledger; single vendor-adjusted price series

- **Model**: all price-derived analytics (TWR, benchmark comparison, factor regression inputs).
- **Assumption**: Yahoo's adjusted-close series correctly folds every split/dividend/spinoff/
  merger into price with no separate reconciliation.
- **Failure mode**: a corporate action Yahoo mis-adjusts (known to happen, unofficial API) would
  silently corrupt every downstream return calculation with no independent check.
- **Severity**: P0 per the merged audit's own release-gate table ("corporate actions can silently
  corrupt returns" caps performance-accounting credibility outright).
- **Mitigation**: none currently beyond vendor trust. Confirmed absent this pass — see
  `docs/AUDIT-VERIFICATION-RESULTS.md` §7.2.
- **Monitoring metric**: none exists; would need an independent action-by-action reconciliation
  against a second source (SEC filings or a second price vendor) to detect drift.

### 4. `yfinance` is an unofficial, unaffiliated API wrapper

- **Model**: nearly every price/statement/estimate/news input.
- **Assumption**: Yahoo's underlying (undocumented) API continues to serve the fields this
  pipeline depends on, on terms compatible with the product's actual use.
- **Failure mode**: Yahoo's own documentation states its API is intended for personal/research/
  educational use, not commercial redistribution — a genuine productization risk if ValueSignal
  is ever opened beyond personal use, independent of the PIT/restatement concern in risk #2.
  `yfinance` can also break silently on upstream shape changes with no notice (already a standing
  caveat in `TODO.md`).
- **Severity**: P1 today (personal use); would become P0 before any multi-user launch.
- **Mitigation**: cache-and-fallback pattern already in place for reliability; no terms-of-use
  mitigation exists.
- **Monitoring metric**: `source_status.yahoo_news.status`/equivalent freshness fields already
  published per refresh; a dedicated schema-drift check for `yfinance` payload shape does not
  exist and would be the real mitigation.

### 5. Validation status: 0 of 24 eligible IC periods

- **Model**: `pipeline/validation/ic_harness.py`.
- **Assumption**: none broken — this is accurately self-reported.
- **Failure mode risk here is misreading, not miscalculation**: if a future consumer (dashboard
  copy, a sales conversation, a user) treats any live Sharpe/IC/hit-rate figure as validated, that
  would be the actual failure — the number itself is honestly labeled "accumulating."
- **Severity**: P0 *if misrepresented*, otherwise none — already correctly gated:
  `docs/MODEL-CARD.md:61-63` states no such figure should be read as validated, and no promotion
  has occurred or is proposed (`docs/RESEARCH-CONTRACT.md` §4).
- **Mitigation**: already in place (explicit "accumulating" status, no promotion).
- **Monitoring metric**: `periods_accumulated` in `public/data/validation/ic_validation.json`,
  already published.

### 6. Options ranking math combines real chain data with an undisclosed r=0 simplification

- **Model**: `pipeline/options_common.py` (delta/probability/EV via zero-risk-free Black-Scholes).
- **Assumption**: the risk-free rate's effect on these approximations is small enough to ignore
  for ranking purposes.
- **Failure mode**: a user reading a probability-of-profit or EV figure could reasonably assume
  it reflects current rates; it does not, and unlike the (separately, prominently disclosed)
  quote-staleness risk, this specific simplification is not disclosed in the UI.
- **Severity**: P1 (affects ranking precision, not a wrong-direction signal).
- **Mitigation**: none yet; a one-line UI disclosure is proposed (`docs/AUDIT-ROADMAP.md` item 9).
- **Monitoring metric**: none needed beyond the disclosure itself — this is a communication gap,
  not a data-quality one.

### 7. Planning engine's user-set return assumption could be misread as a forecast

- **Model**: `src/lib/projectionEngine.js`, `src/pages/Planning.jsx`.
- **Assumption**: placing the return-target percentage in the section immediately below the
  success-probability gauge (rather than inside the gauge card itself) is sufficiently close to
  prevent the assumption from reading as a validated expectation.
- **Failure mode**: a user who reads only the gauge number, without scrolling to the adjacent
  card, could treat "72% success" as an objective probability rather than a probability
  conditional on a user-chosen 15% return assumption.
- **Severity**: P1 — this pass found the risk narrower than the merged audit prompt assumed (not
  "buried in settings"; it's the very next section, same page, same scroll), but the residual gap
  is real.
- **Mitigation**: none yet; proposed UI merge/overlay in `docs/AUDIT-ROADMAP.md` item 26.
- **Monitoring metric**: none applicable (a UI/communication risk, not a data risk).

### 8. Two structurally different `momentum_12_1` implementations

- **Model**: `pipeline/risk_metrics.py:36` (champion) vs. `pipeline/research_screens_v2.py:39-54`
  (standalone Momentum screen).
- **Assumption**: day-count and calendar-month-end resampling produce close-enough results that
  the divergence doesn't matter.
- **Failure mode**: a name could rank well on one momentum view and poorly on the other purely
  from implementation differences around trading-calendar gaps, with no indication to the user
  that this is possible.
- **Severity**: P2 — no evidence either implementation is *wrong*, just that they can disagree
  without disclosure.
- **Mitigation**: none yet; proposed reconciliation or disclosure in `docs/AUDIT-ROADMAP.md`
  item 27.
- **Monitoring metric**: pairwise rank correlation between the two implementations' outputs,
  not currently measured.
