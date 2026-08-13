# P0 — Verdict

**B. A factor tilt with no residual alpha.** Six-factor regression on the strategy's own
published 5-year backtest returns (n = 58 months, 2021-09 → 2026-06, the longest window the
already-cached Ken French data supports) finds an annualized alpha of **−2.57%, Newey-West(3)
t = −0.437** — net of market, size, value, profitability, investment, and momentum, there is
nothing left, and the point estimate is negative. Per the brief's own threshold (|t| < 1.0 → no
residual alpha), this is not the ambiguous middle case. The deflation accounting below shows this
verdict does not rest on a cherry-picked winner from a search — it's the direct result of one
pre-specified regression, and no "best variant" was selected from a set of competing
configurations this session, because both work orders that would have run a real variant search
(WO-3's cost regimes, WO-5's turnover controls) were blocked by this session's network policy
before they could produce anything to select from.

Two qualifications keep this from being a clean B-and-done:

1. **The strategy is competitive against better-matched benchmarks** (beats RSP 11.14% vs 9.23%
   CAGR, beats IWM decisively on Sharpe, 0.644 vs 0.439). "Loses to SPY" was never strong evidence
   against the score; it was evidence the yardstick was wrong. That doesn't change the six-factor
   result, but it means the honest reframing isn't "this failed," it's "this is a tilt, and a
   reasonably executed one, that happens to have been benchmarked against the hardest target
   available."
2. **A factor tilt is only worth running yourself, instead of buying a factor ETF, if it's cheap.**
   At 64.9% monthly turnover (WO-5), this one is not. The dominant driver of that turnover, per
   the one piece of turnover evidence available this session, is not band quantization (0.42% of
   live-refresh churn events) but metric availability flicker (96.72%) — a data-consistency
   problem, not a normalization-mode problem. **This means the standard Verdict-B prescription
   ("reposition as a cheap tilt, stop trying to beat SPY") is not yet actionable as stated** —
   it's cheap in theory, not in the numbers this system currently produces.

## Ranked recommendations

**1. Fix metric availability flicker before anything else. *Corrective.***
Claim: statement-derived metrics flip between present and missing across refreshes hours apart
for the same company, for reasons unrelated to any real change in the business — falsifiable by
instrumenting one refresh cycle and checking whether a flickering metric's *source data* (not
just its presence flag) actually changed. Test: extend `pipeline/p0_q2_turnover_attribution.py`'s
already-built classifier to log *why* a metric disappears (provider error vs. cache staleness vs.
enrichment-shortlist exclusion) for the next several live refreshes, then trace the top cause in
`fetch_advisor.py`/`cache.py`. Expected effect: if the top cause is fixable (e.g., a caching TTL
mismatch rather than genuine provider gaps), turnover should fall by a large fraction of the
96.72%-attributed share, not the ~0.4% a normalization-mode fix would touch — meaningfully more
than "improves performance." Cost: 1–2 engineering days, no new data. Abandon if instrumentation
shows the flicker is genuinely provider-side (Yahoo intermittently omitting a statement field)
rather than a pipeline bug — then it graduates to a caching/retry problem, not a quick fix.

**2. Reframe the product honestly, once (1) lands. *Corrective, cheap.***
Claim: presenting this as a transparent factor tilt, benchmarked against RSP/IWM alongside SPY,
is more honest and more favorable than the current SPY-only framing. Test: none needed beyond
WO-4's numbers, which are already reproducible. Effect: no performance change; a credibility and
expectations-setting change. Cost: documentation and one dashboard panel (add the two benchmark
lines already computed in `factor_regression_p0.json`). Abandon: never — this is strictly
dominated by the status quo in cost and has no downside once (1) or an honest "still expensive to
run" caveat accompanies it.

**3. Run the blocked three-regime cost backtest (WO-3) and turnover-control grid (WO-5) once
network access exists. *Diagnostic, becomes corrective if a control clears 150bps net.***
Claim: `costs.py`'s tiered model, already wired into both `backtest_monthly.py` and
`ic_harness.py` and unit-tested this session, will show whether realistic costs erase more than
200bps of annual return relative to the flat-10bps assumption. Test: the exact three commands in
`docs/P0-REPAIRS.md` WO-3. Effect: unknown by design — that's the point of a diagnostic — but at
65% monthly turnover the brief's own math (≈7.8 turns/year) makes a large effect plausible. Cost:
one Yahoo fetch cycle for ~860 names, hours not days, from any environment with real internet
access. Abandon: if flat and tiered costs converge within ~50bps, cost realism was never the
binding constraint and (1) remains the priority on its own.

**4. Bootstrap point-in-time history from SEC EDGAR (Q6). *Diagnostic, longer horizon.***
Claim: the IC harness's 0-of-24-period gate is the only path to genuine prospective validation,
and reconstructing as-reported fundamentals from EDGAR full-text filings could shorten the
~2-year wait. Test: as specified in `docs/RESEARCH-PROMPT.md` Q6, unchanged by this phase's
findings — this is about future validation, not this backtest. Cost: weeks, not hours; the
highest-cost item here. Abandon: if EDGAR full-text search doesn't expose structured
period-over-period figures cheaply enough to beat just waiting out the 2 years in real time.

**5. Run WO-6 (unconstrained shortlist, 910 names). *Diagnostic, deprioritized.***
No longer load-bearing: WO-4 already shows no demonstrated alpha for a shortlist-repair to be
protecting. Still worth doing eventually since it's a real structural question independent of
Q1 — reproduction command and reasoning in `docs/P0-Q3-SHORTLIST.md` — but below items 1–4 in
expected value per hour.

**Do not** build the Capital Efficiency, FCF Quality, or Catalyst sleeves. Verdict B removes the
premise (a validated edge worth extending) that would justify them, on top of the brief's own
scope rule.

## Deflation accounting

**Total configurations tried this session: 5**, all logged in `pipeline/reports/p0_trial_log.jsonl`
(4 from WO-4: the six-factor regression, the single-factor CAPM, and the RSP/IWM benchmark
simulations; 1 from WO-5: the turnover attribution). **All five are fixed-specification
diagnostics, not a search over candidate configurations from which a best performer was
selected** — there was no "try N variants, report the winner" step this session, because the two
work orders structured that way (WO-3's cost-regime grid, WO-5's turnover-control grid) were both
blocked before producing anything to select from. `pipeline/evaluation.py`'s deflated Sharpe and
PBO machinery is built for exactly that selection scenario and has nothing to deflate here: there
is no "best variant" Sharpe ratio from this session to report, and forcing the calculation onto a
single fixed regression would misrepresent what deflation is for. **The pre-existing published
Sharpe (0.644) is likewise not a best-of-N figure — it's the one number the original backtest
ever produced, not a selection from alternatives — so it isn't deflation-eligible either.** When
WO-3 and WO-5's blocked variant grids do run, every configuration they try must be logged in the
same file and deflated against that count before anything from them is called a result rather
than a diagnostic.
