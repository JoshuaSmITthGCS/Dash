"""Shared walk-forward backtest engine for the options strategy screens.

Real historical option chains aren't available to this pipeline - Yahoo only exposes
the CURRENT chain, and there's no paid historical-options vendor wired in here. Every
backtest built on this module prices its option legs with Black-Scholes, using trailing
realized volatility as the implied-volatility input, and only ever reads the REAL future
closing price to settle a trade at expiration - so the ENTRY price is modeled, the
OUTCOME is real. Every published backtest result must carry a disclosure that its option
pricing is simulated, not quoted. Treat every number this produces as a rough, honest
estimate of strategy mechanics against real price history, not a claim of what live
fills would actually have produced - real historical bid/ask spreads, open interest, and
fill quality are not modeled at all (open interest in synthetic_chain is a constant
placeholder solely so the existing liquidity gate in options_common.contract_liquidity
passes; it carries no information).

Because pricing is simulated, this needs no live option-chain network call at all - it
runs entirely off the same 2-year daily price history fetch_advisor.py already cached
for the live screens, so running a backtest costs nothing extra against Yahoo's rate
limiter.
"""

import math
import statistics

from options_common import CONTRACT_FEE, call_price, put_price  # noqa: F401 - re-exported for callers


class SyntheticFrame:
    """Duck-types pandas DataFrame.iterrows() well enough for options_common's selectors."""

    def __init__(self, rows):
        self.rows = rows

    def iterrows(self):
        return enumerate(self.rows)


def synthetic_chain(price, iv, dte, spread_pct=0.03, strike_step_pct=2, strike_range_pct=40):
    """Calls/puts frames priced with Black-Scholes at `iv`, shaped like a real yfinance chain
    (strike/bid/ask/openInterest/impliedVolatility/volume) so the SAME select_by_target_delta,
    select_by_target_moneyness, and select_contract helpers the live screens use can select
    from these exactly as they would a real chain.

    openInterest/volume are constant placeholders solely so options_common.contract_liquidity's
    liquidity gate passes - they carry no real information. Must stay >=
    options_common.MINIMUM_OPEN_INTEREST/MINIMUM_VOLUME respectively, and `spread_pct` must
    stay comfortably under options_common.MAXIMUM_SPREAD_PCT (not merely under it - the
    resulting bid/ask are each independently rounded to a cent, so a spread_pct target equal
    to the live ceiling can round up past it for some strikes and silently drop contracts a
    backtest needs).
    """
    if not price or not iv or iv <= 0 or not dte or dte <= 0:
        return SyntheticFrame([]), SyntheticFrame([])
    calls, puts = [], []
    for pct in range(-strike_range_pct, strike_range_pct + 1, strike_step_pct):
        strike = round(price * (1 + pct / 100), 2)
        if strike <= 0:
            continue
        call_mid = call_price(price, strike, iv, dte)
        if call_mid is not None and call_mid > 0.01:
            half_spread = max(0.01, call_mid * spread_pct / 2)
            calls.append({"strike": strike, "bid": round(max(0.01, call_mid - half_spread), 2),
                          "ask": round(call_mid + half_spread, 2), "openInterest": 1000,
                          "impliedVolatility": iv, "volume": 500})
        put_mid = put_price(price, strike, iv, dte)
        if put_mid is not None and put_mid > 0.01:
            half_spread = max(0.01, put_mid * spread_pct / 2)
            puts.append({"strike": strike, "bid": round(max(0.01, put_mid - half_spread), 2),
                        "ask": round(put_mid + half_spread, 2), "openInterest": 1000,
                        "impliedVolatility": iv, "volume": 500})
    return SyntheticFrame(calls), SyntheticFrame(puts)


def walk_periods(closes, target_dte, lookback=21):
    """Sequential, non-overlapping (entry_index, expiry_index) pairs through price history.

    Each period is target_dte calendar days, approximated as target_dte * 5/7 trading
    sessions since Yahoo's daily history only has trading days, after the previous
    period's expiry - periods chain end-to-end with no overlap, mimicking someone
    rolling a fresh position open every time the last one expires. `lookback` sessions of
    trailing history are required before the first entry so realized volatility is
    defined from day one.
    """
    session_step = max(1, round(target_dte * 5 / 7))
    periods = []
    entry = lookback
    while entry + session_step < len(closes):
        expiry = entry + session_step
        periods.append((entry, expiry))
        entry = expiry
    return periods


def performance_stats(period_returns, periods_per_year, trade_pnls=None, position_weight=0.05):
    """period_returns: fractional return per period (.02 = +2%) ON THE CAPITAL RISKED IN
    THAT SPECIFIC TRADE, not the whole account.

    These trades are pooled across every ticker in the universe and, because each ticker
    rolls its own position independently, are really happening in PARALLEL, not one after
    another - `walk_periods` just interleaves them into a single list. Compounding that
    list at 100% of equity per trade (as if you bet the whole account, sequentially, on
    each one) is wrong twice over: it overstates every gain and, worse, a single -100%
    trade (common for a bought option that expires worthless) permanently zeroes the
    account and every trade after it, however unrelated. `position_weight` fixes this by
    scaling each trade's effect on the account-level equity curve to the fraction of
    capital a real position would actually risk - 0.05 (5%) sits inside the 0.5%-5%
    per-trade risk-budget range this feature's own design doc calls for. win_rate and
    average_pnl_per_trade describe individual trades and are intentionally NOT scaled by
    this - they're about the trade, not the account.
    """
    if not period_returns:
        return None
    scaled_returns = [value * position_weight for value in period_returns]
    equity = [1.0]
    for value in scaled_returns:
        equity.append(equity[-1] * (1 + value))
    n = len(period_returns)
    total_return = equity[-1] - 1
    annualized_return = equity[-1] ** (periods_per_year / n) - 1 if equity[-1] > 0 else -1.0
    mean_return = statistics.mean(scaled_returns)
    stdev_return = statistics.stdev(scaled_returns) if n > 1 else 0
    sharpe_ratio = (mean_return / stdev_return) * math.sqrt(periods_per_year) if stdev_return else None
    peak = equity[0]
    max_drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        drawdown = (value - peak) / peak
        max_drawdown = min(max_drawdown, drawdown)
    win_rate = sum(1 for value in period_returns if value > 0) / n
    average_pnl_per_trade = statistics.mean(trade_pnls) if trade_pnls else None
    return {
        "num_trades": n,
        "total_return": round(total_return, 4),
        "annualized_return": round(annualized_return, 4),
        "sharpe_ratio": round(sharpe_ratio, 3) if sharpe_ratio is not None else None,
        "max_drawdown": round(max_drawdown, 4),
        "win_rate": round(win_rate, 4),
        "average_pnl_per_trade": round(average_pnl_per_trade, 2) if average_pnl_per_trade is not None else None,
        "equity_curve": [round(value, 4) for value in equity],
    }
