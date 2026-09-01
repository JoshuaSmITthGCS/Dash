"""R11 pre-merge gate, Stage 1b: is the rank-buffer (1.25/1.5/2.0) variant that appears in
pipeline/experiment_registry.py (``C4-turnover-controls``, ``C7-turnover-walkforward``) the
same underlying trial as the rank-buffer variant Stage-1/Part-1's mapping traced
harness_freeze.json's pre-freeze labels (``backtest_variants_r3``/``r4``/``r5``,
``turnover_control_sweep_pre_r3``) to in the round3-6 audit scripts -- i.e. a trial counted
once in the frozen ``dsr_trial_count_used: 50`` and a second time in
``experiment_registry.total_variants_tested()``, or two genuinely separate trials that happen
to share a parameter value?

Per the task brief: identity is decided by config hashes/timestamps, not by "both used
rank_buffer=1.5". The round3-6 audit scripts' own output files (``bt_buffer125.json`` etc.)
were never committed -- they lived in a local scratchpad path baked into those scripts'
source (see e.g. ``research/audit/round5/task6_noise_standard.py``'s ``S = "/private/tmp/
claude-501/..."``) -- so there is no byte-identical file to hash-compare. What IS committed,
and carries both an exact numeric fingerprint and pinned identifying metadata, is
``research/audit/remediation/before_after.json``:

- Its ``backtest_cagr_maxdd_cost.rank_buffer_1_5`` CAGR matches, to four decimal places,
  ``research/audit/round6/task4_netcost.py``'s hard-coded reference tuple
  ``("restated buffer 1.5", "bt_buffer150.json", 0.1260)``. An exact match on a number neither
  file needed to share unless one was read from the other is the identity evidence for
  CONFIRMED_DUPLICATE between the round5/6 audit "restated_buffer150" trial and
  ``before_after.json``'s ``rank_buffer_1_5`` entry: they are the same underlying backtest,
  surfaced in two files, not two independent trials.
- Its ``pinned_to`` block pins a ``pit_refresh_id``, a ``price_cache_tree_sha256_prefix`` and
  a ``universe_size`` (880) -- a specific, identifiable run, not a generic label.

Against that fingerprint:

- ``C4-turnover-controls`` reports ``buffer15_cagr=0.1233`` on, per its own ``result`` field,
  "the 360-symbol committed price cache" -- a different universe size (360, not 880) and a
  different CAGR (0.1233, not 0.1260) at the same nominal rank_buffer=1.5 parameter. A shared
  parameter value with both a different result AND a different universe size is evidence of
  CONFIRMED_DISTINCT: if this were the same trial re-read, the CAGR would match exactly the
  way 0.1260 == 0.1260 does above, and it does not.
- ``C7-turnover-walkforward`` reports only ``in_sample_winner="buffer15"`` and its
  out-of-sample rank/PBO -- no raw CAGR comparable to 0.1260 or 0.1233 at all.
  ``configuration.runs`` states "860 usable names", close to but not stated identical to the
  880 pinned in ``before_after.json``. No exact numeric match exists to confirm identity, and
  none exists to rule it out either -- verdict AMBIGUOUS, not a guess in either direction.

This module changes no promotion constant and no trial count -- see
``RECOMMENDATION`` at the bottom, which is a decision item for explicit human sign-off, not an
applied correction.
"""

import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(PIPELINE_DIR)
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

from experiment_registry import REGISTRY  # noqa: E402
from validation.deflated_sharpe import deflated_sharpe_ratio  # noqa: E402

NETCOST_SCRIPT = os.path.join(REPO_ROOT, "research", "audit", "round6", "task4_netcost.py")
REMEDIATION_JSON = os.path.join(REPO_ROOT, "research", "audit", "remediation", "before_after.json")

VERDICTS = {"confirmed_duplicate", "confirmed_distinct", "ambiguous"}


def _registry_entry(entry_id):
    for entry in REGISTRY:
        if entry["id"] == entry_id:
            return entry
    raise KeyError(entry_id)


def round6_restated_buffer_150_cagr(netcost_script=NETCOST_SCRIPT):
    """The CAGR round6/task4_netcost.py hard-codes for the as-filed 'restated buffer 1.5'
    trial, read from the source file itself rather than re-typed here."""
    text = open(netcost_script, encoding="utf-8").read()
    match = re.search(r'\("restated buffer 1\.5", "bt_buffer150\.json", ([\d.]+)\)', text)
    if not match:
        raise ValueError(f"expected reference tuple not found in {netcost_script}")
    return float(match.group(1))


def remediation_rank_buffer_1_5(remediation_json=REMEDIATION_JSON):
    with open(remediation_json, encoding="utf-8") as handle:
        data = json.load(handle)
    cagr, max_dd, cost = data["backtest_cagr_maxdd_cost"]["rank_buffer_1_5"]
    pinned = data["pinned_to"]
    return {
        "cagr": cagr, "max_dd": max_dd, "cost": cost,
        "universe_size": pinned["universe_size"],
        "pit_refresh_id": pinned["pit_refresh_id"],
        "price_cache_tree_sha256_prefix": pinned["price_cache_tree_sha256_prefix"],
    }


