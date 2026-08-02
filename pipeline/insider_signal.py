"""Score SEC Form 4 insider trading the way the literature says it actually works.

The pipeline already downloaded Form 4 filings and then did almost nothing with them -
it counted acquisitions and disposals. Raw counts are close to worthless, and the reason
is the central finding of Cohen, Malloy & Pomorski, "Decoding Inside Information"
(*Journal of Finance* 67(3), 2012): insider trades split into two populations with
completely different information content.

  * **Routine** trades follow a calendar. An executive who sells in March every year is
    diversifying, funding a tax bill, or exercising on a schedule. The paper finds returns
    to routine trades are "essentially zero".
  * **Opportunistic** trades break the pattern. These carry the signal: value-weighted
    abnormal returns of ~82 bps/month (about 9.8% annualized) and ~180 bps/month
    equal-weighted, concentrated in the months right after the trade.

So the classification is the signal. A model that counts all insider buys equally is
averaging a real effect against noise and getting noise.

Three further asymmetries the implementation respects:

  * **Buys beat sells.** Insiders sell for diversification, liquidity, divorce, and houses;
    they buy for one reason. Lakonishok & Lee and Jeng, Metrick & Zeckhauser all find the
    purchase side carries the information, so sells get a smaller coefficient.
  * **Clusters beat singletons.** Several insiders buying independently inside a short
    window is much harder to explain away than one person topping up.
  * **The signal decays.** The abnormal return accrues over roughly one to three months,
    so a six-month-old purchase should not still be moving today's score.

Everything here is pure. ``score_insider_activity`` takes parsed transactions and an as-of
date and returns a bounded modifier, so it is fully testable without touching the network.
"""

from collections import defaultdict
from datetime import date, datetime

# A trade is routine when the same insider traded this same calendar month in at least
# this many *prior* years. Cohen-Malloy-Pomorski require a run of three consecutive years;
# with a three-year download window that means two prior observations plus the current one.
ROUTINE_MIN_PRIOR_YEARS = 2
# Distinct insiders trading the same side within this many days count as one cluster.
CLUSTER_WINDOW_DAYS = 90
# Trades older than this contribute nothing: the documented alpha is a one-to-three-month
# effect, and a stale purchase pretending to be fresh conviction is worse than no signal.
SIGNAL_HALF_LIFE_DAYS = 45
MAX_AGE_DAYS = 120

