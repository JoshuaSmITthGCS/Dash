"""Immutable shadow snapshots and legal manual external-ranking imports."""

import csv
import hashlib
import json
import os
import math
import random
from collections import defaultdict
from statistics import mean, stdev
from datetime import datetime, timezone

REQUIRED_EXTERNAL = {"date", "ticker", "rank"}
STRATEGIES = ("production", "structural_tactical", "momentum", "quality_value", "combined",
              "SPY", "eligible_universe_equal_weight", "external")


def append_immutable_snapshot(root, strategy, as_of, rows, metadata=None):
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy}")
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    directory = os.path.join(root, strategy)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{str(as_of)[:10]}-{digest[:12]}.json")
    if os.path.exists(path):
        return path
    if any(name.startswith(f"{str(as_of)[:10]}-") for name in os.listdir(directory)):
        raise FileExistsError("an immutable snapshot already exists for this strategy/date")
    payload = {"schema_version": "1.0.0", "strategy": strategy, "as_of": str(as_of)[:10],
               "recorded_at": datetime.now(timezone.utc).isoformat(), "content_sha256": digest,
               "methodology": metadata or {}, "rows": rows}
    temporary = f"{path}.tmp"
    with open(temporary, "w") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False)
        handle.write("\n")
    os.replace(temporary, path)
    return path


def import_external_rankings(path):
    """Read a user-provided CSV/JSON only; never fetch or scrape external pages."""
    path = str(path)
    if path.lower().endswith(".json"):
        with open(path) as handle: rows = json.load(handle)
    else:
        with open(path, newline="") as handle: rows = list(csv.DictReader(handle))
    if not isinstance(rows, list): raise ValueError("external ranking must be an array")
    clean = []
    for row in rows:
        missing = REQUIRED_EXTERNAL - row.keys()
        if missing: raise ValueError(f"missing external fields: {sorted(missing)}")
        clean.append({**row, "date": str(row["date"])[:10], "ticker": str(row["ticker"]).strip().upper(),
                      "rank": int(row["rank"])})
    return clean


def label_overlap_periods(horizon_sessions, sessions_per_period=21):
    """How many observation periods a forward label spans.

    A 63-session label observed at period t is still resolving at t+1 and t+2. Those periods'
    labels are built from overlapping price paths, so training on them and testing on t leaks
    the answer. Rounded up: a label that spills even partly into the next period overlaps it.
    """
    if horizon_sessions <= 0 or sessions_per_period <= 0:
        return 0
    return max(0, -(-horizon_sessions // sessions_per_period) - 1)


def walk_forward_splits(observations, train_periods, test_periods, *, purge_periods=0,
                        embargo_periods=0):
    """Expanding-window splits; test observations are never used to fit earlier weights.

    ``purge_periods`` drops training observations immediately before the test window whose
    forward labels overlap it -- the leak that overlapping labels create in any horizon longer
    than the rebalance interval (Lopez de Prado, *Advances in Financial Machine Learning*,
    ch. 7). ``embargo_periods`` additionally drops observations immediately *after* the test
    window from later training folds, so serial correlation across the boundary cannot carry
    test information back into training.

    ``embargo_periods`` drops a further band on top of the purge, to break serial correlation
    across the boundary rather than only label overlap.

    Both act on the *trailing edge of training* because these splits are strictly expanding:
    training is always earlier than test, so the post-test embargo band of combinatorial
    cross-validation has no analogue here -- there is no path by which post-test data reaches
    a training fold. Claiming otherwise would be theatre.

    Both default to zero, which reproduces the original behaviour exactly. Derive the purge
    from the target horizon with ``label_overlap_periods``.
    """
    if purge_periods < 0 or embargo_periods < 0:
        raise ValueError("purge_periods and embargo_periods must be non-negative")
    excluded = purge_periods + embargo_periods
    splits, end = [], train_periods
    while end + test_periods <= len(observations):
        test_start, test_end = end, end + test_periods
        train_end = max(0, test_start - excluded)
        splits.append({
            "train": observations[:train_end],
            "test": observations[test_start:test_end],
            "purged": observations[train_end:test_start],
            "purge_periods": purge_periods,
            "embargo_periods": embargo_periods,
        })
        end += test_periods
    return splits


def _ranks(values):
    """Average ranks for ties; rank 1 is the smallest value."""
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][1] == ordered[cursor][1]:
            end += 1
        rank = (cursor + 1 + end) / 2
        for original, _ in ordered[cursor:end]: ranks[original] = rank
        cursor = end
    return ranks


def spearman_rank_ic(scores, forward_returns):
    pairs = [(float(score), float(result)) for score, result in zip(scores, forward_returns)
             if score is not None and result is not None and math.isfinite(float(score))
             and math.isfinite(float(result))]
    if len(pairs) < 3: return None
    left, right = _ranks([pair[0] for pair in pairs]), _ranks([pair[1] for pair in pairs])
    left_mean, right_mean = mean(left), mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    scale = math.sqrt(sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right))
    return numerator / scale if scale else None


