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

import random

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

    @classmethod
    def from_slices(cls, train, validation, holdout):
        """A Panel whose three slices are supplied directly, for transforming an
        already-split panel without re-splitting it.

        The split-once-before-any-candidate-exists guarantee lives in ``__init__``; this is
        for applying the SAME row filter to slices that were already split there (a universe
        restriction, say), never for choosing new boundaries. Re-deriving a split from
        filtered data would silently move the train/validation line, which is exactly the
        leakage ``__init__`` exists to prevent -- so callers pass the original boundaries
        through and only the contents change.
        """
        panel = cls.__new__(cls)
        panel.train, panel.validation, panel.holdout = (tuple(train), tuple(validation),
                                                        tuple(holdout))
        if not (panel.train and panel.validation and panel.holdout):
            raise ValueError("from_slices requires a nonempty train, validation, and holdout")
        return panel


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


# "High-growth, good company", stated as explicit gates rather than left implicit.
#
# Two gates, not three, and deliberately so: profitability and financial_health are both
# measures of the same underlying idea (is this a sound business), so requiring each to clear
# its own independent floor both double-counts quality and compounds the selectivity
# multiplicatively -- three ~independent floors at 0.70/0.50/0.50 keep only ~7.5% of a
# cross-section, which on a per-sector slice leaves too few names per period to compute a rank
# IC on at all. Averaging the two quality percentiles into one gate is also the more robust
# reading: it lets a strongly profitable name with a merely-adequate balance sheet qualify,
# instead of dropping it on a single marginal metric. Net retention is ~0.30 x 0.50 = 15%.
GROWTH_QUALITY_GATES = {
    "growth": {"legs": ("growth",), "floor": 0.70},
    "quality": {"legs": ("profitability", "financial_health"), "floor": 0.50},
}


def _period_percentile_ranks(period, leg):
    """{ticker: percentile in [0, 1]} for one leg within one period's own cross-section."""
    scores = {ticker: legs.get(leg) for ticker, legs in (period.get("leg_scores") or {}).items()}
    scores = {ticker: value for ticker, value in scores.items() if isinstance(value, (int, float))}
    if not scores:
        return {}
    ordered = sorted(scores.items(), key=lambda item: item[1])
    last = max(len(ordered) - 1, 1)
    return {ticker: index / last for index, (ticker, _score) in enumerate(ordered)}


def filter_periods_by_quality_gates(periods, gates=None):
    """Restrict each period to names clearing every gate within that period's OWN
    cross-section.

    ``gates`` maps a label to ``{"legs": (...), "floor": percentile}``. A gate scores a name
    by the MEAN of its available legs' percentiles, so a multi-leg gate reads as one concept
    (see ``GROWTH_QUALITY_GATES``) rather than as several independent thresholds that compound
    away the cross-section.

    Ranking within each period separately is what keeps this point-in-time honest: a name
    qualifies on how it compared to its peers on that date, never against a threshold derived
    from the full history, which would leak later information backward. A name with no score
    for ANY leg in a gate fails that gate rather than passing by default -- missing data is
    not evidence of quality.

    Used to answer "do these weights rank high-growth, good companies well", which is a
    different question from "do they rank the whole universe well" -- and the one that matters
    if that is the kind of company the score exists to surface.
    """
    gates = GROWTH_QUALITY_GATES if gates is None else gates
    filtered = []
    for period in periods:
        ranks = {label: {leg: _period_percentile_ranks(period, leg) for leg in gate["legs"]}
                 for label, gate in gates.items()}
        qualifying = set()
        for ticker in (period.get("leg_scores") or {}):
            clears = True
            for label, gate in gates.items():
                available = [ranks[label][leg][ticker] for leg in gate["legs"]
                             if ticker in ranks[label][leg]]
                if not available or sum(available) / len(available) < gate["floor"]:
                    clears = False
                    break
            if clears:
                qualifying.add(ticker)
        restricted = {**period}
        for key in ("leg_scores", "forward_returns", "scores"):
            values = period.get(key) or {}
            restricted[key] = {ticker: value for ticker, value in values.items()
                               if ticker in qualifying}
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


