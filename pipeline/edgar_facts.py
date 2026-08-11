"""SEC XBRL company facts as point-in-time observations (Phase 2.2).

The one thing that makes this file worth having: **every observation is stamped with the
date the filing was actually accepted, not the date the fiscal period ended.** A 10-Q for the
quarter ending June 30 is typically filed in early August. Any backtest that lets a strategy
see that quarter's numbers on July 1 is trading on information nobody had, and will report a
performance it could never have earned. ``pipeline/backtest_historical.py`` currently
approximates this with a fixed ``report_lag_days`` applied to period ends; ``filed`` is the
real number and it varies by weeks between filers.

Two further properties the restated-fundamentals sources cannot offer:

* **Restatements are visible rather than erased.** A provider serving "current" fundamentals
  overwrites a revised figure. companyfacts carries every filing that ever reported a period,
  each with its own accession and filing date, so an amendment appears as an additional
  observation and the original survives. That is the raw material for measuring how often
  restatements would have changed a historical decision.
* **Tag heterogeneity is resolved explicitly.** Filers tag the same economic concept
  differently -- ``Revenues`` against
  ``RevenueFromContractWithCustomerExcludingAssessedTax`` against ``SalesRevenueNet``. The
  concept map below is ordered by preference and the tag that satisfied each concept is
  recorded on the observation, so a later analysis can tell which filers were read through
  which tag rather than assuming one comparable series.

Rate limits: SEC fair access allows 10 requests/second and requires a declaring User-Agent.
Pacing is delegated to the process-wide token bucket in ``cache.limiter_for("sec_edgar")``
(9/s, deliberately under the ceiling), and ``SecEdgarClient`` now backs off on 403/429.
For a universe-scale refresh prefer ``companyfacts.zip`` -- one download instead of ~900
requests. See ``build_pit_fundamentals.py``.
"""

from datetime import datetime, timezone

SEC_DATA = "https://data.sec.gov"

