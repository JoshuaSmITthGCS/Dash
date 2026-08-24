"""Regime diagnosis for the research-score panel: is the champion IC's sign instability a
real regime break in time, a data-source artifact, or diffuse noise?

Round 11's searches kept hitting the same wall from every direction: champion's mean IC is
negative over the earlier half of the 10-year panel and positive over the later half, inside
nearly every sector, for every weight vector tried -- 505 candidates per sector included. No
static weighting survives a signal that points backwards for half its history, so WHERE and
WHY it flips is the question that decides whether any of this round's numbers mean what they
appear to mean. Three hypotheses, each with a distinct fingerprint this script tests for:

1. **Real regime break**: a single, statistically significant breakpoint in the IC series at
   some market event, not aligned with anything about how the data was built.
2. **Data-source artifact**: the break sits at the boundary where per-ticker statement data
   stops being Yahoo's native quarterly history (~2 years deep) and becomes the EDGAR PIT
   reconstruction (R11-P7). The boundary is COMPUTED from the actual cache, not assumed, and
   compared against the detected break.
3. **Diffuse noise**: no single break clears a permutation test that already accounts for
   having scanned every possible breakpoint -- the instability is spread everywhere, and the
   honest summary is "no stable edge at this horizon", not "an edge with one bad patch".

Statistics, stated plainly: the break statistic is Welch's t between the mean IC before and
after each candidate breakpoint (segments of at least ``--min-segment`` periods); the
p-value is a permutation test on the MAXIMUM such |t| over all breakpoints, so scanning many
break locations is priced in rather than quietly inflating significance. Per-leg
before/after tables show whether a break is composite-wide or driven by specific legs.

Reads the committed panel and cache only -- no network. Never touches holdout semantics:
this diagnoses the score's own history, it does not select or promote weights.

Usage:
    python3 pipeline/regime_diagnosis.py
    python3 pipeline/regime_diagnosis.py --panel pipeline/backtest_signal_panel.json \
        --out research/audit/round11/regime_diagnosis.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from optimization_harness import _configuration_ic_series  # noqa: E402

DEFAULT_PANEL = os.path.join(HERE, "backtest_signal_panel.json")
DEFAULT_OUT = os.path.join(os.path.dirname(HERE), "research", "audit", "round11",
                           "regime_diagnosis.json")
DEFAULT_CACHE = os.path.join(HERE, "data", "backtest_cache")
REPORT_LAG_DAYS = 45
ARTIFACT_ALIGNMENT_MONTHS = 3


def champion_ic_series(periods, weights):
    """(dates, ics) for the composite under ``weights``, keeping only resolved periods."""
    raw = _configuration_ic_series(periods, weights)
    dates, ics = [], []
    for period, ic in zip(periods, raw):
        if ic is not None:
            dates.append(period.get("date"))
            ics.append(ic)
    return dates, ics


def welch_t(before, after):
    """Welch's t for a difference in means; None when a segment is degenerate."""
    n1, n2 = len(before), len(after)
    if n1 < 2 or n2 < 2:
        return None
    mean1, mean2 = sum(before) / n1, sum(after) / n2
    var1 = sum((value - mean1) ** 2 for value in before) / (n1 - 1)
    var2 = sum((value - mean2) ** 2 for value in after) / (n2 - 1)
    denominator = (var1 / n1 + var2 / n2) ** 0.5
    if not denominator:
        return None
    return (mean2 - mean1) / denominator


def best_break(ics, *, min_segment=24):
    """The breakpoint index maximizing |Welch t| between the two segments, with its stat.

    Returns (index, t) where ``index`` is the first period of the AFTER segment, or
    (None, None) if no breakpoint leaves both segments at least ``min_segment`` long.
    """
    best_index, best_stat = None, None
    for index in range(min_segment, len(ics) - min_segment + 1):
        stat = welch_t(ics[:index], ics[index:])
        if stat is None:
            continue
        if best_stat is None or abs(stat) > abs(best_stat):
            best_index, best_stat = index, stat
    return best_index, best_stat


