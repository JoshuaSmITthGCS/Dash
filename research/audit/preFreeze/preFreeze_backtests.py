"""Pre-freeze construction round: four challengers, one specification each, one run each.

All variants run on the corrected as-filed TTM quarterly spine (round6
asfiled_ttm_backtest build_snapshot patch). Parameters come from the cited papers, not
from search:

  orthogonal    Asness, Frazzini, Pedersen (Rev. Accounting Studies 24(1), 2019):
                quality exposure constructed independent of value. Profitability,
                growth, and financial-health category scores are residualized
                cross-sectionally against book-to-market at each rebalance, rescaled to
                the original category distribution, and the composite rebuilt.
  max_screen    Bali, Cakici, Whitelaw (JFE 99(2), 2011): MAX = mean of the five
                highest daily returns in the prior month. Top MAX decile is EXCLUDED
                from selection. Not a scored factor.
  net_issuance  Pontiff, Woodgate (JF 63(2), 2008): net share issuance = log change in
                split-adjusted shares outstanding over the trailing twelve months,
                from as-filed diluted share counts. REPLACES buyback yield in the
                capital-allocation block (issuance is the comprehensive measure of
                which repurchase is one side; carrying both double-counts).
  parsimony     DeMiguel, Garlappi, Uppal (RFS 22(5), 2009): equal weights over six
                near-orthogonal replication-grade signals (EBITDA/EV, gross
                profits/assets, net issuance, asset growth, momentum 12-1, Altman Z),
                winsorized 1/99, sector-conditional percentile ranks. No other
                machinery: no modifiers, no coverage multipliers, no blend.

Usage: preFreeze_backtests.py <variant> <out.json>
"""
import json
import math
import sys
import types

import numpy as np

HERE = "/Users/eyerise/Documents/GitHub/Dash/pipeline"
sys.path.insert(0, HERE)
sys.path.insert(0, "/Users/eyerise/Documents/GitHub/Dash/research/audit/round6")

variant, out = sys.argv[1], sys.argv[2]

import advisor_engine  # noqa: E402
import backtest_historical as bh  # noqa: E402
import scorer  # noqa: E402

# Install the as-filed TTM snapshot builder (round 6 spine) without running its main.
fake = types.ModuleType("backtest_monthly")
fake.main = lambda: None
sys.modules["backtest_monthly"] = fake
_argv = sys.argv
sys.argv = ["asfiled_ttm_backtest.py", "asfiled_q", "/dev/null"]
import asfiled_ttm_backtest  # noqa: F401, E402
del sys.modules["backtest_monthly"]
sys.argv = _argv

CAT_W = scorer.SETTINGS["fundamentals"]["category_weights"]
MET_W = scorer.SETTINGS["fundamentals"]["metric_weights"]
ORTHO_CATS = ("profitability", "growth", "financial_health")

_original_valuation_score = scorer.valuation_score
_original_rank_week = bh.rank_week
_override = {}


def _prepare(universe_data, as_of, report_lag_days):
    prepared = {}
    for symbol, ticker_data in universe_data.items():
        built = bh.build_snapshot(ticker_data, as_of, report_lag_days)
        if built is not None:
            prepared[symbol] = built
    return prepared


def _issuance(snap):
    """Log 12-month change in as-filed diluted shares (index 0 vs 1 of the TTM series
    is TTM vs latest FY, approximately trailing twelve months at quarterly cadence)."""
    # build_snapshot_asfiled_ttm does not expose the share series directly, so read it
    # from the statement periods it recorded: fall back to reported diluted shares.
    s0 = snap.get("_shares_now")
    s1 = snap.get("_shares_prior")
    if s0 and s1 and s0 > 0 and s1 > 0:
        return math.log(s0 / s1)
    return None


# Patch the TTM builder once to also stash the share series for issuance math.
_build0 = bh.build_snapshot


def build_with_shares(ticker_data, as_of, report_lag_days, *a, **k):
    built = _build0(ticker_data, as_of, report_lag_days, *a, **k)
    if built is None:
        return None
    snap, closes, volumes = built
    from edgar_enrichment import _all_facts_as_of, _ticker_to_cik
    cik = _ticker_to_cik().get(str(snap["ticker"]).upper())
    if cik:
        from datetime import date, timedelta
        rows = [(pe, v) for c, pe, days, v in _all_facts_as_of(cik, as_of.isoformat())
                if c == "shares_diluted" and v]
        if rows:
            rows.sort()
            now_pe, now_v = rows[-1]
            target = (date.fromisoformat(now_pe) - timedelta(days=365)).isoformat()
            prior = min(rows, key=lambda r: abs((date.fromisoformat(r[0])
                                                 - date.fromisoformat(target)).days))
            if abs((date.fromisoformat(prior[0])
                    - date.fromisoformat(target)).days) <= 100:
                snap["_shares_now"], snap["_shares_prior"] = now_v, prior[1]
    return snap, closes, volumes


bh.build_snapshot = build_with_shares


