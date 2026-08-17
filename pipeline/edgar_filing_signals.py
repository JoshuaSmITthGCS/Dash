"""Score 8-K materiality, contested proxies, and late 10-K/10-Q filings from form codes alone.

SEC EDGAR doesn't expose DEF 14A vote results or exact 8-K narrative in structured form -
reading either reliably would mean parsing free-text filings, which fail silently wrong
across filers' differing formats. Everything scored here instead comes from a form code SEC
itself assigns, the same way ``institutional_ownership.py`` and ``insider_signal.py`` score
only what a filing's own structure asserts:

  * **8-K Item codes.** Every 8-K declares which numbered Item(s) it reports under (Item 1.03
    bankruptcy, Item 4.02 restatement, ...) - a fixed SEC taxonomy, present in EDGAR's
    submissions payload as plain text (``SecEdgarClient.filings_for_cik``'s ``items`` field,
    never parsed from the filing document itself. ``EIGHT_K_ITEM_SENTIMENT`` maps the item
    codes with a well-established negative reading (bankruptcy, restatement, delisting,
    impairment, auditor change, ...) to a penalty; everything else - including the single most
    common 8-K item, 2.02 earnings results - scores zero. There is deliberately no positive
    side: no 8-K Item code reliably means "good news" the way 1.03 reliably means "bad news",
    so nothing here is scored positive, the same asymmetry ``insider_signal.py`` documents for
    why sells are capped lower than buys.
  * **DEF 14A variant.** SEC itself distinguishes a contested proxy fight (``DEFC14A``) and
    additional soliciting material (``DEFA14A``) from a routine annual proxy (``DEF 14A``) at
    the form-type level. Only ``DEFC14A`` - an unambiguous governance conflict - moves the
    score. ``DEFA14A`` is published as a flag with zero score impact: it covers everything from
    a routine adjournment notice to genuine activist correspondence, and the form code alone
    can't tell those apart.
  * **10-K/10-Q lateness.** ``NT 10-K``/``NT 10-Q`` (Notification of Late Filing) is a
    well-documented distress or accounting-problem signal on its own - a company files one
    only when it cannot complete its financials on time. An on-time 10-K/10-Q carries no
    score signal by itself; it is recorded as a date only.

Every score here is a small, bounded, decaying modifier - fully unit-testable without network
access, exactly like ``insider_signal.score_insider_activity``.
"""

from datetime import date, datetime

# ---------------- 8-K item materiality ----------------

# (direction, weight in [0, 1]) - weight scales how much of max_penalty a single occurrence
# of this item earns. Multiple qualifying items on one filing take the worst (highest-weight)
# one, not a sum - one 8-K describing one event should not double-count because it cites two
# related item numbers (a bankruptcy filing routinely cites 1.03 alongside 2.04 or 2.05).
EIGHT_K_ITEM_SENTIMENT = {
    "1.03": ("negative", 1.00),  # Bankruptcy or Receivership
    "4.02": ("negative", 1.00),  # Non-Reliance on Previously Issued Financials (restatement)
    "3.01": ("negative", 0.85),  # Notice of Delisting / Failure to Satisfy Listing Rule
    "2.06": ("negative", 0.70),  # Material Impairments
    "2.04": ("negative", 0.65),  # Triggering Events That Accelerate a Financial Obligation
    "2.05": ("negative", 0.60),  # Costs Associated with Exit or Disposal Activities
    "4.01": ("negative", 0.55),  # Changes in Registrant's Certifying Accountant
    "1.02": ("negative", 0.45),  # Termination of a Material Definitive Agreement
    "3.02": ("negative", 0.35),  # Unregistered Sales of Equity Securities (dilution)
}

DEFAULTS_8K = {
    "max_penalty": 4.0,
    "half_life_days": 30,
    "max_age_days": 90,
}

DEFAULTS_PROXY = {
    "max_penalty": 2.0,
    "half_life_days": 45,
    "max_age_days": 180,
}

DEFAULTS_FILING_INTEGRITY = {
    "max_penalty": 3.0,
    "half_life_days": 30,
    "max_age_days": 120,
}


def _parse_date(value):
    if isinstance(value, date):
        return value
    if not value:
        return None
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _days_between(earlier, later):
    if earlier is None or later is None:
        return None
    return (later - earlier).days


