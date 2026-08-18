"""Signal-quality and monitoring metrics, split by what needs a live sample and what does not.

The dashboard has always led with returns. Returns are the slowest possible way to learn
whether a scoring model works: at eighteen days live, the return series carries no
information at all, and it will take years before it does. Almost everything worth knowing
about the signal can be measured today, on the backtest panel, without waiting - whether the
composite ranks anything, which legs earn their weight, where the edge decays, and whether
the configuration that won the search would have won out of sample.

So every metric published here carries an explicit ``requires_live_sample`` flag:

  * **False** - computable now from the point-in-time backtest panel. Rank IC and its decay,
    per-leg and drop-one-leg contribution, leg redundancy, quantile monotonicity, score
    autocorrelation, factor loadings, concentration, breakeven alpha, and the four
    overfitting statistics. These are the reads that answer "is there an edge here at all".
  * **True** - needs observations that only accumulate once real money is trading. Fill
    quality and implementation shortfall, the distribution-shape family (Omega, Ulcer,
    CVaR, skew), and the drift alarms that compare live behaviour against the backtest.
    These are wired up and reported with their own sample counters, so they start reading
    the day the sample exists rather than the day someone remembers to build them.

Nothing here fabricates a value it cannot compute. A metric with no usable input publishes
its status and the reason, which is a more useful artifact than a plausible number.

    python pipeline/signal_metrics.py --help
"""

import argparse
from collections import Counter, defaultdict
import json
import math
import os
import statistics
from datetime import datetime, timezone

import evaluation
import risk_metrics
import sector_attribution
import stress_scenarios
from common import LOG, load_json, save_json

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = load_json("settings.json", from_config=True) or {}
PUBLIC_NAME = "validation/signal_metrics.json"

BACKTEST_PATH = os.path.join(HERE, "backtest_monthly_results.json")
OPTIMIZER_PATH = os.path.join(HERE, "optimize_weights_results.json")
PANEL_PATH = os.path.join(HERE, "backtest_signal_panel.json")
PIT_ROOT = os.path.join(HERE, "pit_store")
SHADOW_ROOT = os.path.join(HERE, "shadow_store")
SECTOR_WEIGHT_HISTORY_PATH = os.path.join(
    HERE, "data", "validation", "sector_weight_history.jsonl")
UNIVERSE_HISTORY_PATH = os.path.join(HERE, "data", "pit", "universe.jsonl")
LIVE_EXECUTION_PATH = os.path.join(HERE, "data", "validation", "live_execution.json")

TRADING_DAYS = 252
MONTHS_PER_YEAR = 12
# Horizons the signal is graded at. 1 and 5 days say whether the score is tradable at all
# after cost; 21 and 63 say where the fundamental content actually lives.
HORIZON_TRADING_DAYS = {"1d": 1, "5d": 5, "21d": 21, "63d": 63}
FACTOR_KEYS = ("market_excess", "size", "value", "profitability", "investment", "momentum")

# Kill thresholds, stated up front so a failing metric fails visibly rather than being
# reinterpreted after the fact.
MINIMUM_MEAN_IC = evaluation.MEANINGFUL_IC
MINIMUM_IC_IR = 0.3
REDUNDANT_LEG_CORRELATION = 0.7
MAXIMUM_PBO = 0.5
FEATURE_PSI_MINIMUM_DAYS = 60
FEATURE_PSI_WINDOW_DAYS = 20
FEATURE_PSI_KILL_THRESHOLD = 0.25
DIVERGENCE_MINIMUM_OBSERVATIONS = 20
# Shared two-tailed 95% z-value -- used both for the live-vs-backtest divergence
# z-test and for the backtest IC confidence interval `live_vs_backtest_ic` compares
# against. Same constant ic_harness.py's own IC interval uses.
CONFIDENCE_INTERVAL_Z = 1.96
PRICE_STALE_AFTER_HOURS = 36
MAXIMUM_PERCENT_OF_ADV = 5
SEARCH_SURVIVAL_MINIMUM = 0.95
MAXIMUM_BETA_SWING = 0.3
MINIMUM_SECTOR_CLASSIFICATION_COVERAGE = 0.8
MOMENTUM_LOADING_KILL_THRESHOLD = -0.1
UNEXPLAINED_POSITION_DIFFERENCE_BPS = 10
MINIMUM_BOOTSTRAP_OBSERVATIONS = 40
VAR_BACKTEST_WINDOW = TRADING_DAYS
VAR_BACKTEST_MINIMUM_OBSERVATIONS = VAR_BACKTEST_WINDOW + 21
VAR_CONFIDENCES = (0.95, 0.99)
STRESS_2022_START, STRESS_2022_END = "2022-01-01", "2022-12-31"
STRESS_2022_MINIMUM_DAYS = 60

GROUPS = [
    {"id": "signal", "letter": "A", "title": "Signal quality",
     "summary": "Does the composite predict anything, and which legs earn their weight.",
     "requires_live_sample": False},
    {"id": "construction", "letter": "B", "title": "Construction diagnostics",
     "summary": "The factor and concentration bets being made whether or not they were intended.",
     "requires_live_sample": False},
    {"id": "cost", "letter": "C", "title": "Cost and capacity",
     "summary": "What the signal must earn before trading it is worth doing.",
     "requires_live_sample": False},
    {"id": "honesty", "letter": "D", "title": "Statistical honesty",
     "summary": "What the search that produced these weights costs in credibility.",
     "requires_live_sample": False},
    {"id": "distribution", "letter": "E", "title": "Distribution shape",
     "summary": "Tail and drawdown behaviour. Wired now, readable after roughly six months live.",
     "requires_live_sample": True},
    {"id": "monitoring", "letter": "F", "title": "Drift alarms",
     "summary": "Live behaviour against the backtest that predicted it.",
     "requires_live_sample": True},
    {"id": "risk_adjusted", "letter": "G", "title": "Classic risk-adjusted return",
     "summary": "Return per unit of systematic risk, and the single-factor alpha left once beta is priced in.",
     "requires_live_sample": False},
    {"id": "tax_stress", "letter": "H", "title": "Tax and stress",
     "summary": "After-tax reality, and how this book's own exposures fared in a known stress window.",
     "requires_live_sample": False},
]

CADENCE = [
    {"frequency": "Daily", "items": "Reconciliation, data quality, fill rate, shortfall bps, exposure drift"},
    {"frequency": "Weekly", "items": "Rolling IC, turnover, factor betas, effective N"},
    {"frequency": "Monthly", "items": "Per-leg IC, quantile spreads, cost versus breakeven, PSI"},
    {"frequency": "Quarterly", "items": "DSR, PSR, MinTRL, factor attribution, distribution shape once the sample allows"},
    {"frequency": "Annually or on any refit", "items": "PBO, drop-one-leg, re-derived weights"},
]


# Distinguishes "read this from disk" from "this input does not exist", which report
# assembly has to treat differently or a missing file silently becomes the live file.
_UNSET = object()


# ---------------- metric construction ----------------

def metric(identifier, group, label, *, value=None, display=None, reads=None,
           kill_threshold=None, kill_threshold_value=None, comparison=None,
           breached=None, cadence=None, requires_live_sample=False,
           status=None, status_message=None, detail=None, source=None,
           observations=None, required_observations=None, backtest_reference=None):
    """One published metric. ``status`` is derived from the value unless stated.

    ``kill_threshold`` is the prose description shown next to the metric; it has never
    been guaranteed to be a number, and for several metrics it fundamentally cannot be
    (a shape condition, a comparison against a quantity this pipeline doesn't compute
    yet). ``kill_threshold_value`` + ``comparison`` are the numeric, same-scale-as-``value``
    pair a bullet chart needs, and are populated only where that pair genuinely exists and
    means the same thing as ``value`` -- never derived from ``kill_threshold`` text, and
    never fabricated for a metric that doesn't have one. ``comparison`` is ``"lt"``
    (breach when ``value < kill_threshold_value``) or ``"gt"`` (breach when
    ``value > kill_threshold_value``).
    """
    if status is None:
        status = "ready" if value is not None else "unavailable"
    return {
        "id": identifier,
        "group": group,
        "label": label,
        "value": value,
        "display": display if display is not None else _display(value),
        "reads": reads,
        "kill_threshold": kill_threshold,
        "kill_threshold_value": kill_threshold_value,
        "comparison": comparison,
        "breached": breached,
        "cadence": cadence,
        "requires_live_sample": requires_live_sample,
        "status": status,
        "status_message": status_message,
        "observations": observations,
        "required_observations": required_observations,
        "backtest_reference": backtest_reference,
        "detail": detail,
        "source": source,
    }