def permutation_p_value(ics, observed_stat, *, min_segment=24, permutations=2000, seed=0):
    """Share of shuffled series whose own best |t| meets or beats the observed one.

    The null being simulated is "the ICs are exchangeable in time" -- shuffling destroys any
    real break while keeping the same values. Because each shuffle is scanned for ITS best
    breakpoint exactly the way the real series was, the multiplicity of having searched
    every break location is priced into the p-value rather than ignored.
    """
    if observed_stat is None:
        return None
    generator = random.Random(seed)
    shuffled = list(ics)
    at_least_as_extreme = 0
    for _ in range(permutations):
        generator.shuffle(shuffled)
        _index, stat = best_break(shuffled, min_segment=min_segment)
        if stat is not None and abs(stat) >= abs(observed_stat):
            at_least_as_extreme += 1
    return at_least_as_extreme / permutations


def yearly_summary(dates, ics):
    """Mean IC, count, and hit rate per calendar year, in year order."""
    buckets = {}
    for date_str, ic in zip(dates, ics):
        buckets.setdefault(str(date_str)[:4], []).append(ic)
    return [{"year": year,
             "periods": len(values),
             "mean_ic": round(sum(values) / len(values), 4),
             "hit_rate": round(sum(1 for value in values if value > 0) / len(values), 3)}
            for year, values in sorted(buckets.items())]


def per_leg_break_table(periods, legs, break_index):
    """Mean standalone IC per leg before/after the break -- composite-wide or leg-specific?"""
    table = {}
    for leg in legs:
        series = _configuration_ic_series(periods, {leg: 1.0})
        before = [value for value in series[:break_index] if value is not None]
        after = [value for value in series[break_index:] if value is not None]
        table[leg] = {
            "mean_ic_before": round(sum(before) / len(before), 4) if before else None,
            "mean_ic_after": round(sum(after) / len(after), 4) if after else None,
            "periods_before": len(before), "periods_after": len(after),
        }
    return table


