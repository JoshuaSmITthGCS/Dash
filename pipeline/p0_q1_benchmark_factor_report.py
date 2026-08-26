"""P0 WO-4 (Q1) -- is the benchmark wrong, or is the signal wrong?

Everything here runs against data already committed to the repo: the published monthly
backtest (pipeline/backtest_monthly_results.json), full daily ETF histories for RSP and IWM
(public/data/etf/{RSP,IWM}.json -- fetched previously for the ETF watchlist, unrelated to this
brief, and happen to cover the entire 2021-08-02..2026-07-31 backtest window), and the cached
Kenneth R. French five-factor plus momentum series (public/data/factors/french.json). No network
access is used or required.

A sector-neutral fourth benchmark was in scope per the brief but is NOT built here: only 193 of
the 397 unique tickers that passed through the backtest's 20-name portfolio have a sector label
anywhere in the currently-published data (public/data/advisor.json's research/screen_universe/
portfolio_coverage rows -- the only place sector is recorded at all, since backtest_monthly.py
deliberately nulls sector on every fetched context and the committed backtest artifact carries no
sector field). Building a sector composite would mean fabricating labels for the uncovered 51%
of picks, which this brief's evidence discipline rules out. See docs/P0-Q1-BENCHMARK.md for the
coverage count and what would resolve it (a point-in-time sector map, which does not exist yet).

Method for RSP and IWM: identical to how backtest_monthly.py already prices the SPY leg --
simulate_benchmark() (buy-and-hold from the strategy's first execution date, one entry cost at
10bps, no further trading) applied to each ETF's own daily adjusted-close series. This makes the
three benchmark legs directly comparable: same start date, same capital, same one-time cost.

The ETF price files under public/data/etf/ and pipeline/backtest_monthly_results.json are
refreshed on independent schedules -- the ETF files by whatever job last updated the ETF
watchlist, the backtest by its own less-frequent monthly-backtest run. A 2026-08-26 re-run of
this script found the ETF files 11 days fresher than the backtest, which without a guard would
have simulated RSP/IWM/etc. through several extra trading days the strategy/SPY legs don't have --
a real period mismatch masquerading as a comparability guarantee this docstring already claimed.
clip_to_end_date() below enforces the guarantee: every ETF-derived leg is truncated to the
strategy portfolio's own last history date before simulate_benchmark() runs, so "directly
comparable" stays true regardless of which file happened to refresh more recently.

Method for the six-factor regression: monthly strategy returns are month-end-to-month-end
resamples of the daily portfolio value series already in backtest_monthly_results.json (a full
calendar month already includes the 10bps-per-rebalance cost baked into that series -- this is
the same already-published, cost-aware return path, not a re-simulation). The backtest's mid-month
start date (2021-08-02) only affects the level of the first month-end value, not any return
computed from it forward, so every monthly return used is a genuine full-calendar-month return;
none is dropped as partial. Ken French's five factors plus momentum are read from the already-
cached, already-parsed public/data/factors/french.json (latest available month: 2026-06, so the
regression sample ends there regardless of the backtest's own July 2026 endpoint).

OLS is implemented directly with numpy (statsmodels/scipy are not installed in this environment).
Newey-West HAC standard errors use the standard Bartlett-kernel sandwich estimator with the
requested 3 lags: for design matrix X and residuals u, g_t = x_t * u_t,
S = sum_t g_t g_t' + sum_{l=1}^{3} (1 - l/4) * sum_t (g_t g_{t-l}' + g_{t-l} g_t'),
Cov(beta) = (X'X)^-1 S (X'X)^-1. No small-sample correction is applied.

Usage: python pipeline/p0_q1_benchmark_factor_report.py
"""

import json
import os
import sys
from datetime import date

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

from backtest_monthly import performance_metrics, simulate_benchmark  # noqa: E402
from common import LOG  # noqa: E402

BACKTEST_PATH = os.path.join(HERE, "backtest_monthly_results.json")
FRENCH_PATH = os.path.join(ROOT, "public", "data", "factors", "french.json")
ADVISOR_PATH = os.path.join(ROOT, "public", "data", "advisor.json")
ETF_DIR = os.path.join(ROOT, "public", "data", "etf")
OUT_PATH = os.path.join(HERE, "reports", "factor_regression_p0.json")
BENCHMARK_COMPARISON_PATH = os.path.join(HERE, "reports", "benchmark_comparison.json")
FACTOR_REGRESSION_PATH = os.path.join(HERE, "reports", "factor_regression.json")