def rank_diagnostics(periods, quantiles=5):
    """Monthly cross-sectional IC and monotonicity from point-in-time rows."""
    monthly, quantile_returns = [], defaultdict(list)
    for period in periods:
        rows = [row for row in period.get("rows", []) if row.get("score") is not None
                and row.get("forward_return") is not None]
        ic = spearman_rank_ic([row["score"] for row in rows], [row["forward_return"] for row in rows])
        monthly.append({"date": period.get("date"), "rank_ic": ic, "eligible_count": len(rows)})
        ordered = sorted(rows, key=lambda row: row["score"])
        for index, row in enumerate(ordered):
            bucket = min(quantiles, int(index * quantiles / max(1, len(ordered))) + 1)
            quantile_returns[bucket].append(float(row["forward_return"]))
    values = [row["rank_ic"] for row in monthly if row["rank_ic"] is not None]
    averages = {str(bucket): mean(results) for bucket, results in sorted(quantile_returns.items())}
    monotonic = all(averages[str(index)] <= averages[str(index + 1)]
                    for index in range(1, quantiles) if str(index) in averages and str(index + 1) in averages)
    return {"monthly_rank_ic": monthly, "mean_rank_ic": mean(values) if values else None,
            "ic_information_ratio": (mean(values) / stdev(values) if len(values) > 1 and stdev(values) else None),
            "quantile_returns": averages, "quantile_monotonic": monotonic,
            "top_minus_bottom_spread": (averages.get(str(quantiles), 0) - averages.get("1", 0)
                                        if str(quantiles) in averages and "1" in averages else None),
            "hit_rate": (sum(value > 0 for value in values) / len(values) if values else None)}


def convert_annual_risk_free(annual_rate, periods_per_year=12):
    """Convert an effective annual decimal rate to the matching periodic rate."""
    rate = float(annual_rate)
    if rate <= -1: raise ValueError("annual risk-free rate must be greater than -100%")
    return (1 + rate) ** (1 / periods_per_year) - 1


def untouched_holdout(observations, holdout_periods):
    if holdout_periods <= 0 or holdout_periods >= len(observations):
        raise ValueError("holdout_periods must leave nonempty development and holdout sets")
    return {"development": observations[:-holdout_periods], "holdout": observations[-holdout_periods:],
            "holdout_locked": True}


def _max_drawdown(returns):
    value = peak = 1.0
    worst = 0.0
    for result in returns:
        value *= 1 + result
        peak = max(peak, value)
        worst = min(worst, value / peak - 1)
    return worst