def yahoo_native_start(cache_dir, *, report_lag_days=REPORT_LAG_DAYS):
    """The median date at which cached tickers' native Yahoo statement history begins.

    Each cache entry's oldest quarterly income period, plus the reporting lag, is the
    earliest as-of date build_snapshot can serve from Yahoo data alone for that ticker;
    before it, statements come from the EDGAR PIT reconstruction (R11-P7) or are absent.
    The median across the universe locates the panel-wide data-source boundary from the
    actual files rather than an assumed "about two years".
    """
    starts = []
    try:
        names = os.listdir(cache_dir)
    except OSError:
        return None, 0
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(cache_dir, name), encoding="utf-8") as handle:
                payload = json.load(handle)
            periods = (payload.get("income") or {}).get("periods") or []
            oldest = min(date.fromisoformat(str(p)[:10]) for p in periods)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        starts.append(oldest + timedelta(days=report_lag_days))
    if not starts:
        return None, 0
    starts.sort()
    return starts[len(starts) // 2].isoformat(), len(starts)


def months_between(first_iso, second_iso):
    first, second = date.fromisoformat(first_iso[:10]), date.fromisoformat(second_iso[:10])
    return abs((second.year - first.year) * 12 + (second.month - first.month))


def diagnose(panel_data, *, cache_dir=DEFAULT_CACHE, min_segment=24, permutations=2000,
             seed=0, significance=0.05):
    periods = panel_data["periods"]
    weights = panel_data["leg_weights"]
    dates, ics = champion_ic_series(periods, weights)
    if len(ics) < 2 * min_segment:
        return {"error": f"only {len(ics)} resolved periods; need at least {2 * min_segment} "
                         f"for two {min_segment}-period segments"}

    break_index, break_stat = best_break(ics, min_segment=min_segment)
    p_value = permutation_p_value(ics, break_stat, min_segment=min_segment,
                                  permutations=permutations, seed=seed)
    break_date = dates[break_index] if break_index is not None else None
    boundary_date, boundary_tickers = yahoo_native_start(cache_dir)
    alignment_months = (months_between(break_date, boundary_date)
                        if break_date and boundary_date else None)

    legs = sorted({leg for period in periods
                   for scores in (period.get("leg_scores") or {}).values() for leg in scores})
    significant = p_value is not None and p_value < significance
    aligned = alignment_months is not None and alignment_months <= ARTIFACT_ALIGNMENT_MONTHS
    if significant and aligned:
        verdict = "DATA_ARTIFACT_SUSPECTED"
        reading = (f"the strongest break in the IC series sits within {alignment_months} "
                   "month(s) of the computed Yahoo-native/EDGAR data-source boundary -- "
                   "treat the earlier era's numbers as a measurement question about the "
                   "reconstruction, not as market history, until the alignment is rebutted")
    elif significant:
        verdict = "REGIME_BREAK"
        reading = (f"a significant break ({alignment_months} month(s) from the data "
                   "boundary, too far to blame the data seam) -- the signal genuinely "
                   "behaved differently before and after this date, and any weight vector "
                   "validated only on one side of it is untested on the other")
    else:
        verdict = "NO_SIGNIFICANT_BREAK"
        reading = ("no single breakpoint survives a permutation test that prices in having "
                   "scanned every location -- the instability is diffuse, and the honest "
                   "summary is 'no stable edge at this horizon', not 'an edge with one bad "
                   "patch'")

    before = ics[:break_index] if break_index else []
    after = ics[break_index:] if break_index else []
    return {
        "panel_periods": len(periods),
        "resolved_periods": len(ics),
        "champion_weights": weights,
        "yearly": yearly_summary(dates, ics),
        "break": {
            "date": break_date,
            "index": break_index,
            "welch_t": round(break_stat, 3) if break_stat is not None else None,
            "permutation_p_value": p_value,
            "permutations": permutations,
            "min_segment": min_segment,
            "mean_ic_before": round(sum(before) / len(before), 4) if before else None,
            "mean_ic_after": round(sum(after) / len(after), 4) if after else None,
        },
        "data_source_boundary": {
            "yahoo_native_start_median": boundary_date,
            "tickers_measured": boundary_tickers,
            "months_from_break": alignment_months,
            "alignment_window_months": ARTIFACT_ALIGNMENT_MONTHS,
        },
        "per_leg_at_break": (per_leg_break_table(periods, legs, break_index)
                             if break_index is not None else None),
        "verdict": verdict,
        "reading": reading,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", default=DEFAULT_PANEL)
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--min-segment", type=int, default=24,
                        help="Smallest segment either side of a candidate break (periods)")
    parser.add_argument("--permutations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    with open(args.panel, encoding="utf-8") as handle:
        panel_data = json.load(handle)
    result = diagnose(panel_data, cache_dir=args.cache_dir, min_segment=args.min_segment,
                      permutations=args.permutations, seed=args.seed)
    if "error" in result:
        print(f"[regime] {result['error']}")
        return 1

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)

    print(f"[regime] champion IC by year ({result['resolved_periods']} resolved periods):")
    for row in result["yearly"]:
        bar_length = int(abs(row["mean_ic"]) * 200)
        bar = ("+" if row["mean_ic"] >= 0 else "-") * min(bar_length, 40)
        print(f"  {row['year']}  mean_ic={row['mean_ic']:+.4f}  hit={row['hit_rate']:.0%}  {bar}")
    brk, boundary = result["break"], result["data_source_boundary"]
    print(f"\n[regime] strongest break: {brk['date']} "
          f"(IC {brk['mean_ic_before']:+.4f} before -> {brk['mean_ic_after']:+.4f} after, "
          f"Welch t={brk['welch_t']}, permutation p={brk['permutation_p_value']} over "
          f"{brk['permutations']} shuffles)")
    print(f"[regime] data-source boundary (median Yahoo-native statement start across "
          f"{boundary['tickers_measured']} cached tickers): "
          f"{boundary['yahoo_native_start_median']} -- "
          f"{boundary['months_from_break']} month(s) from the break")
    print(f"\n[regime] verdict: {result['verdict']}")
    print(f"[regime] {result['reading']}")
    print(f"[regime] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