def _pct(values, value, lower_is_better=False):
    arr = np.sort(np.asarray(values, dtype=float))
    if len(arr) < 2:
        return 50.0
    lo, hi = np.percentile(arr, 1), np.percentile(arr, 99)
    v = min(max(value, lo), hi)
    p = np.searchsorted(arr, v) / len(arr) * 100
    return 100 - p if lower_is_better else p


def override_valuation(snap, **kwargs):
    t = snap.get("ticker")
    if t in _override:
        return _override[t]
    return _original_valuation_score(snap, **kwargs)


def _rebuild_total(cats, parts):
    avail = [(cats[c], CAT_W[c]) for c in CAT_W if cats.get(c) is not None]
    if not avail:
        return None
    raw = sum(v * w for v, w in avail) / sum(w for _v, w in avail)
    coverage = parts.get("coverage", 0.0)
    return round(raw * (0.65 + 0.35 * coverage), 1)


def rank_week_orthogonal(universe_data, benchmark_closes, as_of, report_lag_days, **k):
    prepared = _prepare(universe_data, as_of, report_lag_days)
    rows = []
    for symbol, (snap, _c, _v) in prepared.items():
        total, parts = _original_valuation_score(snap)
        pb = snap.get("price_to_book")
        bm = 1.0 / pb if isinstance(pb, (int, float)) and pb > 0 else None
        rows.append((symbol, snap, total, parts, bm))
    _override.clear()
    with_bm = [r for r in rows if r[4] is not None and r[3]]
    bm_arr = np.array([r[4] for r in with_bm])
    for cat in ORTHO_CATS:
        pairs = [(i, r[3].get("categories", {}).get(cat)) for i, r in enumerate(with_bm)]
        idx = [i for i, v in pairs if v is not None]
        if len(idx) < 30:
            continue
        y = np.array([with_bm[i][3]["categories"][cat] for i in idx], dtype=float)
        x = np.log(bm_arr[idx])
        X = np.column_stack([np.ones(len(x)), x])
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        resid = y - X @ beta
        scale = y.std(ddof=1) / max(resid.std(ddof=1), 1e-9)
        adjusted = np.clip(resid * scale + y.mean(), 0, 100)
        for j, i in enumerate(idx):
            with_bm[i][3]["categories"][cat] = round(float(adjusted[j]), 1)
    for symbol, snap, total, parts, _bm in rows:
        if parts:
            new_total = _rebuild_total(parts.get("categories", {}), parts)
            _override[symbol] = (new_total, parts)
        else:
            _override[symbol] = (total, parts)
    return _original_rank_week(universe_data, benchmark_closes, as_of,
                               report_lag_days, **k)


def rank_week_max_screen(universe_data, benchmark_closes, as_of, report_lag_days, **k):
    ranked = _original_rank_week(universe_data, benchmark_closes, as_of,
                                 report_lag_days, **k)
    prepared = _prepare(universe_data, as_of, report_lag_days)
    max_by_ticker = {}
    for symbol, (_snap, closes, _v) in prepared.items():
        if len(closes) < 22:
            continue
        window = np.asarray(closes[-22:], dtype=float)
        rets = np.diff(window) / window[:-1]
        if len(rets) >= 5:
            max_by_ticker[symbol] = float(np.mean(np.sort(rets)[-5:]))
    if len(max_by_ticker) < 20:
        return ranked
    cutoff = np.percentile(list(max_by_ticker.values()), 90)
    excluded = {t for t, m in max_by_ticker.items() if m >= cutoff}
    return [row for row in ranked if row["ticker"] not in excluded]


def rank_week_net_issuance(universe_data, benchmark_closes, as_of, report_lag_days, **k):
    prepared = _prepare(universe_data, as_of, report_lag_days)
    issuance = {}
    for symbol, (snap, _c, _v) in prepared.items():
        v = _issuance(snap)
        if v is not None:
            issuance[symbol] = v
    values = list(issuance.values())
    _override.clear()
    for symbol, (snap, _c, _v) in prepared.items():
        total, parts = _original_valuation_score(snap)
        if not parts:
            _override[symbol] = (total, parts)
            continue
        score = (_pct(values, issuance[symbol], lower_is_better=True)
                 if symbol in issuance and len(values) >= 30 else None)
        parts["net_buyback_yield"] = score
        weights = MET_W["capital_allocation"]
        cats = parts.get("categories", {})
        avail = [(parts.get(m), w) for m, w in weights.items()
                 if parts.get(m) is not None]
        cats["capital_allocation"] = (round(sum(v * w for v, w in avail)
                                            / sum(w for _v, w in avail), 1)
                                      if avail else None)
        _override[symbol] = (_rebuild_total(cats, parts), parts)
    return _original_rank_week(universe_data, benchmark_closes, as_of,
                               report_lag_days, **k)


PARSIMONY_SIGNALS = ("ebitda_to_ev", "gross_profits_to_assets", "net_issuance",
                     "asset_growth", "momentum_12_1", "altman_z")


