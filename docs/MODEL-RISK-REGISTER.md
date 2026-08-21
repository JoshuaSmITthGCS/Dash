# Model Risk Register

Model / assumption / failure mode / severity / mitigation / monitoring metric, compiled from the
verification pass in `docs/AUDIT-VERIFICATION-RESULTS.md`. Severity follows that document's P0/P1/
P2 convention (P0 = can make a user act on a materially wrong number; P1 = materially weakens
analysis; P2 = quality/usability). This register tracks *risks*, including ones already mitigated
— an entry being here is not itself a call to action; see `docs/AUDIT-ROADMAP.md` for what's
actually scheduled.

---

### 1. Fundamentals-category confidence multiplier still drives enrichment-priority selection

- **Model**: `pipeline/scorer.py::_band_valuation_score`'s multiplied return value, consumed by
  `fetch_advisor.py::enrich()`'s shortlist-priority sort key
  (`valuation_score(context["snapshot"])[0]`).
- **Assumption**: `confidence_multiplier = 0.65 + 0.35 × coverage` was inherited from an earlier
  design that treated missing evidence as a reason to score lower, not a reason to defer judgment.
- **Corrected finding (this session)**: an earlier pass of this audit claimed this multiplier was
  still live for the *champion's published score*. It is not — `build_research()` reads
  `fundamental_parts["raw_score"]` (pre-multiplier) for `components["fundamentals"]`, never the
  multiplied value, confirmed by `test_champion_carries_no_completeness_multiplier` (pre-existing)
  and `TestFundamentalsCategoryMultiplierScope::test_champion_published_score_bypasses_the_multiplier`
  (added this session). The multiplier's one real remaining live consumer is `enrich()`'s sort
  key, which runs *before* enrichment/publication and has nothing to do with the score a user
  ever sees for an already-published name.
- **Failure mode**: a company with genuinely strong fundamentals but thin *pre-enrichment*
  statement coverage has its raw evidence pushed down in the enrichment-priority ranking by this
  multiplier, making it less likely to be selected for the scarce statement-enrichment budget in
  the first place — compounding the shortlist-gating bias already described in
  `docs/CONSOLIDATED-ASSESSMENT.md` §2.2. This is a selection-mechanism risk, not a published-score
  correctness risk.
- **Severity**: P1 — real and live, but narrower in consequence than a defect in the published
  score itself would be (it affects who gets a chance to be scored well, not the scoring of
  already-published names).
- **Mitigation**: documented and tested this session
  (`pipeline/tests/test_round4_remediation.py::TestFundamentalsCategoryMultiplierScope::test_enrichment_priority_sort_key_is_still_directional`).
  An additive, default-preserving `apply_confidence_multiplier` parameter was added to
  `scorer.py::valuation_score`/`_band_valuation_score` (no existing caller's behavior changes) so
  a future challenger measuring `enrich()`'s sort key with the multiplier off is a small,
  reviewable diff rather than a new formula variant. No production change to `enrich()` itself
  without measuring its effect on shortlist composition first, per audit tier-2 authorization.
- **Monitoring metric**: overlap between the current enrichment shortlist and a shortlist built
  from `raw_score` instead of the multiplied sort key, once that comparison is run.

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
  explicitly deprioritized there since no validated edge exists yet to protect). Added this
  session: `enrichment_rotation()` (`pipeline/fetch_advisor.py`) now gives statement-starved
  names the theme screen already flagged as exposed (`theme_exposure` non-empty) first claim on
  the rotation slice, ahead of the plain oldest-unenriched queue, and the rotation slice itself
  grew from 15 to 20 names/refresh (`ADVISOR_ENRICHMENT_ROTATION_SIZE`). This shrinks the
  specific case `themes.explain_rank` already discloses -- a sector-peer name ranked on a
  business-quality reading with no financial statements behind it -- faster than before, but it
  is a same-tier reprioritization of who gets enriched *sooner*, not a change to
  `select_enrichment_priority`'s preliminary-score-only gate itself; the underlying structural
  risk this entry describes is unchanged. That reprioritization was silently defeated until
  entry 11 below was fixed later the same session -- see that entry for why.
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

### 6. Options ranking math combines real chain data with an undisclosed r=0 simplification (fixed this session)

- **Model**: `pipeline/options_common.py` (delta/probability/EV via zero-risk-free Black-Scholes).
- **Assumption**: the risk-free rate's effect on these approximations is small enough to ignore
  for ranking purposes.
- **Failure mode**: a user reading a probability-of-profit or EV figure could reasonably assume
  it reflects current rates; it does not, and unlike the (separately, prominently disclosed)
  quote-staleness risk, this specific simplification was not disclosed in the UI.
- **Severity**: P1 (affects ranking precision, not a wrong-direction signal).
- **Mitigation**: fixed this session — one line next to the existing staleness notice in
  `src/pages/OptionsScreen.jsx` and `src/pages/StrategyScreen.jsx` (`docs/AUDIT-ROADMAP.md`
  item 9).
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

### 9. Alpha Vantage client bypassed the shared rate limiter (fixed this session)

- **Model**: `pipeline/alpha_vantage.py::AlphaVantageClient`.
- **Assumption**: a hardcoded 1.1s `min_interval` between calls was an adequate stand-in for
  Alpha Vantage's real free-tier limit.
