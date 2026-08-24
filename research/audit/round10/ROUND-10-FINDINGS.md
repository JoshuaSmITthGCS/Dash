# Round 10 — Leg and quantile-spread diagnosis

Diagnostic only. No production weights, no shadow-variant promotion, no leg removed from
the live composite. Method: `research/audit/round10/leg_diagnosis.py`, reading
`pipeline/backtest_signal_panel.json` (the same 60-period, 2021-09..2026-08 monthly panel
Round 7's `reweighting_backtest.py` used) through `pipeline/evaluation.py`'s existing
`per_leg_ic` / `drop_one_leg_delta_ic` / `walk_forward` functions — no new statistics
invented, nothing re-derived that the codebase doesn't already compute. Raw results:
`research/audit/round10/leg_diagnosis_results.json`.

## Priority 1 — classifying the four drag legs

| Leg | Panel coverage | Classification |
|---|---:|---|
| `growth` | **0.0%** (0/51,600) | **(c) inherent backtest-data-depth limit, already documented in code, not a live defect** |
| `news_sentiment` | **0.0%** (0/51,600) | **(c) inherent backtest-reconstruction limit, already documented in code, not a live defect** |
| `capital_allocation` | 6.5% (3,339/51,600) | **(a)-adjacent: too data-starved in this panel to classify as window-artifact vs. genuinely weak** |
| `accounting_quality` | 6.7% (3,442/51,600) | **(a)-adjacent: too data-starved in this panel to classify as window-artifact vs. genuinely weak** |

### `growth` — data-availability limit, not a bug

`revenue_growth`/`earnings_growth` need **two full trailing-twelve-month periods** (8
consecutive quarters) in `backtest_historical.py::build_ttm_statements` — the *current* TTM
plus the *year-ago* TTM for the YoY comparison. Every other category needs only the current
TTM (4 quarters). `backtest_historical.py`'s own docstring already states why that second
TTM essentially never resolves: *"Quarterly statement history from yfinance typically only
reaches back ~2 years (about 8 quarters), so year-over-year growth figures thin out for the
earliest weeks in a long lookback window — this is a real data-availability limit, not a
bug."* Across a 5-year, 60-period panel, "thins out" evidently means "never clears" — 0 of
51,600 ticker-periods. This is a **backtest-reconstruction ceiling** (free Yahoo quarterly
history, not the full EDGAR PIT batch Round 4 already collected — 1.4M+ as-filed facts back
to 2010 — which this backtest path doesn't read from), **not** a live-production defect:
production `advisor.json` shows real, non-null `growth` scores today (MSFT 78.2, JPM 100.0
in the current committed snapshot). `drop_one_leg_delta_ic` for `growth` is exactly `0.0`
— correctly, since a leg with zero coverage cannot move a renormalized composite either
way. That number says nothing about whether `growth` is predictive; it says the panel never
gave it a chance to be.

### `news_sentiment` — same shape, different mechanism, and the A1 fix confirmed live

`backtest_monthly.py`'s `rank_week` calls `build_research(symbol, snap, closes_to_date,
benchmark_closes_to_date, [], ...)` — the news-items argument is a **literal empty list**,
every ticker, every period; there is no historical news archive to replay. Before
A1-NEWS-NEUTRAL (2026-08-07), a zero-article name still got a numeric neutral-50 default, so
it would have shown up as 100% "covered" here — misleadingly. After A1, `weighted_sentiment`
correctly reports unavailable (`None`) for zero-coverage names, so this leg is now correctly
excluded from `leg_scores` for every single period: **0.0% coverage, confirming the A1 fix
is live in this exact per-leg-IC calculation**, not just committed to the codebase. The
`news_sentiment_neutral_pileup` check (before/after A1, looking for a pile-up at exactly
50.0) found `n=0` observations on both sides of the A1 date — there is no pileup to measure,
because there are no numeric observations of any kind. One stale byproduct worth flagging
for a later cleanup (not done this round, diagnostic only): `backtest_historical.py`'s own
docstring still says *"News sentiment defaults to neutral (50) for historical weeks, same
as it does live"* — that description predates A1 and is no longer accurate for the live
half of that sentence.

### `capital_allocation` / `accounting_quality` — too data-starved to confirm or refute Round 7's framing

Round 7 (section 4.3) attributed their negative IC specifically to the 5-period measurement
window. Reproducing per-leg IC at 1d/5d/21d/63d:

| Horizon | `capital_allocation` mean IC (n periods) | `accounting_quality` mean IC (n periods) |
|---|---:|---:|
| 1d | −0.109 (n=6) | +0.005 (n=6) |
| 5d | −0.037 (n=5) | −0.038 (n=5) |
| 21d | −0.042 (n=5) | −0.047 (n=5) |
| 63d | −0.131 (n=3) | −0.002 (n=3) |

Two findings, not one:
1. **`capital_allocation` reads negative at every horizon tested**, not just 5d — the
   opposite of "isolated to the 5-period window." **`accounting_quality`'s sign flips**
   (positive at 1d, negative at 5d/21d, near-zero at 63d) — the opposite of "persistent."
2. Neither result should be trusted at face value: **3 to 6 periods** is nowhere near
   enough to distinguish a real window-specific effect from noise at any single horizon, let
   alone compare horizons against each other. At 6.5–6.7% panel coverage, these two legs hit
   the same root problem as `growth`/`news_sentiment` in a milder form — this backtest panel
   never had statement-derived data for most ticker-periods (matches
   `A3-FULL-UNIVERSE-ENRICHMENT`'s already-documented enrichment-coverage bottleneck:
   statement metrics only ever existed for the shortlist, historically too). **Verdict: not
   classifiable as window-artifact vs. genuinely-weak from this panel — the honest answer is
   "insufficient data to tell," not a confirmation or a rejection of Round 7's framing.**
   `drop_one_leg_delta_ic` for both sits at essentially zero (−0.0001), consistent with
   "too thin to move the composite either way," not "confirmed mild drag."

### A finding the brief didn't ask for, but the same table shows it

`drop_one_leg_delta_ic` on the full 8-leg composite: the leg actually **hurting the
composite the most by far is `market_behavior`** (delta −0.0398, "hurts_composite=True"),
roughly 40x larger in magnitude than any of the four flagged drag legs (`capital_allocation`
−0.0001, `accounting_quality` −0.0001, `profitability` −0.0005). None of the four legs this
round was asked to classify move the composite's IC by a measurable amount in this panel;
`market_behavior` does. That's outside this round's scope to act on (no leg removed, no
weight changed), but it's directly relevant to what a future search round should prioritize
first.

## Priority 2 — quantile-spread compression

- **Full 8-leg composite mean quantile spread**: 0.49% (0.0049) — matches Round 7's cited
  0.48% closely, confirming this reproduction is measuring the same thing the same way.
- **4 non-drag-legs-only composite** (valuation, profitability, financial_health,
  market_behavior, renormalized): mean quantile spread **0.49% (0.0049) — identical to four
  decimal places.**

**Removing the four flagged drag legs changes the quantile spread by nothing.** That
follows directly from Priority 1: two of the four contribute exactly 0% of the composite in
this panel already, and the other two contribute to only 6.5–6.7% of rows. The compression
is not coming from these four legs — it has to be sitting in the four that actually carry
weight here (`valuation`, `profitability`, `financial_health`, `market_behavior`), or in how
they combine, which is outside this round's scope to diagnose further.

**Quantile membership is not frozen.** Month-over-month overlap of the top quintile with
itself: 60.3%; bottom quintile: 66.2% — meaning 34–40% of names rotate in/out of each bucket
every month. Low turnover muting the spread is not the primary story here; a composite that
re-ranks a real fraction of the universe each month is still only producing a 0.49% forward
top-minus-bottom gap, which points at weak signal in the legs that actually carry weight,
not at a stale membership problem.

## Does this mean the R7 shadow variant (`reweighted_composite_a`) will show real improvement?

**Unlikely, and for a reason worth stating precisely: R7's own in-sample comparison (this
exact panel) never actually tested removing `growth` or `news_sentiment`, because neither
one was contributing anything to the *champion* baseline in this panel to begin with.**
Zeroing a leg that already carries 0% effective weight against a champion where it also
carried 0% effective weight is not a comparison — both sides of that half of the test were
identical before the reweighting was ever applied. The other half of proposal A
(`capital_allocation`, `accounting_quality`) touches legs that carried a small but genuinely
present weight (6.5–6.7% of rows), so there is *something* to zero there, but the underlying
signal is too data-starved in this panel to say whether removing it helps, hurts, or is
noise either way.

This does **not** mean removing these four legs is a bad idea, or that the shadow variant
will fail — it means this specific offline panel is close to uninformative about the
question, in both directions, because of a data-availability ceiling in the backtest
reconstruction, not because the legs are known to be harmless (or known to help). **Live
production has real coverage for `growth` and `news_sentiment` that this backtest panel
structurally cannot reproduce** (MSFT/JPM show real growth scores today; live news coverage
exists for covered names), so the prospective shadow run — which scores against live,
current data, not this reconstructed panel — is actually a *more* informative test of
proposal A than the backtest that originally proposed it. The prospective clock, already
running since 2026-08-21 per the R7 registry entry, is the right place to get a real answer
here; nothing in this round's findings argues for accelerating or short-circuiting it.

## What NOT done, per the brief

No production leg weights changed. No leg dropped from the live composite. The R7 shadow
variant was not touched, accelerated, or promoted — it continues running prospectively
exactly as before. This report classifies; it does not decide.