def decay(days_since, half_life, max_age):
    """Exponential decay of signal strength with age, 1.0 today, 0.0 past ``max_age`` -
    same shape as ``insider_signal.decay`` / ``institutional_ownership.decay``."""
    if days_since is None or days_since < 0:
        return 0.0
    if days_since > max_age:
        return 0.0
    return round(0.5 ** (days_since / half_life), 4)


def _item_codes(filing):
    raw = str(filing.get("items") or "")
    return [code.strip() for code in raw.split(",") if code.strip()]


def classify_8k_filing(filing):
    """The worst (highest-weight) qualifying item on one 8-K, or ``None`` if it cites
    nothing in ``EIGHT_K_ITEM_SENTIMENT`` - which is most 8-Ks, since routine items
    (2.02 earnings, 5.02 routine officer changes, 7.01 Reg FD, 8.01 catch-all, ...)
    carry no reliable materiality signal on their own."""
    best = None
    for code in _item_codes(filing):
        entry = EIGHT_K_ITEM_SENTIMENT.get(code)
        if entry and (best is None or entry[1] > best[2]):
            best = (code, entry[0], entry[1])
    if best is None:
        return None
    code, direction, weight = best
    return {"item": code, "direction": direction, "weight": weight}


def score_8k_activity(filings, *, as_of=None, config=None):
    """A bounded, decaying penalty from the most recent materially negative 8-K, or 0.0.

    Returns ``(points, detail)``. Only the single freshest qualifying filing is scored -
    like ``insider_signal``, a stale material event should not still be moving today's
    score, and stacking several old ones would let a company's compliance history rather
    than its current condition dominate the modifier.
    """
    settings = {**DEFAULTS_8K, **(config or {})}
    as_of_date = _parse_date(as_of) or date.today()
    classified = []
    for filing in filings or []:
        match = classify_8k_filing(filing)
        if not match:
            continue
        filed = _parse_date(filing.get("filed"))
        classified.append({**match, "filed": filing.get("filed"), "_filed_date": filed})
    if not filings:
        return 0.0, {"available": False, "reason": "no 8-K filings reviewed",
                     "filings_reviewed": 0}
    if not classified:
        return 0.0, {"available": True, "filings_reviewed": len(filings),
                     "material_items": 0,
                     "notes": ["no materially negative 8-K item in the reviewed filings"]}

    classified.sort(key=lambda row: row["_filed_date"] or date.min, reverse=True)
    latest = classified[0]
    age = _days_between(latest["_filed_date"], as_of_date)
    weight = decay(age, settings["half_life_days"], settings["max_age_days"])
    points = -round(settings["max_penalty"] * latest["weight"] * weight, 2)
    notes = []
    if points:
        notes.append(f"8-K Item {latest['item']} filed {latest['filed']} "
                     f"({age} day(s) ago) is a materially negative event")
    else:
        notes.append(f"8-K Item {latest['item']} filed {latest['filed']} has decayed out "
                     "of the scoring window")
    return points, {
        "available": True,
        "filings_reviewed": len(filings),
        "material_items": len(classified),
        "latest_item": latest["item"],
        "latest_filed": latest["filed"],
        "points": points,
        "notes": notes,
        "method": "SEC 8-K Item-code materiality lookup; freshest qualifying item only; "
                  f"{settings['half_life_days']}-day half-life",
    }


# ---------------- DEF 14A proxy signal ----------------

def classify_proxy_filing(form):
    """``"CONTESTED"`` for a DEFC14A (proxy fight), ``"SOLICITING_MATERIAL"`` for a DEFA14A,
    else ``None``. A routine ``DEF 14A`` classifies as ``None`` - it is the expected annual
    filing and carries no signal by itself."""
    form = str(form or "").strip().upper()
    if form == "DEFC14A":
        return "CONTESTED"
    if form == "DEFA14A":
        return "SOLICITING_MATERIAL"
    return None


