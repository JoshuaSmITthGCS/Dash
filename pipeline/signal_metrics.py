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
DIVERGENCE_Z_THRESHOLD = 1.96
PRICE_STALE_AFTER_HOURS = 36
MAXIMUM_PERCENT_OF_ADV = 5
SEARCH_SURVIVAL_MINIMUM = 0.95

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
            _pending("ic_decay", "signal", "IC decay curve", message,
                     reads="Which horizon the edge lives at.", cadence="Monthly"),
            _pending("per_leg_ic", "signal", "Per-leg IC", message,
                     reads="Which legs predict on their own.",
                     kill_threshold="Any leg IC around zero", cadence="Monthly"),
            _pending("drop_one_leg", "signal", "Drop-one-leg delta IC", message,
                     reads="Marginal contribution of each leg to the composite.",
                     kill_threshold="Negative delta means the leg hurts",
                     cadence="Annually or on any refit"),
            _pending("leg_correlation", "signal", "Leg correlation matrix", message,
                     reads="Redundancy between legs.",
                     kill_threshold=f"Correlation > {REDUNDANT_LEG_CORRELATION}", cadence="Monthly"),
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
                       kill_threshold=f"Any leg IC below {MINIMUM_MEAN_IC}", breached=bool(dead),
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
                           breached=bool(harmful), detail=dropped,
                           cadence="Annually or on any refit", source="backtest panel"))
    else:
        rows.append(_pending("drop_one_leg", "signal", "Drop-one-leg delta IC",
                             "The panel carries no leg weights to drop.",
                             cadence="Annually or on any refit"))

    correlation = evaluation.leg_correlation_matrix(periods, list(weights) or None)
    rows.append(metric("leg_correlation", "signal", "Leg correlation matrix",
                       value=len(correlation["redundant_pairs"]),
                       display=(f"{len(correlation['redundant_pairs'])} redundant pair"
                                f"{'' if len(correlation['redundant_pairs']) == 1 else 's'}"),
                       reads="Redundancy between legs. Two correlated legs are one leg counted twice.",
                       kill_threshold=f"Correlation above {REDUNDANT_LEG_CORRELATION}",
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


def _sector_active_weight_metric(history):
    if not history:
        return _pending(
            "sector_active_weights", "construction", "Sector active weights",
            "No prospective sector snapshot exists. Run pipeline/sector_weight_history.py; "
            "historical sectors are not backfilled from today's classifications.",
            reads="Sector bets against SPY at each recorded production refresh.",
            cadence="Daily",
        )
    latest = history[-1]
    active = latest.get("active_sector_weights") or {}
    classified = latest.get("strategy_classified_weight")
    if not active:
        return _pending(
            "sector_active_weights", "construction", "Sector active weights",
            "The sector history has no comparable strategy and benchmark weights.",
            reads="Sector bets against SPY at each recorded production refresh.",
            cadence="Daily",
        )
    ranked = sorted(active.items(), key=lambda item: abs(item[1]), reverse=True)
    sector, largest = ranked[0]
    history_detail = [
        {"as_of": row.get("as_of"), "active_sector_weights": row.get("active_sector_weights"),
         "strategy_classified_weight": row.get("strategy_classified_weight"),
         "benchmark_classified_weight": row.get("benchmark_classified_weight")}
        for row in history[-60:]
    ]
    return metric(
        "sector_active_weights", "construction", "Sector active weights",
        value=round(abs(largest) * 100, 2),
        display=f"{sector.replace('_', ' ').title()} {largest * 100:+.1f}pp largest",
        reads="Current production-sector weights minus SPY, retained prospectively by date.",
        kill_threshold="Strategy sector classification coverage below 80%",
        breached=classified is not None and classified < 0.8,
        detail={"as_of": latest.get("as_of"), "strategy": latest.get("strategy"),
                "benchmark": latest.get("benchmark"), "active_sector_weights": active,
                "strategy_sector_weights": latest.get("strategy_sector_weights"),
                "benchmark_sector_weights": latest.get("benchmark_sector_weights"),
                "strategy_classified_weight": classified,
                "benchmark_classified_weight": latest.get("benchmark_classified_weight"),
                "history": history_detail},
        observations=len(history), cadence="Daily",
        source="prospective sector-weight history",
    )


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
        breached=negative_momentum is not None and negative_momentum < -0.1,
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
    rows.append(metric("rolling_beta_60d", "construction", "Rolling 60-day beta",
                       value=round(betas[-1], 2) if betas else None,
                       display=None if not betas else f"{betas[-1]:.2f} (range {min(betas):.2f}–{max(betas):.2f})",
                       reads="A point-estimate beta hides how unstable every beta-adjusted "
                             "number on the dashboard is.",
                       kill_threshold="A swing wider than 0.3 makes excess-return figures unstable",
                       breached=swing is not None and swing > 0.3,
                       detail={"window": 60, "observations": len(betas), "swing": swing,
                               "series": [round(value, 3) for value in betas[-60:]]},
                       cadence="Weekly", source="backtest equity curve"))

    drift = [round(sum(weight for weight in row if weight), 4) for row in weights if row]
    rows.append(metric("net_exposure_drift", "construction", "Net exposure drift",
                       value=round(max(drift) - min(drift), 4) if drift else None,
                       display=None if not drift else f"{min(drift):.3f}–{max(drift):.3f} invested",
                       reads="Whether planned weights sum where they are supposed to.",
                       detail={"rebalances": len(drift)}, cadence="Daily",
                       source="backtest rebalances"))

    rows.append(_sector_active_weight_metric(sector_history or []))
    return rows


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
                           "decision_notional": notional})
    total_notional = sum(row["decision_notional"] for row in shortfalls)
    shortfall = (sum(row["bps"] * row["decision_notional"] for row in shortfalls)
                 / total_notional if total_notional else None)
    fill_rate = filled_quantity / intended_quantity if intended_quantity else None
    intended = execution.get("intended_positions") or {}
    actual = execution.get("actual_positions") or {}
    unpositioned = sorted(ticker for ticker, weight in intended.items()
                          if float(weight or 0) > 0 and float(actual.get(ticker) or 0) <= 0)
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
    return rows