# A sector "win" has to clear more than "beat champion once". Testing N sectors is N chances
# to find a winner by luck, and champion being badly calibrated in one sector is not the same
# finding as that sector genuinely wanting different weights.
SECTOR_EFFICIENCY_FLOOR = 0.5  # validation IC at least half the train IC: the pattern held


def sector_significance_threshold(sector_count, *, family_alpha=0.05, floor=3.0):
    """Bonferroni-adjusted |t| a per-sector result must clear, never below the repo's own
    existing ``clears_multiple_testing_bar`` threshold of 3.

    Searching 11 sectors for one that beats champion is 11 independent chances to find a
    winner in noise; grading each against the same bar a single pre-registered hypothesis
    would face is how a family of tests manufactures a false positive.
    """
    from statistics import NormalDist

    if sector_count < 1:
        return floor
    per_test_alpha = family_alpha / sector_count
    return max(floor, NormalDist().inv_cdf(1 - per_test_alpha / 2))


def sector_verdict(candidates, *, significance_threshold,
                   efficiency_floor=SECTOR_EFFICIENCY_FLOOR, formula_name="sector_formula"):
    """Whether one sector's fitted formula is real evidence or noise, as an explicit
    conjunction of gates rather than a single IC comparison.

    Every gate has to pass. Beating champion alone is the weakest possible reading -- it is
    equally consistent with "champion happens to be miscalibrated in this sector" -- so the
    formula must also beat the no-opinion equal-weight control, keep at least
    ``efficiency_floor`` of its train-slice IC when moved to validation (a collapse there is
    the overfitting signature), and clear a significance bar already adjusted for how many
    sectors were searched.
    """
    by_name = {row["name"]: row for row in candidates}
    formula = by_name.get(formula_name)
    if formula is None:
        return {"verdict": "NO_FORMULA", "gates": {},
                "reason": "formula_weights() produced nothing usable on this sector's train slice"}

    def ic(name):
        value = (by_name.get(name) or {}).get("validation_mean_ic")
        return value if value is not None else float("-inf")

    efficiency = formula.get("walk_forward_efficiency")
    t_stat = ((formula.get("validation_ic") or {}).get("t_stat"))
    gates = {
        "beats_champion": ic(formula_name) > ic("champion"),
        "beats_equal_weight": ic(formula_name) > ic("equal_weight"),
        "efficiency_holds": efficiency is not None and efficiency >= efficiency_floor,
        # Directional on purpose, not abs(): a strongly NEGATIVE t is a significant result
        # that the weights rank backwards, which must never read as evidence for them. The
        # real Consumer Defensive slice hit exactly this -- sector_formula scored IC -0.2627
        # at t = -3.457, clearing |t| >= 3 while being the worst candidate in its sector.
        # The other gates caught it there, but only incidentally; a sector where champion and
        # equal_weight were even more negative would have let an anti-predictive formula
        # through on a conjunction that looks airtight.
        "clears_sector_adjusted_significance":
            t_stat is not None and t_stat >= significance_threshold,
    }
    failed = [name for name, passed in gates.items() if not passed]
    return {
        "verdict": "REAL" if not failed else "NOT_ESTABLISHED",
        "gates": gates,
        "failed_gates": failed,
        "significance_threshold": round(significance_threshold, 4),
        "efficiency_floor": efficiency_floor,
    }


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
                "validation_ic": validation_verdict["ic"],
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

    # Graded only once every sector's own result exists: the significance bar depends on how
    # many sectors were actually searched, which isn't known until the loop finishes.
    threshold = sector_significance_threshold(
        sum(1 for row in report.values() if row.get("candidates")))
    for row in report.values():
        if row.get("candidates"):
            row["verdict"] = sector_verdict(row["candidates"], significance_threshold=threshold)
    return report


