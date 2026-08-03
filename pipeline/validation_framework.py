"""Immutable shadow snapshots and legal manual external-ranking imports."""

import csv
import hashlib
import json
import os
import math
import random
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


def walk_forward_splits(observations, train_periods, test_periods):
    """Expanding-window splits; test observations are never used to fit earlier weights."""
    splits, end = [], train_periods
    while end + test_periods <= len(observations):
        splits.append({"train": observations[:end], "test": observations[end:end + test_periods]})
        end += test_periods
    return splits


def _max_drawdown(returns):
    value = peak = 1.0
    worst = 0.0
    for result in returns:
        value *= 1 + result
        peak = max(peak, value)
        worst = min(worst, value / peak - 1)
    return worst


def performance_metrics(gross_returns, benchmark_returns=None, turnover=None, cost_bps=0, periods_per_year=12):
    """Matched-period, net-of-cost metrics. Inputs are decimal periodic returns."""
    gross_returns = [float(value) for value in gross_returns]
    turnover = list(turnover or [0] * len(gross_returns))
    if len(turnover) != len(gross_returns): raise ValueError("turnover must match returns")
    net = [value - float(turnover[index]) * cost_bps / 10_000 for index, value in enumerate(gross_returns)]
    total = math.prod(1 + value for value in net) - 1
    years = len(net) / periods_per_year
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 and total > -1 else None
    volatility = stdev(net) * math.sqrt(periods_per_year) if len(net) > 1 else None
    sharpe = mean(net) / stdev(net) * math.sqrt(periods_per_year) if len(net) > 1 and stdev(net) else None
    downside = math.sqrt(mean(min(value, 0) ** 2 for value in net)) if net else 0
    sortino = mean(net) / downside * math.sqrt(periods_per_year) if downside else None
    drawdown = _max_drawdown(net)
    output = {"observations": len(net), "gross_return": math.prod(1 + value for value in gross_returns) - 1,
              "transaction_costs": sum(float(value) for value in turnover) * cost_bps / 10_000,
              "net_return": total, "cagr": cagr, "annualized_volatility": volatility,
              "sharpe": sharpe, "sortino": sortino, "maximum_drawdown": drawdown,
              "calmar": cagr / abs(drawdown) if cagr is not None and drawdown else None,
              "turnover": sum(float(value) for value in turnover)}
    if benchmark_returns is not None:
        benchmark = [float(value) for value in benchmark_returns]
        if len(benchmark) != len(net): raise ValueError("benchmark must match returns")
        variance = sum((value - mean(benchmark)) ** 2 for value in benchmark) / max(1, len(benchmark) - 1)
        covariance = sum((r - mean(net)) * (b - mean(benchmark)) for r, b in zip(net, benchmark)) / max(1, len(net) - 1)
        beta = covariance / variance if variance else None
        output.update({"beta": beta, "annualized_alpha": (mean(net) - (beta or 0) * mean(benchmark)) * periods_per_year,
                       "net_excess_return": total - (math.prod(1 + value for value in benchmark) - 1)})
    return output


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
