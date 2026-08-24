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
    per_leg_ic,
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


def leg_coverage(periods, legs):
    """Fraction of ticker-periods where a leg resolved a real number, per leg.

    Same shape as research/audit/round10/leg_diagnosis.py's own leg_coverage() (present /
    total), so a formula_weights() candidate can be sanity-checked directly against that
    report's numbers rather than trusting a second, silently-diverged implementation.
    """
    coverage = {}
    for leg in legs:
        present = total = 0
        for period in periods:
            for scores in (period.get("leg_scores") or {}).values():
                total += 1
                if isinstance(scores.get(leg), (int, float)):
                    present += 1
        coverage[leg] = present / total if total else 0.0
    return coverage


def formula_weights(periods, *, legs=None, periods_per_year=12):
    """A coverage-and-signal-weighted candidate: weight_leg proportional to
    coverage_leg * max(0, standalone_ic_leg).

    Directly operationalizes the mismatch a hand-authored weight vector accumulates over
    time: a leg's declared weight should track how often it actually resolves AND how
    predictive it is when it does, not stay fixed at whatever was set when the leg's
    real-world coverage was different. (Concrete case this catches: growth's coverage went
    from near-zero to 95%+ after Round 11 Priority 4's EDGAR PIT fix, but its declared weight
    was never revisited.) A leg with broad coverage but no measured predictive power is
    driven toward zero here just as surely as a leg with strong IC but almost no coverage --
    neither alone earns weight; a leg needs both to matter.

    Compute this ONLY from a train slice, never from validation or holdout -- calling it on
    data a candidate will later be graded against reintroduces exactly the search-then-split
    mistake this whole harness exists to prevent. Returns {} if every leg's coverage-weighted
    IC is zero or negative (nothing here to build a candidate from).
    """
    legs = list(legs or sorted({leg for period in periods
                                for scores in (period.get("leg_scores") or {}).values()
                                for leg in scores}))
    coverage = leg_coverage(periods, legs)
    standalone_ic = per_leg_ic(periods, legs, periods_per_year=periods_per_year)
    raw = {leg: coverage.get(leg, 0.0) * max(0.0, standalone_ic.get(leg, {}).get("mean_ic") or 0.0)
          for leg in legs}
    total = sum(raw.values())
    if not total:
        return {}
    return {leg: round(weight / total, 6) for leg, weight in raw.items() if weight}


def equal_weight_candidate(legs):
    """1/N per leg -- the no-opinion baseline every weighting scheme should beat.

    Exists so a search session always has a control that encodes no belief about which
    leg matters, not just hand-tuned or IC-derived candidates that could all be
    correlated in the same direction.
    """
    legs = list(legs)
    if not legs:
        return {}
    share = round(1.0 / len(legs), 6)
    return {leg: share for leg in legs}


def blended_full_coverage_candidate(recommended, legs, *, blend=0.5):
    """Average ``recommended`` with an equal-weight baseline over the FULL leg universe.

    ``recommended`` (e.g. reweighted_composite_a) may assign zero weight to legs it drops
    entirely -- that is a deliberate finding, not an oversight, but it also means the
    candidate never gets tested with every leg still contributing something. Blending
    against equal_weight_candidate(legs), which by construction covers every leg, keeps
    every leg's coefficient above zero (at least ``(1 - blend) / len(legs)``) while still
    pulling the mix toward whatever ``recommended`` emphasizes.
    """
    legs = list(legs)
    if not legs:
        return {}
    if not 0 <= blend <= 1:
        raise ValueError("blend must be within [0, 1]")
    equal = equal_weight_candidate(legs)
    raw = {leg: blend * recommended.get(leg, 0.0) + (1 - blend) * equal[leg] for leg in legs}
    total = sum(raw.values())
    if not total:
        return {}
    return {leg: round(weight / total, 6) for leg, weight in raw.items() if weight}


def period_sectors(period):
    """{ticker: sector} for one panel period, or {} if the panel predates sector tagging."""
    return period.get("sectors") or {}