# Canonical concept -> us-gaap tags in preference order. First tag that yields facts wins,
# and the winner is recorded per observation. Ordering is by specificity: the post-ASC-606
# revenue tags are more precisely defined than the legacy aggregate, so they are preferred
# where a filer supplies both.
CONCEPT_TAGS = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"),
    "cost_of_revenue": ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "pretax_income": ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"),
    "tax_provision": ("IncomeTaxExpenseBenefit",),
    "interest_expense": ("InterestExpense", "InterestExpenseDebt",
                         "InterestIncomeExpenseNet"),
    "eps_diluted": ("EarningsPerShareDiluted",),
    "assets": ("Assets",),
    "current_assets": ("AssetsCurrent",),
    "liabilities": ("Liabilities",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "equity": ("StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    # Round 6: unblocks Altman Z, whose retained-earnings input capped as-filed coverage
    # at 66% through Round 5 (docs/AUDIT-ROUND-5-FINDINGS.md section 1).
    "retained_earnings": ("RetainedEarningsAccumulatedDeficit",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "inventory": ("InventoryNet",),
    "receivables": ("AccountsReceivableNetCurrent", "ReceivablesNetCurrent"),
    "goodwill": ("Goodwill",),
    "intangibles": ("FiniteLivedIntangibleAssetsNet", "IntangibleAssetsNetExcludingGoodwill"),
    "long_term_debt": ("LongTermDebtNoncurrent", "LongTermDebt"),
    "short_term_debt": ("LongTermDebtCurrent", "ShortTermBorrowings",
                        "DebtCurrent"),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",
                            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
    "capital_expenditure": ("PaymentsToAcquirePropertyPlantAndEquipment",
                            "PaymentsToAcquireProductiveAssets"),
    "depreciation_amortization": ("DepreciationDepletionAndAmortization",
                                  "DepreciationAmortizationAndAccretionNet",
                                  "DepreciationAndAmortization"),
    "share_based_compensation": ("ShareBasedCompensation",),
    "dividends_paid": ("PaymentsOfDividendsCommonStock", "PaymentsOfDividends"),
    "share_repurchases": ("PaymentsForRepurchaseOfCommonStock",),
    "shares_diluted": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
    "shares_basic": ("WeightedAverageNumberOfSharesOutstandingBasic",),
}

# Only periodic reports carry a reliable filing date for a fiscal period. 8-K and S-1 facts
# are excluded rather than mixed in: their periods are irregular and their tags episodic.
PERIODIC_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A")

# Facts stated in these units are carried as-is; anything else is recorded with its unit so a
# consumer can reject it rather than silently mixing scales.
KNOWN_UNITS = ("USD", "shares", "USD/shares", "pure")


def _fact_rows(companyfacts, taxonomy, tag):
    node = ((companyfacts or {}).get("facts") or {}).get(taxonomy, {}).get(tag)
    if not node:
        return []
    rows = []
    for unit, entries in (node.get("units") or {}).items():
        for entry in entries or []:
            rows.append((unit, entry))
    return rows


def _period_kind(entry):
    """``instant`` for a balance-sheet fact, else the length of the flow period.

    ``nine_months`` is a separate kind, not a short year. Filers tag year-to-date
    cumulatives in every 10-Q, so a Q3 filing carries a nine-month figure alongside the
    quarter. Folding those into ``annual`` put 9,076 of 23,048 supposedly-annual facts --
    39% -- at three quarters of a year: Apple's nine-month revenue of $293.8B sat labelled
    as an annual figure against a true full year of $383.3B. Any TTM or annual derivation
    reading that would have understated by a quarter.
    """
    start, end = entry.get("start"), entry.get("end")
    if not start:
        return "instant", None
    try:
        days = (datetime.fromisoformat(end).date() - datetime.fromisoformat(start).date()).days
    except (TypeError, ValueError):
        return "duration", None
    if days <= 100:
        return "quarter", days
    if days <= 200:
        return "half_year", days
    if days <= 300:
        return "nine_months", days
    if days <= 380:
        return "annual", days
    return "duration", days


def observations_for_concept(companyfacts, concept, *, forms=PERIODIC_FORMS,
                             requested_at=None, cik=None, ticker=None):
    """Every point-in-time observation of one canonical concept, newest filing last.

    Each record carries the provenance Phase 2.2 requires: source, the tag that satisfied
    the concept, the accession, the period, the *filing* date as ``available_at``, units, and
    a reliability tier. Nothing here is averaged, deduplicated across filings, or corrected.
    """
    requested_at = requested_at or datetime.now(timezone.utc).isoformat()
    allowed_forms = set(forms or ())
    # Round 5 fix: observations are UNIONED across every matching tag, not taken from the
    # first tag that has any rows. Returning on first match silently discarded a filer's
    # entire pre-2018 history whenever it switched tags (ASC 606 moved most issuers from
    # Revenues / SalesRevenueNet to RevenueFromContractWithCustomer* in 2018), which is
    # exactly the coverage cliff the Round 5 as-filed backtest measured: revenue visible
    # for 1% of names in 2011 and 10% in 2014 despite the legacy tags being listed here.
    # Tag order remains a priority order: for the same (period, filing) the earlier tag
    # wins, later tags only contribute periods the earlier ones did not cover.
    merged, seen, primary_tag = [], set(), None
    for tag in CONCEPT_TAGS.get(concept, ()):
        for taxonomy in ("us-gaap", "ifrs-full", "dei"):
            rows = _fact_rows(companyfacts, taxonomy, tag)
            if not rows:
                continue
            observations = []
            for unit, entry in rows:
                form, filed, end = entry.get("form"), entry.get("filed"), entry.get("end")
                value = entry.get("val")
                if not filed or not end or value is None:
                    continue
                if allowed_forms and form not in allowed_forms:
                    continue
                # A fact cannot be filed before the period it reports has ended. Two such
                # rows appeared in the first live sample (AES share counts tagged with a
                # period ending five months after the filing date -- a filer tagging error).
                # Carrying one would make a value readable before it could exist, which is
                # precisely the look-ahead this module exists to prevent.
                if filed < end:
                    continue
                period_type, period_days = _period_kind(entry)
                observations.append({
                    "cik": str(cik).zfill(10) if cik else None,
                    "ticker": ticker,
                    "concept": concept,
                    "value": value,
                    "unit": unit,
                    "unit_recognized": unit in KNOWN_UNITS,
                    "source": "sec_edgar_xbrl",
                    "source_taxonomy": taxonomy,
                    "source_field": tag,
                    "accession": entry.get("accn"),
                    "form": form,
                    "amended": bool(form and form.endswith("/A")),
                    "fiscal_year": entry.get("fy"),
                    "fiscal_period": entry.get("fp"),
                    "frame": entry.get("frame"),
                    "period_start": entry.get("start"),
                    "period_end": end,
                    "period_type": period_type,
                    "period_days": period_days,
                    # The whole point of this module. `available_at` is the first date this
                    # value could have been known; a backtest must not read it before then.
                    "available_at": filed,
                    "filed": filed,
                    "observed_at": filed,
                    "requested_at": requested_at,
                    "transformation": "identity",
                    "split_adjusted": False,
                    "reliability_tier": "regulatory_primary",
                    "point_in_time": True,
                })
            if observations and primary_tag is None:
                primary_tag = tag
            for row in observations:
                key = (row["unit"], row["period_start"], row["period_end"], row["filed"])
                if key in seen:
                    continue
                seen.add(key)
                merged.append(row)
    if merged:
        merged.sort(key=lambda row: (row["period_end"], row["filed"]))
        return merged, primary_tag
    return [], None


def company_observations(companyfacts, *, concepts=None, cik=None, ticker=None,
                         forms=PERIODIC_FORMS, requested_at=None):
    """All concepts for one company, plus which tag satisfied each and which found nothing."""
    requested_at = requested_at or datetime.now(timezone.utc).isoformat()
    selected = concepts or tuple(CONCEPT_TAGS)
    rows, resolved_tags, missing = [], {}, []
    for concept in selected:
        observations, tag = observations_for_concept(
            companyfacts, concept, forms=forms, requested_at=requested_at,
            cik=cik, ticker=ticker)
        if not observations:
            missing.append(concept)
            continue
        resolved_tags[concept] = tag
        rows.extend(observations)
    return rows, {"resolved_tags": resolved_tags, "missing_concepts": sorted(missing),
                  "observation_count": len(rows)}


def as_of(observations, when, *, concept=None, period_type=None):
    """The latest value knowable on ``when``, honouring filing dates and amendments.

    Selection is by (period_end, filed): the most recent period whose filing had been
    accepted on or before ``when``, and within that period the latest filing -- so an
    amendment supersedes the original it revises, but only from the date the amendment was
    itself filed. Returns ``None`` when nothing had been filed yet, which is the correct
    answer for an early backtest date and the one a fixed reporting lag gets wrong.
    """
    cutoff = str(when)[:10]
    candidates = [row for row in observations
                  if str(row.get("available_at"))[:10] <= cutoff
                  and (concept is None or row.get("concept") == concept)
                  and (period_type is None or row.get("period_type") == period_type)]
    if not candidates:
        return None
    return max(candidates, key=lambda row: (row["period_end"], row["filed"]))


def restatements(observations):
    """Periods reported more than once with a changed value, oldest filing first.

    This is the record a restated-fundamentals provider destroys. Each entry names the
    original and the revision, so a later analysis can ask how often a decision made on the
    original would have been made differently on the revision.
    """
    grouped = {}
    for row in observations:
        key = (row.get("concept"), row.get("period_start"), row.get("period_end"), row.get("unit"))
        grouped.setdefault(key, []).append(row)
    found = []
    for (concept, start, end, unit), rows in grouped.items():
        rows = sorted(rows, key=lambda row: row["filed"])
        first = rows[0]
        for later in rows[1:]:
            if later["value"] != first["value"]:
                found.append({
                    "concept": concept, "period_start": start, "period_end": end, "unit": unit,
                    "original_value": first["value"], "original_filed": first["filed"],
                    "original_accession": first["accession"],
                    "revised_value": later["value"], "revised_filed": later["filed"],
                    "revised_accession": later["accession"],
                    "change_fraction": (
                        (later["value"] - first["value"]) / abs(first["value"])
                        if isinstance(first["value"], (int, float)) and first["value"] else None),
                })
    return sorted(found, key=lambda row: (row["period_end"], row["revised_filed"]))
