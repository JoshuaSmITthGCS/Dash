"""Reproducible peer rankings, reported at a resolution the sample can support.

What this ranks, precisely: the model's own ``fundamental_categories.valuation`` composite --
a weighted average of discrete band scores -- not a price multiple. Calling that "cheaper
than X% of peers" was wrong twice over, and the published dataset showed both failures inside
a single peer group of six visible names:

  * **The claim was not a valuation ordering.** THG (2.18x book, 2.48x tangible book) was
    published as cheaper than SIGI (1.66x book, 1.60x tangible book). The band for
    price-to-tangible-book scores everything from 1.5x to 3.0x identically, so a 55% gap in
    the canonical insurer valuation metric is invisible to the composite being ranked.
  * **The gap between them was decided by the alphabet.** Both scored exactly 95.7. The old
    ``sorted(key=(value, ticker))`` gave tied names adjacent ranks, so THG landed one rank
    above SIGI and the two were published 7.7 percentile points apart. Ties now share an
    averaged rank and therefore share a tier.

Two rules follow, and this module enforces both:

  1. **n >= 30 or nothing.** Below that, ``peer_context`` is ``None`` with a reason code. A
     14-name group cannot support a percentile at all -- its resolution is 100/13 = 7.7
     points -- and a degraded estimate is worse than an absent one because it still reads as
     a measurement.
  2. **Tiers, never a two-significant-figure percentage.** Cheapest third / middle third /
     most expensive third is what a rank over a few dozen noisy composite scores actually
     supports. ``n`` is always published alongside.

See ``research/audit/CURRENT_MODEL_AUDIT.md`` section 2.
"""

import statistics
from datetime import date

from canonical_metrics import BUSINESS_PROFILES, classify_profile

# Below this, no peer-relative claim is published at all. Chosen so the coarsest tier
# boundary (a third) is resolved by at least ten observations rather than by two or three.
MINIMUM_VALID_PEERS = 30

TIER_LABELS = {
    "cheapest_third": "in the cheapest third of",
    "middle_third": "in the middle third of",
    "most_expensive_third": "in the most expensive third of",
}

# The ordinal handed to downstream ranking models in place of the old spurious percentile.
# A tier midpoint says "we know which third, and no more", which is the truth. Anything
# finer would reintroduce precision the sample cannot carry.
TIER_MIDPOINTS = {"most_expensive_third": 16.7, "middle_third": 50.0, "cheapest_third": 83.3}


def _sector_fallback_group(snapshot):
    sector = snapshot.get("sector") or "Unclassified"
    return f"sector:{sector.lower().replace(' ', '_')}", sector


# The seven profiles the THG audit (see module docstring) was built around: coarse enough that
# each already approximates a whole GICS sector's worth of comparably-valued names, and the
# reason a below-minimum group here must stay silent rather than roll up -- broadening a P&C
# insurer's peer set to "all Financial Services" mixes it with banks and asset managers, which
# is the exact category error this module exists to prevent. Every other profile
# classify_profile() returns is a narrower sub-industry split added for metric-applicability
# precision, never a deliberate peer-comparison design choice, so those are free to roll up to
# their sector when their own sample can't carry a claim (below).
LEGACY_PEER_COMPARISON_PROFILES = frozenset({
    "bank", "property_casualty_insurer", "life_insurer", "diversified_insurer",
    "reit", "utility", "commodity_producer",
})


def peer_group(snapshot):
    override = BUSINESS_PROFILES.get("ticker_overrides", {}).get(str(snapshot.get("ticker") or "").upper(), {})
    if override.get("peer_group_id"):
        return override["peer_group_id"], override["peer_group_label"]
    profile = classify_profile(snapshot)
    labels = {
        "bank": "Banks",
        "property_casualty_insurer": "Property & casualty insurers",
        "life_insurer": "Life insurers",
        "diversified_insurer": "Diversified insurers",
        "reit": "REITs",
        "utility": "Utilities",
        "commodity_producer": "Commodity producers",
    }
    if profile != "general":
        return profile, labels.get(profile, profile.replace("_", " ").title())
    return _sector_fallback_group(snapshot)


