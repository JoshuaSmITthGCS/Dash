"""Sleeve interface (docs/RESEARCH-CONTRACT.md, brief section 5).

A sleeve wraps one independently testable alpha idea (value, quality, momentum, ...) behind
one return shape, so a challenger sleeve can be swapped in without any other sleeve or the
composite layer needing to know. This module is the interface only -- it defines the shape
and a constructor that fills in the parts every sleeve shares (config hash, timestamp,
default empty containers). Individual sleeves live in sibling modules
(pipeline/sleeves/value.py, ...) and wrap *existing* scoring code rather than reimplementing
it; see each sleeve module's docstring for what it wraps.

As of this contract, only the value sleeve is implemented (pipeline/sleeves/value.py), as a
worked example proving the wrapping pattern. The other 13 sleeves the research contract
specifies (quality, momentum, short/long reversal, mean reversion, growth, GARP, catalyst,
dividend, low-volatility, trend, insider/political, multi-factor) are not yet built --
research_only by construction, since an unbuilt sleeve cannot be anything else.
"""

from datetime import datetime, timezone

from common import config_hash as _config_hash


def empty_sleeve(sleeve_id, version, target_horizon_days, as_of=None):
    """The shared skeleton every sleeve result starts from, matching the research contract's
    sleeve schema exactly. Sleeve implementations fill in raw_features, normalized_features,
    subscores, raw_score, confidence, eligibility, warnings, and explanation; as_of and
    config_hash are set here so no sleeve can forget them (docs/RESEARCH-CONTRACT.md requires
    every research row to carry a model version and config hash).
    """
    return {
        "sleeve_id": sleeve_id,
        "version": version,
        "target_horizon_days": target_horizon_days,
        "raw_features": {},
        "normalized_features": {},
        "subscores": {},
        "raw_score": None,
        "confidence": None,
        "eligibility": {"eligible": True, "reasons": []},
        "warnings": [],
        "explanation": [],
        "as_of": as_of or datetime.now(timezone.utc).isoformat(),
        "config_hash": _config_hash(),
    }


def ineligible_sleeve(sleeve_id, version, target_horizon_days, reasons, as_of=None):
    """A sleeve result for a security this sleeve cannot score at all (e.g. an ETF hitting a
    stock sleeve -- reason code unsupported_security_type). Still a complete, schema-valid
    result, not an exception or a silently-dropped row: the research contract requires every
    sleeve to say *why* a security didn't qualify, not just that it's absent.
    """
    result = empty_sleeve(sleeve_id, version, target_horizon_days, as_of)
    result["eligibility"] = {"eligible": False, "reasons": list(reasons)}
    return result