- **Failure mode**: `cache.py`'s `DEFAULT_RATE_LIMITS` declares `alpha_vantage: 5` (5
  requests/minute) and every other provider (Yahoo, SEC EDGAR, Marketaux) paces itself
  through the shared `limiter_for()` token bucket that setting configures - but
  `AlphaVantageClient` never called it, self-pacing at 1.1s instead. 15-20 calls/refresh at
  1.1s apart complete in ~17-22 seconds, all inside one 60-second window: 3-4x over the real
  5/min cap. Caught, not catastrophic - `fetch_advisor.py` catches `AlphaVantageError` (which
  Alpha Vantage raises via its own rate-limit "Note" response) and logs a warning, returning
  `{}` for that field rather than failing the run - but it meant some Alpha Vantage-derived
  fields could go silently missing on a full refresh from self-inflicted rate-limiting, not
  real data unavailability.
- **Severity**: P1 - silent data loss risk, not a wrong-published-score risk.
- **Mitigation**: fixed this session. `AlphaVantageClient.query()` now calls
  `limiter_for("alpha_vantage").acquire()` like every other provider, so a `settings.json`
  change is the only place the real limit needs to stay in sync. Added
  `pipeline/tests/test_alpha_vantage.py` (previously no test file existed for this module).
- **Monitoring metric**: none needed beyond the fix itself - this was a pacing defect, not
  something requiring ongoing measurement.

### 10. conflicts.jsonl grew unbounded, breaking every full-mode refresh's push (fixed this session)

- **Model**: `pipeline/price_archive.py::append_series`.
- **Assumption**: logging every archived-vs-incoming price mismatch was a rare, meaningful
  signal worth a permanent record.
- **Failure mode**: Yahoo's adjusted-close values for a given historical date keep drifting
  slightly as later dividends change the adjustment factor, so a rolling window of
  already-archived dates disagrees with the freshly fetched series on essentially every run.
  With no dedup, the same (ticker, date) mismatch was re-logged on every subsequent daily
  run forever: 663,964 lines for only 108,033 distinct pairs (some repeated 9 times),
  inflating the committed file to ~111MB and failing every full-mode refresh's push past
  GitHub's 100MB hard limit (confirmed on GitHub Actions run #181).
- **Severity**: P0 for pipeline availability - a scheduled refresh silently failing to
  publish is a worse failure mode than a scoring defect, since nothing about it is visible
  in the published data itself.
- **Mitigation**: fixed this session. Conflict logging is now deduplicated per (ticker,
  date) - a mismatch is recorded once, not on every run that rediscovers it. The existing
  committed file was pruned to one entry per pair (~17MB, no information lost). Added two
  regression tests in `pipeline/tests/test_price_archive.py`.
- **Monitoring metric**: the manifest's per-run `conflicts` count now means *newly
  discovered* conflicts, a more useful signal than before (a spike is meaningful; a constant
  re-report of already-known drift was noise).

### 11. screen_universe silently dropped the one field rotation needs to know a name is done (fixed this session)

- **Model**: `pipeline/fetch_advisor.py::_screen_row`, consumed by
  `enrichment_rotation()`'s `last_enriched()` via `previous_rows_by_ticker`.
- **Assumption**: `fundamental_categories` (carried into the lightweight `screen_universe`
  projection for every row) was enough for downstream consumers to reason about a name's
  statement coverage.
- **Failure mode**: `fundamental_categories` is computed and populated for every row
  regardless of enrichment status (it's the base category breakdown, not enrichment
  evidence); the one field that actually signals real statement coverage,
  `fundamental_detail.raw_score`, was never projected into `screen_universe` at all. A name
  `enrichment_rotation()` sent to `enrich()` and that resolved real metrics, but that still
  wasn't good enough to crack the `publish_limit` leaderboard, landed in `screen_universe`
  and lost that fact the moment it did. Every subsequent run's `last_enriched()` check then
  saw it as never-enriched, so rotation could burn a "next 20" slot re-selecting the same
  handful of already-covered names indefinitely instead of ever treating them as done and
  moving on to genuinely untouched ones. Confirmed against the live published data: of 879
  total universe rows, all 40 `research` rows carried real statement coverage but all 839
  `screen_universe` rows read as uncovered - not because rotation hadn't reached them, but
  because the signal couldn't survive the projection. This directly undermined this same
  session's earlier theme-priority rotation fix (entry 2's mitigation): the "next 20" batch
  could never actually observe its own progress.
- **Severity**: P1 - caps how much of the universe the rotation mechanism can ever durably
  expand past the initial ~150-name shortlist, compounding entry 2's structural risk.
- **Mitigation**: fixed this session. `_screen_row()` now projects a minimal
  `{"raw_score": ...}` slice of `fundamental_detail` (not the full ~2KB nested structure,
  which would bloat the ~850-row tail for no reader-facing purpose) so the exact field
  `last_enriched()` already checks survives for every row, not just the published top 40.
  Added regression tests in `pipeline/tests/test_fetch_advisor.py` covering the projection
  and the end-to-end rotation behavior against a `screen_universe`-only row.
- **Monitoring metric**: distinct-ticker statement coverage across the *whole* published
  universe (`research` + `screen_universe` combined), not just `statement_enriched_count`
  (which only ever reflected the current run's ~150-name priority queue and would read the
  same near-ceiling number whether rotation was expanding coverage or silently recycling the
  same names - not a useful signal on its own, which is what prompted this investigation).