def score_proxy_activity(filings, *, as_of=None, config=None):
    """A bounded, decaying penalty when the most recent proxy filing is a contested
    election (``DEFC14A``). ``DEFA14A`` (additional soliciting material) is reported as a
    flag but never scored - the form code alone can't distinguish a genuine activist
    situation from a routine adjournment notice or M&A vote update.
    """
    settings = {**DEFAULTS_PROXY, **(config or {})}
    as_of_date = _parse_date(as_of) or date.today()
    classified = []
    for filing in filings or []:
        label = classify_proxy_filing(filing.get("form"))
        if not label:
            continue
        classified.append({"label": label, "filed": filing.get("filed"),
                           "_filed_date": _parse_date(filing.get("filed"))})
    if not filings:
        return 0.0, {"available": False, "reason": "no DEF 14A filings reviewed",
                     "filings_reviewed": 0}

    contested = [row for row in classified if row["label"] == "CONTESTED"]
    soliciting = [row for row in classified if row["label"] == "SOLICITING_MATERIAL"]
    detail = {
        "available": True,
        "filings_reviewed": len(filings),
        "contested_filings": len(contested),
        "soliciting_material_filings": len(soliciting),
        "points": 0.0,
        "notes": [],
    }
    if not contested:
        if soliciting:
            detail["notes"].append(
                f"{len(soliciting)} DEFA14A soliciting-material filing(s) seen - "
                "informational only, not scored")
        else:
            detail["notes"].append("no contested (DEFC14A) or soliciting-material "
                                   "(DEFA14A) proxy filings")
        return 0.0, detail

    contested.sort(key=lambda row: row["_filed_date"] or date.min, reverse=True)
    latest = contested[0]
    age = _days_between(latest["_filed_date"], as_of_date)
    weight = decay(age, settings["half_life_days"], settings["max_age_days"])
    points = -round(settings["max_penalty"] * weight, 2)
    if points:
        detail["notes"].append(f"contested proxy (DEFC14A) filed {latest['filed']} "
                               f"({age} day(s) ago)")
    else:
        detail["notes"].append(f"contested proxy (DEFC14A) filed {latest['filed']} has "
                               "decayed out of the scoring window")
    detail["points"] = points
    detail["latest_contested_filed"] = latest["filed"]
    detail["method"] = ("DEFC14A form-code detection; only a contested election scores; "
                        f"{settings['half_life_days']}-day half-life")
    return points, detail


# ---------------- 10-K / 10-Q filing integrity ----------------

def _latest_nt_filing(filings):
    nt_filings = [row for row in (filings or [])
                 if str(row.get("form") or "").strip().upper() in ("NT 10-K", "NT 10-Q")]
    if not nt_filings:
        return None
    return max(nt_filings, key=lambda row: row.get("filed") or "")


def score_filing_integrity(filings_10k, filings_10q, *, as_of=None, config=None):
    """A bounded, decaying penalty when the most recent 10-K or 10-Q filing activity is an
    ``NT 10-K``/``NT 10-Q`` (notification the company could not file on time). On-time
    10-K/10-Q filings are recorded (as ``latest_10k_filed``/``latest_10q_filed``) but score
    nothing - lateness is the signal, not the filing itself.
    """
    settings = {**DEFAULTS_FILING_INTEGRITY, **(config or {})}
    as_of_date = _parse_date(as_of) or date.today()
    all_filings = list(filings_10k or []) + list(filings_10q or [])
    latest_10k = max((row for row in filings_10k or [] if row.get("form") == "10-K"),
                     key=lambda row: row.get("filed") or "", default=None)
    latest_10q = max((row for row in filings_10q or [] if row.get("form") == "10-Q"),
                     key=lambda row: row.get("filed") or "", default=None)
    detail = {
        "available": bool(all_filings),
        "latest_10k_filed": (latest_10k or {}).get("filed"),
        "latest_10q_filed": (latest_10q or {}).get("filed"),
        "points": 0.0,
        "notes": [],
    }
    if not all_filings:
        detail["reason"] = "no 10-K/10-Q/NT filing activity reviewed"
        return 0.0, detail

    nt_filing = _latest_nt_filing(all_filings)
    if not nt_filing:
        detail["notes"].append("no late-filing notification (NT 10-K/NT 10-Q) on record")
        return 0.0, detail

    age = _days_between(_parse_date(nt_filing.get("filed")), as_of_date)
    weight = decay(age, settings["half_life_days"], settings["max_age_days"])
    points = -round(settings["max_penalty"] * weight, 2)
    if points:
        detail["notes"].append(f"{nt_filing['form']} filed {nt_filing['filed']} "
                               f"({age} day(s) ago) - company notified it could not file "
                               "on time")
    else:
        detail["notes"].append(f"{nt_filing['form']} filed {nt_filing['filed']} has decayed "
                               "out of the scoring window")
    detail["points"] = points
    detail["latest_nt_form"] = nt_filing["form"]
    detail["latest_nt_filed"] = nt_filing["filed"]
    detail["method"] = ("NT 10-K/NT 10-Q form-code detection; "
                        f"{settings['half_life_days']}-day half-life")
    return points, detail
