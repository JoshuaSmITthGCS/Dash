"""Fail-loud plausibility screening for provider values before they reach the model.

Phase 2.4. The pipeline accepted whatever a provider returned. Two consequences were visible
in the published dataset: THG carried an incremental margin of 89.9% and NEM one of 128.2%,
neither flagged anywhere, both arithmetically impossible as a steady state and both produced
by a tiny revenue denominator rather than by operating leverage. Nothing downstream could
tell those apart from a real reading.

Three principles, in order of importance:

1. **A suspicious observation does not quietly enter the scoring model.** A violation drops
   the field. Publishing nothing for a metric is always available; publishing a number the
   pipeline has reason to disbelieve is not.
2. **Every drop is recorded, with the rule that fired and the value that fired it.** A silent
   drop is the same defect as a silent default, one layer up.
3. **Rules encode arithmetic and accounting impossibilities, not opinions about companies.**
   A margin above 100% is impossible. A P/E of 3 is merely unusual, and this module has no
   business touching it.

Unit errors get their own rules because they are the failure that looks most like data:
thousands reported as millions, a percentage where a decimal was expected, an unadjusted
price against a split-adjusted share count. Each produces a value that is wrong by orders of
magnitude while remaining a perfectly ordinary-looking float.
"""

# Ratios expressed as decimals where 1.0 means 100%. A margin cannot exceed one, and a value
# far above one is almost always a percentage that was never divided by 100.
DECIMAL_RATIO_FIELDS = ("profit_margin", "gross_margin", "operating_margin")

# Cross-provider agreement tolerances, as a fraction of the reference value.
MARKET_CAP_TOLERANCE = 0.20
PRICE_TOLERANCE = 0.05
SHARES_IMPLIED_TOLERANCE = 0.20

# A margin change divided by a near-zero revenue change explodes. Below this revenue delta,
# relative to the prior period, incremental margin carries no information.
MINIMUM_INCREMENTAL_REVENUE_FRACTION = 0.02


