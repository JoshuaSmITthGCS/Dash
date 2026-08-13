"""Which companies can never receive a peer claim, and why that is not a bug to patch.

``peer_groups.MINIMUM_VALID_PEERS`` is 30, set in Phase 1 after the published dataset claimed
THG was "cheaper than ~85% of P&C insurers, based on 14 valid peers" -- a percentile whose
resolution was 7.7 points, over a band composite that was not a valuation ordering. The gate
is right.

What the gate exposes is a grouping problem underneath it. ``peer_group`` returns a business
profile where the registry assigns one and falls back to the sector otherwise, and in an
874-name universe the seventeen profile groups average four members against sector groups of
88 to 150. So a company the registry classifies *precisely* -- a medical device maker, a
property & casualty insurer, a commodity producer -- lands in a group that cannot reach thirty
and never carries a peer claim, while a company the registry leaves unclassified falls into a
broad sector bucket and always does. Being described accurately costs you the comparison.

**The obvious fix is wrong, and this module exists partly to record why.** Widening an
undersized profile group to its sector restores a claim for those companies and restores the
wrong one: an insurer ranked against banks, exchanges, payment networks and asset managers is
the universal-multiple error the profiles were introduced to prevent, and financials are where
that error is largest. Phase 1's regression tests reject the change, correctly. A degraded
estimate still reads as a measurement.

So the gap is real, unfixable by grouping, and worth *measuring* rather than patching: it is a
statement about universe size. Thirty comparable medical device companies is a data
requirement, not a code change. This reports which groups are short and by how much, so the
decision to expand the universe can be made against a number.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

from peer_groups import MINIMUM_VALID_PEERS, peer_group  # noqa: E402


def coverage(rows, *, minimum=MINIMUM_VALID_PEERS):
    """Per peer group: members, and whether the group can ever support a claim."""
    groups = {}
    for row in rows:
        group_id, label = peer_group(row)
        entry = groups.setdefault(group_id, {"label": label, "members": 0, "tickers": []})
        entry["members"] += 1
        entry["tickers"].append(row.get("ticker"))

    reachable, unreachable = [], []
    for group_id, entry in groups.items():
        record = {"group": entry["label"], "group_id": group_id, "members": entry["members"],
                  "short_by": max(0, minimum - entry["members"]),
                  "examples": sorted(entry["tickers"])[:6]}
        (reachable if entry["members"] >= minimum else unreachable).append(record)
    reachable.sort(key=lambda record: -record["members"])
    unreachable.sort(key=lambda record: -record["members"])

    stranded = sum(record["members"] for record in unreachable)
    return {
        "minimum_valid_peers": minimum,
        "universe": len(rows),
        "groups": len(groups),
        "groups_that_can_publish": len(reachable),
        "groups_that_cannot": len(unreachable),
        "companies_permanently_unrankable": stranded,
        "share_permanently_unrankable": round(stranded / len(rows), 4) if rows else None,
        "reachable": reachable,
        "unreachable": unreachable,
        "note": (
            "A group below the minimum is a universe-size problem, not a code defect. Widening "
            "it to the sector would restore a claim and make it wrong -- an insurer ranked "
            "against banks and payment networks is the universal-multiple error the profiles "
            "exist to prevent, and Phase 1's regression tests reject that change. The honest "
            "options are to enlarge the universe until these groups reach thirty, or to accept "
            "that these companies carry no peer claim and say so where one would appear."),
    }


def main(argv=None):
    path = (argv or sys.argv[1:] or [os.path.join(ROOT, "public", "data", "advisor.json")])[0]
    with open(path, encoding="utf-8") as handle:
        artifact = json.load(handle)
    rows = [row for row in (artifact.get("research") or []) + (artifact.get("screen_universe") or [])
            if not row.get("is_etf")]
    print(json.dumps(coverage(rows), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