# C1: the strategy runs at beta 0.79 / SMB 0.455 (see the six-factor regression below) --
# a small/mid-tilted book with less market beta than SPY. These style/size ETFs, all
# committed and covering the full 2021-08-02..2026-07-31 backtest window, let the question
# "is this more than repackaged factor exposure?" get asked against benchmarks that actually
# share that risk profile, not just SPY and the two already-published RSP/IWM legs.
STYLE_SIZE_BENCHMARKS = {
    "iwd_value": "IWD", "iwf_growth": "IWF", "ijh_mid_cap": "IJH", "ijr_small_cap": "IJR",
    "vb_small_cap": "VB", "schd_quality_dividend": "SCHD", "nobl_quality_dividend": "NOBL",
    "vxf_extended_market": "VXF",
}

FACTOR_NAMES = ["market_excess", "size", "value", "profitability", "investment", "momentum"]
NEWEY_WEST_LAGS = 3


def load_etf_benchmark(ticker):
    with open(os.path.join(ETF_DIR, f"{ticker}.json"), encoding="utf-8") as handle:
        payload = json.load(handle)
    fund = payload["price_series"]["fund"]
    dates = [row["date"] for row in fund]
    closes = [row["adjusted_close"] for row in fund]
    return {"dates": dates, "closes": closes}


def clip_to_end_date(benchmark, end_date):
    """Drop any date past ``end_date`` so an independently-refreshed ETF file can't simulate
    through days the strategy/SPY legs don't have -- see the module docstring."""
    kept = [(day, close) for day, close in zip(benchmark["dates"], benchmark["closes"]) if day <= end_date]
    return {"dates": [day for day, _ in kept], "closes": [close for _, close in kept]}


def month_end_values(dates, values):
    by_month = {}
    for day, value in zip(dates, values):
        by_month[day[:7]] = value  # dates are sorted ascending; last write per month wins
    months = sorted(by_month)
    return months, [by_month[month] for month in months]


def blend_benchmark(a, b, weight_a=0.5):
    """A static (non-rebalanced) growth-weighted blend of two ETF daily series, indexed to
    1.0 on their first common date. ``simulate_benchmark`` only ever uses the ratio of a
    close to the first usable day's close, so this arbitrary-scale growth index feeds it
    exactly like a real price series would.
    """
    a_map, b_map = dict(zip(a["dates"], a["closes"])), dict(zip(b["dates"], b["closes"]))
    common_dates = sorted(set(a_map) & set(b_map))
    if not common_dates:
        return {"dates": [], "closes": []}
    a_start, b_start = a_map[common_dates[0]], b_map[common_dates[0]]
    closes = [
        weight_a * (a_map[day] / a_start) + (1 - weight_a) * (b_map[day] / b_start)
        for day in common_dates
    ]
    return {"dates": common_dates, "closes": closes}


def monthly_returns(dates, values):
    """Month-end-to-month-end returns. Every entry is a genuine full-calendar-month return
    (last trading day of month M-1 to last trading day of month M) regardless of when the
    underlying position was first established -- the backtest's mid-month start date (2021-08-02)
    only affects the *level* of the first month-end value, not the return computed from it
    forward, so no month needs to be dropped as "partial."
    """
    months, month_values = month_end_values(dates, values)
    returns = {}
    for index in range(1, len(months)):
        returns[months[index]] = month_values[index] / month_values[index - 1] - 1
    return returns


def sector_coverage(backtest_tickers, advisor_path=ADVISOR_PATH):
    with open(advisor_path, encoding="utf-8") as handle:
        advisor = json.load(handle)
    sector_map = {}
    for key in ("research", "screen_universe", "portfolio_coverage"):
        for row in advisor.get(key, []):
            ticker = row.get("ticker")
            sector = row.get("sector")
            if ticker and sector and ticker not in sector_map:
                sector_map[ticker] = sector
    found = sorted(t for t in backtest_tickers if t in sector_map)
    missing = sorted(t for t in backtest_tickers if t not in sector_map)
    return {"total": len(backtest_tickers), "found": len(found), "missing": len(missing),
            "missing_sample": missing[:20]}


