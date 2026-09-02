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

Rank IC is computed once per calendar month of expiration (not a start/end snapshot pair, since
each row resolves on its own 1-14-day schedule rather than a shared horizon): every position
expiring in that month is one cross-sectional read of "did the screen's score predict which of
that month's picks paid off."

    python pipeline/validation/options_ic.py
"""

import os
import sys
from datetime import datetime, timezone

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

from common import LOG, load_json, save_json  # noqa: E402
from evaluation import ic_summary, rank_ic  # noqa: E402
from options_common import CONTRACT_FEE  # noqa: E402
import options_pit_store  # noqa: E402
import pit_store  # noqa: E402

SETTINGS = load_json("settings.json", from_config=True) or {}
CONFIG = SETTINGS.get("validation", {})
MINIMUM_PERIODS = CONFIG.get("minimum_icir_periods", 24)
PERIODS_PER_YEAR = 12
PUBLIC_NAME = "validation/options_metrics.json"
GRADED_METRIC = "short_term_trades_score"


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


def _periods(resolved_rows):
    """One IC observation per calendar month of expiration."""
    by_month = {}
    for row in resolved_rows:
        month = row["expiration"][:7]
        by_month.setdefault(month, []).append(row)
    periods = []
    for month, rows in sorted(by_month.items()):
        scores = [row["score"] for row in rows]
        returns = [row["realized_return"] for row in rows]
        ic = rank_ic(scores, returns)
        if ic is not None:
            periods.append({"expiration_month": month, "sample_size": len(rows), "rank_ic": ic})
    return periods


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
    }


def write_report(report=None):
    report = report or build_report()
    save_json(PUBLIC_NAME, report)
    return report


def main(argv=None):
    report = write_report()
    LOG.info(f"options_ic: {report['positions_recorded']} position(s) recorded, "
             f"{report['positions_resolved']} resolved; {MINIMUM_PERIODS} eligible months "
             "required before the screen's score is reported as meaningful")
    print(f"options_ic: {report['positions_resolved']} of {report['positions_recorded']} "
         f"recorded positions resolved, status={report['metrics'][GRADED_METRIC]['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
