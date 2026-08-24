"""Auditable monthly top-N walk-forward backtest for the Dash appeal score.

Signals are calculated at a month-end close using only trailing prices and financial
statements whose period end plus the configured reporting lag is already known. Picks are
then locked and executed at the *next* market close. The portfolio is held until the next
monthly execution and is weighted in proportion to each selected stock's appeal score.

This prevents signal/return lookahead, but a run against ``advisor_universe.json`` still has
current-constituent survivorship bias. A dated constituent file is required before a result
can honestly be described as a fully point-in-time Russell 1000 backtest.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from backtest_historical import (  # noqa: E402
    REPORT_LAG_DAYS_DEFAULT,
    fetch_benchmark,
    fetch_ticker_data,
    load_universe,
    price_index,
    rank_week,
)
from common import LOG, load_json  # noqa: E402
from costs import estimate_cost_bps  # noqa: E402
from portfolio_construction import apply_controls  # noqa: E402
from screen_inputs import universe_rows  # noqa: E402

COST_MODELS = ("flat", "tiered")


def _month_end(year, month):
    return date(year, month, monthrange(year, month)[1])


def _shift_month(value, months):
    absolute = value.year * 12 + value.month - 1 + months
    year, month0 = divmod(absolute, 12)
    return _month_end(year, month0 + 1)


def build_rebalance_calendar(benchmark_dates, years):
    """Return 60 signal/execution pairs for five years when data permits."""
    trading_days = sorted(date.fromisoformat(value[:10]) for value in benchmark_dates)
    if len(trading_days) < 2:
        return []
    latest = trading_days[-1]
    first_month_end = _shift_month(latest, -(years * 12))
    pairs = []
    for offset in range(years * 12 + 1):
        target = _shift_month(first_month_end, offset)
        eligible = [day for day in trading_days if day <= target]
        if not eligible:
            continue
        signal = eligible[-1]
        executions = [day for day in trading_days if day > signal]
        if not executions:
            continue
        execution = executions[0]
        if not pairs or pairs[-1][0] != signal:
            pairs.append((signal, execution))
    return pairs[: years * 12]


CONSTRUCTION_METHODS = ("appeal", "inverse_volatility")


def appeal_weights(rows, top_n, universe_data=None, as_of=None):
    """The champion's construction: weight in proportion to each selected name's own score.

    ``universe_data``/``as_of`` are accepted and ignored so this and ``inverse_volatility_weights``
    share one call signature - the rebalance loop picks a weighter by name, not by argument shape.
    """
    selected = [row for row in rows[:top_n] if row.get("price") and row.get("score") is not None]
    scores = [max(float(row["score"]), 0.0) for row in selected]
    total = sum(scores)
    if not selected:
        return {}
    if total <= 0:
        return {row["ticker"]: 1 / len(selected) for row in selected}
    return {row["ticker"]: score / total for row, score in zip(selected, scores)}


def inverse_volatility_weights(rows, top_n, universe_data, as_of, *, window=60):
    """A challenger construction: weight each selected name inversely to its own trailing
    realized volatility, using only trailing prices as of ``as_of`` - no look-ahead.

    An inverse-volatility approximation of risk parity, not the real thing: true risk parity
    solves for equal marginal risk contribution across names using their full covariance
    matrix, which means it accounts for correlation between names. This ignores correlation
    entirely and weights purely off each name's own volatility in isolation - materially
    cheaper to compute and reason about, and a real, defensible construction in its own
    right, but a different and weaker claim than "risk parity" on its own would suggest.
    Published under its own name for exactly that reason.

    A name whose trailing volatility cannot be computed - too little price history as of this
    rebalance - is dropped from the book rather than assigned a guessed volatility, the same
    "computable or absent" discipline the rest of this pipeline follows. This is a challenger:
    ``backtest_monthly.py`` defaults to ``appeal_weights`` and only calls this when
    ``--construction-method inverse_volatility`` is passed explicitly.
    """
    selected = [row for row in rows[:top_n] if row.get("price") and row.get("score") is not None]
    inverse_vols = {}
    for row in selected:
        ticker = row.get("ticker")
        if not ticker:
            continue
        _, annualized_volatility = trailing_liquidity_and_volatility(
            (universe_data or {}).get(ticker), as_of, window=window)
        if annualized_volatility and annualized_volatility > 0:
            inverse_vols[ticker] = 1.0 / annualized_volatility
    total = sum(inverse_vols.values())
    if not inverse_vols or total <= 0:
        return {}
    return {ticker: value / total for ticker, value in inverse_vols.items()}


CONSTRUCTION_WEIGHTERS = {
    "appeal": appeal_weights,
    "inverse_volatility": inverse_volatility_weights,
}


# ---------------- scored panel ----------------
#
# The equity curve answers one question - what would this have been worth - and answers it
# slowly, because a return series needs years before it separates skill from noise. The panel
# written below answers the faster and more useful question: did the score rank anything,
# which legs did the ranking, and at what horizon. It costs nothing extra to produce, because
# every ranked row already exists in memory at each rebalance and is otherwise discarded once
# the top N have been taken from it.

PANEL_HORIZON_TRADING_DAYS = {"1d": 1, "5d": 5, "21d": 21, "63d": 63}
PANEL_PRIMARY_HORIZON = "21d"
ADV_WINDOW_DAYS = 60


def panel_leg_weights(settings):
    """The two-level blend flattened into one linear weight per leg.

    Live scoring blends six fundamental categories into a fundamentals score, then blends
    that with market behaviour and news sentiment. For a drop-one-leg test the useful shape
    is flat: each category carries its own weight times the fundamentals share. Score-level
    modifiers are deliberately outside this - they are caps and penalties, not legs, and
    folding them in would make the leg contributions unattributable.
    """
    categories = (settings.get("fundamentals") or {}).get("category_weights") or {}
    ranking = settings.get("ranking_weights") or {}
    weights = {name: round(weight * ranking.get("fundamentals", 0.0), 4)
               for name, weight in categories.items()}
    for name in ("market_behavior", "news_sentiment"):
        if ranking.get(name):
            weights[name] = ranking[name]
    return weights


def current_sector_map():
    """{ticker: sector} from the live advisor snapshot.

    Same approximation ``backtest_swing.py``'s ``current_sector_map`` already discloses:
    the backtest cache carries no point-in-time sector history, so this is the CURRENT
    GICS sector applied retroactively to every historical period. It is the only sector
    data that exists anywhere in this repository. Good enough to ask "how would each leg
    have scored on today's tech names historically", not point-in-time-accurate for names
    that changed sector classification along the way.
    """
    return {row["ticker"]: row.get("sector") for row in universe_rows() if row.get("ticker")}


def panel_scores(rows):
    """Composite score and every leg score for one ranked cross-section."""
    scores, legs = {}, {}
    for row in rows:
        ticker, score = row.get("ticker"), row.get("score")
        if not ticker or not isinstance(score, (int, float)):
            continue
        components = row.get("components") or {}
        leg_scores = {name: value for name, value
                      in (row.get("fundamental_categories") or {}).items()
                      if isinstance(value, (int, float))}
        for name in ("market_behavior", "news_sentiment"):
            if isinstance(components.get(name), (int, float)):
                leg_scores[name] = components[name]
        scores[ticker] = score
        legs[ticker] = leg_scores
    return scores, legs


# build_research (advisor_engine.py) returns {**snapshot, ...these keys}. Everything in a row
# that is NOT one of these, and not a bare identity field, is an individual raw metric
# snap/build_snapshot computed -- P/E, ROE, Piotroski F, Altman Z, buyback yield, and so on --
# not a rolled-up category. Kept as an explicit set (rather than inferring numeric-vs-not
# alone) so a future field added to build_research's own return dict doesn't silently get
# mistaken for a scoring input.
_ROW_NON_METRIC_KEYS = {
    "ticker", "name", "sector", "is_etf", "score", "base_score", "raw_score", "stance",
    "data_coverage", "components", "fundamental_categories", "fundamental_detail",
    "technical_detail", "sentiment_detail", "modifiers", "news_available",
    "sector_valuation_percentile", "recommendation", "strengths", "risks", "analysis_v2",
    "recommendation_v2", "action",
}


def panel_metric_scores(rows):
    """Every individual numeric metric the methodology currently computes, per ticker --
    not just the 6-8 rolled-up legs panel_scores() captures. Lets sector-level analysis
    (optimization_harness.as_metric_periods + sector_weight_report) test which specific
    metric (trailing P/E, ROE, Piotroski F, ...) carries signal in which sector, rather than
    only which category.
    """
    metrics = {}
    for row in rows:
        ticker = row.get("ticker")
        if not ticker:
            continue
        metrics[ticker] = {
            key: value for key, value in row.items()
            if key not in _ROW_NON_METRIC_KEYS and isinstance(value, (int, float))
            and not isinstance(value, bool)
        }
    return metrics


def panel_forward_returns(universe_data, execution_date, tickers):
    """Forward return at each graded horizon, counted in that name's own trading days.

    A horizon that runs past the end of the price history yields no observation rather than
    a truncated one, so a short horizon never gets silently graded as a long one.
    """
    output = {label: {} for label in PANEL_HORIZON_TRADING_DAYS}
    for ticker in tickers:
        data = universe_data.get(ticker)
        if not data:
            continue
        start = price_index(data["dates"], date.fromisoformat(execution_date))
        if start is None:
            continue
        entry = data["closes"][start]
        if not entry:
            continue
        for label, days in PANEL_HORIZON_TRADING_DAYS.items():
            end = start + days
            if end < len(data["closes"]) and data["closes"][end]:
                output[label][ticker] = data["closes"][end] / entry - 1
    return output


def panel_dollar_volume(universe_data, window=ADV_WINDOW_DAYS):
    """Trailing average daily dollar volume per name, for the capacity ceiling."""
    volumes = {}
    for symbol, data in universe_data.items():
        closes, traded = data.get("closes") or [], data.get("volumes") or []
        pairs = [(close, volume) for close, volume in zip(closes[-window:], traded[-window:])
                 if close and volume]
        if len(pairs) >= window // 2:
            volumes[symbol] = round(sum(close * volume for close, volume in pairs) / len(pairs), 2)
    return volumes


def build_panel(periods, universe_data, leg_weights):
    """Assemble the artifact pipeline/signal_metrics.py grades the signal from."""
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "primary_horizon": PANEL_PRIMARY_HORIZON,
        "horizon_trading_days": PANEL_HORIZON_TRADING_DAYS,
        "leg_weights": leg_weights,
        "note": ("Leg scores are pre-modifier. Forward returns are measured from the locked "
                 "execution close, so the score is always older than the return it is graded "
                 "against."),
        "periods": periods,
        "dollar_volume": panel_dollar_volume(universe_data),
    }


def committed_benchmark(ticker="SPY"):
    """The benchmark's daily series from committed ETF history, for offline reproduction.

    ``--cache-only`` loads every universe symbol from ``pipeline/data/backtest_cache`` but the
    benchmark was still fetched live, so the whole backtest failed at the last hop with no
    network. ``public/data/etf/SPY.json`` carries 8,437 real sessions and is already committed
    for the ETF comparison feature, which is more history than the 10-year fetch it replaces.

    Returns None rather than raising if the series is absent, so the caller's existing
    "could not fetch" path still handles it.
    """
    path = os.path.join(os.path.dirname(HERE), "public", "data", "etf", f"{ticker}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        series = (json.load(handle).get("price_series") or {}).get("fund") or []
    rows = [row for row in series if row.get("date") and row.get("adjusted_close") is not None]
    if not rows:
        return None
    return {"dates": [str(row["date"])[:10] for row in rows],
            "closes": [float(row["adjusted_close"]) for row in rows]}


def _price_maps(universe_data):
    return {
        symbol: dict(zip(data["dates"], data["closes"]))
        for symbol, data in universe_data.items()
    }


def trailing_liquidity_and_volatility(ticker_data, as_of, window=60):
    """60-trading-day median dollar volume and annualized volatility as of a date, using
    only the trailing window (no look-ahead) from a ticker's already-fetched daily history.

    This is the same shape of input costs.py.estimate_cost_bps expects, computed from data
    the monthly backtest already holds in memory -- no additional fetch required once
    ``universe_data`` (with volumes) is populated.
    """
    if not ticker_data:
        return None, None
    dates = ticker_data.get("dates") or []
    closes = ticker_data.get("closes") or []
    volumes = ticker_data.get("volumes") or []
    idx = None
    for position, day in enumerate(dates):
        if day <= as_of:
            idx = position
        else:
            break
    if idx is None or idx < 1:
        return None, None
    start = max(0, idx - window + 1)
    trail_closes = closes[start:idx + 1]
    trail_volumes = volumes[start:idx + 1] if volumes else []
    dollar_volumes = [
        close * volume for close, volume in zip(trail_closes, trail_volumes)
        if close and volume
    ]
    median_dollar_volume_60d = statistics.median(dollar_volumes) if dollar_volumes else None
    returns = [
        trail_closes[i] / trail_closes[i - 1] - 1
        for i in range(1, len(trail_closes))
        if trail_closes[i - 1]
    ]
    annualized_volatility = (
        statistics.pstdev(returns) * math.sqrt(252) if len(returns) > 1 else None
    )
    return median_dollar_volume_60d, annualized_volatility


def _rebalance_turnover_and_cost(current, target, value, day, *, cost_model,
                                 cost_scenario, transaction_cost_bps, universe_data):
    """Turnover is always the same portfolio-weight math; only the cost estimate changes
    with ``cost_model``. ``flat`` reproduces the pre-existing single-rate behavior exactly
    so old results stay reproducible; ``tiered`` prices every name's own trade through
    costs.py using that name's trailing liquidity and volatility as of ``day``.
    """
    names = set(current) | set(target)
    turnover = 0.5 * sum(abs(current.get(name, 0) - target.get(name, 0)) for name in names)
    if not current and target:
        turnover = 1.0
    if cost_model == "flat":
        return turnover, value * turnover * transaction_cost_bps / 10000
    total_cost = 0.0
    for name in names:
        trade_weight = abs(current.get(name, 0) - target.get(name, 0))
        trade_dollar_value = trade_weight * value
        if trade_dollar_value <= 0:
            continue
        median_dollar_volume_60d, annualized_volatility = trailing_liquidity_and_volatility(
            universe_data.get(name), day,
        )
        estimate = estimate_cost_bps(
            median_dollar_volume_60d=median_dollar_volume_60d,
            annualized_volatility=annualized_volatility,
            trade_dollar_value=trade_dollar_value,
            scenario=cost_scenario,
        )
        total_cost += trade_dollar_value * estimate["total_bps"] / 10000
    return turnover, total_cost


def simulate_locked_portfolio(plans, universe_data, benchmark, initial_capital,
                              transaction_cost_bps=10.0, cost_model="flat",
                              cost_scenario="base"):
    """Mark holdings daily; only replace weights on a predeclared execution date."""
    if not plans:
        return {"history": [], "rebalances": [], "metrics": {}}
    if cost_model not in COST_MODELS:
        raise ValueError(f"unsupported cost model: {cost_model}")
    price_maps = _price_maps(universe_data)
    benchmark_map = dict(zip(benchmark["dates"], benchmark["closes"]))
    executions = {plan["execution_date"]: plan for plan in plans}
    start = plans[0]["execution_date"]
    end = max(benchmark_map)
    days = [day for day in benchmark["dates"] if start <= day <= end]
    dollars = {}
    value = float(initial_capital)
    previous_day = None
    total_turnover = 0.0
    total_cost = 0.0
    missing_price_days = 0
    history = []
    rebalances = []

    for day in days:
        if previous_day is not None and dollars:
            updated = {}
            for ticker, amount in dollars.items():
                before = price_maps.get(ticker, {}).get(previous_day)
                after = price_maps.get(ticker, {}).get(day)
                if before and after:
                    updated[ticker] = amount * after / before
                else:
                    updated[ticker] = amount
                    missing_price_days += 1
            dollars = updated
            value = sum(dollars.values())

        plan = executions.get(day)
        if plan:
            target = {
                ticker: weight for ticker, weight in plan["weights"].items()
                if price_maps.get(ticker, {}).get(day)
            }
            weight_sum = sum(target.values())
            target = {ticker: weight / weight_sum for ticker, weight in target.items()} if weight_sum else {}
            current = {ticker: amount / value for ticker, amount in dollars.items()} if value else {}
            turnover, cost = _rebalance_turnover_and_cost(
                current, target, value, day,
                cost_model=cost_model, cost_scenario=cost_scenario,
                transaction_cost_bps=transaction_cost_bps, universe_data=universe_data,
            )
            value -= cost
            total_turnover += turnover
            total_cost += cost
            dollars = {ticker: value * weight for ticker, weight in target.items()}
            rebalances.append({
                "signal_date": plan["signal_date"],
                "execution_date": day,
                "portfolio_value": round(value, 2),
                "turnover": round(turnover, 6),
                "cost": round(cost, 2),
                "picks": plan["picks"],
            })

        history.append({"date": day, "value": round(value, 2)})
        previous_day = day

    metrics = performance_metrics(history, initial_capital)
    metrics.update({
        "turnover": round(total_turnover, 6),
        "estimated_transaction_cost": round(total_cost, 2),
        "missing_holding_price_days": missing_price_days,
        "unique_tickers_selected": len({pick["ticker"] for row in rebalances for pick in row["picks"]}),
    })
    return {"history": history, "rebalances": rebalances, "metrics": metrics}


def performance_metrics(history, initial_capital):
    if not history:
        return {}
    values = [row["value"] for row in history]
    start = date.fromisoformat(history[0]["date"])
    end = date.fromisoformat(history[-1]["date"])
    years = max((end - start).days / 365.25, 1 / 365.25)
    total_return = values[-1] / initial_capital - 1
    cagr = (values[-1] / initial_capital) ** (1 / years) - 1 if values[-1] > 0 else -1
    peak = values[0]
    max_drawdown = 0.0
    daily_returns = []
    for before, after in zip(values[:-1], values[1:]):
        if before:
            daily_returns.append(after / before - 1)
        peak = max(peak, after)
        max_drawdown = min(max_drawdown, after / peak - 1)
    mean = sum(daily_returns) / len(daily_returns) if daily_returns else 0.0
    variance = sum((value - mean) ** 2 for value in daily_returns) / len(daily_returns) if daily_returns else 0.0
    return {
        "start_date": history[0]["date"],
        "end_date": history[-1]["date"],
        "initial_value": round(initial_capital, 2),
        "final_value": round(values[-1], 2),
        "total_return": round(total_return, 6),
        "cagr": round(cagr, 6),
        "maximum_drawdown": round(max_drawdown, 6),
        "annualized_volatility": round(math.sqrt(variance) * math.sqrt(252), 6),
        "sharpe_zero_rate": round(mean / math.sqrt(variance) * math.sqrt(252), 4) if variance else None,
    }


def simulate_benchmark(benchmark, start_date, initial_capital, transaction_cost_bps=0.0):
    price_map = dict(zip(benchmark["dates"], benchmark["closes"]))
    days = [day for day in benchmark["dates"] if day >= start_date]
    if not days:
        return {"history": [], "metrics": {}}
    start_price = price_map[days[0]]
    entry_cost = initial_capital * transaction_cost_bps / 10000
    investable = initial_capital - entry_cost
    history = [{"date": day, "value": round(investable * price_map[day] / start_price, 2)} for day in days]
    metrics = performance_metrics(history, initial_capital)
    metrics["estimated_transaction_cost"] = round(entry_cost, 2)
    return {"history": history, "metrics": metrics}


def _cache_path(cache_dir, symbol):
    return os.path.join(cache_dir, symbol.replace("/", "_") + ".json")


def load_or_fetch(yf, symbol, delay, cache_dir, refresh=False, cache_only=False):
    path = _cache_path(cache_dir, symbol)
    if not refresh and os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        # Older cache entries may have been created by the legacy runner, which includes
        # today's sector/name/share metadata. Normalize them to the same strict input shape
        # as newly fetched monthly-backtest entries.
        data.update({
            "name": symbol,
            "sector": None,
            "is_etf": False,
            "current_shares_outstanding": None,
        })
        return data
    if cache_only:
        return None
    data = None
    for attempt in range(2):
        data = fetch_ticker_data(
            yf, symbol, delay, history_period="10y", include_current_metadata=False,
        )
        if data:
            break
        if attempt == 0:
            time.sleep(1.0)
    if data:
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--universe-limit", type=int, default=0,
                        help="Configured candidates to use; 0 means the entire universe (default 0)")
    parser.add_argument("--tickers", default="")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--construction-method", choices=CONSTRUCTION_METHODS, default="appeal",
                        help="'appeal' preserves the original score-proportional weighting "
                             "(default, reproduces prior results exactly). "
                             "'inverse_volatility' is a challenger construction; see "
                             "inverse_volatility_weights().")
    parser.add_argument("--initial-capital", type=float, default=100000.0)
    parser.add_argument("--report-lag-days", type=int, default=REPORT_LAG_DAYS_DEFAULT)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0,
                        help="One-way cost in bps for --cost-model=flat (default 10.0)")
    parser.add_argument("--cost-model", choices=COST_MODELS, default="flat",
                        help="'flat' preserves the original single-rate cost (default, "
                             "reproduces prior results exactly). 'tiered' prices each "
                             "name's own trade through costs.py using its trailing "
                             "60-day liquidity and volatility")
    parser.add_argument("--cost-scenario", choices=("optimistic", "base", "stress"),
                        default="base",
                        help="Which costs.py scenario to use when --cost-model=tiered")
    # Turnover-control challengers (pipeline/portfolio_construction.py). All default to off,
    # so omitting them reproduces the champion's plain top-N selection exactly.
    parser.add_argument("--rank-buffer", type=float, default=None,
                        help="hold an incumbent while its rank stays inside this multiple of "
                             "top-n (e.g. 1.5); sell once past it")
    parser.add_argument("--min-holding-months", type=int, default=None,
                        help="hold a name at least this many months unless its rank collapses "
                             "past 3x top-n")
    parser.add_argument("--score-smoothing", type=float, default=None,
                        help="exponentially weighted score smoothing alpha in (0, 1]; 1.0 is "
                             "a no-op")
    parser.add_argument("--replacement-margin", type=float, default=None,
                        help="score points by which a challenger must beat the incumbent it "
                             "would displace")
    parser.add_argument("--delay", type=float, default=0.1)
    parser.add_argument("--workers", type=int, default=6,
                        help="Concurrent cached Yahoo fetches (default 6)")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--cache-only", action="store_true",
                        help="Use cached candidates without retrying unavailable symbols")
    parser.add_argument("--fetch-only", action="store_true",
                        help="Populate the resumable cache and exit before ranking")
    parser.add_argument("--yfinance-cache-dir", default="",
                        help="Optional isolated yfinance cookie/timezone cache")
    parser.add_argument("--cache-dir", default=os.path.join(HERE, "data", "backtest_cache"))
    parser.add_argument("--out", default=os.path.join(HERE, "backtest_monthly_results.json"))
    parser.add_argument("--panel-out", default=os.path.join(HERE, "backtest_signal_panel.json"),
                        help="Scored cross-section panel for pipeline/signal_metrics.py. "
                             "Pass an empty string to skip it.")
    args = parser.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        LOG.error("yfinance not installed. Install pipeline/requirements.txt first.")
        return 1
    if args.yfinance_cache_dir:
        os.makedirs(args.yfinance_cache_dir, exist_ok=True)
        yf.set_tz_cache_location(args.yfinance_cache_dir)

    symbols = load_universe(args.universe_limit, args.tickers)
    LOG.info(f"Fetching/caching {len(symbols)} candidates for a {args.years}-year monthly backtest")
    universe_data = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        pending = {
            executor.submit(
                load_or_fetch, yf, symbol, args.delay, args.cache_dir,
                args.refresh_cache, args.cache_only,
            ): symbol
            for symbol in symbols
        }
        for index, future in enumerate(as_completed(pending), 1):
            symbol = pending[future]
            try:
                data = future.result()
            except Exception as exc:  # noqa: BLE001 - preserve the rest of a long run
                LOG.warn(f"{symbol}: worker failed ({type(exc).__name__}: {exc})")
                data = None
            if data:
                universe_data[symbol] = data
            if index % 25 == 0:
                LOG.info(f"...{index}/{len(symbols)} fetched, {len(universe_data)} usable")

    if args.fetch_only:
        LOG.info(f"Fetch complete: {len(universe_data)}/{len(symbols)} usable")
        return 0

    benchmark = committed_benchmark("SPY") if args.cache_only else fetch_benchmark(
        yf, "SPY", args.delay, history_period="10y")
    if not benchmark:
        LOG.error("Could not fetch SPY")
        return 1
    calendar = build_rebalance_calendar(benchmark["dates"], args.years)
    if len(calendar) < args.years * 12:
        LOG.error(f"Only {len(calendar)} monthly execution dates were available")
        return 1

    plans, panel_periods = [], []
    leg_weights = panel_leg_weights(load_json("settings.json", from_config=True) or {})
    sectors = current_sector_map()
    holdings, held_months, previous_scores = [], {}, {}
    for index, (signal_date, execution_date) in enumerate(calendar, 1):
        spy_idx = price_index(benchmark["dates"], signal_date)
        spy_to_date = benchmark["closes"][:spy_idx + 1] if spy_idx is not None else []
        rows = rank_week(
            universe_data, spy_to_date, signal_date, args.report_lag_days,
            allow_current_shares=False, allow_empty_fundamentals=True,
        )
        eligible = [row for row in rows if row.get("price") and row.get("score") is not None]
        selected = apply_controls(
            holdings, eligible, args.top_n,
            previous_scores=previous_scores, held_months=held_months,
            rank_buffer=args.rank_buffer, minimum_months=args.min_holding_months,
            smoothing_alpha=args.score_smoothing,
            replacement_margin=args.replacement_margin,
        )
        chosen = {row["ticker"]: row for row in eligible if row["ticker"] in set(selected)}
        ordered = [chosen[ticker] for ticker in selected if ticker in chosen]
        weighter = CONSTRUCTION_WEIGHTERS[args.construction_method]
        weights = weighter(ordered, args.top_n, universe_data, signal_date.isoformat())
        picks = [
            {"ticker": row["ticker"], "appeal_score": row["score"], "weight": round(weights[row["ticker"]], 8)}
            for row in ordered if row["ticker"] in weights
        ]
        plans.append({
            "signal_date": signal_date.isoformat(),
            "execution_date": execution_date.isoformat(),
            "weights": weights,
            "picks": picks,
        })
        scores, leg_scores = panel_scores(rows)
        metric_scores = panel_metric_scores(rows)
        forwards = panel_forward_returns(universe_data, execution_date.isoformat(), scores)
        panel_periods.append({
            "date": execution_date.isoformat(),
            "signal_date": signal_date.isoformat(),
            "names": len(scores),
            "scores": scores,
            "leg_scores": leg_scores,
            "metric_scores": metric_scores,
            "sectors": {ticker: sectors.get(ticker) for ticker in scores if sectors.get(ticker)},
            "forward_returns_by_horizon": forwards,
            "forward_returns": forwards[PANEL_PRIMARY_HORIZON],
        })
        carried = set(selected) & set(holdings)
        held_months = {ticker: held_months.get(ticker, 0) + 1 if ticker in carried else 0
                       for ticker in selected}
        previous_scores = {row["ticker"]: row["score"] for row in eligible}
        holdings = selected
        if index % 12 == 0:
            LOG.info(f"Ranked {index}/{len(calendar)} months; latest signal {signal_date}")

    portfolio = simulate_locked_portfolio(
        plans, universe_data, benchmark, args.initial_capital, args.transaction_cost_bps,
        cost_model=args.cost_model, cost_scenario=args.cost_scenario,
    )
    benchmark_result = simulate_benchmark(
        benchmark, plans[0]["execution_date"], args.initial_capital,
        args.transaction_cost_bps,
    )
    from validation.experiment_manifest import build_manifest
    manifest = build_manifest(
        strategy=f"{args.construction_method}-top{args.top_n}-monthly",
        start_date=plans[0]["signal_date"], end_date=plans[-1]["signal_date"],
        normalization_mode=str(__import__("scorer").SETTINGS.get("normalization_mode")),
        scoring_mode="champion",
        rebalance_frequency="monthly",
        universe_tickers=list(universe_data),
        execution_assumptions={"execution": "next SPY trading-day close after signal",
                               "weighting": "appeal score proportional",
                               "report_lag_days": args.report_lag_days},
        cost_model={"transaction_cost_bps_one_way": args.transaction_cost_bps,
                    "cost_model": args.cost_model, "cost_scenario": args.cost_scenario},
        price_cache_dir=args.cache_dir,
        factor_files=[path for path in (
            os.path.join(HERE, "data", "factors", "fama_french_5_monthly.zip"),
            os.path.join(HERE, "data", "factors", "momentum_monthly.zip"),
        ) if os.path.exists(path)],
        calendar=[p["signal_date"] for p in plans],
        extra={"turnover_controls": {
            "rank_buffer": args.rank_buffer,
            "minimum_holding_months": args.min_holding_months,
            "score_smoothing_alpha": args.score_smoothing,
            "replacement_margin": args.replacement_margin,
        }},
    )
    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "experiment_manifest": manifest,
        "method": {
            "signal": "Dash appeal score at month-end adjusted close",
            "execution": "next SPY trading-day close after signal",
            "selection": f"top {args.top_n}",
            "turnover_controls": {
                "rank_buffer": args.rank_buffer,
                "minimum_holding_months": args.min_holding_months,
                "score_smoothing_alpha": args.score_smoothing,
                "replacement_margin": args.replacement_margin,
                "active": any(value is not None for value in (
                    args.rank_buffer, args.min_holding_months,
                    args.score_smoothing, args.replacement_margin)),
            },
            "weighting": ("appeal score divided by sum of selected appeal scores"
                         if args.construction_method == "appeal" else
                         "inverse-volatility (a risk-parity approximation ignoring "
                         "cross-name correlation, not a full risk-parity solve)"),
            "construction_method": args.construction_method,
            "fundamental_availability": f"quarter end plus {args.report_lag_days} calendar days",
            "prices": "Yahoo adjusted close (split and dividend adjusted)",
            "transaction_cost_bps_one_way": args.transaction_cost_bps,
            "cost_model": args.cost_model,
            "cost_scenario": args.cost_scenario if args.cost_model == "tiered" else None,
        },
        "bias_disclosures": {
            "signal_return_lookahead": False,
            "current_share_count_fallback_used": False,
            "survivorship_bias": True,
            "reason": "advisor_universe.json is a current candidate list, not dated Russell 1000 membership",
            "filing_date_approximation": True,
            "missing_historical_inputs": [
                "point-in-time analyst estimates", "historical news sentiment", "actual SEC filing timestamps",
                "quarterly fundamentals before Yahoo's retained statement window; early dates use the available price/volume factors only",
            ],
        },
        "universe_requested": len(symbols),
        "universe_usable": len(universe_data),
        "portfolio": portfolio,
        "benchmark_spy": benchmark_result,
    }
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    if args.panel_out:
        with open(args.panel_out, "w", encoding="utf-8") as handle:
            json.dump(build_panel(panel_periods, universe_data, leg_weights), handle, indent=2)
        graded = sum(1 for period in panel_periods if period["forward_returns"])
        print(f"Wrote {args.panel_out}: {len(panel_periods)} scored cross-sections, "
              f"{graded} with {PANEL_PRIMARY_HORIZON} forward returns")
    strategy = portfolio["metrics"]
    spy = benchmark_result["metrics"]
    print(f"Strategy CAGR {strategy.get('cagr', 0):.2%}, max DD {strategy.get('maximum_drawdown', 0):.2%}")
    print(f"SPY CAGR      {spy.get('cagr', 0):.2%}, max DD {spy.get('maximum_drawdown', 0):.2%}")
    print(f"Unique picks {strategy.get('unique_tickers_selected', 0)}, usable universe {len(universe_data)}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
