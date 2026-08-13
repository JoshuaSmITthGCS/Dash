"""Task 1: the as-filed backtest. Statement metrics come from SEC EDGAR facts visible on
each signal date (real filing dates, no approximated reporting lag, no restatement
look-ahead). Prices, volumes, and universe membership still come from the Yahoo cache, so
the run removes the restatement bias and keeps the survivorship bias, which the findings
document states explicitly.

Usage: asfiled_backtest.py <variant> <out.json>
Variants:
  asfiled                as-filed statements, production weights
  asfiled_fund_only      as-filed, fundamentals only (for the regression pair)
  asfiled_drop_<signal>  as-filed, one technical sub-signal removed
  asfiled_slow_rs        as-filed, relative_strength computed on a 63-day window
  asfiled_stack          as-filed, rank buffer 1.5 + max-weight/sector/liquidity stack
"""
import sys

HERE = "/Users/eyerise/Documents/GitHub/Dash/pipeline"
sys.path.insert(0, HERE)

variant, out = sys.argv[1], sys.argv[2]

import advisor_engine  # noqa: E402
import backtest_historical as bh  # noqa: E402
import scorer  # noqa: E402
from backtest_historical import (at, basic_ratios, line, nearest_close,  # noqa: E402
                                 price_index)
from edgar_enrichment import (_annual_facts_as_of, _statements,  # noqa: E402
                              _ticker_to_cik)
from fundamentals_extended import derive_extended  # noqa: E402


def build_snapshot_asfiled(ticker_data, as_of, report_lag_days, allow_current_shares=True,
                           allow_empty_fundamentals=False):
    """As-filed replacement for backtest_historical.build_snapshot.

    Visibility rule: a statement fact exists on ``as_of`` only if its filing date is on or
    before ``as_of``. The latest visible filing wins per (concept, period), so amendments
    appear on their own filing date and never rewrite the earlier view. Enforced by
    edgar_enrichment._annual_facts_as_of and asserted in
    pipeline/tests/test_asfiled_backtest.py.
    """
    symbol = ticker_data["symbol"]
    as_of_iso = as_of.isoformat()
    cik = _ticker_to_cik().get(str(symbol).upper())
    annual = None
    if cik:
        facts = _annual_facts_as_of(cik, as_of_iso)
        annual = _statements(facts)
    if annual is None and not allow_empty_fundamentals:
        return None
    empty = {"periods": [], "rows": {}}
    income = (annual or {}).get("income", empty)
    balance = (annual or {}).get("balance", empty)

    raw_closes = ticker_data.get("raw_closes") or ticker_data["closes"]
    price = nearest_close(ticker_data["dates"], raw_closes, as_of)
    if price is None:
        return None
    shares = at(line(income, "diluted_shares"))
    if not shares and allow_current_shares:
        shares = ticker_data["current_shares_outstanding"]
    market_cap = price * shares if shares else None

    revenue_now, revenue_prior = at(line(income, "revenue"), 0), at(line(income, "revenue"), 1)
    revenue_growth = (revenue_now / revenue_prior - 1) if (
        revenue_now and revenue_prior and revenue_prior > 0) else None
    ni_now, ni_prior = at(line(income, "net_income"), 0), at(line(income, "net_income"), 1)
    earnings_growth = (ni_now / ni_prior - 1) if (
        ni_now is not None and ni_prior not in (None, 0)) else None

    first = lambda stmt: {"periods": stmt["periods"][:1],
                          "rows": {k: v[:1] for k, v in stmt["rows"].items()}}
    snap = basic_ratios(first(income), first(balance), market_cap, revenue_growth)
    snap.update({
        "ticker": symbol, "name": ticker_data["name"], "sector": ticker_data["sector"],
        "is_etf": ticker_data["is_etf"], "market_cap": market_cap, "price": price,
        "revenue_growth": round(revenue_growth, 4) if revenue_growth is not None else None,
        "earnings_growth": round(earnings_growth, 4) if earnings_growth is not None else None,
        "statement_source": "sec_edgar_pit_asfiled",
    })

    idx = price_index(ticker_data["dates"], as_of)
    closes_to_date = ticker_data["closes"][:idx + 1] if idx is not None else []
    volumes_to_date = ticker_data["volumes"][:idx + 1] if idx is not None else []
    if annual is not None:
        snap.update(derive_extended(annual=annual, info={}, market_cap=market_cap,
                                    price=price, sector=ticker_data["sector"],
                                    closes=closes_to_date, volumes=volumes_to_date))
        cashflow = annual.get("cashflow", empty)
        ttm_fcf = None
        op_cf, capex = at(line(cashflow, "operating_cash_flow")), at(line(cashflow, "capex"))
        if op_cf is not None:
            ttm_fcf = op_cf - abs(capex or 0)
        snap["free_cash_flow"] = round(ttm_fcf) if ttm_fcf is not None else None
        snap["free_cash_flow_yield"] = (round(ttm_fcf / market_cap, 4)
                                        if ttm_fcf and market_cap else None)
    return snap, closes_to_date, volumes_to_date


