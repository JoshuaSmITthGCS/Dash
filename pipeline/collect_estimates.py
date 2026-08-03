"""Append today's normalized consensus snapshot; never manufacture prior history."""

import json
import os
from datetime import datetime, timezone

from estimate_snapshots import append_estimate_snapshot, normalize_estimates

HERE = os.path.dirname(os.path.abspath(__file__))


def _table(frame):
    if frame is None or getattr(frame, "empty", True): return {}
    return {str(index): {str(key): (None if value != value else value) for key, value in row.items()}
            for index, row in frame.to_dict(orient="index").items()}


def _first(tables, row_keys, field_keys):
    for table in tables:
        for row_key in row_keys:
            row = table.get(row_key) or {}
            for field in field_keys:
                if row.get(field) is not None: return row[field]
    return None


def collect(root=None, symbols=None):
    import yfinance as yf
    with open(os.path.join(HERE, "config", "estimate_collection.json")) as handle: config = json.load(handle)
    symbols = list(symbols or config["symbols"])
    root = root or os.path.join(HERE, "data", "estimates")
    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    complete, failed = [], {}
    horizons = {"current_quarter": ("0q",), "next_quarter": ("+1q", "1q"),
                "current_year": ("0y",), "next_year": ("+1y", "1y")}
    for ticker in symbols:
        try:
            instrument = yf.Ticker(ticker)
            eps, revenue = _table(instrument.get_earnings_estimate()), _table(instrument.get_revenue_estimate())
            trend, revisions = _table(instrument.get_eps_trend()), _table(instrument.get_eps_revisions())
            normalized = {}
            for horizon, keys in horizons.items():
                normalized[horizon] = {
                    "eps_consensus": _first((eps, trend), keys, ("avg", "current")),
                    "revenue_consensus": _first((revenue,), keys, ("avg",)),
                    "analyst_count": _first((eps, revenue), keys, ("numberOfAnalysts",)),
                    "upward_revisions": _first((revisions,), keys, ("upLast7days", "upLast30days")),
                    "downward_revisions": _first((revisions,), keys, ("downLast7days", "downLast30days")),
                    "estimate_high": _first((eps,), keys, ("high",)),
                    "estimate_low": _first((eps,), keys, ("low",)),
                    "dispersion": None,
                    "fiscal_period": horizon,
                }
                high, low, average = normalized[horizon]["estimate_high"], normalized[horizon]["estimate_low"], normalized[horizon]["eps_consensus"]
                if high is not None and low is not None and average not in (None, 0):
                    normalized[horizon]["dispersion"] = (high - low) / abs(average)
            contract = normalize_estimates(normalized, config["provider"], observed_at, freshness="current")
            contract["raw_provider_tables"] = {"earnings_estimate": eps, "revenue_estimate": revenue,
                                               "eps_trend": trend, "eps_revisions": revisions}
            append_estimate_snapshot(root, ticker, observed_at, contract, config["provider"])
            complete.append(ticker)
        except Exception as error:
            failed[ticker] = type(error).__name__
    print(json.dumps({"observed_at": observed_at, "complete": complete, "failed": failed}, sort_keys=True))
    return {"complete": complete, "failed": failed}


if __name__ == "__main__":
    collect()
