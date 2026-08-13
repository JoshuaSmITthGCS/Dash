"""Data-coverage decomposition (docs/RESEARCH-CONTRACT.md).

The champion's single scalar (``advisor_engine.data_coverage_scalar``) mixes several
distinct kinds of incompleteness into one number: how much data resolved, how stale it is,
how many peers a company was ranked against, and how much the challenger variants agree
with the champion. Collapsing all of that into one number means a low value cannot be
explained, only observed -- exactly the complaint that motivated this module (see
docs/BASELINE-2026-08-06.md).

**Naming.** Every component here is a completeness or provenance measure. None is a
statistical property of the signal. The scalar and this breakdown were published as
"confidence", which is a claim about reliability that nothing here establishes -- and the
frontend went on to gate position sizing on it. They are named for what they measure.
A real confidence metric, validated against realised prediction error, is Phase 8 work and
does not exist yet. See ``research/audit/CURRENT_MODEL_AUDIT.md`` section 4.

This module is additive: it does not change ``row["data_coverage"]``, the champion formula,
or how coverage feeds the score. It publishes a ``data_coverage_detail`` breakdown alongside
the scalar so *why* coverage is low becomes visible.
"""

import statistics
from datetime import datetime, timezone

from scorer import SETTINGS

CFG = SETTINGS.get("confidence", {})  # config key unchanged; the published field name is not

# Providers that are intentionally not attempted this run (opt-in features, quota-gated
# intraday refreshes, or a secret like SEC_USER_AGENT that was never set) must not drag
# reliability down -- an unconfigured feature is not the same thing as a broken one.
# "unavailable_provider_error" is deliberately absent from this set: that status means the
# provider *was* configured and still failed, which is real evidence of unreliability, not
# an intentional gap, so it must count against source_reliability like "degraded"/"failed".
_NOT_CONFIGURED_STATUSES = {"unavailable", "unavailable_not_configured", "opt_in",
                            "disabled_for_intraday_refresh", "configuration_required"}


def _clamp01(value):
    return max(0.0, min(1.0, value))


def completeness_component(row):
    """Identical to the blend the champion's scalar already computes (see
    advisor_engine.data_coverage_scalar) -- reused, not rewritten, so this component and the
    scalar can never silently disagree.
    """
    fundamentals = (row.get("fundamental_detail") or {}).get("coverage") or 0.0
    technical = (row.get("technical_detail") or {}).get("coverage") or 0.0
    sentiment = (row.get("sentiment_detail") or {}).get("coverage") or 0.0
    return round(0.65 * fundamentals + 0.25 * technical + 0.10 * sentiment, 2)


def freshness_component(row, *, now=None):
    """1.0 at zero age, decaying linearly to 0.0 at twice the stale-after threshold used
    elsewhere in the pipeline (pit_store.freshness_report, data_freshness reporting).
    """
    stale_after = CFG.get("freshness_stale_after_hours", 36)
    stamp = row.get("data_fetched_at")
    if not stamp:
        return None
    try:
        observed = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    age_hours = ((now or datetime.now(timezone.utc)) - observed).total_seconds() / 3600
    if age_hours <= 0:
        return 1.0
    if not stale_after:
        return None
    return round(_clamp01(1 - age_hours / (2 * stale_after)), 2)


def peer_sample_component(row):
    """How close the company's peer group is to the industry full-strength count the
    hierarchical-normalization design in docs/RESEARCH-CONTRACT.md targets (currently 20;
    see pipeline/config/settings.json confidence.peer_sample_full_strength_count).
    """
    percentile = row.get("valuation_percentile") or {}
    peer_count = percentile.get("peer_count_with_valid_data")
    full_strength = CFG.get("peer_sample_full_strength_count", 20)
    if peer_count is None or not full_strength:
        return None
    return round(_clamp01(peer_count / full_strength), 2)