def performance_metrics(gross_returns, benchmark_returns=None, turnover=None, cost_bps=0, periods_per_year=12,
                        risk_free_returns=None, risk_free_metadata=None):
    """Matched-period, net-of-cost metrics. Inputs are decimal periodic returns."""
    gross_returns = [float(value) for value in gross_returns]
    turnover = list(turnover or [0] * len(gross_returns))
    if len(turnover) != len(gross_returns): raise ValueError("turnover must match returns")
    net = [value - float(turnover[index]) * cost_bps / 10_000 for index, value in enumerate(gross_returns)]
    total = math.prod(1 + value for value in net) - 1
    years = len(net) / periods_per_year
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 and total > -1 else None
    volatility = stdev(net) * math.sqrt(periods_per_year) if len(net) > 1 else None
    risk_free = ([float(value) for value in risk_free_returns] if risk_free_returns is not None else [0.0] * len(net))
    if len(risk_free) != len(net): raise ValueError("risk-free series must match returns")
    excess_rf = [value - risk_free[index] for index, value in enumerate(net)]
    sharpe = mean(excess_rf) / stdev(excess_rf) * math.sqrt(periods_per_year) if len(excess_rf) > 1 and stdev(excess_rf) else None
    downside = math.sqrt(mean(min(value, 0) ** 2 for value in excess_rf)) if excess_rf else 0
    sortino = mean(excess_rf) / downside * math.sqrt(periods_per_year) if downside else None
    drawdown = _max_drawdown(net)
    output = {"observations": len(net), "gross_return": math.prod(1 + value for value in gross_returns) - 1,
              "transaction_costs": sum(float(value) for value in turnover) * cost_bps / 10_000,
              "net_return": total, "cagr": cagr, "annualized_volatility": volatility,
              "sharpe": sharpe, "sortino": sortino, "maximum_drawdown": drawdown,
              "calmar": cagr / abs(drawdown) if cagr is not None and drawdown else None,
              "turnover": sum(float(value) for value in turnover),
              "risk_free": {"series": risk_free, "periods_per_year": periods_per_year,
                            "metadata": risk_free_metadata or {"series_id": None, "as_of": None,
                                                                "missing_data_policy": "zero_only_when_explicit"}}}
    if benchmark_returns is not None:
        benchmark = [float(value) for value in benchmark_returns]
        if len(benchmark) != len(net): raise ValueError("benchmark must match returns")
        variance = sum((value - mean(benchmark)) ** 2 for value in benchmark) / max(1, len(benchmark) - 1)
        covariance = sum((r - mean(net)) * (b - mean(benchmark)) for r, b in zip(net, benchmark)) / max(1, len(net) - 1)
        beta = covariance / variance if variance else None
        output.update({"beta": beta, "annualized_alpha": (mean(net) - (beta or 0) * mean(benchmark)) * periods_per_year,
                       "net_excess_return": total - (math.prod(1 + value for value in benchmark) - 1)})
    return output


def grouped_attribution(rows, group_field):
    """Additive return contribution by sector, size, regime, or another declared group."""
    groups = defaultdict(float)
    for row in rows:
        groups[str(row.get(group_field) or "unclassified")] += float(row.get("contribution") or 0)
    return dict(sorted(groups.items()))


def deflated_sharpe_ratio(observed_sharpe, observations, trials=1, skew=0.0, kurtosis=3.0):
    """Conservative normal approximation that records the multiple-testing penalty."""
    if observations < 3 or trials < 1: return None
    expected_max = math.sqrt(2 * math.log(max(1, trials))) if trials > 1 else 0.0
    variance = max(1e-12, (1 - skew * observed_sharpe + ((kurtosis - 1) / 4) * observed_sharpe ** 2) / (observations - 1))
    z = (observed_sharpe - expected_max) / math.sqrt(variance)
    probability = .5 * (1 + math.erf(z / math.sqrt(2)))
    return {"deflated_sharpe_probability": probability, "observed_sharpe": observed_sharpe,
            "expected_maximum_sharpe": expected_max, "trials": trials, "observations": observations,
            "assumption": "normal_approximation"}


def append_multiple_testing_log(path, test):
    """Append a hypothesis declaration without mutating prior test records."""
    required = {"test_id", "declared_at", "hypothesis", "holdout_start"}
    missing = required - set(test)
    if missing: raise ValueError(f"missing multiple-testing fields: {sorted(missing)}")
    existing = []
    if os.path.exists(path):
        with open(path) as handle: existing = json.load(handle)
    if any(row["test_id"] == test["test_id"] for row in existing):
        raise FileExistsError("test_id already recorded")
    payload = [*existing, test]
    temporary = f"{path}.tmp"
    with open(temporary, "w") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False); handle.write("\n")
    os.replace(temporary, path)
    return len(payload)


def block_bootstrap_excess(strategy_returns, benchmark_returns, block_size=3, samples=2000, seed=0):
    """Preserve short-run dependence by resampling contiguous return blocks."""
    if len(strategy_returns) != len(benchmark_returns) or not strategy_returns: raise ValueError("matched returns required")
    excess = [s - b for s, b in zip(strategy_returns, benchmark_returns)]
    rng, n, estimates = random.Random(seed), len(excess), []
    for _ in range(samples):
        draw = []
        while len(draw) < n:
            start = rng.randrange(n)
            draw.extend(excess[(start + offset) % n] for offset in range(block_size))
        estimates.append(mean(draw[:n]))
    estimates.sort()
    return {"mean_excess": mean(excess), "confidence_interval_95": [estimates[int(.025 * samples)], estimates[int(.975 * samples)]],
            "probability_positive": sum(value > 0 for value in estimates) / samples, "samples": samples,
            "block_size": block_size}