def _tier_for(rank_fraction):
    """Map an averaged rank fraction in [0, 1] (higher = better score) to a tier."""
    if rank_fraction >= 2 / 3:
        return "cheapest_third"
    if rank_fraction <= 1 / 3:
        return "most_expensive_third"
    return "middle_third"


def _averaged_rank_fractions(ordered_values):
    """Rank fraction per position, with tied values sharing one averaged rank.

    Tied names must land in the same tier. Giving them adjacent ranks is what let an
    alphabetical ordering become a published valuation difference.
    """
    count = len(ordered_values)
    fractions = []
    index = 0
    while index < count:
        end = index
        while end + 1 < count and ordered_values[end + 1] == ordered_values[index]:
            end += 1
        average_rank = (index + end) / 2
        fraction = 0.5 if count == 1 else average_rank / (count - 1)
        fractions.extend([fraction] * (end - index + 1))
        index = end + 1
    return fractions


def canonical_percentiles(rows, key="valuation", constructed_at=None, minimum=MINIMUM_VALID_PEERS):
    """Peer context per ticker, or an explicit null with a reason code.

    Returns ``{ticker: metadata}``. ``metadata["peer_context"]`` is ``None`` whenever the
    group cannot support a claim; ``metadata["peer_count_with_valid_data"]`` is always
    populated so a consumer can see how thin the sample was.
    """
    constructed_at = constructed_at or date.today().isoformat()

    def build_groups(group_of):
        built = {}
        for row in rows:
            group_id, label = group_of(row)
            value = (row.get("categories") or {}).get(key)
            built.setdefault(group_id, {"label": label, "total": 0, "valid": []})["total"] += 1
            if isinstance(value, (int, float)):
                built[group_id]["valid"].append((row["ticker"], float(value)))
        return built

    groups = build_groups(peer_group)

    # A profile-specific peer group too thin to support a tier claim rolls up into the
    # broader sector bucket instead of publishing nothing for every member -- the same
    # fallback already used for the generic "general" profile, applied once more when a
    # narrower profile's own sample can't carry a claim. classify_profile()'s finer
    # distinctions still govern which *metrics* apply to each name; this only changes the
    # population a valuation percentile is measured against.
    thin_profile_groups = {group_id for group_id, group in groups.items()
                           if len(group["valid"]) < minimum and not group_id.startswith("sector:")
                           and group_id not in LEGACY_PEER_COMPARISON_PROFILES}
    if thin_profile_groups:
        def group_of(row):
            group_id, label = peer_group(row)
            return _sector_fallback_group(row) if group_id in thin_profile_groups else (group_id, label)
        groups = build_groups(group_of)

    result = {}
    for group_id, group in groups.items():
        ordered = sorted(group["valid"], key=lambda item: (item[1], item[0]))
        if len(ordered) < minimum:
            for ticker, value in ordered:
                result[ticker] = _metadata(group_id, group, value, None, constructed_at,
                                           minimum, "insufficient_valid_peers", ordered)
            continue
        fractions = _averaged_rank_fractions([value for _, value in ordered])
        for position, (ticker, value) in enumerate(ordered):
            result[ticker] = _metadata(group_id, group, value, _tier_for(fractions[position]),
                                       constructed_at, minimum, None, ordered)
    return result


