"""Rank-IC harness for candidate (not-yet-scored) metrics.

pipeline/validation/ic_harness.py grades the live composite score's forward-return IC; it has
no path for a metric that is not in settings.json's fundamentals.metric_weights, because
_metric_scores() only ever reads that weighted set. ROTCE, gross_margin_trend,
market_implied_growth, and the other informational fields this pipeline now computes
(fundamentals_extended.py, reverse_dcf.py) are deliberately NOT in that weighted set --
docs/VALIDATION-METHODOLOGY.md's own rule is that a scoring change ships only if it improves
out-of-sample IC after deflation, and a brand-new metric has no history to measure that
against yet. This module is the missing other half: a way to actually run that measurement,
independent of the live score, once enough pipeline/pit_store history accumulates.

Same rank-IC/ICIR statistics as ic_harness.py (this reuses its _ic_summary directly, so the
eligibility gate, confidence interval, and annualized ICIR are computed identically), but
against raw pit_store observation history rather than scored refresh snapshots -- it needs
only two point-in-time series per ticker (the candidate metric, and price), which is exactly
what makes it usable for a metric this pipeline has never scored. A period is scored only from
tickers actually observed at that exact date, so a name's stale reading is never silently
reused across periods it was not actually refreshed in.
"""

import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

import pit_store  # noqa: E402
from evaluation import pearson, rank  # noqa: E402
from validation.ic_harness import _ic_summary  # noqa: E402

# The metrics this pipeline has computed as real (not name-only) informational fields this
# session, and so the natural first candidate list for this harness once history exists.
DEFAULT_CANDIDATES = ("return_on_tangible_common_equity", "price_to_ffo", "gross_margin_trend",
                     "market_implied_growth")


def _series_by_ticker(rows, field):
    """{ticker: [(observed_date, value), ...]}, oldest first, for one numeric field."""
    out = defaultdict(list)
    for row in rows:
        value = (row.get("values") or {}).get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[row["ticker"]].append((str(row.get("observed_at"))[:10], value))
    for ticker in out:
        out[ticker].sort()
    return out


def _value_as_of(series, cutoff):
    """Latest ``(date, value)`` at or before ``cutoff``, or None."""
    candidates = [pair for pair in series if pair[0] <= cutoff]
    return candidates[-1] if candidates else None


def candidate_metric_rank_ic(metric_field, *, horizon_days=90, price_field="price",
                             minimum_names=10, rows=None):
    """One candidate metric's rank-IC against forward price return, period by period.

    ``rows`` defaults to the real pipeline/pit_store observation log; a caller (test or a
    future backtest script) can pass a synthetic list instead, since this never touches disk
    itself beyond that one read.
    """
    rows = rows if rows is not None else pit_store._read(pit_store.OBSERVATIONS)
    metric_series = _series_by_ticker(rows, metric_field)
    price_series = _series_by_ticker(rows, price_field)
    if not metric_series:
        return {"metric": metric_field, "horizon_days": horizon_days, "periods": [],
               "summary": _ic_summary([]),
               "note": f"No pit_store history recorded yet for '{metric_field}'."}

    all_dates = sorted({date for series in metric_series.values() for date, _ in series})
    periods = []
    for start_date in all_dates:
        cross_section = []
        for ticker, series in metric_series.items():
            point = _value_as_of(series, start_date)
            if not point or point[0] != start_date:
                continue  # only score names actually observed on this exact date
            price_then = _value_as_of(price_series.get(ticker, []), start_date)
            if not price_then or price_then[1] <= 0:
                continue
            target = (datetime.fromisoformat(start_date) + timedelta(days=horizon_days)).date().isoformat()
            price_now = _value_as_of(price_series.get(ticker, []), target)
            if not price_now or price_now[0] <= start_date or price_now[1] <= 0:
                continue
            forward_return = price_now[1] / price_then[1] - 1
            cross_section.append((point[1], forward_return))
        if len(cross_section) < minimum_names:
            continue
        metrics, returns = zip(*cross_section)
        ic = pearson(rank(list(metrics)), rank(list(returns)))
        if ic is not None:
            periods.append({"period_start": start_date, "names": len(cross_section), "rank_ic": round(ic, 4)})

    return {"metric": metric_field, "horizon_days": horizon_days, "periods": periods,
           "summary": _ic_summary([period["rank_ic"] for period in periods])}


def main(argv=None):
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metric", action="append", dest="metrics",
                        help="Candidate metric field to test (repeatable). Defaults to every "
                             "metric this session added as an informational field.")
    parser.add_argument("--horizon-days", type=int, default=90)
    args = parser.parse_args(argv)
    metrics = args.metrics or list(DEFAULT_CANDIDATES)
    rows = pit_store._read(pit_store.OBSERVATIONS)
    results = {metric: candidate_metric_rank_ic(metric, horizon_days=args.horizon_days, rows=rows)
              for metric in metrics}
    for metric, result in results.items():
        summary = result["summary"]
        print(f"{metric}: {summary['status']} ({summary['periods_accumulated']} periods"
              f"{', ' + summary['status_message'] if summary['status'] == 'accumulating' else ''})"
              + (f", mean_rank_ic={summary['mean_rank_ic']:.4f}"
                 if summary["mean_rank_ic"] is not None else ""))
    return results


if __name__ == "__main__":
    main()