def rank_week_parsimony(universe_data, benchmark_closes, as_of, report_lag_days, **k):
    prepared = _prepare(universe_data, as_of, report_lag_days)
    raw = {}
    for symbol, (snap, closes, _v) in prepared.items():
        ee = snap.get("ev_to_ebitda")
        mom = (closes[-21] / closes[-252] - 1
               if len(closes) >= 252 and closes[-252] and closes[-21] else None)
        raw[symbol] = {
            "sector": snap.get("sector"),
            "price": snap.get("price"),
            "ebitda_to_ev": 1.0 / ee if isinstance(ee, (int, float)) and ee > 0 else None,
            "gross_profits_to_assets": snap.get("gross_profits_to_assets"),
            "net_issuance": _issuance(snap),
            "asset_growth": snap.get("asset_growth"),
            "momentum_12_1": mom,
            "altman_z": snap.get("altman_z"),
        }
    lower = {"net_issuance", "asset_growth"}
    by_signal = {s: [v[s] for v in raw.values() if v[s] is not None]
                 for s in PARSIMONY_SIGNALS}
    by_sector = {}
    for v in raw.values():
        for s in PARSIMONY_SIGNALS:
            if v[s] is not None:
                by_sector.setdefault((s, v["sector"]), []).append(v[s])
    rows = []
    for symbol, v in raw.items():
        scores = []
        for s in PARSIMONY_SIGNALS:
            if v[s] is None:
                continue
            peers = by_sector.get((s, v["sector"]), [])
            pool = peers if len(peers) >= 8 else by_signal[s]
            if len(pool) < 8:
                continue
            scores.append(_pct(pool, v[s], lower_is_better=s in lower))
        if len(scores) < 4 or not v["price"]:
            continue
        rows.append({"ticker": symbol, "score": round(float(np.mean(scores)), 2),
                     "price": v["price"], "name": symbol, "sector": v["sector"],
                     "action": None, "recommendation": {}})
    rows.sort(key=lambda r: (-r["score"], r["ticker"]))
    return rows


if variant == "orthogonal":
    scorer.valuation_score = override_valuation
    advisor_engine.valuation_score = override_valuation
    bh.valuation_score = override_valuation
    bh.rank_week = rank_week_orthogonal
elif variant == "max_screen":
    bh.rank_week = rank_week_max_screen
elif variant == "net_issuance":
    scorer.valuation_score = override_valuation
    advisor_engine.valuation_score = override_valuation
    bh.valuation_score = override_valuation
    bh.rank_week = rank_week_net_issuance
elif variant == "parsimony":
    bh.rank_week = rank_week_parsimony
elif variant == "intangible_book":
    pass  # dispatched below, after helper definitions
else:
    raise SystemExit(f"unknown variant {variant}")

# ---- Task 4: intangible-adjusted book value (appended, single spec) ----
# Arnott, Harvey, Kalesnik, Linnainmaa (FAJ 77(1), 2021) via the Peters-Taylor
# capitalization: knowledge capital = perpetual-inventory R&D at 15% depreciation,
# organization capital = 30% of SG&A capitalized at 20% depreciation. Adjusted book =
# common equity + knowledge capital + organization capital. Replaces price_to_book and
# retires price_to_tangible_book. No alternative depreciation rates are tested.


def intangible_capital(cik, as_of_iso):
    from edgar_enrichment import _all_facts_as_of
    facts = _all_facts_as_of(cik, as_of_iso)
    def annual_series(concept):
        rows = sorted((pe, v) for c, pe, days, v in facts
                      if c == concept and v is not None
                      and isinstance(days, (int, float)) and 330 <= days <= 400)
        return rows
    K = 0.0
    for _pe, rd in annual_series("research_development"):
        K = K * (1 - 0.15) + rd
    O = 0.0
    for _pe, sga in annual_series("sga_expense"):
        O = O * (1 - 0.20) + 0.30 * sga
    return K, O


def build_with_ibook(ticker_data, as_of, report_lag_days, *a, **k):
    built = build_with_shares(ticker_data, as_of, report_lag_days, *a, **k)
    if built is None:
        return None
    snap, closes, volumes = built
    from edgar_enrichment import _all_facts_as_of, _ticker_to_cik
    cik = _ticker_to_cik().get(str(snap["ticker"]).upper())
    mcap = snap.get("market_cap")
    if cik and mcap:
        equity_rows = sorted((pe, v) for c, pe, _d, v in
                             _all_facts_as_of(cik, as_of.isoformat())
                             if c == "equity" and v is not None)
        if equity_rows:
            K, O = intangible_capital(cik, as_of.isoformat())
            ibook = equity_rows[-1][1] + K + O
            snap["price_to_book"] = (round(mcap / ibook, 2) if ibook > 0 else None)
            snap["price_to_tangible_book"] = None
    return snap, closes, volumes



if variant == "intangible_book":
    bh.build_snapshot = build_with_ibook

import backtest_monthly  # noqa: E402

backtest_monthly.rank_week = bh.rank_week
sys.argv = ["backtest_monthly.py", "--cache-only", "--years", "5", "--out", out]
backtest_monthly.main()


