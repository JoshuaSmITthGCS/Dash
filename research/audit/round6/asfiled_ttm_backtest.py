"""Round 6 Task 1: as-filed backtest at TTM-quarterly cadence.

Same visibility rules as the annual path (real filing dates, amendments visible on their
own filing date, tested in pipeline/tests/test_asfiled_backtest.py). Statement index 0 is
the as-filed TTM row built by edgar_enrichment.edgar_ttm_statements (FY + current YTD
minus prior-year YTD, latest visible balance instant). Growth rates come from the annual
fiscal-year series so a partial-year stub never masquerades as a growth rate.

Usage: asfiled_ttm_backtest.py <variant> <out.json>
Variants: asfiled_q, asfiled_q_fund_only, asfiled_q_stack, asfiled_q_drop_<signal>,
          asfiled_q_drop_fast
"""
import sys

HERE = "/Users/eyerise/Documents/GitHub/Dash/pipeline"
sys.path.insert(0, HERE)

variant, out = sys.argv[1], sys.argv[2]

import advisor_engine  # noqa: E402
import backtest_historical as bh  # noqa: E402
from backtest_historical import (at, basic_ratios, line, nearest_close,  # noqa: E402
                                 price_index)
from edgar_enrichment import edgar_ttm_statements  # noqa: E402
from fundamentals_extended import derive_extended  # noqa: E402


def build_snapshot_asfiled_ttm(ticker_data, as_of, report_lag_days,
                               allow_current_shares=True, allow_empty_fundamentals=False):
    symbol = ticker_data["symbol"]
    as_of_iso = as_of.isoformat()
    stmts = edgar_ttm_statements(symbol, as_of_iso)
    if stmts is None and not allow_empty_fundamentals:
        return None
    empty = {"periods": [], "rows": {}}
    income = (stmts or {}).get("income", empty)
    balance = (stmts or {}).get("balance", empty)

    raw_closes = ticker_data.get("raw_closes") or ticker_data["closes"]
    price = nearest_close(ticker_data["dates"], raw_closes, as_of)
    if price is None:
        return None
    shares = at(line(income, "diluted_shares"))
    if not shares and allow_current_shares:
        shares = ticker_data["current_shares_outstanding"]
    market_cap = price * shares if shares else None

    # Growth from the fiscal-year series (index 1 vs 2 of the TTM-prepended statements).
    revenue_fy = line(income, "revenue")
    ni_fy = line(income, "net_income")
    revenue_growth = None
    if at(revenue_fy, 1) and at(revenue_fy, 2):
        revenue_growth = at(revenue_fy, 1) / at(revenue_fy, 2) - 1
    earnings_growth = None
    if at(ni_fy, 1) is not None and at(ni_fy, 2) not in (None, 0):
        earnings_growth = at(ni_fy, 1) / at(ni_fy, 2) - 1

    first = lambda stmt: {"periods": stmt["periods"][:1],
                          "rows": {k: v[:1] for k, v in stmt["rows"].items()}}
    snap = basic_ratios(first(income), first(balance), market_cap, revenue_growth)
    snap.update({
        "ticker": symbol, "name": ticker_data["name"], "sector": ticker_data["sector"],
        "is_etf": ticker_data["is_etf"], "market_cap": market_cap, "price": price,
        "revenue_growth": round(revenue_growth, 4) if revenue_growth is not None else None,
        "earnings_growth": round(earnings_growth, 4) if earnings_growth is not None else None,
        "statement_source": "sec_edgar_pit_asfiled_ttm",
    })

    idx = price_index(ticker_data["dates"], as_of)
    closes_to_date = ticker_data["closes"][:idx + 1] if idx is not None else []
    volumes_to_date = ticker_data["volumes"][:idx + 1] if idx is not None else []
    if stmts is not None:
        snap.update(derive_extended(annual=stmts, info={}, market_cap=market_cap,
                                    price=price, sector=ticker_data["sector"],
                                    closes=closes_to_date, volumes=volumes_to_date))
        cashflow = stmts.get("cashflow", empty)
        op_cf, capex = at(line(cashflow, "operating_cash_flow")), at(line(cashflow, "capex"))
        ttm_fcf = op_cf - abs(capex or 0) if op_cf is not None else None
        snap["free_cash_flow"] = round(ttm_fcf) if ttm_fcf is not None else None
        snap["free_cash_flow_yield"] = (round(ttm_fcf / market_cap, 4)
                                        if ttm_fcf and market_cap else None)
    return snap, closes_to_date, volumes_to_date


bh.build_snapshot = build_snapshot_asfiled_ttm

base = variant.replace("asfiled_q", "")
if base == "":
    pass
elif base == "_fund_only":
    advisor_engine.RANKING_WEIGHTS = {"fundamentals": 1.0}
    advisor_engine.apply_modifiers = lambda b, *a, **k: (round(b, 1), {"applied": {}, "total": 0.0})
elif base == "_drop_fast":
    weights = dict(advisor_engine.TECHNICAL_WEIGHTS)
    for key in ("relative_strength", "volume_confirmation"):
        weights.pop(key, None)
    advisor_engine.TECHNICAL_WEIGHTS = weights
elif base == "_stack":
    pass
elif base.startswith("_drop_"):
    dropped = base.replace("_drop_", "")
    weights = dict(advisor_engine.TECHNICAL_WEIGHTS)
    if dropped not in weights:
        raise SystemExit(f"unknown technical sub-signal {dropped}: {sorted(weights)}")
    del weights[dropped]
    advisor_engine.TECHNICAL_WEIGHTS = weights
elif base == "_val2":
    import scorer
    scorer.SETTINGS["fundamentals"]["metric_weights"]["valuation"] = {
        "ev_to_ebitda": 0.6, "ev_to_fcf": 0.4}
elif base == "_val1":
    import scorer
    scorer.SETTINGS["fundamentals"]["metric_weights"]["valuation"] = {"ev_to_ebitda": 1.0}
else:
    raise SystemExit(f"unknown variant {variant}")

import backtest_monthly  # noqa: E402

args = ["backtest_monthly.py", "--cache-only", "--years", "5", "--out", out]
if base == "_stack":
    args += ["--rank-buffer", "1.5"]
sys.argv = args
backtest_monthly.main()
