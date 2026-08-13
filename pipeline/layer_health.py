"""Weight renormalization and the constant-layer guard.

Two mechanisms, both general, both replacing per-site ad-hoc handling.

**Renormalization.** When an input to a weighted layer has no value, its weight is
redistributed proportionally across the inputs that *do* have a value for that row. It is
never replaced by a neutral. The distinction matters: imputing 50 for a missing input asserts
"we looked and it was average", which is a claim about the world nobody made. Redistributing
its weight asserts "we scored this on what we had", which is true. ``renormalize`` also
returns a record of what it dropped, so a consumer can tell a fully-evidenced score from one
computed on a third of its intended weight -- previously indistinguishable in the payload.

**The constant-layer guard.** A layer whose value is identical for every company in the
universe carries zero information and must not be published as evidence. The
``timeliness`` layer resolved to exactly ``effective_score 50.0, confidence 0.0, coverage 0``
for 40 of 40 published names, and the shadow policy's two-axis matrix branched on that
constant -- ``buy_candidate`` was mathematically unreachable, and every company in the
universe resolved to ``insufficient_evidence``. ``assert_layers_vary`` turns that class of
defect into a build failure instead of a year of published output. See
``research/audit/CURRENT_MODEL_AUDIT.md`` sections 3 and 7.
"""

import statistics

# Below this many resolved observations a layer is too sparse for zero variance to be
# evidence of anything -- three companies legitimately sharing a score is not a defect.
DEFAULT_MINIMUM_ROWS = 30

# Values within this distance of each other count as identical. Layers are published rounded
# to one decimal, so anything under half a display unit is indistinguishable to a reader.
DEFAULT_TOLERANCE = 1e-9


class ConstantLayerError(ValueError):
    """A published layer has no cross-sectional variance across the universe."""


def renormalize(contributions):
    """Weighted mean over resolved inputs, with the redistribution recorded.

    ``contributions`` maps an input name to ``(value_or_None, declared_weight)``. Returns
    ``(score_or_None, record)``. The score is ``None`` when nothing resolved -- callers must
    publish nothing rather than substitute a neutral.

    ``record`` carries the declared weights, the effective weights after redistribution, the
    names dropped, and ``covered_weight_fraction``: the share of declared weight that was
    actually answered. That last number is the honest version of "coverage" -- it is what the
    score was computed from, not what a sector exemption removed from the denominator.
    """
    declared = {name: float(weight) for name, (_, weight) in contributions.items()}
    resolved = {name: (float(value), float(weight))
                for name, (value, weight) in contributions.items() if value is not None}
    declared_total = sum(declared.values())
    answered_total = sum(weight for _, weight in resolved.values())
    dropped = sorted(set(declared) - set(resolved))
    record = {
        "weights_declared": {name: round(weight, 6) for name, weight in declared.items()},
        "weights_effective": {},
        "inputs_dropped": dropped,
        "inputs_resolved": sorted(resolved),
        "covered_weight_fraction": round(answered_total / declared_total, 4) if declared_total else 0.0,
        "redistributed_weight": round(declared_total - answered_total, 6),
    }
    if not resolved or not answered_total:
        return None, record
    record["weights_effective"] = {name: round(weight / answered_total, 6)
                                   for name, (_, weight) in resolved.items()}
    score = sum(value * weight for value, weight in resolved.values()) / answered_total
    return score, record


def layer_variance(values, *, tolerance=DEFAULT_TOLERANCE):
    """Population standard deviation of the resolved values, or ``None`` if fewer than two."""
    numeric = [float(value) for value in values
               if isinstance(value, (int, float)) and not isinstance(value, bool)]
    if len(numeric) < 2:
        return None
    spread = statistics.pstdev(numeric)
    return 0.0 if spread <= tolerance else spread


def constant_layers(rows, layers, *, minimum_rows=DEFAULT_MINIMUM_ROWS,
                    tolerance=DEFAULT_TOLERANCE):
    """Names of layers that resolved widely and still have zero cross-sectional variance.

    ``layers`` maps a layer name to a callable taking one published row and returning the
    number that layer contributes, or ``None`` when the layer did not resolve for that row.
    A layer resolving on fewer than ``minimum_rows`` rows is reported as sparse rather than
    constant, because zero variance over a handful of names is not evidence of a defect.
    """
    offenders = []
    for name, extractor in layers.items():
        values = []
        for row in rows:
            try:
                value = extractor(row)
            except (AttributeError, KeyError, TypeError):
                value = None
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.append(float(value))
        if len(values) < minimum_rows:
            continue
        if layer_variance(values, tolerance=tolerance) == 0.0:
            offenders.append((name, len(values), values[0]))
    return offenders


def assert_layers_vary(rows, layers, *, minimum_rows=DEFAULT_MINIMUM_ROWS,
                       tolerance=DEFAULT_TOLERANCE):
    """Raise ``ConstantLayerError`` if any layer is a constant across the universe.

    Called from the publish path so a degenerate layer fails the run rather than shipping.
    """
    offenders = constant_layers(rows, layers, minimum_rows=minimum_rows, tolerance=tolerance)
    if not offenders:
        return
    detail = "; ".join(
        f"{name} resolved to {value!r} on all {count} rows" for name, count, value in offenders)
    raise ConstantLayerError(
        "a published layer has zero cross-sectional variance and is therefore not a layer: "
        f"{detail}. Publish nothing for it rather than a constant."
    )