def sectors_in_panel(periods):
    """Every distinct sector label present anywhere in the panel, sorted, excluding None."""
    found = set()
    for period in periods:
        found.update(sector for sector in period_sectors(period).values() if sector)
    return sorted(found)


def filter_periods_by_sector(periods, sector):
    """New period objects restricted to tickers tagged with ``sector``.

    Sector is the CURRENT GICS sector applied retroactively (panels carry no
    point-in-time sector history -- see ``backtest_swing.py``'s ``current_sector_map``,
    the same approximation this reuses), so this answers "how would each leg have scored
    on today's tech names historically", not "how would it have scored on whichever
    names were classified as tech at the time." A period with no tickers in the sector
    after filtering keeps an empty ``leg_scores``/``forward_returns``/``scores`` rather
    than being dropped, so period count stays stable across sectors for comparison.
    """
    filtered = []
    for period in periods:
        tickers = {ticker for ticker, name in period_sectors(period).items() if name == sector}
        restricted = {**period}
        for key in ("leg_scores", "forward_returns", "scores"):
            values = period.get(key) or {}
            restricted[key] = {ticker: value for ticker, value in values.items() if ticker in tickers}
        filtered.append(restricted)
    return filtered


def as_metric_periods(periods):
    """Periods with ``metric_scores`` standing in for ``leg_scores``.

    Every leg-level function here (``leg_coverage``, ``formula_weights``, ``per_leg_ic``,
    ``sector_weight_report``) reads ``period.get("leg_scores")`` and has no idea what a "leg"
    actually is beyond a named number per ticker -- an individual metric (trailing P/E, ROE,
    Piotroski F, ...) fits that shape exactly as well as a rolled-up category does. This lets
    every one of them run over ``backtest_monthly.py``'s ``metric_scores`` unchanged, so
    metric-level and leg-level sector analysis share one implementation rather than two. A
    panel built before ``metric_scores`` existed contributes an empty dict per period here,
    the same graceful-degradation shape ``period_sectors`` already uses for pre-sector panels.
    """
    return [{**period, "leg_scores": period.get("metric_scores") or {}} for period in periods]


def sector_weight_report(periods, *, legs=None, periods_per_year=12, minimum_periods=6):
    """formula_weights(), leg_coverage(), and standalone IC computed independently per
    sector -- answers whether different sectors warrant different leg weightings (a tech
    slice with heavy R&D/buyback-funded capital allocation, say, versus a utility slice
    priced mostly on financial_health) rather than assuming one weight vector fits every
    sector equally.

    Call this on a train slice only, same rule as ``formula_weights`` itself -- these
    per-sector weights are meant to be validated on a held-out slice before anyone trusts
    them, not read directly off the same periods a decision will be graded against.

    A sector with fewer than ``minimum_periods`` calendar periods carrying at least 5
    names is reported with ``formula_weights: None`` rather than a formula fit to noise
    from a handful of names.
    """
    report = {}
    for sector in sectors_in_panel(periods):
        sector_periods = filter_periods_by_sector(periods, sector)
        usable = sum(1 for period in sector_periods if len(period.get("leg_scores") or {}) >= 5)
        if usable < minimum_periods:
            report[sector] = {
                "usable_periods": usable,
                "formula_weights": None,
                "reason": f"fewer than {minimum_periods} periods with >=5 names in this sector",
            }
            continue
        sector_legs = list(legs) if legs else sorted({leg for period in sector_periods
                                                       for scores in (period.get("leg_scores") or {}).values()
                                                       for leg in scores})
        report[sector] = {
            "usable_periods": usable,
            "coverage": leg_coverage(sector_periods, sector_legs),
            "standalone_ic": per_leg_ic(sector_periods, sector_legs, periods_per_year=periods_per_year),
            "formula_weights": formula_weights(sector_periods, legs=sector_legs,
                                               periods_per_year=periods_per_year),
        }
    return report


