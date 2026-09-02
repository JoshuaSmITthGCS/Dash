"""Rank-IC validation for the Short-term-trades options screen, once enough recommended
positions have reached their own expiration and can be graded against a realized payoff.

Unlike the other IC modules here, this does not pair a fixed forward-return horizon against
two snapshots: every row ``options_pit_store.py`` recorded already carries its own expiration
date, so a position is "resolved" the moment that date has passed and the underlying's settle
price can be read from ``pipeline/pit_store.py``'s own price history - the same daily
observations the fundamentals harness already relies on - rather than fetching or recording
price a second time. A position whose expiration has not yet arrived, or whose settle price
was never observed by ``pit_store`` (a ticker outside its universe), contributes nothing until
it can be genuinely resolved - never estimated.

Realized payoff mirrors ``build_options_strategies.py``'s own ``backtest_universe()`` formulas
exactly (buy: intrinsic value at expiry minus entry cost; sell_call: capped stock return plus
premium income; sell_put: premium income minus assignment downside), run on the position that
was actually recommended and what actually happened afterward, rather than a synthetic chain.

Rank IC is computed once per calendar *week* of expiration (not a start/end snapshot pair,
since each row resolves on its own 1-14-day schedule rather than a shared horizon): every
position expiring in that week is one cross-sectional read of "did the screen's score predict
which of that week's picks paid off."

Deliberately weekly, not monthly: a position here resolves in 1-14 days, not one-to-several
months like every other screen this pipeline validates, so treating it like them - one period
per calendar month, the same ``minimum_icir_periods`` bar as a monthly-cadence composite - would
sit on 24 *months* of history for a signal that actually produces a fresh, independent
cross-sectional read roughly every week. The eligibility bar itself
(``minimum_icir_periods`` independent periods before ICIR means anything) doesn't change; only
the period length does, matched to how often this screen's picks actually resolve rather than
an arbitrary calendar unit inherited from screens with a much slower clock.

Per-mechanism attribution: the composite (`score`) isn't one weighted blend - Short-term-trades
picks, per ticker, whichever of three mechanisms (buy a call/put, sell a covered call, sell a
cash-secured put) ranks best in its own cross-section, and each mechanism has its own weighted
selection factors (``build_options_screen.WEIGHTS``/``build_covered_call_screen.WEIGHTS``/
``build_cash_secured_put_screen.WEIGHTS``). Mixing rows from different mechanisms into one
``composite_attribution.py`` read would blend factors that were never weighted against each
other, so this grades the three mechanisms separately - one attribution report per mechanism,
each keyed by its own factor names.

    python pipeline/validation/options_ic.py
"""

import os
import sys
from datetime import datetime, timezone

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

from build_cash_secured_put_screen import WEIGHTS as SELL_PUT_WEIGHTS  # noqa: E402
from build_covered_call_screen import WEIGHTS as SELL_CALL_WEIGHTS  # noqa: E402
from build_options_screen import WEIGHTS as BUY_WEIGHTS  # noqa: E402
from common import LOG, load_json, save_json  # noqa: E402
from composite_attribution import build_attribution_report  # noqa: E402
from evaluation import ic_summary, rank_ic  # noqa: E402
from options_common import CONTRACT_FEE  # noqa: E402
import options_pit_store  # noqa: E402
import pit_store  # noqa: E402

SETTINGS = load_json("settings.json", from_config=True) or {}
CONFIG = SETTINGS.get("validation", {})
MINIMUM_PERIODS = CONFIG.get("minimum_icir_periods", 24)
PERIODS_PER_YEAR = 52  # weekly periods - see module docstring for why this differs from the
                      # monthly-cadence 12 every other screen's validation module uses.
PUBLIC_NAME = "validation/options_metrics.json"
GRADED_METRIC = "short_term_trades_score"

# Which recorded ``strategy`` tags belong to each mechanism, and that mechanism's own weights.
# buy_call and buy_put share one mechanism (build_options_screen.py scores and ranks them
# together, in one cross-section, regardless of which side of the trade trend picked).
MECHANISM_STRATEGIES = {"buy": ("buy_call", "buy_put"), "sell_call": ("sell_call",), "sell_put": ("sell_put",)}
MECHANISM_WEIGHTS = {"buy": BUY_WEIGHTS, "sell_call": SELL_CALL_WEIGHTS, "sell_put": SELL_PUT_WEIGHTS}


def _settle_price(ticker, expiration, price_history):
    """First recorded price on or after the expiration date - the same "next observation at
    or past the target" rule ``theme_ic``/``swing_ic`` use for a forward return, applied here
    to a fixed target date instead of a horizon offset.
    """
    series = price_history.get(ticker)
    if series is None:
        series = pit_store.history(ticker, "price")
        price_history[ticker] = series
    for observation in series:
        observed_date = str(observation.get("observed_at") or "")[:10]
        if observed_date and observed_date >= expiration and observation.get("value"):
            return observation["value"]
    return None


def realized_return(row, settle_price):
    """Mirrors ``build_options_strategies.backtest_universe``'s per-mechanism payoff math,
    fed by what was actually recommended (``row``) and what actually happened
    (``settle_price``) instead of a synthetic walk-forward chain.
    """
    strategy = row.get("strategy")
    strike, premium, entry_price = row.get("strike"), row.get("premium"), row.get("entry_price")
    if strike is None or premium is None or not entry_price:
        return None
    fee_per_share = CONTRACT_FEE / 100
    if strategy in ("buy_call", "buy_put"):
        cost = premium * 100 + CONTRACT_FEE
        if cost <= 0:
            return None
        intrinsic = (max(0, settle_price - strike) if strategy == "buy_call"
                    else max(0, strike - settle_price))
        return (intrinsic * 100 - cost) / cost
    if strategy == "sell_call":
        return (min(settle_price, strike) - entry_price) / entry_price + (premium - fee_per_share) / entry_price
    if strategy == "sell_put":
        return (premium - fee_per_share) / strike + min(0, (settle_price - strike) / strike)
    return None


