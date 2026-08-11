"""Task 6: batch statement enrichment from the local EDGAR PIT store, then re-measure.

Decision rule, committed before measurement (see docs/AUDIT-ROUND-4-FINDINGS.md):
if Spearman(fundamentals coverage, final score) stays above +0.20 once mean statement
coverage exceeds 85%, the correlation is a design defect and the imputation redesign is
mandatory. Below +0.10 it was an outage artifact. Between the two, both remain live.

Mechanics: for every ticker in the pinned refresh, fill raw metrics the provider left
missing from edgar_enrichment (as-of 2026-08-10), rescore fundamentals through the
production band scorer, and rebuild the final score by combining the new fundamentals
component with each row's unchanged technical/news residual and modifiers.
"""
import json
import sys

import numpy as np
from scipy import stats

REPO = "/Users/eyerise/Documents/GitHub/Dash"
sys.path.insert(0, f"{REPO}/pipeline")

from edgar_enrichment import edgar_extended  # noqa: E402
import scorer  # noqa: E402

rows = [json.loads(l) for l in open(f"{REPO}/pipeline/pit_store/2026-08-10.jsonl")]
latest = max(r["refresh_id"] for r in rows)
rows = [r for r in rows if r["refresh_id"] == latest]

KEY_METRICS = ["ev_to_ebitda", "ev_to_ebit", "ev_to_fcf", "return_on_invested_capital",
               "gross_profits_to_assets", "piotroski_f", "net_buyback_yield",
               "accruals_ratio", "asset_growth", "stock_comp_to_revenue",
               "interest_coverage", "cash_conversion", "fcf_growth_3y", "altman_z",
               "price_to_tangible_book"]

before_cov = {m: 0 for m in KEY_METRICS}
after_cov = {m: 0 for m in KEY_METRICS}
recs = []
filled_names = 0
for r in rows:
    raw = dict(r.get("raw_metric_inputs") or {})
    t = r["ticker"]
    s_old = r["scores"]["champion"]
    if s_old is None:
        continue
    for m in KEY_METRICS:
        if isinstance(raw.get(m), (int, float)):
            before_cov[m] += 1
    fb = edgar_extended(t, as_of="2026-08-10", market_cap=raw.get("market_cap"),
                        price=raw.get("price"), sector=raw.get("sector"))
    if fb:
        added = 0
        for k, v in fb.items():
            if k in ("statement_source", "statement_periods", "piotroski_tests"):
                continue
            if raw.get(k) is None and v is not None:
                raw[k] = v
                added += 1
        filled_names += added > 0
    for m in KEY_METRICS:
        if isinstance(raw.get(m), (int, float)):
            after_cov[m] += 1

print("coverage before -> after (n=%d):" % len(rows))
for m in KEY_METRICS:
    print(f"  {m:28s} {before_cov[m]:4d} ({before_cov[m]/len(rows)*100:3.0f}%) -> {after_cov[m]:4d} ({after_cov[m]/len(rows)*100:3.0f}%)")
print("names with at least one filled metric:", filled_names)

# Coverage vs score, after: recompute weighted coverage on the new fundamentals detail and
# correlate with the rebuilt final score. The rebuilt final uses the production formula with
# the new fundamentals component and the row's original non-fundamental residual.
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


finals_new, covs_new, finals_old, covs_old_list = [], [], [], []
for r in rows:
    raw = dict(r.get("raw_metric_inputs") or {})
    t = r["ticker"]
    s_old = r["scores"]["champion"]
    if s_old is None:
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
    # Old fundamentals component exactly as production: category blend times coverage mult.
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
    rest = raw_blend_old - 0.78 * fund_old  # technical + news contribution, weight-scaled
    raw_blend_new = 0.78 * fund_new + rest
    final_new = max(0, min(100, raw_blend_new * (0.8 + 0.2 * conf) + mtot))
    finals_new.append(final_new)
    covs_new.append(wcov({m: parts_new.get(m) for ws in settings["metric_weights"].values() for m in ws}))
    finals_old.append(s_old)
    covs_old_list.append(cov_old)

rho_before = stats.spearmanr(covs_old_list, finals_old)
rho_after = stats.spearmanr(covs_new, finals_new)
print("\nmean fundamentals coverage: before %.2f -> after %.2f" % (
    np.mean(covs_old_list), np.mean(covs_new)))
print("Spearman(coverage, final): before %+.3f (p %.1e) -> after %+.3f (p %.1e), n=%d" % (
    rho_before[0], rho_before[1], rho_after[0], rho_after[1], len(finals_new)))
rho_rank = stats.spearmanr(finals_old, finals_new)
print("rank correlation old vs new final: %.3f" % rho_rank[0])
shift = stats.rankdata([-x for x in finals_old]) - stats.rankdata([-x for x in finals_new])
print("rank shifts: mean |shift| %.1f  >25 ranks: %d  >50: %d" % (
    np.abs(shift).mean(), (np.abs(shift) > 25).sum(), (np.abs(shift) > 50).sum()))