def ols_newey_west(y, x_columns, lags=NEWEY_WEST_LAGS):
    """y: (n,) array. x_columns: dict[name] -> (n,) array of regressors (constant added here)."""
    n = len(y)
    names = ["alpha", *x_columns]
    X = np.column_stack([np.ones(n), *(np.asarray(x_columns[name]) for name in x_columns)])
    k = X.shape[1]
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    residuals = y - X @ beta
    ss_res = float(residuals @ residuals)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r_squared = 1 - ss_res / ss_tot if ss_tot else None

    # Classical OLS standard errors (homoskedastic, no autocorrelation adjustment).
    sigma2 = ss_res / (n - k)
    classical_cov = sigma2 * XtX_inv
    classical_se = np.sqrt(np.diag(classical_cov))

    # Newey-West HAC standard errors, Bartlett kernel, `lags` lags.
    g = X * residuals[:, None]
    S = g.T @ g
    for lag in range(1, lags + 1):
        weight = 1 - lag / (lags + 1)
        cross = g[lag:].T @ g[:-lag]
        S += weight * (cross + cross.T)
    nw_cov = XtX_inv @ S @ XtX_inv
    nw_se = np.sqrt(np.diag(nw_cov))

    result = {"observations": n, "r_squared": r_squared, "coefficients": {}}
    for index, name in enumerate(names):
        coefficient = float(beta[index])
        classical_t = coefficient / classical_se[index] if classical_se[index] else None
        nw_t = coefficient / nw_se[index] if nw_se[index] else None
        result["coefficients"][name] = {
            "estimate": coefficient,
            "classical_standard_error": float(classical_se[index]),
            "classical_t_statistic": classical_t,
            "newey_west_standard_error": float(nw_se[index]),
            "newey_west_t_statistic": nw_t,
        }
    return result


