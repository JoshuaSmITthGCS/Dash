"""Round 11 Priority 1 — reusable parameter-search harness enforcing split-then-search.

C4-turnover-controls searched nine configurations on one in-sample path, found apparent
winners (score smoothing, a 6-month holding floor), and C7-turnover-walkforward killed
both on re-test: PBO 0.80-0.84 (worse than random selection) and no variant's deflated
Sharpe cleared even half the 0.95 bar. The mistake was not optimizing, it was validating
in-sample. This module does not add new statistics -- ``evaluation.py`` already has
walk-forward evaluation, CSCV-based PBO, and deflated Sharpe -- it wires those into a
structure where a candidate cannot accidentally be scored against data it was tuned on,
because the split happens exactly once, before any candidate exists, and a session's
``.holdout`` slice is never touched by ``evaluate()`` at all: it exists for a human to
grade the final shortlist by hand, once, not for the harness to search against.

Every ``evaluate()`` call is one trial. Nothing here reads or writes
``experiment_registry.py`` -- that registry is deliberately hand-maintained data (see its
own docstring); this module supplies the honest, gated numbers a human then transcribes
into a new registry entry, the same way Round 7 and Round 10's findings were written up.
"""

from evaluation import (
    composite_score,
    evaluate_candidate,
    probability_of_backtest_overfitting,
    rank_ic,
    walk_forward,
)
from experiment_registry import total_variants_tested

DEFAULT_PBO_SPLITS = 8
OVERFITTING_LINE = 0.5  # evaluation.probability_of_backtest_overfitting's own documented line


class Panel:
    """Immutable chronological train/validation/holdout split of a period panel.

    ``periods`` must already be in ascending date order (``backtest_signal_panel.json``'s
    ``periods`` list is). Splitting is a plain slice, never a shuffle -- shuffling a time
    series before splitting is its own leakage bug, not a safeguard against one.
    """

    __slots__ = ("train", "validation", "holdout")

    def __init__(self, periods, *, train_fraction=0.5, validation_fraction=0.25):
        if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1:
            raise ValueError("train_fraction and validation_fraction must each be in (0, 1)")
        if train_fraction + validation_fraction >= 1:
            raise ValueError("train_fraction + validation_fraction must leave a nonzero holdout")
        total = len(periods)
        train_end = int(total * train_fraction)
        validation_end = train_end + int(total * validation_fraction)
        self.train = tuple(periods[:train_end])
        self.validation = tuple(periods[train_end:validation_end])
        self.holdout = tuple(periods[validation_end:])
        if not (self.train and self.validation and self.holdout):
            raise ValueError(
                "split produced an empty train, validation, or holdout slice -- "
                "panel too short for this split")


def score_with_weights(periods, weights):
    """Attach a ``scores`` key computed by ``composite_score`` under ``weights``.

    Leaves ``leg_scores`` and ``forward_returns`` untouched so the same period objects can
    still be used for leg-level diagnostics (``per_leg_ic``, ``drop_one_leg_delta_ic``)
    alongside this composite view.
    """
    scored = []
    for period in periods:
        leg_scores_by_ticker = period.get("leg_scores") or {}
        scores = {ticker: composite_score(legs, weights)
                  for ticker, legs in leg_scores_by_ticker.items()}
        scores = {ticker: score for ticker, score in scores.items() if score is not None}
        scored.append({**period, "scores": scores})
    return scored


def _configuration_ic_series(periods, weights):
    series = []
    for period in periods:
        leg_scores_by_ticker = period.get("leg_scores") or {}
        forwards = period.get("forward_returns") or {}
        pairs = []
        for ticker, legs in leg_scores_by_ticker.items():
            score = composite_score(legs, weights)
            forward = forwards.get(ticker)
            if score is not None and forward is not None:
                pairs.append((score, forward))
        ic = rank_ic([pair[0] for pair in pairs], [pair[1] for pair in pairs]) if len(pairs) >= 5 else None
        series.append(ic)
    return series