def _resolved_rows(as_of=None, store_dir=None):
    """Every recorded position whose expiration has passed, paired with its realized return."""
    as_of_date = (as_of or datetime.now(timezone.utc)).date().isoformat()
    price_history = {}
    resolved = []
    for row in options_pit_store.all_rows(store_dir):
        expiration = row.get("expiration")
        if not expiration or expiration > as_of_date:
            continue
        settle_price = _settle_price(row["ticker"], expiration, price_history)
        if settle_price is None:
            continue
        realized = realized_return(row, settle_price)
        if realized is None:
            continue
        resolved.append({**row, "settle_price": settle_price, "realized_return": realized})
    return resolved


def _expiration_week(expiration):
    """ISO (year, week) of an expiration date, as a sortable ``"YYYY-Www"`` label."""
    year, week, _weekday = datetime.strptime(expiration, "%Y-%m-%d").isocalendar()
    return f"{year}-W{week:02d}"


def _periods(resolved_rows):
    """One IC observation per ISO week of expiration - see the module docstring for why a
    week, not a calendar month.
    """
    by_week = {}
    for row in resolved_rows:
        by_week.setdefault(_expiration_week(row["expiration"]), []).append(row)
    periods = []
    for week, rows in sorted(by_week.items()):
        scores = [row["score"] for row in rows]
        returns = [row["realized_return"] for row in rows]
        ic = rank_ic(scores, returns)
        if ic is not None:
            periods.append({"expiration_week": week, "sample_size": len(rows), "rank_ic": ic})
    return periods


def _mechanism_periods(resolved_rows, strategies):
    """One ``{leg_scores, forward_returns}`` period per ISO week, pooling only rows whose
    strategy tag belongs to this mechanism - the shape ``composite_attribution.py``'s
    ``build_attribution_report`` expects, built directly from resolved rows rather than
    (start, end) snapshot pairs (options resolves on its own schedule; there is no shared
    horizon to pair against).
    """
    by_week = {}
    for row in resolved_rows:
        if row.get("strategy") not in strategies:
            continue
        by_week.setdefault(_expiration_week(row["expiration"]), []).append(row)
    periods = []
    for week, rows in sorted(by_week.items()):
        leg_scores = {row["ticker"]: row["factors"] for row in rows if row.get("factors")}
        forward_returns = {row["ticker"]: row["realized_return"] for row in rows if row.get("factors")}
        if leg_scores:
            periods.append({"expiration_week": week, "leg_scores": leg_scores, "forward_returns": forward_returns})
    return periods


def _attribution_by_mechanism(resolved_rows):
    return {
        mechanism: build_attribution_report(
            _mechanism_periods(resolved_rows, strategies), dict(MECHANISM_WEIGHTS[mechanism]),
            minimum_periods=MINIMUM_PERIODS, periods_per_year=PERIODS_PER_YEAR)
        for mechanism, strategies in MECHANISM_STRATEGIES.items()
    }


def build_report(as_of=None, store_dir=None):
    recorded_dates = options_pit_store.snapshot_dates(store_dir)
    resolved = _resolved_rows(as_of, store_dir)
    periods = _periods(resolved)
    summary = ic_summary([period["rank_ic"] for period in periods], PERIODS_PER_YEAR)
    eligible = summary["periods"] >= MINIMUM_PERIODS
    metric = {
        "requires_live_sample": True,
        "eligible_periods": summary["periods"],
        "minimum_icir_periods": MINIMUM_PERIODS,
        "status": "eligible" if eligible else "accumulating",
        "mean_rank_ic": summary["mean_ic"] if eligible else None,
        "icir": summary["icir"] if eligible else None,
        "t_stat": summary["t_stat"] if eligible else None,
        "hit_rate": summary["hit_rate"] if eligible else None,
        "clears_multiple_testing_bar": summary["clears_multiple_testing_bar"] if eligible else False,
        "periods": periods if eligible else [],
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_integrity": "prospective_point_in_time",
        "reconstructed_history": {
            "included": False,
            "label": "no history exists before options_pit_store began recording - this "
                     "module never reconstructs a recommendation or a settle price for a date "
                     "it did not observe",
        },
        "snapshot_dates_recorded": len(recorded_dates),
        "positions_recorded": sum(len(options_pit_store.load_snapshot(date, store_dir))
                                  for date in recorded_dates),
        "positions_resolved": len(resolved),
        "metrics": {GRADED_METRIC: metric},
        "attribution_by_mechanism": _attribution_by_mechanism(resolved),
    }


def write_report(report=None):
    report = report or build_report()
    save_json(PUBLIC_NAME, report)
    return report


def main(argv=None):
    report = write_report()
    LOG.info(f"options_ic: {report['positions_recorded']} position(s) recorded, "
             f"{report['positions_resolved']} resolved; {MINIMUM_PERIODS} eligible weeks "
             "required before the screen's score is reported as meaningful")
    print(f"options_ic: {report['positions_resolved']} of {report['positions_recorded']} "
         f"recorded positions resolved, status={report['metrics'][GRADED_METRIC]['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