def main():
    with open(BACKTEST_PATH, encoding="utf-8") as handle:
        backtest = json.load(handle)
    portfolio = backtest["portfolio"]
    spy = backtest["benchmark_spy"]
    start_date = portfolio["metrics"]["start_date"]
    initial_capital = portfolio["metrics"]["initial_value"]
    # Every ETF-derived leg is clipped to this so a more-recently-refreshed ETF file can't
    # simulate through days the strategy/SPY legs (bounded by backtest_monthly_results.json)
    # don't have -- see clip_to_end_date() and the module docstring.
    end_date = portfolio["history"][-1]["date"]

    # --- Four-benchmark comparison ---------------------------------------------------
    rsp_benchmark = clip_to_end_date(load_etf_benchmark("RSP"), end_date)
    iwm_benchmark = clip_to_end_date(load_etf_benchmark("IWM"), end_date)
    rsp_result = simulate_benchmark(rsp_benchmark, start_date, initial_capital, 10.0)
    iwm_result = simulate_benchmark(iwm_benchmark, start_date, initial_capital, 10.0)

    backtest_tickers = sorted({pick["ticker"] for row in portfolio["rebalances"] for pick in row["picks"]})
    sector_neutral_status = {
        "built": False,
        "reason": "insufficient on-disk sector coverage to build without fabricating labels",
        "coverage": sector_coverage(backtest_tickers),
    }

    # C1: style/size/quality benchmarks matched to the strategy's realized beta 0.79 / SMB
    # 0.455 profile, plus a 50/50 IWD+IJH blend as the closest single passive match.
    style_size_results = {
        label: simulate_benchmark(
            clip_to_end_date(load_etf_benchmark(ticker), end_date), start_date, initial_capital, 10.0
        )["metrics"]
        for label, ticker in STYLE_SIZE_BENCHMARKS.items()
    }
    iwd_ijh_blend = clip_to_end_date(
        blend_benchmark(load_etf_benchmark("IWD"), load_etf_benchmark("IJH")), end_date
    )
    style_size_results["iwd_ijh_50_50_blend"] = simulate_benchmark(
        iwd_ijh_blend, start_date, initial_capital, 10.0
    )["metrics"]

    benchmark_comparison = {
        "strategy": portfolio["metrics"],
        "spy": spy["metrics"],
        "rsp_equal_weight_sp500": rsp_result["metrics"],
        "iwm_small_mid_cap": iwm_result["metrics"],
        **style_size_results,
        "sector_neutral_composite": sector_neutral_status,
        "method": (
            "All ETF legs use backtest_monthly.simulate_benchmark: buy-and-hold from the "
            "strategy's own first execution date, one 10bps entry cost, no further trading -- "
            "identical method and cost to the SPY/RSP/IWM legs, so every row is directly "
            "comparable. iwd_ijh_50_50_blend is a static (non-rebalanced) growth-weighted "
            "blend, not a rebalanced index."
        ),
    }

    # --- Six-factor regression ---------------------------------------------------------
    strategy_dates = [row["date"] for row in portfolio["history"]]
    strategy_values = [row["value"] for row in portfolio["history"]]
    strategy_monthly = monthly_returns(strategy_dates, strategy_values)

    with open(FRENCH_PATH, encoding="utf-8") as handle:
        french = json.load(handle)
    factor_by_month = {obs["month"]: obs for obs in french["observations"]}

    aligned_months = sorted(set(strategy_monthly) & set(factor_by_month))
    excess_returns = np.array([
        strategy_monthly[month] - factor_by_month[month]["risk_free"] for month in aligned_months
    ])
    factor_columns = {
        name: np.array([factor_by_month[month][name] for month in aligned_months])
        for name in FACTOR_NAMES
    }
    regression = ols_newey_west(excess_returns, factor_columns)
    regression["months"] = aligned_months
    regression["first_month"] = aligned_months[0] if aligned_months else None
    regression["last_month"] = aligned_months[-1] if aligned_months else None
    regression["annualized_alpha_pct"] = (
        (1 + regression["coefficients"]["alpha"]["estimate"]) ** 12 - 1
    ) * 100

    # --- Single-factor CAPM, for the beta-vs-selection shortfall decomposition ---------
    capm = ols_newey_west(excess_returns, {"market_excess": factor_columns["market_excess"]})
    capm["months"] = aligned_months
    capm["annualized_alpha_pct"] = ((1 + capm["coefficients"]["alpha"]["estimate"]) ** 12 - 1) * 100
    spy_mean_monthly_excess = float(factor_columns["market_excess"].mean())
    capm_beta = capm["coefficients"]["market_excess"]["estimate"]
    strategy_mean_monthly_excess = float(excess_returns.mean())
    expected_from_beta_monthly = capm_beta * spy_mean_monthly_excess
    selection_residual_monthly = strategy_mean_monthly_excess - expected_from_beta_monthly
    shortfall_decomposition = {
        "description": (
            "Mean monthly excess return over the same aligned sample, decomposed via the "
            "single-factor CAPM: strategy_mean_excess = beta * spy_mean_excess + alpha. "
            "The beta*spy_mean_excess term is 'explained by running at this beta in this "
            "market'; alpha is what beta exposure alone does not explain (selection, "
            "positive or negative)."
        ),
        "capm_beta": capm_beta,
        "capm_beta_newey_west_t": capm["coefficients"]["market_excess"]["newey_west_t_statistic"],
        "spy_mean_monthly_excess_return": spy_mean_monthly_excess,
        "strategy_mean_monthly_excess_return": strategy_mean_monthly_excess,
        "explained_by_beta_monthly": expected_from_beta_monthly,
        "residual_selection_monthly": selection_residual_monthly,
        "explained_by_beta_annualized_pct": ((1 + expected_from_beta_monthly) ** 12 - 1) * 100,
        "residual_selection_annualized_pct": capm["annualized_alpha_pct"],
    }

    output = {
        "generated_at": backtest.get("generated_at"),
        "note": "See pipeline/p0_q1_benchmark_factor_report.py docstring for exact method and data provenance.",
        "benchmark_comparison": benchmark_comparison,
        "six_factor_regression": regression,
        "single_factor_capm": capm,
        "shortfall_decomposition": shortfall_decomposition,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)
    LOG.info(f"Wrote {OUT_PATH}")

    # C1: the same content, split into the two brief-specified report files (kept alongside
    # the original combined factor_regression_p0.json, not replacing it).
    with open(BENCHMARK_COMPARISON_PATH, "w", encoding="utf-8") as handle:
        json.dump({"generated_at": output["generated_at"], **benchmark_comparison}, handle, indent=2)
    LOG.info(f"Wrote {BENCHMARK_COMPARISON_PATH}")
    with open(FACTOR_REGRESSION_PATH, "w", encoding="utf-8") as handle:
        json.dump({
            "generated_at": output["generated_at"],
            "six_factor_regression": regression,
            "single_factor_capm": capm,
            "shortfall_decomposition": shortfall_decomposition,
        }, handle, indent=2)
    LOG.info(f"Wrote {FACTOR_REGRESSION_PATH}")

    alpha = regression["coefficients"]["alpha"]
    print(f"n={regression['observations']} months ({regression['first_month']}..{regression['last_month']})")
    print(f"alpha monthly={alpha['estimate']:.5f} annualized={regression['annualized_alpha_pct']:.2f}%")
    print(f"alpha classical t={alpha['classical_t_statistic']:.3f} NW(3) t={alpha['newey_west_t_statistic']:.3f}")
    print(f"R^2={regression['r_squared']:.4f}")
    print(f"strategy CAGR={portfolio['metrics']['cagr']:.4f} vs. "
          f"iwd_ijh_50_50_blend CAGR={style_size_results['iwd_ijh_50_50_blend']['cagr']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