def sector_candidate_report(panel, *, champion_weights, periods_per_year=12, quantiles=5,
                            trial_count=None, minimum_periods=6, extra_candidates=None):
    """The validation-side follow-up to ``sector_weight_report``: fit a candidate on one
    sector's OWN train slice, then test it on that SAME sector's validation slice -- data the
    candidate was never fit on -- to tell a real, generalizing sector pattern apart from a
    formula fit to noise in a thin, sector-restricted train sample.

    For each sector with enough usable train AND validation periods: builds
    ``sector_formula`` (``formula_weights`` on the sector's train slice only) and
    ``equal_weight`` (the no-opinion control), evaluates both alongside ``champion_weights``
    and any ``extra_candidates`` ([(name, weights)]) purely on the sector's validation slice,
    via the same ``walk_forward``/``evaluate_candidate`` apparatus every other candidate this
    session has been graded through -- same deflated-Sharpe gate, same trial count. A sector
    where ``sector_formula`` beats champion here is real evidence its pattern generalizes;
    one where it doesn't (walk_forward_efficiency collapsing toward zero or negative) is the
    classic overfitting signature this whole harness exists to catch, not a reason to trust
    the train-slice number anyway.

    Never touches ``panel.holdout`` -- this is a validation-side check, not the one-time
    final grade. A sector with fewer than ``minimum_periods`` usable periods in either train
    or validation is reported with ``candidates: None`` rather than a comparison built on too
    few names to mean anything.
    """
    trial_count = trial_count if trial_count is not None else total_variants_tested()
    report = {}
    for sector in sectors_in_panel(panel.train):
        sector_train = filter_periods_by_sector(panel.train, sector)
        sector_validation = filter_periods_by_sector(panel.validation, sector)
        usable_train = sum(1 for period in sector_train if len(period.get("leg_scores") or {}) >= 5)
        usable_validation = sum(1 for period in sector_validation
                                if len(period.get("leg_scores") or {}) >= 5)
        if usable_train < minimum_periods or usable_validation < minimum_periods:
            report[sector] = {
                "usable_train_periods": usable_train,
                "usable_validation_periods": usable_validation,
                "candidates": None,
                "reason": f"fewer than {minimum_periods} usable periods in this sector's "
                         "train or validation slice",
            }
            continue

        legs = sorted({leg for period in sector_train
                       for scores in (period.get("leg_scores") or {}).values() for leg in scores})
        sector_formula = formula_weights(sector_train, legs=legs, periods_per_year=periods_per_year)

        candidates = [("champion", champion_weights)]
        if sector_formula:
            candidates.append(("sector_formula", sector_formula))
        if legs:
            candidates.append(("equal_weight", equal_weight_candidate(legs)))
        candidates += list(extra_candidates or [])

        results = []
        for name, weights in candidates:
            train_result = walk_forward(score_with_weights(sector_train, weights),
                                        quantiles=quantiles, periods_per_year=periods_per_year)
            validation_verdict = evaluate_candidate(
                score_with_weights(sector_validation, weights), trials=trial_count,
                quantiles=quantiles, periods_per_year=periods_per_year)
            train_ic = train_result["ic"]["mean_ic"]
            validation_ic = validation_verdict["ic"]["mean_ic"]
            efficiency = (round(validation_ic / train_ic, 4)
                         if train_ic and validation_ic is not None else None)
            results.append({
                "name": name, "weights": weights,
                "train_mean_ic": train_ic, "validation_mean_ic": validation_ic,
                "walk_forward_efficiency": efficiency,
                "deflated_sharpe_probability": validation_verdict["deflated_sharpe_probability"],
                "ship": validation_verdict["ship"],
            })
        results.sort(key=lambda row: -(row["validation_mean_ic"] if row["validation_mean_ic"]
                                       is not None else float("-inf")))
        report[sector] = {
            "usable_train_periods": usable_train,
            "usable_validation_periods": usable_validation,
            "candidates": results,
        }
    return report


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