DEFAULTS = {
    "max_points": 5.0,
    "max_penalty": 3.0,          # the sell side is noisier, so it is capped lower
    "cluster_bonus": 1.0,
    "min_trade_value": 25000.0,  # below this a "purchase" is a gesture, not a position
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


def insider_key(transaction):
    """Stable identity for one insider. CIK when present, normalized name otherwise."""
    cik = transaction.get("owner_cik")
    if cik:
        return f"cik:{str(cik).lstrip('0') or '0'}"
    name = " ".join(str(transaction.get("owner_name") or "").lower().split())
    return f"name:{name}" if name else "unknown"


# ---------------- routine vs opportunistic ----------------

def classify_transactions(transactions):
    """Tag every transaction routine or opportunistic, per Cohen-Malloy-Pomorski.

    An insider's trade is routine when that insider traded the same side in the same
    calendar month in at least ``ROUTINE_MIN_PRIOR_YEARS`` earlier years. Insiders without
    enough history to judge are classified opportunistic but flagged ``unproven`` - the
    honest reading is "no evidence of a pattern", not "confirmed irregular", and the
    scoring weights it down accordingly.
    """
    parsed = []
    for transaction in transactions:
        when = _parse_date(transaction.get("date") or transaction.get("filed"))
        if when is None:
            continue
        parsed.append({**transaction, "_date": when, "_key": insider_key(transaction)})

    months_by_insider = defaultdict(lambda: defaultdict(set))
    for row in parsed:
        months_by_insider[(row["_key"], row.get("side"))][row["_date"].month].add(row["_date"].year)

    classified = []
    for row in parsed:
        calendar = months_by_insider[(row["_key"], row.get("side"))]
        years_this_month = calendar.get(row["_date"].month, set())
        prior_years = {year for year in years_this_month if year < row["_date"].year}
        observed_years = {year for years in calendar.values() for year in years}
        routine = len(prior_years) >= ROUTINE_MIN_PRIOR_YEARS
        # Too little history to have seen a pattern even if one exists. Not the same claim
        # as "this trade broke a known pattern", so the score treats it more cautiously.
        unproven = not routine and len(observed_years) < ROUTINE_MIN_PRIOR_YEARS + 1
        classified.append({
            **{key: value for key, value in row.items() if not key.startswith("_")},
            "date": row["_date"].isoformat(),
            "insider_key": row["_key"],
            "classification": "routine" if routine else "opportunistic",
            "pattern_confidence": "low" if unproven else "high",
            "prior_same_month_years": sorted(prior_years),
        })
    return classified


# ---------------- clustering ----------------

def cluster_trades(transactions, side, *, as_of=None, window_days=CLUSTER_WINDOW_DAYS):
    """Distinct insiders trading one side inside a trailing window, and what they moved.

    Counts *insiders*, not filings: one executive filing four amendments is one voice.
    """
    as_of = _parse_date(as_of) or date.today()
    insiders, total_value, most_recent = {}, 0.0, None
    for row in transactions:
        if row.get("side") != side:
            continue
        when = _parse_date(row.get("date"))
        age = _days_between(when, as_of)
        if age is None or age < 0 or age > window_days:
            continue
        key = row.get("insider_key") or insider_key(row)
        insiders.setdefault(key, {"name": row.get("owner_name"), "roles": row.get("roles") or [],
                                  "value": 0.0, "trades": 0, "pattern_confidence": "high"})
        insiders[key]["value"] += float(row.get("value") or 0)
        insiders[key]["trades"] += 1
        if row.get("pattern_confidence") == "low":
            insiders[key]["pattern_confidence"] = "low"
        total_value += float(row.get("value") or 0)
        if most_recent is None or when > most_recent:
            most_recent = when
    proven = sum(1 for entry in insiders.values() if entry["pattern_confidence"] == "high")
    # An insider with no trading history yet is "not known to be routine", which is weaker
    # evidence than "known to break their own pattern". Discount rather than discard.
    confidence = 1.0 if not insiders else round(0.6 + 0.4 * proven / len(insiders), 3)
    return {
        "side": side,
        "window_days": window_days,
        "insider_count": len(insiders),
        "trade_count": sum(entry["trades"] for entry in insiders.values()),
        "total_value": round(total_value, 2),
        "latest_date": most_recent.isoformat() if most_recent else None,
        "days_since_latest": _days_between(most_recent, as_of),
        "pattern_confidence": confidence,
        "insiders": insiders,
    }


def decay(days_since, half_life=SIGNAL_HALF_LIFE_DAYS, max_age=MAX_AGE_DAYS):
    """Exponential decay of signal strength with age. 1.0 today, 0.0 past ``max_age``."""
    if days_since is None or days_since < 0:
        return 0.0
    if days_since > max_age:
        return 0.0
    return round(0.5 ** (days_since / half_life), 4)


# ---------------- scoring ----------------

def score_insider_activity(transactions, *, as_of=None, config=None):
    """A bounded, decaying score modifier from classified Form 4 activity.

    Returns ``(points, detail)``. Points are positive for fresh opportunistic cluster
    buying and negative for fresh opportunistic cluster selling, capped by config. Routine
    trades on either side contribute exactly zero - which is what the evidence says they
    are worth - but they are still reported so the UI can show that they were seen and
    deliberately discounted.
    """
    settings = {**DEFAULTS, **(config or {})}
    as_of_date = _parse_date(as_of) or date.today()
    classified = classify_transactions(transactions or [])
    if not classified:
        return 0.0, {"available": False, "reason": "no open-market Form 4 transactions",
                     "transactions_reviewed": 0}

    opportunistic = [row for row in classified if row["classification"] == "opportunistic"]
    routine = [row for row in classified if row["classification"] == "routine"]
    material = [row for row in opportunistic
                if (row.get("value") or 0) >= settings["min_trade_value"]]

    buys = cluster_trades(material, "purchase", as_of=as_of_date)
    sells = cluster_trades(material, "sale", as_of=as_of_date)

    notes = []
    points = 0.0

    buy_strength = _side_strength(buys, settings, positive=True)
    if buy_strength:
        points += buy_strength["points"]
        notes.append(buy_strength["note"])
    sell_strength = _side_strength(sells, settings, positive=False)
    if sell_strength:
        points -= sell_strength["points"]
        notes.append(sell_strength["note"])

    cap = settings["max_points"]
    floor = -settings["max_penalty"]
    total = round(max(floor, min(cap, points)), 2)
    if routine and not notes:
        notes.append(f"{len(routine)} routine calendar-scheduled insider trade(s) carry no signal")

    return total, {
        "available": True,
        "transactions_reviewed": len(classified),
        "opportunistic": len(opportunistic),
        "routine": len(routine),
        "material_opportunistic": len(material),
        "buy_cluster": _public_cluster(buys),
        "sell_cluster": _public_cluster(sells),
        "uncapped_points": round(points, 2),
        "points": total,
        "notes": notes,
        "method": "Cohen-Malloy-Pomorski routine/opportunistic split; buys weighted above sells; "
                  f"{SIGNAL_HALF_LIFE_DAYS}-day half-life",
    }


def _side_strength(cluster, settings, *, positive):
    """Magnitude for one side: insider breadth x freshness, plus a cluster bonus."""
    insider_count = cluster["insider_count"]
    if not insider_count:
        return None
    freshness = decay(cluster["days_since_latest"])
    if freshness <= 0:
        return None
    cap = settings["max_points"] if positive else settings["max_penalty"]
    # One insider earns roughly half the cap, three or more approach all of it. Breadth is
    # what distinguishes a signal from one person's personal balance sheet.
    breadth = min(1.0, 0.5 + 0.25 * (insider_count - 1))
    magnitude = cap * breadth * freshness * cluster.get("pattern_confidence", 1.0)
    if insider_count >= 3:
        magnitude = min(cap, magnitude + settings["cluster_bonus"] * freshness)
    verb = "bought" if positive else "sold"
    days = cluster["days_since_latest"]
    value = cluster["total_value"]
    note = (f"{insider_count} insider{'s' if insider_count > 1 else ''} {verb} "
            f"${value / 1e6:.1f}M on the open market, most recently {days} day(s) ago "
            f"(opportunistic, not calendar-scheduled)")
    return {"points": round(magnitude, 2), "note": note}


def _public_cluster(cluster):
    """Cluster summary without the per-insider dict, which is too granular to publish."""
    return {key: value for key, value in cluster.items() if key != "insiders"}


def summarize(transactions, *, as_of=None, config=None):
    """Convenience wrapper returning a single publishable insider-activity record."""
    points, detail = score_insider_activity(transactions, as_of=as_of, config=config)
    return {
        "source": "SEC EDGAR Form 4",
        "score_points": points,
        **detail,
        "recent_acquisitions": sum(1 for row in transactions or [] if row.get("side") == "purchase"),
        "recent_disposals": sum(1 for row in transactions or [] if row.get("side") == "sale"),
    }
