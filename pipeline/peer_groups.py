"""Reproducible, metadata-rich peer rankings."""

from datetime import date

from canonical_metrics import BUSINESS_PROFILES, classify_profile

MIN_VALID_PEERS = 4


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
    sector = snapshot.get("sector") or "Unclassified"
    return f"sector:{sector.lower().replace(' ', '_')}", sector


def canonical_percentiles(rows, key="valuation", constructed_at=None, minimum=MIN_VALID_PEERS):
    constructed_at = constructed_at or date.today().isoformat()
    groups = {}
    for row in rows:
        group_id, label = peer_group(row)
        value = (row.get("categories") or {}).get(key)
        groups.setdefault(group_id, {"label": label, "total": 0, "valid": []})["total"] += 1
        if isinstance(value, (int, float)):
            groups[group_id]["valid"].append((row["ticker"], float(value)))
    result = {}
    for group_id, group in groups.items():
        ordered = sorted(group["valid"], key=lambda item: (item[1], item[0]))
        if len(ordered) < minimum:
            for ticker, value in ordered:
                result[ticker] = _metadata(group_id, group, value, None, constructed_at, minimum,
                                           "insufficient_valid_peers", ordered)
            continue
        for rank, (ticker, value) in enumerate(ordered):
            percentile = 100 * rank / (len(ordered) - 1)
            result[ticker] = _metadata(group_id, group, value, round(percentile, 1), constructed_at,
                                       minimum, None, ordered)
    return result


def _metadata(group_id, group, value, percentile, constructed_at, minimum, invalid_reason, ordered):
    display = None if percentile is None else min(percentile, 99.0)
    confidence = 0 if percentile is None else min(1.0, len(ordered) / 20)
    return {
        "value": percentile,
        "display_value": display,
        "peer_group_id": group_id,
        "peer_group_label": group["label"],
        "peer_count_total": group["total"],
        "peer_count_with_valid_data": len(ordered),
        "constructed_at": constructed_at,
        "metric_count": 1,
        "metric_id": "structural_valuation_score",
        "underlying_value": value,
        "direction": "higher_is_cheaper",
        "winsorization_method": "none",
        "percentile_method": "inclusive_rank",
        "missing_value_treatment": "exclude",
        "minimum_peer_count": minimum,
        "confidence": round(confidence, 2),
        "invalid_reason": invalid_reason,
        "bottom_peers": [{"ticker": ticker, "value": score} for ticker, score in ordered[:3]],
        "top_peers": [{"ticker": ticker, "value": score} for ticker, score in ordered[-3:][::-1]],
    }