class OptimizationSession:
    """One bounded search over a fixed :class:`Panel`.

    ``trial_count`` defaults to ``experiment_registry.total_variants_tested()`` so a new
    search's deflated Sharpe deflates against the real cumulative research programme, the
    same wiring ``ic_harness.py`` already uses -- not against just this session's own
    candidate count, which is how ``signal_metrics.py`` currently understates it.
    """

    def __init__(self, panel, *, pbo_splits=DEFAULT_PBO_SPLITS, quantiles=5,
                periods_per_year=12, trial_count=None):
        self.panel = panel
        self.pbo_splits = pbo_splits
        self.quantiles = quantiles
        self.periods_per_year = periods_per_year
        self.trial_count = trial_count if trial_count is not None else total_variants_tested()
        self.results = []

    def evaluate(self, name, weights, *, baseline=None):
        """Score one candidate: train-vs-validation walk-forward efficiency, gated by
        deflated Sharpe on the validation slice. Never reads ``self.panel.holdout``.
        """
        train_scored = score_with_weights(self.panel.train, weights)
        validation_scored = score_with_weights(self.panel.validation, weights)

        train_result = walk_forward(train_scored, quantiles=self.quantiles,
                                    periods_per_year=self.periods_per_year)
        validation_verdict = evaluate_candidate(
            validation_scored, trials=self.trial_count, quantiles=self.quantiles,
            periods_per_year=self.periods_per_year, baseline=baseline)

        train_ic = train_result["ic"]["mean_ic"]
        validation_ic = validation_verdict["ic"]["mean_ic"]
        efficiency = None
        if train_ic:
            efficiency = round(validation_ic / train_ic, 4) if validation_ic is not None else None

        record = {
            "name": name,
            "weights": dict(weights),
            "train_mean_ic": train_ic,
            "validation_mean_ic": validation_ic,
            "walk_forward_efficiency": efficiency,
            "validation_verdict": validation_verdict,
            "trials_considered": self.trial_count,
        }
        self.results.append(record)
        return record

    def probability_of_overfitting(self, candidates):
        """PBO via CSCV across every ``(name, weights)`` in ``candidates``, on the
        validation slice.

        Call once with the full candidate set actually searched -- PBO measures whether
        the *selection process* across all of them is generating winners at random, so it
        needs every candidate compared together, not one at a time.
        """
        series_by_name = {name: _configuration_ic_series(self.panel.validation, weights)
                          for name, weights in candidates}
        periods = len(self.panel.validation)
        matrix = [[series_by_name[name][row] if series_by_name[name][row] is not None else 0.0
                  for name, _ in candidates] for row in range(periods)]
        pbo = probability_of_backtest_overfitting(matrix, splits=self.pbo_splits)
        return {"names": [name for name, _ in candidates], "splits": self.pbo_splits, "pbo": pbo}


def classify(session, candidates, *, baseline=None):
    """Run every candidate through the full gate sequence and suggest a decision.

    Mirrors the existing ``experiment_registry`` vocabulary (PROMOTE / KEEP_AS_CHALLENGER /
    ABANDON) rather than inventing a fourth one. This is a suggestion, not a promotion --
    nothing here writes to the registry or a shadow strategy; see this module's docstring.
    """
    evaluated = [session.evaluate(name, weights, baseline=baseline) for name, weights in candidates]
    overfitting = session.probability_of_overfitting(candidates)
    search_overfit = overfitting["pbo"] is not None and overfitting["pbo"] >= OVERFITTING_LINE

    classified = []
    for record in evaluated:
        verdict = record["validation_verdict"]
        if search_overfit:
            decision = "ABANDON"
            reason = (f"search-wide PBO {overfitting['pbo']} across {len(candidates)} candidates "
                      f"is at or above {OVERFITTING_LINE} -- the selection process itself is "
                      "generating winners at random, independent of any one candidate's own numbers")
        elif verdict["ship"]:
            decision = "PROMOTE"
            reason = "clears walk-forward, deflated Sharpe, and PBO gates"
        elif verdict["ic"]["meaningful"] or (record["walk_forward_efficiency"] or 0) > 0.5:
            decision = "KEEP_AS_CHALLENGER"
            reason = "some validation-period signal but does not clear every gate: " + "; ".join(
                verdict.get("ship_blockers") or [])
        else:
            decision = "ABANDON"
            reason = "; ".join(verdict.get("ship_blockers") or ["no validation-period signal"])
        classified.append({**record, "suggested_decision": decision, "reason": reason})

    return {"candidates": classified, "search_overfitting": overfitting}