bh.build_snapshot = build_snapshot_asfiled

if variant == "asfiled":
    pass
elif variant == "asfiled_fund_only":
    advisor_engine.RANKING_WEIGHTS = {"fundamentals": 1.0}
    advisor_engine.apply_modifiers = lambda base, *a, **k: (round(base, 1), {"applied": {}, "total": 0.0})
elif variant == "asfiled_drop_fast":
    weights = dict(advisor_engine.TECHNICAL_WEIGHTS)
    for key in ("relative_strength", "volume_confirmation"):
        weights.pop(key, None)
    advisor_engine.TECHNICAL_WEIGHTS = weights
elif variant == "asfiled_stack":
    pass
elif variant.startswith("asfiled_drop_"):
    dropped = variant.replace("asfiled_drop_", "")
    weights = dict(advisor_engine.TECHNICAL_WEIGHTS)
    if dropped not in weights:
        raise SystemExit(f"unknown technical sub-signal {dropped}: {sorted(weights)}")
    del weights[dropped]
    advisor_engine.TECHNICAL_WEIGHTS = weights
elif variant == "asfiled_slow_rs":
    original = advisor_engine.technical_factors
    combine = advisor_engine.technical_score_from_parts
    SIGNALS = ("momentum_12_1", "risk_adjusted", "relative_strength",
               "drawdown_resilience", "volume_confirmation", "low_beta",
               "technical_extended")

    def slowed_technical(closes, benchmark_closes=None, volumes=None, extended=None,
                         **kwargs):
        score, detail = original(closes, benchmark_closes, volumes, extended, **kwargs)
        if score is None or not benchmark_closes:
            return score, detail
        parts = {name: detail.get(name) for name in SIGNALS}
        if (len(closes) > 63 and len(benchmark_closes) > 63
                and closes[-64] and benchmark_closes[-64]):
            own = closes[-1] / closes[-64] - 1
            spy = benchmark_closes[-1] / benchmark_closes[-64] - 1
            parts["relative_strength"] = max(0.0, min(100.0, 50 + (own - spy) * 100))
        new_score, _variant = combine(parts, detail.get("short_horizon_treatment",
                                                        "legacy_momentum"))
        detail = {**detail,
                  "relative_strength": parts.get("relative_strength"),
                  "relative_strength_window_days": 63}
        return new_score, detail

    advisor_engine.technical_factors = slowed_technical
    bh.technical_factors = slowed_technical
else:
    raise SystemExit(f"unknown variant {variant}")

import backtest_monthly  # noqa: E402

args = ["backtest_monthly.py", "--cache-only", "--years", "5", "--out", out]
if variant == "asfiled_stack":
    args += ["--rank-buffer", "1.5"]
sys.argv = args
backtest_monthly.main()