def _solve_linear_system(matrix, vector):
    """Solve ``matrix @ x = vector`` by Gaussian elimination with partial pivoting.

    Pure-stdlib on purpose: the pipeline carries no numpy, and a ridge system here is at
    most legs x legs (8x8), where this is instant and exact enough.
    """
    size = len(vector)
    augmented = [list(row) + [value] for row, value in zip(matrix, vector)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda r: abs(augmented[r][col]))
        if abs(augmented[pivot][col]) < 1e-12:
            return None
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        for row in range(col + 1, size):
            factor = augmented[row][col] / augmented[col][col]
            for k in range(col, size + 1):
                augmented[row][k] -= factor * augmented[col][k]
    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        residual = augmented[row][size] - sum(augmented[row][k] * solution[k]
                                              for k in range(row + 1, size))
        solution[row] = residual / augmented[row][row]
    return solution


def ridge_weights(periods, *, legs=None, lam=1.0):
    """Fama-MacBeth-style ridge weights: per period, regress forward returns on ALL legs
    jointly (cross-sectionally standardized, ridge-shrunk), then average the coefficients
    across periods and keep the positive part as a weight vector.

    The supervised-learning fix for ``formula_weights``' structural blind spot: that formula
    scores each leg standalone, so two correlated legs (profitability and financial_health
    move together by construction) each collect full credit for the same information. A
    joint regression splits credit between correlated legs instead of double-counting; the
    ridge penalty (``lam``, scaled by the cross-section size) keeps the 7x7 system stable on
    the small samples a sector slice actually has, shrinking coefficients toward zero rather
    than letting near-collinear legs trade huge offsetting loadings.

    Legs are z-scored within each period's own cross-section (missing values imputed at the
    cross-sectional mean, i.e. zero -- absence carries no information, matching how
    ``composite_score`` renormalizes around missing legs rather than penalizing them), so no
    period's scale leaks into another and the averaged coefficients are comparable across
    time. Negative averaged coefficients clip to zero: production weights are long-only
    shares by contract, and a leg whose best joint use is as a SHORT signal is a finding to
    surface separately, not to smuggle in as a negative weight ``composite_score`` would
    renormalize incoherently. Fit on train (or fit) slices only, same rule as
    ``formula_weights``. Returns {} when nothing earns positive weight.
    """
    legs = list(legs or sorted({leg for period in periods
                                for scores in (period.get("leg_scores") or {}).values()
                                for leg in scores}))
    if not legs:
        return {}
    size = len(legs)
    coefficient_sums = [0.0] * size
    usable_periods = 0
    for period in periods:
        forwards = period.get("forward_returns") or {}
        leg_scores = period.get("leg_scores") or {}
        tickers = [ticker for ticker in forwards
                   if forwards[ticker] is not None and ticker in leg_scores]
        if len(tickers) < max(5, size + 2):
            continue
        columns = []
        for leg in legs:
            values = [leg_scores[ticker].get(leg) for ticker in tickers]
            present = [value for value in values if isinstance(value, (int, float))]
            if len(present) < 2:
                columns.append([0.0] * len(tickers))
                continue
            mean = sum(present) / len(present)
            variance = sum((value - mean) ** 2 for value in present) / len(present)
            spread = variance ** 0.5
            columns.append([((value - mean) / spread if isinstance(value, (int, float))
                            and spread else 0.0) for value in values])
        returns = [forwards[ticker] for ticker in tickers]
        mean_return = sum(returns) / len(returns)
        centered = [value - mean_return for value in returns]
        rows = len(tickers)
        gram = [[sum(columns[i][r] * columns[j][r] for r in range(rows))
                 for j in range(size)] for i in range(size)]
        for i in range(size):
            gram[i][i] += lam * rows
        moment = [sum(columns[i][r] * centered[r] for r in range(rows)) for i in range(size)]
        beta = _solve_linear_system(gram, moment)
        if beta is None:
            continue
        for i in range(size):
            coefficient_sums[i] += beta[i]
        usable_periods += 1
    if not usable_periods:
        return {}
    averaged = [total / usable_periods for total in coefficient_sums]
    clipped = {leg: coefficient for leg, coefficient in zip(legs, averaged) if coefficient > 0}
    total = sum(clipped.values())
    if not total:
        return {}
    return {leg: round(coefficient / total, 6) for leg, coefficient in clipped.items()}


