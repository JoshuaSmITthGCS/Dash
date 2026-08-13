"""Task 6.2 companion: characteristic battery on the REBUILT FINAL score at restored
coverage, so the comparison to Round 4's battery (which used the published final score on
the coverage-degraded snapshot) is apples-to-apples. The rebuilt final combines the
EDGAR-augmented bands fundamentals with each row's unchanged technical/news residual and
modifiers, the Round 4 task6 construction.
"""
import json
import math
import sys
from bisect import bisect_left

import numpy as np
from scipy import stats

REPO = "/Users/eyerise/Documents/GitHub/Dash"
sys.path.insert(0, f"{REPO}/pipeline")
import scorer  # noqa: E402
from edgar_enrichment import edgar_extended  # noqa: E402

rows = [json.loads(l) for l in open(f"{REPO}/pipeline/pit_store/2026-08-10.jsonl")]
latest = max(r["refresh_id"] for r in rows)
rows = [r for r in rows if r["refresh_id"] == latest]
settings = scorer.SETTINGS["fundamentals"]


def wcov(detail):
    answered = total = 0.0
    for cat, ws in settings["metric_weights"].items():
        cw = settings["category_weights"].get(cat, 0)
        for m, w in ws.items():
            share = cw * w
            total += share
            if detail.get(m) is not None:
                answered += share
    return answered / total if total else 0.0


def mom_12_1(ticker, asof="2026-08-10"):
    try:
        d = json.load(open(f"{REPO}/pipeline/data/backtest_cache/{ticker}.json"))
    except FileNotFoundError:
        return None
    dates, closes = d["dates"], d["closes"]
    i = min(bisect_left(dates, asof), len(dates) - 1)
    if i < 252 or not closes[i - 21] or not closes[i - 252]:
        return None
    return closes[i - 21] / closes[i - 252] - 1


finals, chars = {}, {}
for r in rows:
    raw = dict(r.get("raw_metric_inputs") or {})
    t = r["ticker"]
    s_old = r["scores"]["champion"]
    if s_old is None or raw.get("sector") == "ETF":
        continue
    fb = edgar_extended(t, as_of="2026-08-10", market_cap=raw.get("market_cap"),
                        price=raw.get("price"), sector=raw.get("sector"))
    if fb:
        for k, v in fb.items():
            if k in ("statement_source", "statement_periods", "piotroski_tests"):
                continue
            if raw.get(k) is None and v is not None:
                raw[k] = v
    snap = {**raw, "ticker": t, "is_etf": False}
    fund_new, parts_new = scorer.valuation_score(snap, mode="bands")
    if fund_new is None:
        continue
    conf = (r.get("confidence") or r["data_coverage"])["champion"]
    mods = r["modifiers"]["champion"]
    mtot = mods.get("total")
    if mtot is None:
        mtot = sum((mods.get("applied") or {}).values())
    base_old = s_old - mtot
    if not (0 < base_old < 100):
        continue
    raw_blend_old = base_old / (0.8 + 0.2 * conf)
    cats = r["category_scores"]["champion"]
    num = den = 0.0
    for c, w in settings["category_weights"].items():
        if cats.get(c) is not None:
            num += cats[c] * w
            den += w
    if not den:
        continue
    cov_old = wcov(r["normalized_metric_scores"]["champion"])
    fund_old = (num / den) * (0.65 + 0.35 * cov_old)
    rest = raw_blend_old - 0.78 * fund_old
    final = max(0, min(100, (0.78 * fund_new + rest) * (0.8 + 0.2 * conf) + mtot))
    finals[t] = final
    chars[t] = {
        "log_mcap": math.log(raw["market_cap"]) if isinstance(raw.get("market_cap"), (int, float)) and raw["market_cap"] > 0 else None,
        "book_to_market": 1.0 / raw["price_to_book"] if isinstance(raw.get("price_to_book"), (int, float)) and raw["price_to_book"] > 0 else None,
        "gross_prof_assets": raw.get("gross_profits_to_assets"),
        "profit_margin": raw.get("profit_margin"),
        "asset_growth": raw.get("asset_growth"),
        "mom_12_1": mom_12_1(t),
    }

print("rebuilt FINAL score battery, EDGAR-augmented snapshot, n_base=%d:" % len(finals))
for name in ("log_mcap", "book_to_market", "gross_prof_assets", "profit_margin",
             "asset_growth", "mom_12_1"):
    xs = [(chars[t][name], finals[t]) for t in finals
          if isinstance(chars[t][name], (int, float)) and not math.isnan(chars[t][name])]
    a = np.array(xs)
    rho, p = stats.spearmanr(a[:, 1], a[:, 0])
    print(f"  {name:20s} rho {rho:+.3f}  p {p:.1e}  n {len(a)}")