def _numeric(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return float(value)


def _violation(field, value, rule, detail):
    return {"field": field, "value": value, "rule": rule, "detail": detail}


def field_violations(snapshot):
    """Every implausible field in one snapshot, as records naming the rule that fired.

    Pure and side-effect free so the rules can be tested directly against the values that
    motivated them.
    """
    snapshot = snapshot or {}
    found = []

    def check(field, predicate, rule, detail):
        value = _numeric(snapshot.get(field))
        if value is not None and predicate(value):
            found.append(_violation(field, value, rule, detail))

    # --- arithmetic impossibilities -------------------------------------------------
    for field in DECIMAL_RATIO_FIELDS:
        check(field, lambda value: value > 1.0, "margin_above_100_percent",
              "a margin cannot exceed 100% of revenue; a value far above 1.0 is usually a "
              "percentage that was never converted to a decimal")
        check(field, lambda value: value < -10.0, "margin_below_negative_1000_percent",
              "losses beyond ten times revenue indicate a denominator error, not a business")

    check("return_on_invested_capital", lambda value: abs(value) > 2.0, "roic_above_200_percent",
          "invested capital near zero produces an unbounded ratio rather than a real return")
    check("return_on_equity", lambda value: abs(value) > 5.0, "roe_above_500_percent",
          "book equity near zero or negative produces an unbounded ratio")
    check("accruals_ratio", lambda value: abs(value) > 1.0, "accruals_exceed_total_assets",
          "accruals scaled by assets cannot exceed the asset base")
    check("piotroski_f", lambda value: not 0 <= value <= 9, "piotroski_outside_0_9",
          "the F-score is nine binary tests")
    check("current_ratio", lambda value: value < 0, "negative_current_ratio",
          "current assets and liabilities are both non-negative")
    check("shares_outstanding", lambda value: value <= 0, "non_positive_share_count",
          "a listed company has a positive share count")

    # --- metric-definition violations ------------------------------------------------
    # forward_pe is scored by multiple_score, which treats <= 0 as a distress signal. A
    # negative forward P/E means the provider divided by a negative forward EPS, which the
    # metric definition excludes -- it is not a cheap stock.
    check("forward_pe", lambda value: value < 0, "negative_forward_pe",
          "the forward P/E metric excludes negative forward earnings; a negative value is a "
          "provider artefact, not a valuation")

    # Yahoo's dividendYield field has a documented history of switching between a decimal
    # fraction (0.031) and an already-multiplied percentage number (3.1) depending on which
    # underlying endpoint served the quote. rank_picks.py hard-codes the decimal convention
    # (`dy > 0.03`), so a percentage-shaped value would silently satisfy every yield threshold
    # in that comparison rather than erroring. No real, sustained dividend yield reaches 50%.
    check("dividend_yield", lambda value: value > 0.5, "dividend_yield_likely_percentage_not_decimal",
          "a dividend yield above 50% is virtually always a percentage number (e.g. 3.1) that "
          "was never converted to a decimal fraction (0.031), not a real sustained yield")
    check("dividend_yield", lambda value: value < 0, "negative_dividend_yield",
          "a dividend yield cannot be negative")

    # --- unit errors -----------------------------------------------------------------
    # A US-listed company with a market capitalisation under $100k is a units error
    # (thousands or millions reported as units), not a nano-cap.
    check("market_cap", lambda value: 0 < value < 1e5, "market_cap_implausibly_small",
          "a market capitalisation this small indicates a thousands/millions unit error")
    check("market_cap", lambda value: value < 0, "negative_market_cap",
          "market capitalisation is price times shares and cannot be negative")

    # --- cycle and denominator contamination -----------------------------------------
    incremental = _numeric(snapshot.get("incremental_margin"))
    if incremental is not None and abs(incremental) > 1.0:
        found.append(_violation(
            "incremental_margin", incremental, "incremental_margin_outside_unit_interval",
            "incremental margin is the share of an incremental revenue dollar that reaches "
            "operating profit; above 1.0 it is a near-zero revenue denominator, not operating "
            "leverage. THG published 89.9% and NEM 128.2%."))

    revenue, prior_revenue = _numeric(snapshot.get("revenue")), _numeric(snapshot.get("prior_revenue"))
    if incremental is not None and revenue is not None and prior_revenue:
        change = abs(revenue - prior_revenue) / abs(prior_revenue)
        if change < MINIMUM_INCREMENTAL_REVENUE_FRACTION:
            found.append(_violation(
                "incremental_margin", incremental, "incremental_margin_denominator_too_small",
                f"revenue moved {change * 100:.2f}%, below the "
                f"{MINIMUM_INCREMENTAL_REVENUE_FRACTION * 100:.0f}% floor this ratio needs to "
                "carry information"))

    return found


def cross_source_violations(values_by_source, *, field, tolerance):
    """Disagreement beyond tolerance between providers reporting the same field.

    ``values_by_source`` maps a source name to its value. The first source in iteration
    order is the reference, matching provider_reconciliation.json's precedence-not-average
    policy. Returns records; it never picks a winner, because a 30% market-cap disagreement
    means neither value is trustworthy.
    """
    numeric = {source: _numeric(value) for source, value in (values_by_source or {}).items()}
    numeric = {source: value for source, value in numeric.items() if value is not None}
    if len(numeric) < 2:
        return []
    sources = list(numeric)
    reference_source = sources[0]
    reference = numeric[reference_source]
    if not reference:
        return []
    found = []
    for source in sources[1:]:
        drift = abs(numeric[source] - reference) / abs(reference)
        if drift > tolerance:
            found.append(_violation(
                field, numeric[source], f"{field}_provider_disagreement",
                f"{source} reports {numeric[source]:.6g} against {reference_source}'s "
                f"{reference:.6g}, a {drift * 100:.1f}% gap over a "
                f"{tolerance * 100:.0f}% tolerance"))
    return found


def implied_share_count_violations(snapshot):
    """Market capitalisation that does not reconcile with price times share count.

    Catches a split-adjusted price paired with an unadjusted share count, and the reverse.
    Both leave every individual field looking ordinary.
    """
    price = _numeric((snapshot or {}).get("price"))
    market_cap = _numeric((snapshot or {}).get("market_cap"))
    shares = _numeric((snapshot or {}).get("shares_outstanding"))
    if not price or not market_cap or not shares or price <= 0 or shares <= 0:
        return []
    implied = price * shares
    drift = abs(implied - market_cap) / abs(market_cap) if market_cap else 0.0
    if drift <= SHARES_IMPLIED_TOLERANCE:
        return []
    return [_violation(
        "market_cap", market_cap, "market_cap_inconsistent_with_price_times_shares",
        f"price x shares implies {implied:.6g} against a reported {market_cap:.6g}, a "
        f"{drift * 100:.1f}% gap -- typically an unadjusted price against a split-adjusted "
        "share count, or the reverse")]


def screen(snapshot, *, cross_source=None):
    """Return ``(screened_snapshot, violations)`` with every implausible field removed.

    ``cross_source`` optionally maps a field name to ``{source: value}`` for the two fields
    with a defined cross-provider tolerance (``market_cap``, ``price``).

    The screened snapshot carries ``data_quality_violations`` so a consumer can see what was
    dropped and why. Removing the field rather than correcting it is deliberate: this module
    can tell that a number is wrong, never what the right number was.
    """
    snapshot = dict(snapshot or {})
    violations = [*field_violations(snapshot), *implied_share_count_violations(snapshot)]
    tolerances = {"market_cap": MARKET_CAP_TOLERANCE, "price": PRICE_TOLERANCE}
    for field, values in (cross_source or {}).items():
        violations.extend(cross_source_violations(
            values, field=field, tolerance=tolerances.get(field, MARKET_CAP_TOLERANCE)))
    for violation in violations:
        snapshot[violation["field"]] = None
    if violations:
        snapshot["data_quality_violations"] = violations
    return snapshot, violations