def _mean_ic(periods, weights):
    """Plain mean of the per-period rank ICs for one weight vector, and how many resolved."""
    series = [value for value in _configuration_ic_series(periods, weights) if value is not None]
    if not series:
        return None, 0
    return sum(series) / len(series), len(series)


def _sector_search_pool(fit_periods, legs, *, count, seed):
    """The candidate pool one sector's search draws from -- every entry derived from the
    sector's own fit slice or from pure randomness, never from selection or validation data.

    Deliberate mix rather than random-only: ``formula`` is the coverage-x-IC point estimate;
    the ``shrunk_*`` entries pull it toward equal weight (its known failure mode is
    collapsing to one or two legs when most train ICs are negative -- shrinkage keeps the
    idea while restoring breadth); the ``ridge_*`` entries are the supervised-learning
    candidates (``ridge_weights``: legs regressed JOINTLY on forward returns, so correlated
    legs split credit instead of double-counting, at three shrinkage strengths);
    ``equal_weight`` anchors the no-opinion baseline; the range-sampled remainder covers
    weight space the structured guesses don't.
    """
    pool = [("equal_weight", equal_weight_candidate(legs))]
    fitted = formula_weights(fit_periods, legs=legs)
    if fitted:
        pool.append(("formula", fitted))
        for share in (0.25, 0.5, 0.75):
            blended = blended_full_coverage_candidate(fitted, legs, blend=share)
            if blended:
                pool.append((f"shrunk_{int(share * 100)}", blended))
    for lam in (0.1, 1.0, 10.0):
        learned = ridge_weights(fit_periods, legs=legs, lam=lam)
        if learned:
            pool.append((f"ridge_{lam:g}", learned))
    rng = random.Random(seed)
    for index in range(count):
        raw = {leg: rng.uniform(0.0, 1.0) for leg in legs}
        total = sum(raw.values()) or 1.0
        pool.append((f"random_{index:03d}",
                     {leg: round(value / total, 6) for leg, value in raw.items()}))
    return pool