def _probability_of_overfitting(optimizer):
    """CSCV across the optimizer's holdout folds, with the block count stated honestly.

    Combinatorially-symmetric cross-validation wants at least eight blocks. The optimizer
    currently writes three holdout folds, which is enough to run the statistic and not
    enough to trust it - so the result is published as provisional rather than suppressed or
    presented as final.
    """
    searched = (optimizer or {}).get("sweeps", {}).get("categories") or []
    # The optimizer only re-runs holdout folds for the configurations that survived the
    # in-sample sweep, so those are the ones CSCV can be run across. The full search count is
    # carried alongside because it, not the finalist count, is what deflation has to price.
    trials = [trial for trial in searched if len(trial.get("holdout_folds") or []) >= 2]
    depth = min((len(trial["holdout_folds"]) for trial in trials), default=0)
    if depth < 2 or len(trials) < 2:
        return {"status": "awaiting_input", "value": None,
                "configurations_searched": len(searched),
                "reason": "Needs at least two holdout folds across two or more configurations. "
                          "Run pipeline/optimize_weights.py with --holdout-folds."}
    matrix = [[trial["holdout_folds"][fold].get("score_vs_spy") for trial in trials]
              for fold in range(depth)]
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
    return {
        "status": "ready" if ready else "provisional",
        "value": round((live_mean - backtest_mean) * 10_000, 3),
        "observations": len(live_returns),
        "required_observations": DIVERGENCE_MINIMUM_OBSERVATIONS,
        "live_mean_daily_return": live_mean,
        "backtest_mean_daily_return": backtest_mean,
        "divergence_bps_per_day": (live_mean - backtest_mean) * 10_000,
        "z_score": z_score,
        "breached": bool(ready and z_score is not None
                         and abs(z_score) > DIVERGENCE_Z_THRESHOLD),
        "reason": None if ready else
        f"Directional only until {DIVERGENCE_MINIMUM_OBSERVATIONS} matched live periods.",
        "periods": (live_return_data or {}).get("periods") or [],
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
            "worst_ticker": worst["ticker"], "breached": value > 10}


def monitoring_metrics(live, ic_validation, *, backtest=None, live_return_data=None,
                       pit_root=PIT_ROOT, universe_path=UNIVERSE_HISTORY_PATH,
                       execution=None):
    live_days = live["days"]
    accumulating = (f"{live_days} live day{'' if live_days == 1 else 's'} recorded, "
                    f"{live['refreshes']} refresh{'' if live['refreshes'] == 1 else 'es'}.")
    champion = ((ic_validation or {}).get("variants") or {}).get("champion") or {}
    monthly = champion.get("1M") or {}
    psi = feature_psi_from_pit(pit_root)
    divergence = live_backtest_divergence(backtest, live_return_data)
    quality = data_quality_from_pit(pit_root, universe_path)
    reconciliation = position_reconciliation(execution)
    rows = [
        metric("live_vs_backtest_ic", "monitoring", "Rolling 60-day live IC versus backtest",
               value=monthly.get("mean_rank_ic"),
               reads="The decay alarm. Live IC below the backtest confidence interval means "
                     "the edge is gone or was never there.",
               kill_threshold="Live IC below the backtest 95% interval",
               requires_live_sample=True, status="accumulating",
               status_message=monthly.get("status_message") or accumulating,
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
               + distribution_metrics(backtest, live, live_return_data)
               + monitoring_metrics(live, ic_validation, backtest=backtest,
                                    live_return_data=live_return_data, pit_root=pit_root,
                                    universe_path=universe_path, execution=execution))
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