def model_agreement_component(row):
    """1.0 when every scored variant (champion + challengers) agrees; decays as their final
    scores spread apart. The scale is configurable rather than a bare magic number: a spread
    of one full scale unit (confidence.model_agreement_scale_points) floors agreement at 0.
    """
    variants = row.get("score_variants") or {}
    scores = [variant.get("score") for variant in variants.values() if isinstance(variant, dict)]
    scores = [value for value in scores if isinstance(value, (int, float))]
    scale = CFG.get("model_agreement_scale_points", 15.0)
    if len(scores) < 2 or not scale:
        return None
    spread = statistics.pstdev(scores)
    return round(_clamp01(1 - spread / scale), 2)


def run_source_reliability(source_health):
    """Fraction of *configured* providers that resolved healthy this refresh.

    This is a run-wide signal (identical for every row published in the same refresh), not a
    per-ticker one -- there is no per-symbol reliability signal for e.g. the FRED macro
    regime, which is shared across every row. ``source_health`` is a plain
    ``{name: "healthy" | "degraded" | "failed" | <not-configured status>}`` map built once
    per run; unconfigured/opt-in providers are excluded rather than penalized.
    """
    if not source_health:
        return None
    weight = healthy = 0
    for status in source_health.values():
        if status in _NOT_CONFIGURED_STATUSES:
            continue
        weight += 1
        if status == "healthy":
            healthy += 1
        elif status == "degraded":
            healthy += 0.5
    return round(healthy / weight, 2) if weight else None


def historical_calibration_component(row, calibration=None):
    """The score bucket's measured outcome rate, or None while the evidence is absent.

    ``calibration`` is a ``score_calibration.build_report()`` payload. It gates itself: until
    at least one bucket clears the observation minimum, the whole report is
    ``insufficient_data`` and this returns None. That is deliberate and load-bearing -- a
    number here would read as "we know what scores like this have done", and we do not.
    """
    if not calibration or not calibration.get("publishable_to_confidence_detail"):
        return None
    score = row.get("score")
    if not isinstance(score, (int, float)):
        return None
    for bucket in calibration.get("fixed_score_bands", []):
        if bucket.get("status") != "measured":
            continue
        label = bucket["bucket"]
        low = float(label.rstrip("+").split("-")[0])
        high = 101.0 if label.endswith("+") else float(label.split("-")[1]) + 1
        if low <= score < high:
            return round(_clamp01(bucket["beat_sector_rate"]), 2)
    return None


def data_coverage_components(row, *, source_reliability=None, now=None, calibration=None):
    """Full data-coverage breakdown for one published row:
      {"data_coverage": <scalar>, "components": {...}, "limitations": [...]}

    ``data_coverage`` is exactly ``row["data_coverage"]`` -- the share of the evidence this
    model intended to use that actually resolved. It is not a probability that the stock
    rises, and it is not a measure of how reliable the rank is.

    ``historical_calibration`` stays null until the IC harness has enough prospective periods.
    Pass ``calibration`` (a ``score_calibration.build_report()`` payload) to populate it once
    that gate is met; the report gates itself, so passing an unqualified one changes nothing.
    """
    calibration_minimum = CFG.get("historical_calibration_minimum_periods", 24)
    components = {
        "completeness": completeness_component(row),
        "freshness": freshness_component(row, now=now),
        "source_reliability": source_reliability,
        "peer_sample": peer_sample_component(row),
        "model_agreement": model_agreement_component(row),
        "historical_calibration": historical_calibration_component(row, calibration),
    }
    limitations = []
    if components["historical_calibration"] is None:
        limitations.append(
            f"insufficient prospective calibration history (requires {calibration_minimum} "
            "eligible IC periods)")
    for name, value in components.items():
        if value is None and name != "historical_calibration":
            limitations.append(f"{name} unavailable for this row")
    return {
        "data_coverage": row.get("data_coverage"),
        "components": components,
        "limitations": limitations,
        "interpretation": ("data coverage measures how much of the intended evidence resolved. "
                           "It is not a reliability score and not a probability that the stock "
                           "rises. No validated confidence metric exists yet."),
    }