def sector_weight_search(panel, *, champion_weights, count=200, seed=0, periods_per_year=12,
                         quantiles=5, trial_count=None, minimum_periods=6,
                         fit_fraction=0.6, pbo_splits=DEFAULT_PBO_SPLITS):
    """An actual per-sector weight SEARCH, not one guess per sector.

    ``sector_candidate_report`` grades exactly one fitted candidate per sector
    (``formula_weights``), whose max(0, train-IC) construction collapses to one or two legs
    whenever most legs' train ICs are negative -- the observed failure on the real panel.
    A sector failing that test shows one brittle guess failed, not that no sector-specific
    weighting exists. This searches properly, with the selection step itself kept inside the
    train slice so validation stays a genuine out-of-sample grade:

    1. The sector's train slice is split chronologically into fit (``fit_fraction``) and
       select (the rest). Candidates are built from fit only (see ``_sector_search_pool``).
    2. Every candidate is ranked by mean IC on the select slice. The winner is chosen there
       -- validation is never consulted for selection.
    3. PBO (CSCV) is computed across the whole pool on the full train slice, so a sector
       whose "winner" is just the luckiest of ``count`` coin flips announces itself.
    4. Only the winner (plus champion and equal_weight as references) is graded on the
       sector's validation slice, with the deflated-Sharpe trial count charged for the FULL
       pool searched in that sector, not one -- the honest price of searching.
    5. The same four ``sector_verdict`` gates apply, with the Bonferroni threshold set by
       how many sectors were searched. Never touches ``panel.holdout``.
    """
    trial_count = trial_count if trial_count is not None else total_variants_tested()
    report = {}
    for sector in sectors_in_panel(panel.train):
        sector_train = filter_periods_by_sector(panel.train, sector)
        sector_validation = filter_periods_by_sector(panel.validation, sector)
        usable_train = sum(1 for period in sector_train
                           if len(period.get("leg_scores") or {}) >= 5)
        usable_validation = sum(1 for period in sector_validation
                                if len(period.get("leg_scores") or {}) >= 5)
        fit_end = int(len(sector_train) * fit_fraction)
        fit_periods, select_periods = sector_train[:fit_end], sector_train[fit_end:]
        usable_select = sum(1 for period in select_periods
                            if len(period.get("leg_scores") or {}) >= 5)
        if usable_train < minimum_periods or usable_validation < minimum_periods \
                or usable_select < minimum_periods:
            report[sector] = {
                "usable_train_periods": usable_train,
                "usable_select_periods": usable_select,
                "usable_validation_periods": usable_validation,
                "candidates": None,
                "reason": f"fewer than {minimum_periods} usable periods in this sector's "
                         "fit, select, or validation slice",
            }
            continue

        legs = sorted({leg for period in sector_train
                       for scores in (period.get("leg_scores") or {}).values()
                       for leg in scores})
        pool = _sector_search_pool(fit_periods, legs, count=count, seed=seed)

        ranked = []
        for name, weights in pool:
            select_ic, select_observations = _mean_ic(select_periods, weights)
            if select_ic is not None and select_observations >= 5:
                ranked.append((select_ic, name, weights))
        if not ranked:
            report[sector] = {
                "usable_train_periods": usable_train,
                "usable_select_periods": usable_select,
                "usable_validation_periods": usable_validation,
                "candidates": None,
                "reason": "no pool candidate produced 5+ scoreable select periods",
            }
            continue
        ranked.sort(key=lambda row: (-row[0], row[1]))
        winner_select_ic, winner_name, winner_weights = ranked[0]

        performance_matrix = []
        series_by_candidate = [_configuration_ic_series(sector_train, weights)
                               for _name, weights in pool]
        for period_index in range(len(sector_train)):
            row = [series[period_index] for series in series_by_candidate]
            if all(value is not None for value in row):
                performance_matrix.append(row)
        search_pbo = probability_of_backtest_overfitting(performance_matrix, splits=pbo_splits)

        # The search's own price: this sector tried len(pool) configurations before this
        # one candidate ever reached validation, on top of the programme-wide count.
        sector_trials = trial_count + len(pool)
        results = []
        for name, weights, select_ic in (
                ("search_winner", winner_weights, winner_select_ic),
                ("champion", champion_weights, None),
                ("equal_weight", equal_weight_candidate(legs), None)):
            verdict = evaluate_candidate(
                score_with_weights(sector_validation, weights), trials=sector_trials,
                quantiles=quantiles, periods_per_year=periods_per_year)
            validation_ic = verdict["ic"]["mean_ic"]
            efficiency = (round(validation_ic / select_ic, 4)
                          if select_ic and validation_ic is not None else None)
            results.append({
                "name": name, "weights": weights,
                "picked_as": winner_name if name == "search_winner" else None,
                "select_mean_ic": round(select_ic, 4) if select_ic is not None else None,
                "validation_mean_ic": validation_ic,
                "walk_forward_efficiency": efficiency,
                "validation_ic": verdict["ic"],
                "deflated_sharpe_probability": verdict["deflated_sharpe_probability"],
                "trials_considered": sector_trials,
                "ship": verdict["ship"],
            })
        report[sector] = {
            "usable_train_periods": usable_train,
            "usable_select_periods": usable_select,
            "usable_validation_periods": usable_validation,
            "pool_size": len(pool),
            "search_pbo": search_pbo,
            "legs": legs,
            "candidates": results,
        }

    threshold = sector_significance_threshold(
        sum(1 for row in report.values() if row.get("candidates")))
    for row in report.values():
        if row.get("candidates"):
            row["verdict"] = sector_verdict(row["candidates"], significance_threshold=threshold,
                                            formula_name="search_winner")
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