def check_rank_buffer_variant_identity():
    """Three-way identity check, one row per registry entry compared against the round5/6
    audit-script rank-buffer-1.5 trial. Never returns a bare boolean -- every row's verdict is
    one of VERDICTS, with the numeric/metadata evidence that produced it."""
    netcost_cagr = round6_restated_buffer_150_cagr()
    remediation = remediation_rank_buffer_1_5()
    if netcost_cagr != remediation["cagr"]:
        raise AssertionError(
            "round6/task4_netcost.py's hard-coded restated-buffer-1.5 CAGR "
            f"({netcost_cagr}) no longer matches remediation/before_after.json's "
            f"rank_buffer_1_5 CAGR ({remediation['cagr']}) -- the identity fingerprint this "
            "check relies on has changed; re-derive the comparison rather than trusting the "
            "verdicts below"
        )

    rows = []

    c4 = _registry_entry("C4-turnover-controls")
    c4_cagr = c4["metrics"]["buffer15_cagr"]
    c4_universe = c4["metrics"]["universe"]
    cagr_matches = c4_cagr == remediation["cagr"]
    universe_matches = c4_universe == remediation["universe_size"]
    if cagr_matches and universe_matches:
        verdict = "confirmed_duplicate"
        evidence = "exact CAGR and universe-size match against the round5/6 trial"
    elif not cagr_matches and not universe_matches:
        verdict = "confirmed_distinct"
        evidence = (
            f"C4 reports buffer15_cagr={c4_cagr} on a {c4_universe}-symbol committed price "
            f"cache; the round5/6 trial reports {remediation['cagr']} on a "
            f"{remediation['universe_size']}-name universe (pit_refresh_id="
            f"{remediation['pit_refresh_id']}). Same nominal rank_buffer=1.5 parameter, "
            "different result and different universe size -- not the same trial."
        )
    else:
        verdict = "ambiguous"
        evidence = "exactly one of CAGR/universe-size matches and the other does not"
    rows.append({
        "pair": "C4-turnover-controls vs round5/6 restated-buffer-1.5",
        "registry_id": "C4-turnover-controls",
        "registry_cagr": c4_cagr, "comparison_cagr": remediation["cagr"],
        "verdict": verdict, "evidence": evidence,
    })

    c7 = _registry_entry("C7-turnover-walkforward")
    c7_cagr = c7["metrics"].get("buffer15_cagr")
    if c7_cagr is not None:
        verdict = "confirmed_duplicate" if c7_cagr == remediation["cagr"] else "confirmed_distinct"
        evidence = f"C7 reports a comparable buffer15_cagr={c7_cagr}"
    else:
        verdict = "ambiguous"
        evidence = (
            "C7-turnover-walkforward's metrics report only in_sample_winner='buffer15' and "
            "its out-of-sample rank/PBO -- no raw CAGR comparable to remediation/"
            f"before_after.json's rank_buffer_1_5={remediation['cagr']}. configuration.runs "
            "states '860 usable names', close to but not stated identical to the "
            f"{remediation['universe_size']} pinned there. No exact numeric match exists to "
            "confirm identity, and none exists to rule it out either."
        )
    rows.append({
        "pair": "C7-turnover-walkforward vs round5/6 restated-buffer-1.5",
        "registry_id": "C7-turnover-walkforward",
        "registry_cagr": c7_cagr, "comparison_cagr": remediation["cagr"],
        "verdict": verdict, "evidence": evidence,
    })

    for row in rows:
        if row["verdict"] not in VERDICTS:
            raise AssertionError(f"invalid verdict {row['verdict']!r} for {row['pair']}")
    return rows


# Decision item for explicit human sign-off -- NOT an applied correction. Current evidence:
# C4-turnover-controls is CONFIRMED_DISTINCT from the round5/6 trial (no dedup warranted).
# C7-turnover-walkforward is AMBIGUOUS (no raw CAGR was ever published for it to compare
# against 0.1260/0.1233, so neither duplication nor distinctness can be confirmed from
# committed evidence). Recommendation: leave dsr_trial_count_used=50 unchanged -- there is no
# confirmed duplicate to remove. If C7's raw per-variant CAGR is ever published (e.g. by a
# future re-run that logs it), re-run this check; an exact match to 0.1260 would flip its
# verdict to confirmed_duplicate and would then be grounds to revisit the count, which this
# module still would not do on its own.
RECOMMENDATION = (
    "no correction to dsr_trial_count_used=50: C4 confirmed_distinct, C7 ambiguous, "
    "neither is a confirmed duplicate"
)


def illustrative_deflated_sharpe_at_trial_counts(trial_counts, *, seed=2026_09_01, n=24):
    """Reference-only sensitivity: what deflated_sharpe_ratio would read at each of
    ``trial_counts``, holding a fixed SEEDED SYNTHETIC monthly return series constant. This is
    NOT a measurement of anything real -- no live backtest return series was available to
    condition on (see the R11 pre-merge gate's Stage 2 network-access finding), and no
    confirmed duplicate exists to correct for (see RECOMMENDATION). Its only purpose is to
    show the direction and rough magnitude a trial-count change would move the statistic, for
    whoever eventually signs off on the C7 ambiguity above. Never cite the probabilities this
    returns as a real DSR for the champion or any challenger.
    """
    generator = random.Random(seed)
    returns = [0.012 + generator.gauss(0, 0.03) for _ in range(n)]
    return {
        trials: deflated_sharpe_ratio(returns, trials=trials)["deflated_sharpe"]
        for trials in trial_counts
    }


if __name__ == "__main__":
    for row in check_rank_buffer_variant_identity():
        print(f"{row['pair']}: {row['verdict']}\n  {row['evidence']}")
    print(f"\nRecommendation: {RECOMMENDATION}")

    print("\nIllustrative only (seeded synthetic returns, not a real measurement):")
    illustrative = illustrative_deflated_sharpe_at_trial_counts([41, 50, 57, 59])
    for trials, probability in sorted(illustrative.items()):
        print(f"  trials={trials}: deflated_sharpe_probability={probability:.4f}")