def _display(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _pending(identifier, group, label, message, **kwargs):
    """A metric whose machinery exists but whose input does not, said plainly."""
    kwargs.setdefault("status", "awaiting_input")
    return metric(identifier, group, label, status_message=message, **kwargs)


# ---------------- inputs ----------------

def _read_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except ValueError:
        LOG.warn(f"Unreadable JSON at {path}")
        return None


def _read_jsonl(path):
    """Read an append-only store while preserving valid rows around a torn line."""
    if not os.path.exists(path):
        return []
    rows = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return rows


def _parse_time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def point_in_time_days(root=PIT_ROOT):
    """Latest complete refresh per date, so intraday runs are not extra PSI samples."""
    days = []
    if not os.path.isdir(root):
        return days
    names = []
    for item in os.listdir(root):
        if not item.endswith(".jsonl"):
            continue
        try:
            datetime.strptime(item[:-6], "%Y-%m-%d")
        except ValueError:
            continue
        names.append(item)
    for name in sorted(names):
        refreshes = defaultdict(list)
        for row in _read_jsonl(os.path.join(root, name)):
            refreshes[row.get("refresh_id")].append(row)
        if not refreshes:
            continue
        latest_id, rows = max(
            refreshes.items(),
            key=lambda item: max(str(row.get("recorded_at") or "") for row in item[1]),
        )
        days.append({"date": name[:-6], "refresh_id": latest_id, "rows": rows})
    return days


def live_sample(root=PIT_ROOT):
    """How much genuinely live, point-in-time history exists. The gate on every F metric."""
    if not os.path.isdir(root):
        return {"days": 0, "refreshes": 0, "first_date": None, "last_date": None}
    dates = sorted(name[:-6] for name in os.listdir(root) if name.endswith(".jsonl"))
    refreshes = set()
    for name in dates:
        with open(os.path.join(root, f"{name}.jsonl")) as handle:
            for line in handle:
                if line.strip():
                    try:
                        refreshes.add(json.loads(line).get("refresh_id"))
                    except ValueError:
                        continue
    return {"days": len(dates), "refreshes": len(refreshes),
            "first_date": dates[0] if dates else None,
            "last_date": dates[-1] if dates else None}


def daily_returns_from_history(history):
    """Daily simple returns from a ``[{date, value}]`` equity curve."""
    values = [row.get("value") for row in history or [] if row.get("value")]
    return [later / earlier - 1 for earlier, later in zip(values, values[1:]) if earlier]


def monthly_returns_from_history(history):
    """Month-end value series compressed into monthly returns, keyed ``YYYY-MM``."""
    by_month = {}
    for row in history or []:
        date, value = row.get("date"), row.get("value")
        if date and value:
            by_month[str(date)[:7]] = value
    months = sorted(by_month)
    return {month: by_month[month] / by_month[previous] - 1
            for previous, month in zip(months, months[1:]) if by_month[previous]}


# ---------------- A. signal quality ----------------

def signal_metrics(panel):
    """Everything that needs a scored panel with forward returns - and nothing that does not.

    The panel is written by ``backtest_monthly.py --panel-out``: one row per rebalance date
    per ticker, carrying the composite score, the individual leg scores, and the forward
    return at each graded horizon. Without it these stay pending, because the alternative -
    grading today's scores against today's returns - is look-ahead, not evidence.

    ``per_leg_ic``, ``drop_one_leg`` and ``leg_correlation`` publish a count (dead legs,
    harmful legs, redundant pairs) as ``value``, and each already treats "any breach at all"
    as the failure condition -- ``breached`` below is exactly ``bool(count)``. So although the
    prose ``kill_threshold`` names a different, per-leg quantity (an IC, a delta, a
    correlation), the count itself has a real, same-scale threshold: zero. ``kill_threshold_value
    =0, comparison="gt"`` states that explicitly rather than leaving a metric whose breach
    condition is this simple without a bullet.
    """
    if not panel:
        message = ("No scored panel found. Run pipeline/backtest_monthly.py --panel-out to "
                   "write one; every metric in this group is computable from it today.")
        return [
            _pending(f"rank_ic_{label}", "signal", f"Rank IC ({label})", message,
                     reads="Spearman correlation of score against forward return.",
                     kill_threshold=f"Mean IC < {MINIMUM_MEAN_IC}",
                     kill_threshold_value=MINIMUM_MEAN_IC, comparison="lt", cadence="Weekly")
            for label in HORIZON_TRADING_DAYS
        ] + [
            _pending("ic_ir", "signal", "IC-IR (annualized)", message,
                     reads="Consistency of prediction, not just its average.",
                     kill_threshold=f"IC-IR < {MINIMUM_IC_IR}",
                     kill_threshold_value=MINIMUM_IC_IR, comparison="lt", cadence="Weekly"),
            _pending("ic_bootstrap_ci", "signal", "Bootstrap IC confidence interval", message,
                     reads="Nonparametric confidence interval on mean rank IC.",
                     cadence="Weekly"),
            _pending("ic_decay", "signal", "IC decay curve", message,
                     reads="Which horizon the edge lives at.", cadence="Monthly"),
            _pending("per_leg_ic", "signal", "Per-leg IC", message,
                     reads="Which legs predict on their own.",
                     kill_threshold="Any leg IC around zero",
                     kill_threshold_value=0, comparison="gt", cadence="Monthly"),
            _pending("drop_one_leg", "signal", "Drop-one-leg delta IC", message,
                     reads="Marginal contribution of each leg to the composite.",
                     kill_threshold="Negative delta means the leg hurts",
                     kill_threshold_value=0, comparison="gt",
                     cadence="Annually or on any refit"),
            _pending("leg_correlation", "signal", "Leg correlation matrix", message,
                     reads="Redundancy between legs.",
                     kill_threshold=f"Correlation > {REDUNDANT_LEG_CORRELATION}",
                     kill_threshold_value=0, comparison="gt", cadence="Monthly"),
            _pending("quantile_spread", "signal", "Quantile spread and monotonicity", message,
                     reads="Whether the whole ranking works or only one tail.",
                     kill_threshold="Non-monotonic quantiles", cadence="Monthly"),
            _pending("score_autocorrelation", "signal", "Score autocorrelation", message,
                     reads="Turnover implied by the signal before a single trade.",
                     cadence="Weekly"),
        ]

    periods = panel.get("periods") or []
    weights = panel.get("leg_weights") or {}
    horizons = [label for label in HORIZON_TRADING_DAYS
                if any((period.get("forward_returns_by_horizon") or {}).get(label)
                       for period in periods)]
    decay = evaluation.ic_decay_curve(periods, horizons)
    graded = panel.get("primary_horizon") or (horizons[-1] if horizons else None)

    rows = []
    for label in HORIZON_TRADING_DAYS:
        summary = decay["horizons"].get(label)
        if not summary:
            rows.append(_pending(f"rank_ic_{label}", "signal", f"Rank IC ({label})",
                                 f"The panel carries no {label} forward returns.",
                                 kill_threshold=f"Mean IC < {MINIMUM_MEAN_IC}",
                                 kill_threshold_value=MINIMUM_MEAN_IC, comparison="lt", cadence="Weekly"))
            continue
        rows.append(metric(
            f"rank_ic_{label}", "signal", f"Rank IC ({label})",
            value=summary["mean_ic"], detail=summary,
            reads="Spearman correlation of score against forward return.",
            kill_threshold=f"Mean IC < {MINIMUM_MEAN_IC}",
            kill_threshold_value=MINIMUM_MEAN_IC, comparison="lt",
            breached=(summary["mean_ic"] is not None
                      and summary["mean_ic"] < MINIMUM_MEAN_IC),
            observations=summary["periods"], cadence="Weekly", source="backtest panel"))

    primary = decay["horizons"].get(graded) or {}
    icir = primary.get("icir")
    rows.append(metric("ic_ir", "signal", "IC-IR (annualized)", value=icir,
                       reads="Consistency of prediction, not just its average.",
                       kill_threshold=f"IC-IR < {MINIMUM_IC_IR}",
                       kill_threshold_value=MINIMUM_IC_IR, comparison="lt",
                       breached=icir is not None and icir < MINIMUM_IC_IR,
                       detail={"horizon": graded, "t_stat": primary.get("t_stat"),
                               "hit_rate": primary.get("hit_rate")},
                       observations=primary.get("periods"), cadence="Weekly",
                       source="backtest panel"))

    ic_bootstrap = evaluation.bootstrap_ic_confidence_interval(primary.get("series") or [])
    if ic_bootstrap:
        lower, upper = ic_bootstrap["ic_ci_95"]
        rows.append(metric(
            "ic_bootstrap_ci", "signal", "Bootstrap IC confidence interval",
            value=ic_bootstrap["mean_ic"], display=f"{ic_bootstrap['mean_ic']:.3f} (95% CI {lower:.3f} to {upper:.3f})",
            reads="Nonparametric confidence interval on mean rank IC -- doesn't assume the "
                  "period IC series is normal, unlike IC-IR's t-statistic.",
            kill_threshold="95% CI includes zero",
            breached=lower <= 0 <= upper,
            detail=ic_bootstrap, observations=ic_bootstrap["observations"], cadence="Weekly",
            source="block bootstrap of the backtest panel's per-period rank IC"))
    else:
        rows.append(_pending(
            "ic_bootstrap_ci", "signal", "Bootstrap IC confidence interval",
            f"Needs at least 10 graded periods at the {graded} horizon; "
            f"{len(primary.get('series') or [])} available.",
            reads="Nonparametric confidence interval on mean rank IC.", cadence="Weekly"))

    rows.append(metric("ic_decay", "signal", "IC decay curve",
                       value=decay["peak_horizon"], display=decay["peak_horizon"],
                       reads="Which horizon the edge lives at, against the cost of trading it.",
                       detail={label: summary["mean_ic"] for label, summary in decay["horizons"].items()},
                       cadence="Monthly", source="backtest panel"))

    legs = evaluation.per_leg_ic(periods, list(weights) or None)
    dead = [leg for leg, summary in legs.items()
            if summary["mean_ic"] is not None and summary["mean_ic"] < MINIMUM_MEAN_IC]
    rows.append(metric("per_leg_ic", "signal", "Per-leg IC",
                       value=len(dead) if legs else None,
                       display=f"{len(dead)} of {len(legs)} legs below {MINIMUM_MEAN_IC}" if legs else None,
                       reads="Which legs predict on their own rather than riding the blend.",
                       kill_threshold=f"Any leg IC below {MINIMUM_MEAN_IC}",
                       kill_threshold_value=0, comparison="gt", breached=bool(dead),
                       detail={leg: summary["mean_ic"] for leg, summary in legs.items()},
                       cadence="Monthly", source="backtest panel"))

    if weights:
        dropped = evaluation.drop_one_leg_delta_ic(periods, weights)
        harmful = [leg for leg, row in dropped["legs"].items() if row["hurts_composite"]]
        rows.append(metric("drop_one_leg", "signal", "Drop-one-leg delta IC",
                           value=len(harmful),
                           display=f"{len(harmful)} leg{'' if len(harmful) == 1 else 's'} hurting the composite",
                           reads="Marginal contribution of each leg. The test that says whether "
                                 "assigned weights are defensible.",
                           kill_threshold="Negative delta means the leg is hurting the composite",
                           kill_threshold_value=0, comparison="gt",
                           breached=bool(harmful), detail=dropped,
                           cadence="Annually or on any refit", source="backtest panel"))
    else:
        rows.append(_pending("drop_one_leg", "signal", "Drop-one-leg delta IC",
                             "The panel carries no leg weights to drop.",
                             kill_threshold_value=0, comparison="gt",
                             cadence="Annually or on any refit"))

    correlation = evaluation.leg_correlation_matrix(periods, list(weights) or None)
    rows.append(metric("leg_correlation", "signal", "Leg correlation matrix",
                       value=len(correlation["redundant_pairs"]),
                       display=(f"{len(correlation['redundant_pairs'])} redundant pair"
                                f"{'' if len(correlation['redundant_pairs']) == 1 else 's'}"),
                       reads="Redundancy between legs. Two correlated legs are one leg counted twice.",
                       kill_threshold=f"Correlation above {REDUNDANT_LEG_CORRELATION}",
                       kill_threshold_value=0, comparison="gt",
                       breached=bool(correlation["redundant_pairs"]), detail=correlation,
                       cadence="Monthly", source="backtest panel"))

    spread = _quantile_spread(periods, graded)
    rows.append(metric("quantile_spread", "signal", "Quantile spread and monotonicity",
                       value=spread.get("mean_spread"),
                       display=None if spread.get("mean_spread") is None
                       else f"{spread['mean_spread'] * 100:.2f}% top minus bottom",
                       reads="Whether the whole ranking works or one tail is doing all of it.",
                       kill_threshold="Non-monotonic quantiles are fragile",
                       breached=spread.get("monotonic") is False, detail=spread,
                       observations=spread.get("periods"), cadence="Monthly",
                       source="backtest panel"))

    autocorrelation = evaluation.rank_autocorrelation(periods)
    rows.append(metric("score_autocorrelation", "signal", "Score autocorrelation",
                       value=autocorrelation["mean_autocorrelation"],
                       reads="Turnover the signal implies before a single trade is placed.",
                       detail=autocorrelation, observations=autocorrelation["periods"],
                       cadence="Weekly", source="backtest panel"))
    return rows


def _quantile_spread(periods, horizon, quantiles=5):
    """Mean top-minus-bottom quantile return and how often the quantiles line up in order."""
    spreads, monotone, buckets = [], 0, 0
    for period in periods:
        forwards = (period.get("forward_returns_by_horizon") or {}).get(horizon) or {}
        scores = period.get("scores") or {}
        tickers = [ticker for ticker in scores if ticker in forwards]
        result = evaluation.quantile_spread(evaluation.quantile_buckets(
            [scores[ticker] for ticker in tickers],
            [forwards[ticker] for ticker in tickers], quantiles))
        if not result:
            continue
        buckets += 1
        spreads.append(result["top_minus_bottom"])
        monotone += 1 if result["monotonic"] else 0
    if not spreads:
        return {"periods": 0, "mean_spread": None, "monotonic": None}
    return {
        "periods": buckets,
        "horizon": horizon,
        "mean_spread": round(sum(spreads) / len(spreads), 4),
        "monotonic_periods": monotone,
        "monotonic": monotone / buckets >= 0.5,
    }


# ---------------- B. construction diagnostics ----------------

def _ordinary_least_squares(observations):
    """Coefficients for ``y = a + Xb`` by Gaussian elimination on the normal equations.

    Small and exact enough for a six-factor monthly regression; a dependency on a linear
    algebra package for a 7x7 solve would cost more than it saves.
    """
    if not observations:
        return None
    width = len(observations[0][1])
    normal = [[sum(row[index] * row[column] for _, row in observations)
               for column in range(width)] + [sum(y * row[index] for y, row in observations)]
              for index in range(width)]
    for column in range(width):
        pivot = max(range(column, width), key=lambda index: abs(normal[index][column]))
        if abs(normal[pivot][column]) < 1e-12:
            return None
        normal[column], normal[pivot] = normal[pivot], normal[column]
        divisor = normal[column][column]
        normal[column] = [value / divisor for value in normal[column]]
        for index in range(width):
            if index == column:
                continue
            factor = normal[index][column]
            normal[index] = [value - factor * other
                             for value, other in zip(normal[index], normal[column])]
    return [row[-1] for row in normal]


def factor_loadings(monthly, factors):
    """FF5 plus momentum loadings on monthly excess returns.

    Sixty-one percent active share means factor bets are being made whether or not they were
    chosen. A persistent negative momentum loading is the kind of thing that explains a
    capture spread directly, and it is invisible in any return-only view.
    """
    rows = {row["month"]: row for row in (factors or {}).get("observations") or []}
    observations = []
    for month, value in sorted(monthly.items()):
        factor = rows.get(month)
        if not factor or any(factor.get(key) is None for key in FACTOR_KEYS):
            continue
        observations.append((value - (factor.get("risk_free") or 0.0),
                             [1.0] + [factor[key] for key in FACTOR_KEYS]))
    if len(observations) < 24:
        return {"months": len(observations), "loadings": None,
                "reason": f"{len(observations)} of 24 aligned monthly observations."}
    coefficients = _ordinary_least_squares(observations)
    if coefficients is None:
        return {"months": len(observations), "loadings": None,
                "reason": "The factor inputs are collinear over this window."}
    fitted = [sum(value * coefficient for value, coefficient in zip(row, coefficients))
              for _, row in observations]
    mean = sum(y for y, _ in observations) / len(observations)
    residual = sum((y - estimate) ** 2 for (y, _), estimate in zip(observations, fitted))
    total = sum((y - mean) ** 2 for y, _ in observations)
    return {
        "months": len(observations),
        "alpha_annualized_pct": round(coefficients[0] * MONTHS_PER_YEAR * 100, 2),
        "loadings": {key: round(value, 3)
                     for key, value in zip(FACTOR_KEYS, coefficients[1:])},
        "r_squared": round(1 - residual / total, 3) if total > 0 else None,
    }


def _rolling_beta(returns, benchmark, window=60):
    betas = []
    for end in range(window, min(len(returns), len(benchmark)) + 1):
        beta = risk_metrics.beta_vs_benchmark(returns[end - window:end],
                                              benchmark[end - window:end],
                                              minimum_observations=window)
        if beta is not None:
            betas.append(beta)
    return betas


def _rolling_sharpe(returns, window=60):
    sharpes = []
    for end in range(window, len(returns) + 1):
        value = risk_metrics.sharpe_ratio(returns[end - window:end], minimum_observations=window)
        if value is not None:
            sharpes.append(value)
    return sharpes


def _sector_active_weight_metric(history):
    """Two metrics, not one -- ``sector_active_weights``'s value (the largest active bet,
    in percentage points) and its ``kill_threshold`` (classification coverage, a fraction)
    are different quantities, so a bullet built from that pair would show a percentage-point
    figure crossing a coverage line it has nothing to do with. ``sector_classification_coverage``
    below carries the actual coverage number against its own real threshold instead.
    """
    if not history:
        return [_pending(
            "sector_active_weights", "construction", "Sector active weights",
            "No prospective sector snapshot exists. Run pipeline/sector_weight_history.py; "
            "historical sectors are not backfilled from today's classifications.",
            reads="Sector bets against SPY at each recorded production refresh.",
            cadence="Daily",
        ), _pending(
            "sector_classification_coverage", "construction", "Sector classification coverage",
            "No prospective sector snapshot exists. Run pipeline/sector_weight_history.py; "
            "historical sectors are not backfilled from today's classifications.",
            reads="Share of strategy weight the sector classifier could place.",
            kill_threshold_value=MINIMUM_SECTOR_CLASSIFICATION_COVERAGE * 100, comparison="lt",
            cadence="Daily",
        )]
    latest = history[-1]
    active = latest.get("active_sector_weights") or {}
    classified = latest.get("strategy_classified_weight")
    if not active:
        return [_pending(
            "sector_active_weights", "construction", "Sector active weights",
            "The sector history has no comparable strategy and benchmark weights.",
            reads="Sector bets against SPY at each recorded production refresh.",
            cadence="Daily",
        ), _pending(
            "sector_classification_coverage", "construction", "Sector classification coverage",
            "The sector history has no comparable strategy and benchmark weights.",
            reads="Share of strategy weight the sector classifier could place.",
            kill_threshold_value=MINIMUM_SECTOR_CLASSIFICATION_COVERAGE * 100, comparison="lt",
            cadence="Daily",
        )]
    ranked = sorted(active.items(), key=lambda item: abs(item[1]), reverse=True)
    sector, largest = ranked[0]
    coverage_breached = classified is not None and classified < MINIMUM_SECTOR_CLASSIFICATION_COVERAGE
    history_detail = [
        {"as_of": row.get("as_of"), "active_sector_weights": row.get("active_sector_weights"),
         "strategy_classified_weight": row.get("strategy_classified_weight"),
         "benchmark_classified_weight": row.get("benchmark_classified_weight")}
        for row in history[-60:]
    ]
    detail = {"as_of": latest.get("as_of"), "strategy": latest.get("strategy"),
              "benchmark": latest.get("benchmark"), "active_sector_weights": active,
              "strategy_sector_weights": latest.get("strategy_sector_weights"),
              "benchmark_sector_weights": latest.get("benchmark_sector_weights"),
              "strategy_classified_weight": classified,
              "benchmark_classified_weight": latest.get("benchmark_classified_weight"),
              "history": history_detail}
    return [
        metric(
            "sector_active_weights", "construction", "Sector active weights",
            value=round(abs(largest) * 100, 2),
            display=f"{sector.replace('_', ' ').title()} {largest * 100:+.1f}pp largest",
            reads="Current production-sector weights minus SPY, retained prospectively by date.",
            kill_threshold=(f"Strategy sector classification coverage below "
                             f"{MINIMUM_SECTOR_CLASSIFICATION_COVERAGE * 100:.0f}%"),
            breached=coverage_breached,
            detail=detail, observations=len(history), cadence="Daily",
            source="prospective sector-weight history",
        ),
        metric(
            "sector_classification_coverage", "construction", "Sector classification coverage",
            value=None if classified is None else round(classified * 100, 2),
            display=None if classified is None else f"{classified * 100:.1f}%",
            reads="Share of strategy weight the sector classifier could place. The active-weight "
                  "figure above is unreliable below this coverage.",
            kill_threshold=f"Below {MINIMUM_SECTOR_CLASSIFICATION_COVERAGE * 100:.0f}%",
            kill_threshold_value=MINIMUM_SECTOR_CLASSIFICATION_COVERAGE * 100, comparison="lt",
            breached=coverage_breached,
            detail={"as_of": latest.get("as_of"), "strategy_classified_weight": classified,
                    "benchmark_classified_weight": latest.get("benchmark_classified_weight")},
            observations=len(history), cadence="Daily",
            source="prospective sector-weight history",
        ),
    ]


def construction_metrics(backtest, factors, sector_history=None):
    rows = []
    portfolio = (backtest or {}).get("portfolio") or {}
    rebalances = portfolio.get("rebalances") or []
    returns = daily_returns_from_history(portfolio.get("history"))
    benchmark = daily_returns_from_history(((backtest or {}).get("benchmark_spy") or {}).get("history"))

    loadings = factor_loadings(monthly_returns_from_history(portfolio.get("history")), factors)
    negative_momentum = (loadings.get("loadings") or {}).get("momentum")
    rows.append(metric(
        "factor_betas", "construction", "FF5 + momentum loadings",
        value=negative_momentum,
        display=None if loadings.get("loadings") is None
        else " ".join(f"{key.split('_')[0]} {value:+.2f}"
                      for key, value in loadings["loadings"].items()),
        reads="The factor bets the portfolio is making, intended or not.",
        kill_threshold="Persistent negative momentum loading explains a capture spread",
        kill_threshold_value=MOMENTUM_LOADING_KILL_THRESHOLD, comparison="lt",
        breached=negative_momentum is not None and negative_momentum < MOMENTUM_LOADING_KILL_THRESHOLD,
        detail=loadings, observations=loadings.get("months"), required_observations=24,
        status="ready" if loadings.get("loadings") else "accumulating",
        status_message=loadings.get("reason"), cadence="Weekly",
        source="backtest equity curve versus Fama-French"))

    weights = [[pick.get("weight") for pick in row.get("picks") or []] for row in rebalances]
    latest = weights[-1] if weights else []
    breadth = evaluation.effective_breadth(latest)
    rows.append(metric("effective_n", "construction", "Effective N (1 / sum of squared weights)",
                       value=breadth, display=None if breadth is None else f"{breadth:.1f} of {len(latest)}",
                       reads="How many equally sized bets the book really is.",
                       detail={"positions": len(latest),
                               "history": [evaluation.effective_breadth(row) for row in weights[-12:]]},
                       cadence="Weekly", source="backtest rebalances"))

    top_ten = sorted((weight for weight in latest if weight), reverse=True)[:10]
    concentration = round(sum(top_ten) * 100, 2) if top_ten else None
    rows.append(metric("top_10_weight", "construction", "Top-10 weight",
                       value=concentration,
                       display=None if concentration is None else f"{concentration:.1f}%",
                       reads="Concentration the effective-N number can hide.",
                       cadence="Weekly", source="backtest rebalances"))

    betas = _rolling_beta(returns, benchmark)
    swing = round(max(betas) - min(betas), 2) if betas else None
    swing_breached = swing is not None and swing > MAXIMUM_BETA_SWING
    rows.append(metric("rolling_beta_60d", "construction", "Rolling 60-day beta",
                       value=round(betas[-1], 2) if betas else None,
                       display=None if not betas else f"{betas[-1]:.2f} (range {min(betas):.2f}–{max(betas):.2f})",
                       reads="A point-estimate beta hides how unstable every beta-adjusted "
                             "number on the dashboard is.",
                       kill_threshold=f"A swing wider than {MAXIMUM_BETA_SWING} makes excess-return figures unstable",
                       breached=swing_breached,
                       detail={"window": 60, "observations": len(betas), "swing": swing,
                               "series": [round(value, 3) for value in betas[-60:]]},
                       cadence="Weekly", source="backtest equity curve"))
    # The point beta above and the swing its own kill_threshold describes are different
    # quantities on different scales (~1.0 vs ~0.3) -- plotting them on one bullet would
    # show the point estimate crossing a threshold that was never about it. Published as
    # its own metric instead, value and kill_threshold_value both genuinely the swing.
    rows.append(metric("rolling_beta_swing", "construction", "Rolling beta swing (60d window)",
                       value=swing,
                       display=None if swing is None else f"{swing:.2f} (max − min over the window)",
                       reads="How unstable the 60-day beta estimate itself has been -- the "
                             "number rolling_beta_60d's point estimate can't show on its own.",
                       kill_threshold=f"Swing wider than {MAXIMUM_BETA_SWING} makes excess-return figures unstable",
                       kill_threshold_value=MAXIMUM_BETA_SWING, comparison="gt",
                       breached=swing_breached,
                       detail={"window": 60, "observations": len(betas),
                               "beta_range": None if not betas else [round(min(betas), 3), round(max(betas), 3)]},
                       cadence="Weekly", source="backtest equity curve"))

    drift = [round(sum(weight for weight in row if weight), 4) for row in weights if row]
    rows.append(metric("net_exposure_drift", "construction", "Net exposure drift",
                       value=round(max(drift) - min(drift), 4) if drift else None,
                       display=None if not drift else f"{min(drift):.3f}–{max(drift):.3f} invested",
                       reads="Whether planned weights sum where they are supposed to.",
                       detail={"rebalances": len(drift)}, cadence="Daily",
                       source="backtest rebalances"))

    rows.extend(_sector_active_weight_metric(sector_history or []))
    rows.extend(_sector_attribution_metrics(sector_history or []))
    return rows


def _sector_attribution_metrics(sector_history):
    """Real sector-index Brinson allocation effect, and an honest stub for selection.

    Allocation is computable now: real sector SPDR total returns times the book's own
    measured active sector weight. Selection needs the book's own realized return *within*
    each sector, which needs a per-holding return series joined to a historical sector
    classification neither the backtest artifacts nor the point-in-time sector log carry --
    so it stays a stub rather than a guess.
    """
    result = sector_attribution.allocation_effect(sector_history)
    if result is None:
        message = (f"Needs at least {sector_attribution.MINIMUM_SNAPSHOTS} recorded "
                   "sector-weight snapshots spanning more than one day, with SPY and every "
                   f"sector SPDR ETF priced through the latest snapshot; "
                   f"{len(sector_history)} snapshots recorded so far.")
        return [
            _pending("sector_allocation_effect", "construction", "Sector allocation effect",
                     message,
                     reads="Real sector-index return times the book's active sector weight "
                           "-- whether the sector tilt helped or hurt, independent of "
                           "stock-picking.", cadence="Monthly"),
            _pending("sector_selection_effect", "construction", "Sector selection effect",
                     "Needs the book's own realized return within each sector, joined to a "
                     "historical sector classification per holding -- neither is logged today.",
                     reads="Whether stock-picking within each sector beat that sector's own "
                           "index.", cadence="Monthly"),
        ]
    return [
        metric("sector_allocation_effect", "construction", "Sector allocation effect",
               value=result["total_allocation_effect_pct"],
               display=f"{result['total_allocation_effect_pct']:+.2f}pp vs SPY "
                       f"({result['start']} to {result['end']})",
               reads="Sum across sectors of (active weight) times (that sector's real index "
                     "return minus SPY's), using real sector SPDR ETFs. Positive means the "
                     "sector tilt itself added return; says nothing about which stocks were "
                     "picked within each sector.",
               detail=result, observations=result["snapshots"], cadence="Monthly",
               source="sector-weight snapshot log and real sector SPDR total returns"),
        _pending("sector_selection_effect", "construction", "Sector selection effect",
                 "Needs the book's own realized return within each sector, joined to a "
                 "historical sector classification per holding -- neither is logged today.",
                 reads="Whether stock-picking within each sector beat that sector's own "
                       "index.", cadence="Monthly"),
    ]


# ---------------- C. cost and capacity ----------------

def _execution_cost_metrics(execution):
    """Measured trade diagnostics when an external execution export is supplied.

    The optional file is intentionally not synthesized by the research pipeline. Its rows
    must come from an order-management or brokerage export and carry decision/fill prices.
    """
    execution = execution or {}
    orders = execution.get("orders") or []
    filled = [row for row in orders
              if row.get("decision_price") and row.get("fill_price")
              and row.get("filled_quantity")]
    intended_quantity = sum(abs(float(row.get("intended_quantity") or 0)) for row in orders)
    filled_quantity = sum(abs(float(row.get("filled_quantity") or 0)) for row in orders)
    shortfalls = []
    for row in filled:
        decision = float(row["decision_price"])
        fill = float(row["fill_price"])
        side = str(row.get("side") or "buy").lower()
        bps = ((fill - decision) / decision if side == "buy" else
               (decision - fill) / decision) * 10_000
        notional = abs(float(row["filled_quantity"]) * decision)
        shortfalls.append({"ticker": row.get("ticker"), "bps": round(bps, 3),
                           "decision_notional": notional,
                           "expected_bps": row.get("expected_cost_bps")})
    total_notional = sum(row["decision_notional"] for row in shortfalls)
    shortfall = (sum(row["bps"] * row["decision_notional"] for row in shortfalls)
                 / total_notional if total_notional else None)
    fill_rate = filled_quantity / intended_quantity if intended_quantity else None
    intended = execution.get("intended_positions") or {}
    actual = execution.get("actual_positions") or {}
    unpositioned = sorted(ticker for ticker, weight in intended.items()
                          if float(weight or 0) > 0 and float(actual.get(ticker) or 0) <= 0)
    rejected = [row for row in orders if str(row.get("status") or "").lower() == "rejected"]
    rejection_rate = len(rejected) / len(orders) if orders else None
    with_expected = [row for row in shortfalls if row.get("expected_bps") is not None]
    slippage_diff = (sum(row["bps"] - row["expected_bps"] for row in with_expected)
                     / len(with_expected) if with_expected else None)
    source_message = ("Needs pipeline/data/validation/live_execution.json from an order or "
                      "broker export; the research pipeline does not place trades.")
    if not execution:
        return [
            _pending("implementation_shortfall", "cost", "Implementation shortfall",
                     source_message, reads="Decision price to fill price, in basis points, per trade.",
                     requires_live_sample=True, cadence="Daily", status="awaiting_live_sample"),
            _pending("fill_rate", "cost", "Fill rate", source_message,
                     reads="Share of intended quantity that executed.",
                     requires_live_sample=True, cadence="Daily", status="awaiting_live_sample"),
            _pending("unpositioned_signals", "cost", "Signals never positioned", source_message,
                     reads="Intended positive-weight names absent from actual positions.",
                     requires_live_sample=True, cadence="Daily", status="awaiting_live_sample"),
            _pending("order_rejection_rate", "cost", "Order rejection rate", source_message,
                     reads="Share of orders rejected by the broker or venue.",
                     requires_live_sample=True, cadence="Daily", status="awaiting_live_sample"),
            _pending("realized_vs_expected_slippage", "cost", "Realized vs. expected slippage",
                     source_message,
                     reads="Implementation shortfall against the cost model's pre-trade "
                           "estimate, per trade.",
                     requires_live_sample=True, cadence="Daily", status="awaiting_live_sample"),
        ]
    return [
        metric("implementation_shortfall", "cost", "Implementation shortfall",
               value=None if shortfall is None else round(shortfall, 3),
               display=None if shortfall is None else f"{shortfall:.2f} bps",
               reads="Notional-weighted adverse move from decision to fill price.",
               requires_live_sample=True,
               status="ready" if shortfall is not None else "awaiting_input",
               status_message=None if shortfall is not None else "No filled order has both prices.",
               observations=len(shortfalls), cadence="Daily", detail={"orders": shortfalls},
               source="external execution export"),
        metric("fill_rate", "cost", "Fill rate", value=fill_rate,
               display=None if fill_rate is None else f"{fill_rate * 100:.1f}%",
               reads="Filled quantity divided by intended quantity.", requires_live_sample=True,
               status="ready" if fill_rate is not None else "awaiting_input",
               status_message=None if fill_rate is not None else "No intended order quantity supplied.",
               observations=len(orders), cadence="Daily", source="external execution export"),
        metric("unpositioned_signals", "cost", "Signals never positioned", value=len(unpositioned),
               reads="Intended positive-weight names absent from actual positions.",
               breached=bool(unpositioned), requires_live_sample=True,
               status="ready" if intended else "awaiting_input",
               status_message=None if intended else "No intended positions supplied.",
               detail={"tickers": unpositioned}, observations=len(intended), cadence="Daily",
               source="external execution export"),
        metric("order_rejection_rate", "cost", "Order rejection rate", value=rejection_rate,
               display=None if rejection_rate is None else f"{rejection_rate * 100:.1f}%",
               reads="Share of orders rejected by the broker or venue.", requires_live_sample=True,
               status="ready" if orders else "awaiting_input",
               status_message=None if orders else "No orders supplied.",
               detail={"rejected_tickers": sorted(filter(None, (row.get("ticker") for row in rejected)))},
               observations=len(orders), cadence="Daily", source="external execution export"),
        metric("realized_vs_expected_slippage", "cost", "Realized vs. expected slippage",
               value=None if slippage_diff is None else round(slippage_diff, 3),
               display=None if slippage_diff is None else f"{slippage_diff:+.2f} bps vs. cost model",
               reads="Implementation shortfall against the pre-trade cost-model estimate, "
                     "per filled trade.",
               requires_live_sample=True,
               status="ready" if with_expected else "awaiting_input",
               status_message=None if with_expected else
               "No filled order carries an expected_cost_bps pre-trade estimate.",
               observations=len(with_expected), cadence="Daily", detail={"orders": with_expected},
               source="external execution export"),
    ]


def cost_metrics(backtest, panel, execution=None):
    rows = []
    portfolio = (backtest or {}).get("portfolio") or {}
    rebalances = portfolio.get("rebalances") or []
    one_way_bps = ((backtest or {}).get("method") or {}).get("transaction_cost_bps_one_way")
    if one_way_bps is None:
        one_way_bps = (SETTINGS.get("validation") or {}).get("long_short_cost_bps", 10.0)
    round_trip_bps = one_way_bps * 2

    turnovers = [row.get("turnover") for row in rebalances if row.get("turnover") is not None]
    annual_turnover = (sum(turnovers) / len(turnovers)) * MONTHS_PER_YEAR if turnovers else None
    breakeven = evaluation.breakeven_gross_alpha(annual_turnover, round_trip_bps)
    rows.append(metric("breakeven_gross_alpha", "cost", "Breakeven gross alpha",
                       value=breakeven, display=None if breakeven is None else f"{breakeven:.2f}%/yr",
                       reads="What the signal must earn gross before trading it is worth doing. "
                             "Above the return the IC implies, the strategy is arithmetically dead.",
                       kill_threshold="Breakeven above IC-implied expected return",
                       detail={"annual_turnover": None if annual_turnover is None else round(annual_turnover, 2),
                               "round_trip_cost_bps": round_trip_bps,
                               "rebalances": len(turnovers)},
                       cadence="Monthly", source="backtest rebalances"))

    if panel and panel.get("periods"):
        spreads = {label: _quantile_spread(panel["periods"], label).get("mean_spread")
                   for label in HORIZON_TRADING_DAYS}
        crossover = evaluation.alpha_cost_crossover(
            spreads, round_trip_cost_bps=round_trip_bps,
            trading_days_by_horizon=HORIZON_TRADING_DAYS, trading_days_per_year=TRADING_DAYS)
        rows.append(metric("alpha_cost_crossover", "cost", "Alpha versus cost crossover",
                           value=crossover["crossover_horizon"],
                           display=crossover["crossover_horizon"] or "No horizon clears its own cost",
                           reads="The shortest holding period whose spread survives the round trip.",
                           kill_threshold="No horizon clears cost",
                           breached=crossover["crossover_horizon"] is None,
                           detail=crossover, cadence="Monthly", source="backtest panel"))
    else:
        rows.append(_pending("alpha_cost_crossover", "cost", "Alpha versus cost crossover",
                             "Needs the scored panel; the quantile spread per horizon is its input.",
                             reads="The shortest holding period whose spread survives the round trip.",
                             cadence="Monthly"))

    adv = _participation(panel, rebalances)
    rows.append(metric("percent_of_adv", "cost", "Position as a share of ADV",
                       value=adv.get("worst"), display=adv.get("display"),
                       reads="The capacity ceiling. Above a few percent of daily volume the "
                             "backtest fills stop being available in reality.",
                       kill_threshold=f"Above {MAXIMUM_PERCENT_OF_ADV}% of average daily volume",
                       kill_threshold_value=MAXIMUM_PERCENT_OF_ADV, comparison="gt",
                       breached=adv.get("worst") is not None and adv["worst"] > MAXIMUM_PERCENT_OF_ADV,
                       detail=adv, status=adv.get("status", "awaiting_input"),
                       status_message=adv.get("reason"), cadence="Monthly",
                       source="backtest panel"))

    rows.extend(_execution_cost_metrics(execution))
    return rows


def _participation(panel, rebalances):
    """Largest position as a share of its own average daily dollar volume."""
    volumes = (panel or {}).get("dollar_volume") or {}
    picks = (rebalances or [{}])[-1].get("picks") or []
    value = (rebalances or [{}])[-1].get("portfolio_value")
    if not volumes or not picks or not value:
        return {"status": "awaiting_input",
                "reason": "Needs per-name dollar volume alongside the panel. "
                          "backtest_monthly.py --panel-out writes it when volume history is available.",
                "worst": None, "display": None}
    shares = []
    for pick in picks:
        volume = volumes.get(pick.get("ticker"))
        if volume:
            shares.append({"ticker": pick["ticker"],
                           "percent_of_adv": round((pick.get("weight") or 0) * value / volume * 100, 3)})
    if not shares:
        return {"status": "awaiting_input", "reason": "No pick has matching volume history.",
                "worst": None, "display": None}
    shares.sort(key=lambda row: row["percent_of_adv"], reverse=True)
    return {"status": "ready", "worst": shares[0]["percent_of_adv"],
            "display": f"{shares[0]['percent_of_adv']:.2f}% worst ({shares[0]['ticker']})",
            "positions": shares[:10]}


# ---------------- D. statistical honesty ----------------

def honesty_metrics(backtest, optimizer):
    """The four numbers that price what seven rounds of iteration cost in credibility."""
    portfolio = (backtest or {}).get("portfolio") or {}
    returns = daily_returns_from_history(portfolio.get("history"))
    trials = len((optimizer or {}).get("sweeps", {}).get("categories") or []) or 1
    rows = []

    per_observation = None
    if len(returns) > 2:
        mean = sum(returns) / len(returns)
        variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
        per_observation = mean / math.sqrt(variance) if variance > 0 else None
    skew = risk_metrics.skewness(returns) or 0.0
    kurtosis = (risk_metrics.excess_kurtosis(returns) or 0.0) + 3.0

    deflated = evaluation.deflated_sharpe_ratio(
        per_observation, observations=len(returns), trials=trials, skew=skew, kurtosis=kurtosis)
    rows.append(metric("deflated_sharpe", "honesty", "Deflated Sharpe ratio",
                       value=deflated,
                       reads="Probability the Sharpe survives the number of configurations tried.",
                       kill_threshold=f"Below {SEARCH_SURVIVAL_MINIMUM} the result does not survive its own search",
                       kill_threshold_value=SEARCH_SURVIVAL_MINIMUM, comparison="lt",
                       breached=deflated is not None and deflated < SEARCH_SURVIVAL_MINIMUM,
                       detail={"trials": trials, "skew": round(skew, 3),
                               "kurtosis": round(kurtosis, 3),
                               "sharpe_per_observation": None if per_observation is None
                               else round(per_observation, 4)},
                       observations=len(returns), cadence="Quarterly",
                       source="backtest daily returns"))

    probabilistic = evaluation.probabilistic_sharpe_ratio(
        per_observation, observations=len(returns), skew=skew, kurtosis=kurtosis)
    rows.append(metric("probabilistic_sharpe", "honesty", "Probabilistic Sharpe ratio",
                       value=probabilistic,
                       reads="Probability the true Sharpe is above zero given this sample.",
                       kill_threshold=f"Below {SEARCH_SURVIVAL_MINIMUM} the sample cannot support the claim",
                       kill_threshold_value=SEARCH_SURVIVAL_MINIMUM, comparison="lt",
                       breached=probabilistic is not None and probabilistic < SEARCH_SURVIVAL_MINIMUM,
                       observations=len(returns), cadence="Quarterly",
                       source="backtest daily returns"))

    required = evaluation.minimum_track_record_length(
        per_observation, skew=skew, kurtosis=kurtosis)
    rows.append(metric("min_track_record_length", "honesty", "Minimum track record length",
                       value=required,
                       display=None if required is None
                       else f"{required} days ({required / TRADING_DAYS:.1f} years)",
                       reads="How long until the Sharpe claim is defensible.",
                       detail={"observations_available": len(returns),
                               "still_needed": None if required is None else max(0, required - len(returns))},
                       observations=len(returns), cadence="Quarterly",
                       source="backtest daily returns"))

    pbo = _probability_of_overfitting(optimizer)
    rows.append(metric("pbo", "honesty", "Probability of backtest overfitting",
                       value=pbo.get("value"),
                       reads="Chance the configuration that won the search beats the median out "
                             "of sample. Above a half, the selection process is producing noise.",
                       kill_threshold=f"PBO > {MAXIMUM_PBO}",
                       kill_threshold_value=MAXIMUM_PBO, comparison="gt",
                       breached=pbo.get("value") is not None and pbo["value"] > MAXIMUM_PBO,
                       detail=pbo, status=pbo.get("status", "unavailable"),
                       status_message=pbo.get("reason"),
                       cadence="Annually or on any refit", source="weight optimizer sweeps"))

    if len(returns) >= MINIMUM_BOOTSTRAP_OBSERVATIONS:
        bootstrap = evaluation.block_bootstrap_return_ci(returns)
    else:
        bootstrap = None
    if bootstrap:
        return_lo, return_hi = bootstrap["annualized_return_ci_95_pct"]
        rows.append(metric(
            "bootstrap_ci", "honesty", "Bootstrap return/Sharpe confidence interval",
            value=bootstrap["mean_annualized_return_pct"],
            display=f"{bootstrap['mean_annualized_return_pct']:.1f}%/yr "
                    f"(95% CI {return_lo:.1f}% to {return_hi:.1f}%)",
            reads="Block-bootstrap uncertainty band on annualized return and Sharpe -- a "
                  "defensible interval without waiting for 253 daily returns.",
            kill_threshold="95% Sharpe CI includes zero",
            breached=bootstrap["sharpe_ci_95"][0] <= 0,
            detail=bootstrap, observations=bootstrap["observations"], cadence="Monthly",
            source="block bootstrap of backtest daily returns"))
    else:
        rows.append(_pending(
            "bootstrap_ci", "honesty", "Bootstrap return/Sharpe confidence interval",
            f"Needs at least {MINIMUM_BOOTSTRAP_OBSERVATIONS} backtest daily returns; "
            f"{len(returns)} available.",
            reads="Block-bootstrap uncertainty band on annualized return and Sharpe.",
            cadence="Monthly"))

    spa = _search_survival(optimizer)
    rows.append(metric(
        "reality_check_spa", "honesty", "White's Reality Check / SPA test",
        value=spa.get("p_value"),
        display=None if spa.get("p_value") is None else f"p = {spa['p_value']:.3f}",
        reads="Whether the best-searched configuration beats the field by more than an "
              "exhaustive search of this many configurations would produce from noise alone.",
        kill_threshold="p-value above 0.05 -- the edge is not distinguishable from search noise",
        kill_threshold_value=0.05, comparison="gt",
        breached=spa.get("p_value") is not None and spa["p_value"] > 0.05,
        detail=spa, status=spa.get("status", "awaiting_input"), status_message=spa.get("reason"),
        cadence="Annually or on any refit", source="weight optimizer sweeps"))

    sharpes = _rolling_sharpe(returns)
    sharpe_swing = round(max(sharpes) - min(sharpes), 2) if sharpes else None
    rows.append(metric(
        "rolling_sharpe_60d", "honesty", "Rolling 60-day Sharpe",
        value=round(sharpes[-1], 2) if sharpes else None,
        display=None if not sharpes else
        f"{sharpes[-1]:.2f} (range {min(sharpes):.2f} to {max(sharpes):.2f})",
        reads="Whether one lucky stretch is carrying the headline Sharpe, or the edge holds "
              "across the full window.",
        detail={"window": 60, "observations": len(sharpes), "swing": sharpe_swing,
                "series": [round(value, 3) for value in sharpes[-60:]]},
        cadence="Weekly", source="backtest equity curve"))

    for confidence in VAR_CONFIDENCES:
        label = f"var_backtest_{int(confidence * 100)}"
        title = f"VaR backtest ({int(confidence * 100)}%)"
        backtest_var = (evaluation.var_backtest(returns, confidence=confidence)
                        if len(returns) >= VAR_BACKTEST_MINIMUM_OBSERVATIONS else None)
        if backtest_var is None:
            rows.append(_pending(
                label, "honesty", title,
                f"Needs at least {VAR_BACKTEST_MINIMUM_OBSERVATIONS} backtest daily returns; "
                f"{len(returns)} available.",
                reads="Kupiec proportion-of-failures and Christoffersen independence tests "
                      "against realized breaches of a rolling historical VaR forecast.",
                kill_threshold_value=0, comparison="gt", cadence="Quarterly"))
            continue
        kupiec = backtest_var.get("kupiec_pof") or {}
        christoffersen = backtest_var.get("christoffersen_independence") or {}
        failing = int(bool(kupiec.get("miscalibrated_at_95"))) \
            + int(bool(christoffersen.get("clustered_at_95")))
        rows.append(metric(
            label, "honesty", title, value=failing,
            display=(f"{backtest_var['breaches']} breaches of {backtest_var['forecasts']} "
                     f"({backtest_var['breach_rate'] * 100:.1f}% vs "
                     f"{backtest_var['expected_breach_rate'] * 100:.1f}% expected)"),
            reads="Kupiec tests whether the breach rate matches the stated coverage; "
                  "Christoffersen tests whether breaches cluster instead of scattering.",
            kill_threshold="Kupiec or Christoffersen rejects calibration at 95%",
            kill_threshold_value=0, comparison="gt", breached=bool(failing),
            detail=backtest_var, observations=backtest_var["forecasts"], cadence="Quarterly",
            source="rolling historical VaR against backtest daily returns"))
    return rows


# ---------------- G. classic risk-adjusted return ----------------

def risk_adjusted_metrics(backtest):
    """Treynor ratio and single-factor Jensen's alpha against the SPY benchmark leg.

    Distinct from the FF5+momentum alpha in construction diagnostics: this isolates the
    market factor alone, the classic Jensen (1968) construction and the more conservative of
    the two claims.
    """
    portfolio = (backtest or {}).get("portfolio") or {}
    returns = daily_returns_from_history(portfolio.get("history"))
    benchmark = daily_returns_from_history(((backtest or {}).get("benchmark_spy") or {}).get("history"))
    overlap = min(len(returns), len(benchmark))
    if overlap < 20:
        message = "Needs the backtest portfolio and SPY benchmark daily histories."
        return [
            _pending("treynor_ratio", "risk_adjusted", "Treynor ratio", message,
                     reads="Annualized excess return per unit of beta.",
                     kill_threshold_value=0, comparison="lt", cadence="Quarterly"),
            _pending("jensens_alpha", "risk_adjusted", "Jensen's alpha (single-factor CAPM)",
                     message, reads="Annualized return beta alone does not explain.",
                     kill_threshold_value=0, comparison="lt", cadence="Quarterly"),
        ]
    risk_free_annual = _risk_free_daily() * TRADING_DAYS
    treynor = risk_metrics.treynor_ratio(returns, benchmark, risk_free_annual)
    jensen = risk_metrics.jensens_alpha(returns, benchmark, risk_free_annual)
    beta = risk_metrics.beta_vs_benchmark(returns, benchmark)
    detail = {"beta": beta, "risk_free_annual_pct": round(risk_free_annual * 100, 3)}
    return [
        metric("treynor_ratio", "risk_adjusted", "Treynor ratio", value=treynor,
               display=None if treynor is None else f"{treynor:.2f}%/yr per unit beta",
               reads="Annualized excess return per unit of systematic risk. Comparable across "
                     "portfolios with different total volatility in a way Sharpe is not.",
               kill_threshold="Negative Treynor means losing money on a beta-adjusted basis",
               kill_threshold_value=0, comparison="lt",
               breached=treynor is not None and treynor < 0,
               detail=detail, observations=overlap, cadence="Quarterly",
               source="backtest equity curve versus SPY"),
        metric("jensens_alpha", "risk_adjusted", "Jensen's alpha (single-factor CAPM)",
               value=jensen, display=None if jensen is None else f"{jensen:+.2f}%/yr",
               reads="The classic Jensen (1968) single-factor alpha: return beta does not "
                     "explain. More conservative than the FF5+momentum alpha in construction "
                     "diagnostics, which lets more factors explain the return away first.",
               kill_threshold="Alpha at or below zero -- beta alone explains the return",
               kill_threshold_value=0, comparison="lt",
               breached=jensen is not None and jensen < 0,
               detail=detail, observations=overlap, cadence="Quarterly",
               source="backtest equity curve versus SPY"),
    ]


# ---------------- H. tax and stress ----------------

def tax_and_stress_metrics(backtest):
    """After-tax return (pending trade-level data) and realized stress-window behaviour.

    The 2022 window is graded from the strategy's own realized daily returns during that
    calendar year, not a synthetic factor replay - the backtest window covers 2022 in full.
    2020 is not: the backtest starts in mid-2021, so no priced day of this strategy's own
    exposures exists for the COVID crash, and fabricating one via factor replay is not
    evidence the rest of this dashboard would accept anywhere else.
    """
    portfolio = (backtest or {}).get("portfolio") or {}
    history = portfolio.get("history") or []
    rows = [_pending(
        "after_tax_return", "tax_stress", "After-tax return",
        "Needs trade-level realized gain/loss and holding-period logging (the Priority 1 "
        "cost/capacity work); short-term capital-gains treatment cannot be applied without it.",
        reads="Realized return after short-term capital gains, alongside the pre-tax figure.",
        cadence="Annually")]

    window = [row for row in history
             if row.get("date") and STRESS_2022_START <= str(row["date"]) <= STRESS_2022_END]
    if len(window) < STRESS_2022_MINIMUM_DAYS:
        rows.append(_pending(
            "stress_test_2022", "tax_stress", "2022 rate-shock stress window",
            f"The backtest carries only {len(window)} priced days inside 2022.",
            reads="Realized return and drawdown during the 2022 rate-shock window.",
            cadence="Annually"))
    else:
        closes = [row["value"] for row in window if row.get("value")]
        window_return = closes[-1] / closes[0] - 1 if closes and closes[0] else None
        drawdown = risk_metrics.max_drawdown(closes)
        rows.append(metric(
            "stress_test_2022", "tax_stress", "2022 rate-shock stress window", value=drawdown,
            display=None if window_return is None or drawdown is None
            else f"{window_return * 100:+.1f}% return, {drawdown:.1f}% max drawdown",
            reads="How this book's own realized exposures performed through the 2022 "
                  "rate-shock period.",
            detail={"start": window[0].get("date"), "end": window[-1].get("date"),
                    "trading_days": len(window),
                    "return_pct": None if window_return is None else round(window_return * 100, 2),
                    "max_drawdown_pct": drawdown},
            observations=len(window), cadence="Annually", source="backtest equity curve"))

    rows.append(_pending(
        "stress_test_2020", "tax_stress", "2020 COVID-crash stress window",
        "The backtest window starts in mid-2021; no priced day of this strategy's own "
        "exposures exists for the 2020 crash, and fabricating one via factor replay is not "
        "evidence.",
        reads="Hypothetical drawdown under a 2020-style crash, replaying factor and sector "
              "exposures.", cadence="Annually"))
    return rows


_SCENARIO_INPUT_MESSAGE = ("Needs public/data/etf/SPY.json and TLT.json for scenario pricing "
                           "and a factor file for the multi-factor projection.")


def scenario_metrics(backtest, factors):
    """Forward-looking scenarios: named historical events and hypothetical shocks, projected
    through the book's own measured exposures rather than replayed from its own history.

    ``stress_test_2020`` above is honestly unavailable because the backtest never lived
    through 2020. This is the answer to that gap: not a replay, but a projection -- the
    book's *current* market beta and FF5+momentum loadings, run through what SPY, TLT, and
    the six factors actually did during the 2008 GFC, the March 2020 crash, and the 2022
    rate-hike drawdown, plus two hypothetical shocks (a flat SPY move, a rate move sized via
    an assumed TLT duration). Every value published here is a linear extrapolation through a
    beta or a duration constant, stated as such in ``reads`` rather than left implicit in a
    precise-looking percentage.
    """
    portfolio = (backtest or {}).get("portfolio") or {}
    history = portfolio.get("history") or []
    benchmark_history = ((backtest or {}).get("benchmark_spy") or {}).get("history") or []
    factor_observations = (factors or {}).get("observations") or []

    spy_prices = stress_scenarios.read_etf_prices("SPY")
    tlt_prices = stress_scenarios.read_etf_prices("TLT")
    if not spy_prices or not tlt_prices or not history:
        rows = [_pending(f"scenario_{scenario_id}", "tax_stress", meta["label"],
                         _SCENARIO_INPUT_MESSAGE, reads=meta["description"], cadence="Annually")
                for scenario_id, meta in stress_scenarios.NAMED_SCENARIOS.items()]
        rows.append(_pending("rate_beta", "construction",
                             "Beta to long Treasuries (rate sensitivity)", _SCENARIO_INPUT_MESSAGE,
                             reads="Beta of the book's daily returns to TLT (long Treasuries).",
                             cadence="Monthly"))
        rows.append(_pending("scenario_hypothetical_spy", "tax_stress",
                             f"Hypothetical: SPY {stress_scenarios.HYPOTHETICAL_SPY_SHOCK_PCT:+.0f}%",
                             _SCENARIO_INPUT_MESSAGE, cadence="Annually"))
        rows.append(_pending("scenario_hypothetical_rates", "tax_stress",
                             f"Hypothetical: rates +{stress_scenarios.HYPOTHETICAL_RATE_SHOCK_BPS}bp",
                             _SCENARIO_INPUT_MESSAGE, cadence="Annually"))
        return rows

    returns = daily_returns_from_history(history)
    spy_backtest_returns = daily_returns_from_history(benchmark_history)
    beta_spy = risk_metrics.beta_vs_benchmark(returns, spy_backtest_returns)
    loadings = (factor_loadings(monthly_returns_from_history(history), factors) or {}).get("loadings")
    portfolio_tlt_returns, tlt_returns = stress_scenarios.aligned_daily_returns(history, tlt_prices)
    rate_beta = risk_metrics.beta_vs_benchmark(portfolio_tlt_returns, tlt_returns)

    rows = [metric(
        "rate_beta", "construction", "Beta to long Treasuries (rate sensitivity)", value=rate_beta,
        display=None if rate_beta is None else f"{rate_beta:+.2f}",
        reads="Beta of the book's daily returns to TLT (long Treasuries). Positive means the "
              "book tends to fall when long rates rise, the way a bond would; negative means "
              "it tends to benefit from rising rates.",
        detail={"proxy": "TLT", "observations": len(tlt_returns)},
        observations=len(tlt_returns), cadence="Monthly",
        source="backtest equity curve versus TLT total return")]

    named = stress_scenarios.named_scenarios(
        spy_prices=spy_prices, tlt_prices=tlt_prices, factor_observations=factor_observations,
        loadings=loadings, beta_spy=beta_spy)
    for scenario_id, result in named.items():
        factor_value = result["factor_model_projection_pct"]
        market_value = result["market_beta_projection_pct"]
        has_reading = factor_value is not None or market_value is not None
        display = None
        if factor_value is not None and market_value is not None:
            display = f"{factor_value:+.1f}% factor model, {market_value:+.1f}% market beta only"
        elif factor_value is not None:
            display = f"{factor_value:+.1f}% (factor model)"
        elif market_value is not None:
            display = f"{market_value:+.1f}% (market beta only)"
        rows.append(metric(
            f"scenario_{scenario_id}", "tax_stress", result["label"], value=factor_value,
            display=display,
            reads=f"{result['description']} Projected through this book's own measured factor "
                  "loadings and market beta, not replayed from its own returns -- the "
                  "strategy did not exist yet.",
            detail=result, cadence="Annually",
            status="ready" if has_reading else "awaiting_input",
            status_message=None if has_reading else
            "Neither the factor loadings nor the market beta could be estimated.",
            source="Fama-French factor windows and SPY/TLT total-return history, projected "
                   "through measured exposures"))

    shocks = stress_scenarios.hypothetical_shocks(beta_spy=beta_spy, rate_beta=rate_beta)
    spy_shock = shocks["spy_shock"]
    rows.append(metric(
        "scenario_hypothetical_spy", "tax_stress",
        f"Hypothetical: SPY {spy_shock['shock_pct']:+.0f}%", value=spy_shock["projected_return_pct"],
        display=None if spy_shock["projected_return_pct"] is None
        else f"{spy_shock['projected_return_pct']:+.1f}%",
        reads="A flat, hypothetical SPY move projected through the book's measured market "
              "beta. A linear extrapolation, not a measurement.",
        detail=spy_shock, cadence="Annually",
        status="ready" if spy_shock["projected_return_pct"] is not None else "awaiting_input",
        status_message=None if spy_shock["projected_return_pct"] is not None
        else "Beta to SPY could not be estimated.",
        source="linear projection through the book's measured market beta"))
    rate_shock = shocks["rate_shock"]
    rows.append(metric(
        "scenario_hypothetical_rates", "tax_stress",
        f"Hypothetical: rates +{rate_shock['shock_bps']}bp", value=rate_shock["projected_return_pct"],
        display=None if rate_shock["projected_return_pct"] is None
        else f"{rate_shock['projected_return_pct']:+.1f}%",
        reads=f"A hypothetical {rate_shock['shock_bps']}bp rate move, converted to a TLT price "
              f"move via an assumed {rate_shock['assumed_tlt_duration_years']:.0f}-year "
              "effective duration, projected through the book's measured beta to TLT. A "
              "modeling assumption stacked on a linear extrapolation, not a measurement.",
        detail=rate_shock, cadence="Annually",
        status="ready" if rate_shock["projected_return_pct"] is not None else "awaiting_input",
        status_message=None if rate_shock["projected_return_pct"] is not None
        else "Beta to TLT could not be estimated.",
        source="linear projection through the book's measured TLT beta and an assumed duration"))
    return rows


def _optimizer_trials_matrix(optimizer):
    """The trial log both PBO (CSCV) and the SPA/Reality Check test grade against.

    The optimizer only re-runs holdout folds for the configurations that survived the
    in-sample sweep, so those are the ones either statistic can be run across. The full
    search count (``searched``) is returned alongside because it, not the finalist count, is
    what deflation has to price. ``matrix`` is ``[fold][configuration]`` holdout performance,
    or ``None`` when fewer than two configurations carry at least two comparable folds.
    """
    searched = (optimizer or {}).get("sweeps", {}).get("categories") or []
    trials = [trial for trial in searched if len(trial.get("holdout_folds") or []) >= 2]
    depth = min((len(trial["holdout_folds"]) for trial in trials), default=0)
    if depth < 2 or len(trials) < 2:
        return searched, trials, None
    matrix = [[trial["holdout_folds"][fold].get("score_vs_spy") for trial in trials]
              for fold in range(depth)]
    return searched, trials, matrix


_TRIAL_LOG_MESSAGE = ("Needs at least two holdout folds across two or more configurations. "
                      "Run pipeline/optimize_weights.py with --holdout-folds.")


def _probability_of_overfitting(optimizer):
    """CSCV across the optimizer's holdout folds, with the block count stated honestly.

    Combinatorially-symmetric cross-validation wants at least eight blocks. The optimizer
    currently writes three holdout folds, which is enough to run the statistic and not
    enough to trust it - so the result is published as provisional rather than suppressed or
    presented as final.
    """
    searched, trials, matrix = _optimizer_trials_matrix(optimizer)
    if matrix is None:
        return {"status": "awaiting_input", "value": None,
                "configurations_searched": len(searched), "reason": _TRIAL_LOG_MESSAGE}
    depth = len(matrix)
    splits = depth if depth % 2 == 0 else depth - 1
    value = evaluation.probability_of_backtest_overfitting(matrix, splits=splits)
    provisional = depth < 8
    return {
        "status": "provisional" if provisional and value is not None else
                  ("ready" if value is not None else "awaiting_input"),
        "value": value,
        "configurations": len(trials),
        "configurations_searched": len(searched),
        "holdout_folds": depth,
        "splits": splits,
        "reason": (f"{depth} holdout folds. CSCV wants at least 8 blocks, so read this as "
                   "directional until the optimizer writes more folds." if provisional else None),
    }


def _search_survival(optimizer):
    """White's Reality Check / SPA verdict for the search, from the same trial log as PBO.

    PBO asks whether the selection *process* is producing noise; this asks whether the
    specific winner it selected beats the field by more than trying this many configurations
    would produce by chance alone. Different question, same trial log.
    """
    searched, trials, matrix = _optimizer_trials_matrix(optimizer)
    if matrix is None:
        return {"status": "awaiting_input", "value": None,
                "configurations_searched": len(searched), "reason": _TRIAL_LOG_MESSAGE}
    result = evaluation.reality_check_spa(matrix)
    if result is None:
        return {"status": "awaiting_input", "value": None,
                "configurations_searched": len(searched),
                "reason": "Not enough complete holdout periods across configurations for the "
                          "SPA bootstrap."}
    return {"status": "ready", "configurations_searched": len(searched), **result}


# ---------------- E. distribution shape ----------------

def live_shadow_returns(root=SHADOW_ROOT):
    """Per-session net returns from immutable production shadow snapshots."""
    try:
        import shadow_portfolios
        _, matched = shadow_portfolios._strategy_matched("production", root)
    except (ImportError, OSError, ValueError, KeyError):
        return {"returns": [], "periods": [], "reason": "Production shadow store is unreadable."}
    if not matched:
        return {"returns": [], "periods": [], "reason": "No production shadow snapshots."}
    defaults = (_read_json(os.path.join(HERE, "config", "shadow_strategies.json")) or {}) \
        .get("construction_defaults", {})
    cost_bps = float(defaults.get("spread_bps", 10)) + float(defaults.get("slippage_bps", 10))
    returns, periods = [], []
    for gross, turnover, period in zip(matched["returns"], matched["turnover"], matched["periods"]):
        sessions = period.get("sessions_elapsed")
        net = float(gross) - float(turnover) * cost_bps / 10_000
        if not sessions or sessions < 1 or net <= -1:
            continue
        daily = (1 + net) ** (1 / sessions) - 1
        returns.append(daily)
        periods.append({**period, "gross_return": gross, "net_return": net,
                        "daily_equivalent_return": daily})
    return {"returns": returns, "periods": periods, "cost_bps": cost_bps,
            "reason": None if returns else "No matched, session-dated production returns."}


def distribution_metrics(backtest, live, live_return_data=None):
    """Wired now, honest about being unreadable until the live sample exists.

    Each metric reports a backtest reference so the machinery is demonstrably working, and
    a live observation counter so nobody mistakes the reference for a live reading.
    """
    portfolio = (backtest or {}).get("portfolio") or {}
    history = portfolio.get("history") or []
    returns = daily_returns_from_history(history)
    closes = [row.get("value") for row in history if row.get("value")]
    required = risk_metrics.DISTRIBUTION_MINIMUM_OBSERVATIONS
    risk_free = _risk_free_daily()

    references = {
        "omega": risk_metrics.omega_ratio(returns, risk_free),
        "ulcer_index": risk_metrics.ulcer_index(closes),
        "martin_ratio": risk_metrics.martin_ratio(returns, closes, risk_free * TRADING_DAYS),
        "cvar_95": risk_metrics.conditional_value_at_risk(returns, 0.95),
        "skew": risk_metrics.skewness(returns),
        "excess_kurtosis": risk_metrics.excess_kurtosis(returns),
        "tail_ratio": risk_metrics.tail_ratio(returns),
        "gain_to_pain": risk_metrics.gain_to_pain(returns),
    }
    labels = {
        "omega": ("Omega ratio", "Probability-weighted gains over losses against the cash rate."),
        "ulcer_index": ("Ulcer index", "How deep and how long the underwater periods run."),
        "martin_ratio": ("Martin ratio", "Excess return per unit of drawdown pain."),
        "cvar_95": ("CVaR-95", "Average loss on the worst 5% of days."),
        "skew": ("Skew", "Which side of the distribution is the fat one."),
        "excess_kurtosis": ("Excess kurtosis", "How much fatter the tails are than normal."),
        "tail_ratio": ("Tail ratio", "Best tail against worst tail."),
        "gain_to_pain": ("Gain to pain", "Net gain per unit of loss taken."),
    }
    live_return_data = live_return_data or {"returns": []}
    live_returns = live_return_data.get("returns") or []
    live_curve, value = [1.0], 1.0
    for result in live_returns:
        value *= 1 + result
        live_curve.append(value)
    live_values = {
        "omega": risk_metrics.omega_ratio(live_returns, risk_free),
        "ulcer_index": risk_metrics.ulcer_index(live_curve),
        "martin_ratio": risk_metrics.martin_ratio(
            live_returns, live_curve, risk_free * TRADING_DAYS),
        "cvar_95": risk_metrics.conditional_value_at_risk(live_returns, 0.95),
        "skew": risk_metrics.skewness(live_returns),
        "excess_kurtosis": risk_metrics.excess_kurtosis(live_returns),
        "tail_ratio": risk_metrics.tail_ratio(live_returns),
        "gain_to_pain": risk_metrics.gain_to_pain(live_returns),
    }
    observations = len(live_returns)
    readable = observations >= required
    message = (f"{observations} matched live return period{'' if observations == 1 else 's'} "
               f"of {required}. Any reading before roughly six months is decorative.")
    return [metric(key, "distribution", labels[key][0],
                   value=live_values[key] if readable else None,
                   reads=labels[key][1], requires_live_sample=True,
                   status="ready" if readable else "accumulating",
                   status_message=None if readable else message,
                   observations=observations, required_observations=required,
                   backtest_reference=references[key], cadence="Quarterly",
                   detail={"live_periods": (live_return_data.get("periods") or [])[-required:]},
                   source="immutable production shadow returns; backtest reference shown")
            for key in labels]


def _risk_free_daily():
    """Per-day risk-free rate for the Omega threshold, from the published factor file."""
    factors = load_json("factors/french.json") or {}
    observations = (factors.get("observations") or [])[-12:]
    monthly = [row.get("risk_free") for row in observations if row.get("risk_free") is not None]
    if not monthly:
        return 0.0
    return (sum(monthly) / len(monthly)) * MONTHS_PER_YEAR / TRADING_DAYS


# ---------------- F. drift alarms ----------------

def population_stability_index(baseline, current, bins=10):
    """PSI between two samples of one feature. Above 0.25 the distribution has moved.

    The standard credit-risk cutoffs apply: below 0.1 is stable, 0.1 to 0.25 is worth
    watching, above 0.25 means the window the model was fitted on no longer describes the
    market it is running in. Quantile edges come from the baseline so the comparison asks
    "where did the current sample land in the old distribution", which is the question.
    """
    baseline = sorted(value for value in baseline if value is not None)
    current = [value for value in current if value is not None]
    if len(baseline) < bins * 2 or len(current) < bins:
        return None
    edges = [baseline[min(len(baseline) - 1, round(index * len(baseline) / bins))]
             for index in range(1, bins)]

    def distribution(values):
        counts = [0] * bins
        for value in values:
            index = sum(1 for edge in edges if value > edge)
            counts[index] += 1
        return [max(count / len(values), 1e-6) for count in counts]

    expected, actual = distribution(baseline), distribution(current)
    return round(sum((a - e) * math.log(a / e) for e, a in zip(expected, actual)), 4)


def feature_psi_from_pit(root=PIT_ROOT, minimum_days=FEATURE_PSI_MINIMUM_DAYS,
                         window_days=FEATURE_PSI_WINDOW_DAYS):
    days = point_in_time_days(root)
    if len(days) < minimum_days:
        return {"status": "accumulating", "value": None, "days": len(days),
                "required_days": minimum_days,
                "reason": (f"Needs {minimum_days} point-in-time days for separated baseline "
                           f"and current windows; {len(days)} recorded.")}
    baseline_days, current_days = days[:window_days], days[-window_days:]

    def samples(selected):
        values = defaultdict(list)
        for day in selected:
            for row in day["rows"]:
                for feature, value in ((row.get("normalized_metric_scores") or {})
                                       .get("champion") or {}).items():
                    if value is not None and not isinstance(value, bool):
                        try:
                            finite = float(value)
                        except (TypeError, ValueError):
                            continue
                        if math.isfinite(finite):
                            values[feature].append(finite)
        return values

    baseline, current = samples(baseline_days), samples(current_days)
    readings = []
    for feature in sorted(set(baseline) & set(current)):
        value = population_stability_index(baseline[feature], current[feature])
        if value is not None:
            readings.append({"feature": feature, "psi": value,
                             "baseline_observations": len(baseline[feature]),
                             "current_observations": len(current[feature])})
    readings.sort(key=lambda row: row["psi"], reverse=True)
    if not readings:
        return {"status": "awaiting_input", "value": None, "days": len(days),
                "required_days": minimum_days,
                "reason": "No feature has enough observations in both PSI windows."}
    return {"status": "ready", "value": readings[0]["psi"], "days": len(days),
            "required_days": minimum_days, "worst_feature": readings[0]["feature"],
            "breached": readings[0]["psi"] > FEATURE_PSI_KILL_THRESHOLD,
            "baseline_window": [baseline_days[0]["date"], baseline_days[-1]["date"]],
            "current_window": [current_days[0]["date"], current_days[-1]["date"]],
            "features": readings}


def data_quality_from_pit(root=PIT_ROOT, universe_path=UNIVERSE_HISTORY_PATH):
    days = point_in_time_days(root)
    if not days:
        return {"status": "awaiting_input", "value": None,
                "reason": "No point-in-time refresh rows exist."}
    latest = days[-1]
    rows = latest["rows"]
    tickers = [row.get("ticker") for row in rows if row.get("ticker")]
    duplicates = sum(count - 1 for count in Counter(tickers).values() if count > 1)
    missing_prices = 0
    missing_price_tickers = []
    missing_price_timestamps = 0
    missing_price_timestamp_tickers = []
    stale_prices = 0
    stale_price_tickers = []
    flags = Counter()
    for row in rows:
        raw = row.get("raw_metric_inputs") or {}
        price = row.get("price", raw.get("price"))
        if price is None:
            missing_prices += 1
            missing_price_tickers.append(row.get("ticker"))
        for flag in row.get("quality_flags") or []:
            flags[str(flag)] += 1
        recorded = _parse_time(row.get("recorded_at"))
        data_as_of = _parse_time(row.get("data_as_of"))
        if price is not None and data_as_of is None:
            missing_price_timestamps += 1
            missing_price_timestamp_tickers.append(row.get("ticker"))
        elif recorded and data_as_of:
            age_hours = (recorded - data_as_of).total_seconds() / 3600
            if age_hours > PRICE_STALE_AFTER_HOURS:
                stale_prices += 1
                stale_price_tickers.append(row.get("ticker"))
    universe = _read_jsonl(universe_path)
    latest_universe = universe[-1] if universe else {}
    critical = missing_prices + missing_price_timestamps + stale_prices + duplicates
    return {
        "status": "ready", "value": critical, "date": latest["date"],
        "refresh_id": latest["refresh_id"], "rows": len(rows),
        "missing_prices": missing_prices,
        "missing_price_tickers": sorted(filter(None, missing_price_tickers)),
        "missing_price_timestamps": missing_price_timestamps,
        "missing_price_timestamp_tickers": sorted(
            filter(None, missing_price_timestamp_tickers)),
        "stale_prices": stale_prices,
        "stale_price_tickers": sorted(filter(None, stale_price_tickers)),
        "duplicate_tickers": duplicates,
        "quality_flags": dict(sorted(flags.items())),
        "universe_churn": {"added": latest_universe.get("added") or [],
                           "removed": latest_universe.get("removed") or [],
                           "observed_at": latest_universe.get("observed_at")},
        "corporate_action_monitoring": {
            "status": "not_available",
            "reason": "No prospective corporate-action event log exists; no miss count is inferred."},
        # A count of critical issues against an implicit zero -- see signal_metrics() for
        # why that's a real, same-scale threshold and not a fabricated one.
        "breached": critical > 0,
    }


def live_backtest_divergence(backtest, live_return_data):
    live_returns = (live_return_data or {}).get("returns") or []
    backtest_returns = daily_returns_from_history(
        ((backtest or {}).get("portfolio") or {}).get("history"))
    if not live_returns or not backtest_returns:
        return {"status": "awaiting_live_sample", "value": None,
                "observations": len(live_returns),
                "reason": (live_return_data or {}).get("reason")
                or "Needs both matched live and backtest daily returns."}
    live_mean = statistics.mean(live_returns)
    backtest_mean = statistics.mean(backtest_returns)
    deviation = statistics.stdev(backtest_returns) if len(backtest_returns) > 1 else None
    error = deviation / math.sqrt(len(live_returns)) if deviation else None
    z_score = (live_mean - backtest_mean) / error if error else None
    ready = len(live_returns) >= DIVERGENCE_MINIMUM_OBSERVATIONS
    # Same-scale (bps/day) form of the z-test bound above, so a bullet chart can plot the
    # divergence against it -- see _signed_bound, which orients this unsigned magnitude to
    # whichever side of zero the divergence currently sits on rather than fabricating a
    # one-sided threshold for a genuinely two-sided (|z| > threshold) test.
    threshold_bps = round(error * CONFIDENCE_INTERVAL_Z * 10_000, 3) if error else None
    return {
        "status": "ready" if ready else "provisional",
        "value": round((live_mean - backtest_mean) * 10_000, 3),
        "observations": len(live_returns),
        "required_observations": DIVERGENCE_MINIMUM_OBSERVATIONS,
        "live_mean_daily_return": live_mean,
        "backtest_mean_daily_return": backtest_mean,
        "divergence_bps_per_day": (live_mean - backtest_mean) * 10_000,
        "z_score": z_score,
        "threshold_bps": threshold_bps,
        "breached": bool(ready and z_score is not None
                         and abs(z_score) > CONFIDENCE_INTERVAL_Z),
        "reason": None if ready else
        f"Directional only until {DIVERGENCE_MINIMUM_OBSERVATIONS} matched live periods.",
        "periods": (live_return_data or {}).get("periods") or [],
    }


def _signed_bound(value, bound):
    """A one-sided ``(kill_threshold_value, comparison)`` pair that reproduces an
    ``abs(value) > bound`` breach test, oriented to whichever side of zero ``value``
    currently sits on. ``bound`` must already be a real, computed, same-scale figure --
    this never invents one, it only picks which direction to compare in so the existing
    lt/gt-only contract can plot a genuinely two-sided test without misrepresenting it.
    """
    if value is None or bound is None:
        return None, None
    return (bound, "gt") if value >= 0 else (-bound, "lt")


def _backtest_ic_reference(panel, horizon="21d"):
    """Mean rank IC and its 95% confidence interval from the backtest panel, at the
    horizon closest to the live monitoring cadence (1 calendar month ~= 21 trading days) --
    the actual backtest-side reference ``live_vs_backtest_ic`` needs to mean what its own
    kill_threshold says ("Live IC below the backtest 95% interval"). Same interval math as
    ic_harness.py's own live-IC confidence interval: mean +/- CONFIDENCE_INTERVAL_Z * (std
    / sqrt(n)), applied here to the backtest series instead of the live one.
    """
    periods = (panel or {}).get("periods") or []
    if not periods:
        return None
    summary = evaluation.ic_decay_curve(periods, [horizon])["horizons"].get(horizon)
    if not summary or summary.get("mean_ic") is None or not summary.get("ic_std") or summary.get("periods", 0) < 2:
        return None
    error = summary["ic_std"] / math.sqrt(summary["periods"])
    return {
        "horizon": horizon,
        "periods": summary["periods"],
        "mean_ic": summary["mean_ic"],
        "standard_error": round(error, 4),
        "confidence_interval_95": [round(summary["mean_ic"] - CONFIDENCE_INTERVAL_Z * error, 4),
                                    round(summary["mean_ic"] + CONFIDENCE_INTERVAL_Z * error, 4)],
    }


def position_reconciliation(execution):
    intended = (execution or {}).get("intended_positions") or {}
    actual = (execution or {}).get("actual_positions") or {}
    if not intended or not actual:
        return {"status": "awaiting_live_sample", "value": None,
                "reason": ("Needs intended and actual close weights in "
                           "pipeline/data/validation/live_execution.json.")}
    rows = []
    for ticker in sorted(set(intended) | set(actual)):
        planned = float(intended.get(ticker) or 0)
        held = float(actual.get(ticker) or 0)
        rows.append({"ticker": ticker, "intended_weight": planned,
                     "actual_weight": held, "difference": held - planned})
    worst = max(rows, key=lambda row: abs(row["difference"]))
    value = abs(worst["difference"]) * 10_000
    return {"status": "ready", "value": round(value, 2), "rows": rows,
            "worst_ticker": worst["ticker"],
            "breached": value > UNEXPLAINED_POSITION_DIFFERENCE_BPS}


def monitoring_metrics(live, ic_validation, *, backtest=None, live_return_data=None,
                       pit_root=PIT_ROOT, universe_path=UNIVERSE_HISTORY_PATH,
                       execution=None, panel=None):
    live_days = live["days"]
    accumulating = (f"{live_days} live day{'' if live_days == 1 else 's'} recorded, "
                    f"{live['refreshes']} refresh{'' if live['refreshes'] == 1 else 'es'}.")
    champion = ((ic_validation or {}).get("variants") or {}).get("champion") or {}
    monthly = champion.get("1M") or {}
    psi = feature_psi_from_pit(pit_root)
    divergence = live_backtest_divergence(backtest, live_return_data)
    quality = data_quality_from_pit(pit_root, universe_path)
    reconciliation = position_reconciliation(execution)

    live_ic = monthly.get("mean_rank_ic")
    backtest_ic = _backtest_ic_reference(panel)
    ic_kill_threshold_value = backtest_ic["confidence_interval_95"][0] if backtest_ic else None
    ic_comparison = "lt" if ic_kill_threshold_value is not None else None
    ic_breached = (live_ic is not None and ic_kill_threshold_value is not None
                   and live_ic < ic_kill_threshold_value)
    div_kill_threshold_value, div_comparison = _signed_bound(
        divergence.get("value"), divergence.get("threshold_bps"))

    rows = [
        metric("live_vs_backtest_ic", "monitoring", "Rolling 60-day live IC versus backtest",
               value=live_ic,
               reads="The decay alarm. Live IC below the backtest confidence interval means "
                     "the edge is gone or was never there.",
               kill_threshold="Live IC below the backtest 95% interval",
               kill_threshold_value=ic_kill_threshold_value, comparison=ic_comparison,
               breached=ic_breached, backtest_reference=backtest_ic["mean_ic"] if backtest_ic else None,
               requires_live_sample=True, status="accumulating",
               status_message=monthly.get("status_message") or accumulating,
               detail={"backtest_reference": backtest_ic},
               observations=monthly.get("periods_accumulated", 0),
               required_observations=monthly.get("minimum_periods"),
               cadence="Weekly", source="prospective IC harness"),
        metric("feature_psi", "monitoring", "Feature distribution PSI",
               value=psi.get("value"),
               display=None if psi.get("value") is None else
               f"{psi['value']:.3f} worst ({psi.get('worst_feature')})",
               reads="Detects when the live feature population leaves its earlier PIT window.",
               kill_threshold=f"PSI above {FEATURE_PSI_KILL_THRESHOLD}",
               kill_threshold_value=FEATURE_PSI_KILL_THRESHOLD, comparison="gt",
               requires_live_sample=True,
               breached=psi.get("breached"), status=psi.get("status"),
               status_message=psi.get("reason"), detail=psi,
               observations=psi.get("days"), required_observations=psi.get("required_days"),
               cadence="Monthly", source="point-in-time normalized feature store"),
        metric("live_vs_backtest_divergence", "monitoring",
               "Live versus backtest daily return divergence", value=divergence.get("value"),
               display=None if divergence.get("value") is None else
               f"{divergence['value']:+.2f} bps/day",
               reads="Mean prospective production return versus the historical backtest mean.",
               kill_threshold="Absolute mean divergence above the 95% backtest sampling interval",
               kill_threshold_value=div_kill_threshold_value, comparison=div_comparison,
               breached=divergence.get("breached"), requires_live_sample=True,
               status=divergence.get("status"), status_message=divergence.get("reason"),
               detail=divergence, observations=divergence.get("observations"),
               required_observations=divergence.get("required_observations"),
               cadence="Daily", source="immutable production shadow returns"),
        metric("data_quality_counters", "monitoring", "Data quality counters",
               value=quality.get("value"),
               display=None if quality.get("value") is None else
               f"{quality['value']} critical refresh issue{'s' if quality['value'] != 1 else ''}",
               reads="Missing/stale price observations, duplicate rows, quality flags, and universe churn.",
               kill_threshold="Any missing, unstamped, stale, or duplicate current price row",
               kill_threshold_value=0, comparison="gt",
               breached=quality.get("breached"), requires_live_sample=True,
               status=quality.get("status"), status_message=quality.get("reason"),
               detail=quality, observations=quality.get("rows"), cadence="Daily",
               source="point-in-time refresh and universe stores"),
        metric("position_reconciliation", "monitoring", "Position reconciliation",
               value=reconciliation.get("value"),
               display=None if reconciliation.get("value") is None else
               f"{reconciliation['value']:.1f} bps worst",
               reads="Intended against actual weights at the close.",
               kill_threshold="Any unexplained difference above 10 bps",
               kill_threshold_value=UNEXPLAINED_POSITION_DIFFERENCE_BPS, comparison="gt",
               breached=reconciliation.get("breached"), requires_live_sample=True,
               status=reconciliation.get("status"), status_message=reconciliation.get("reason"),
               detail=reconciliation, observations=len((execution or {}).get("actual_positions") or {}),
               cadence="Daily", source="external broker position export"),
    ]
    return rows


# ---------------- report ----------------

def build_report(*, backtest=_UNSET, optimizer=_UNSET, panel=_UNSET, factors=_UNSET,
                 ic_validation=_UNSET, live=_UNSET, sector_history=_UNSET,
                 execution=_UNSET, pit_root=PIT_ROOT, shadow_root=SHADOW_ROOT,
                 universe_path=UNIVERSE_HISTORY_PATH):
    """Assemble the artifact. Any input left unset is read from disk; passing None means
    "this input genuinely does not exist", which is a different thing and must stay so."""
    backtest = _read_json(BACKTEST_PATH) if backtest is _UNSET else backtest
    optimizer = _read_json(OPTIMIZER_PATH) if optimizer is _UNSET else optimizer
    panel = _read_json(PANEL_PATH) if panel is _UNSET else panel
    factors = load_json("factors/french.json") if factors is _UNSET else factors
    ic_validation = (load_json("validation/ic_validation.json")
                     if ic_validation is _UNSET else ic_validation)
    live = live_sample() if live is _UNSET else live
    sector_history = (_read_jsonl(SECTOR_WEIGHT_HISTORY_PATH)
                      if sector_history is _UNSET else sector_history)
    execution = _read_json(LIVE_EXECUTION_PATH) if execution is _UNSET else execution
    live_return_data = live_shadow_returns(shadow_root)

    metrics = (signal_metrics(panel)
               + construction_metrics(backtest, factors, sector_history)
               + cost_metrics(backtest, panel, execution)
               + honesty_metrics(backtest, optimizer)
               + risk_adjusted_metrics(backtest)
               + tax_and_stress_metrics(backtest)
               + scenario_metrics(backtest, factors)
               + distribution_metrics(backtest, live, live_return_data)
               + monitoring_metrics(live, ic_validation, backtest=backtest,
                                    live_return_data=live_return_data, pit_root=pit_root,
                                    universe_path=universe_path, execution=execution, panel=panel))
    ready = [row for row in metrics if row["status"] in ("ready", "provisional")]
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "groups": GROUPS,
        "cadence": CADENCE,
        "live_sample": live,
        "metrics": metrics,
        "summary": {
            "total": len(metrics),
            "ready": len(ready),
            "breached": sum(1 for row in metrics if row["breached"]),
            "sample_free_total": sum(1 for row in metrics if not row["requires_live_sample"]),
            "sample_free_ready": sum(1 for row in ready if not row["requires_live_sample"]),
            "needs_sample_total": sum(1 for row in metrics if row["requires_live_sample"]),
        },
        "sources": {
            "backtest": os.path.basename(BACKTEST_PATH) if backtest else None,
            "optimizer": os.path.basename(OPTIMIZER_PATH) if optimizer else None,
            "panel": os.path.basename(PANEL_PATH) if panel else None,
            "factors": "factors/french.json" if factors else None,
            "sector_history": (os.path.relpath(SECTOR_WEIGHT_HISTORY_PATH, HERE)
                               if sector_history else None),
            "execution": os.path.relpath(LIVE_EXECUTION_PATH, HERE) if execution else None,
            "live_returns": "shadow_store/production" if live_return_data.get("returns") else None,
        },
    }


def write_report(report=None):
    report = report or build_report()
    save_json(PUBLIC_NAME, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--panel", default=PANEL_PATH,
                        help="Scored panel written by backtest_monthly.py --panel-out")
    parser.add_argument("--print", action="store_true", help="Print every metric and its status")
    args = parser.parse_args(argv)
    report = build_report(panel=_read_json(args.panel))
    write_report(report)
    summary = report["summary"]
    if args.print:
        for row in report["metrics"]:
            gate = "live" if row["requires_live_sample"] else "now "
            print(f"[{gate}] {row['status']:<18} {row['label']:<44} {row['display'] or '-'}")
    LOG.info(f"Signal metrics: {summary['sample_free_ready']} of {summary['sample_free_total']} "
             f"sample-free metrics computed, {summary['breached']} kill thresholds breached, "
             f"{summary['needs_sample_total']} awaiting live data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