def peer_group_multiple_medians(rows, multiple_key="ev_to_ebitda", minimum=MINIMUM_VALID_PEERS):
    """The peer group's own median raw multiple, published beside (never instead of)
    canonical_percentiles' structural-valuation tier.

    Deliberately narrower than a per-company percentile against this multiple. This module's
    own docstring documents why: the THG/SIGI incident, two peers 55% apart on
    price-to-tangible-book, both scoring 95.7 on the composite this module actually ranks, an
    alphabetical tiebreak turning that near-tie into a published 7.7-point difference. Ranking
    individual companies against each other on a raw multiple at finer resolution than "the
    group's median is N" would reintroduce exactly that failure mode. A single descriptive
    median, gated by the same ``n >= minimum`` floor canonical_percentiles enforces, gives a
    reader who wants a concrete number one -- without implying the model ranks individual
    names by it, and without publishing a percentile this sample cannot support.

    Returns ``{ticker: {"peer_group_median_multiple": value_or_None, "peer_group_multiple_key":
    multiple_key, "peer_group_multiple_sample_count": n}}`` for every ticker in ``rows``.
    Tickers whose own group falls below ``minimum`` still appear, with a null median and their
    group's actual sample count, matching canonical_percentiles' "absent is better than
    degraded" stance for a below-floor group -- see MINIMUM_VALID_PEERS.
    """
    groups = {}
    for row in rows:
        group_id, _ = peer_group(row)
        value = row.get(multiple_key)
        groups.setdefault(group_id, {"tickers": [], "values": []})
        groups[group_id]["tickers"].append(row.get("ticker"))
        if isinstance(value, (int, float)):
            groups[group_id]["values"].append(value)

    # Same thin-group sector rollup canonical_percentiles applies: a profile-specific peer
    # group too thin to support a median rolls up into the broader sector bucket rather than
    # publishing nothing for every member, unless it is one of the deliberate peer-comparison
    # profiles that must stay silent instead (see LEGACY_PEER_COMPARISON_PROFILES).
    thin_profile_groups = {group_id for group_id, group in groups.items()
                           if len(group["values"]) < minimum and not group_id.startswith("sector:")
                           and group_id not in LEGACY_PEER_COMPARISON_PROFILES}
    if thin_profile_groups:
        groups = {}
        for row in rows:
            group_id, _ = peer_group(row)
            if group_id in thin_profile_groups:
                group_id, _ = _sector_fallback_group(row)
            value = row.get(multiple_key)
            groups.setdefault(group_id, {"tickers": [], "values": []})
            groups[group_id]["tickers"].append(row.get("ticker"))
            if isinstance(value, (int, float)):
                groups[group_id]["values"].append(value)

    medians = {}
    for group in groups.values():
        sample_count = len(group["values"])
        median = round(statistics.median(group["values"]), 2) if sample_count >= minimum else None
        for ticker in group["tickers"]:
            medians[ticker] = {
                "peer_group_median_multiple": median,
                "peer_group_multiple_key": multiple_key,
                "peer_group_multiple_sample_count": sample_count,
            }
    return medians


def _metadata(group_id, group, value, tier, constructed_at, minimum, invalid_reason, ordered):
    valid_count = len(ordered)
    tier_counts = None
    if tier is not None:
        fractions = _averaged_rank_fractions([score for _, score in ordered])
        tier_counts = {name: sum(1 for fraction in fractions if _tier_for(fraction) == name)
                       for name in TIER_LABELS}
    return {
        # No `value` and no `display_value`. A continuous percentile over a composite of
        # discrete band scores was never a supportable number, and publishing one invited
        # every consumer to format it to two significant figures.
        "peer_context": None if tier is None else {
            "tier": tier,
            "tier_phrase": TIER_LABELS[tier],
            "tier_count": tier_counts[tier],
            "peer_count_with_valid_data": valid_count,
            "ranked_quantity": "structural_valuation_score",
            "ranked_quantity_note": (
                "A weighted average of discrete valuation band scores, not a price multiple. "
                "Two companies whose multiples differ materially can share a band and "
                "therefore a tier."
            ),
        },
        "tier": tier,
        "ordinal": None if tier is None else TIER_MIDPOINTS[tier],
        "peer_group_id": group_id,
        "peer_group_label": group["label"],
        "peer_count_total": group["total"],
        "peer_count_with_valid_data": valid_count,
        "minimum_peer_count": minimum,
        "constructed_at": constructed_at,
        "metric_count": 1,
        "metric_id": "structural_valuation_score",
        "underlying_value": value,
        "direction": "higher_is_cheaper",
        "winsorization_method": "none",
        "percentile_method": "averaged_rank_tiers",
        "missing_value_treatment": "exclude",
        "invalid_reason": invalid_reason,
        "bottom_peers": [{"ticker": ticker, "value": score} for ticker, score in ordered[:3]],
        "top_peers": [{"ticker": ticker, "value": score} for ticker, score in ordered[-3:][::-1]],
    }
