"""Who to watch on the Political Trading screen, and which of their disclosures stand out.

``build_congress_screen`` already answers "what was disclosed this window" one row at a
time. This module answers the two questions that only exist across rows and across runs:

  * **Who is this, really?** The disclosure feeds spell one person several ways -
    "Rohit Khanna" and "Ro Khanna", "Michael T. McCaul" and "Michael McCaul",
    "Gilbert Ray Cisneros Jr." and "Gilbert Cisneros" are each one filer arriving under
    two or three names. Counting them separately understates every per-politician number
    on the page and silently breaks the committee lookup, which is keyed by one spelling.
    ``canonical_name`` resolves the variants through an explicit alias table
    (``political_tracking.json``) plus a first+last fallback that only ever fires when it
    lands on an already-curated key - an unrecognized name keeps its own full form rather
    than being merged into somebody else's.

  * **Which disclosures are unusual on more than one axis at once?** Any single flag is
    weak on its own: plenty of large trades are routine, plenty of late filings are
    clerical. ``unusual_timing`` ranks a disclosure by how many separately-computable
    things about it are unusual *simultaneously* - size, committee jurisdiction over the
    stock's sector, how long it went unreported, how it performed against SPY afterward,
    and (only when the news feed is live rather than in demo mode) whether it preceded a
    policy headline in that name.

**This is not a conflict-of-interest finding, and the flag is deliberately narrow.**
``build_congress_screen``'s docstring has always refused to invent conflict scoring, and
that refusal still stands: ``COMMITTEE_OVERLAP`` asserts one checkable fact - this filer
sits on a committee whose jurisdiction covers this stock's sector - and asserts nothing
about motive, knowledge, or legality. The committee data behind it is hand-curated and
incomplete by construction (see ``committees.json``'s own ``_verification`` note), so an
*absent* overlap means "not curated", never "no conflict". The published payload carries
the curated-coverage count so a reader can tell those apart. Same standing rule as every
other panel on this screen: display-only, never an ``advisor_engine`` input.

**External figures stay external.** ``political_tracking.json``'s ``external_reference``
block holds third-party 2025 estimates (Unusual Whales, as of their 2025-12-29 cutoff).
``merge_external_into_leaderboard`` attaches them to the leaderboard as separately-named,
separately-sourced fields - never merged into, averaged with, or substituted for
``politician_performance``'s own shrunk alpha, which measures a different thing over a
different window with a different estimator.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from common import load_json, normalize_name

# Generational suffixes carry no identity - "Gilbert Ray Cisneros Jr." and "Gilbert
# Cisneros" are the same filer, and the feeds are inconsistent about including them.
NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

_CACHE = {}


def _config():
    if "config" not in _CACHE:
        _CACHE["config"] = load_json("political_tracking.json", from_config=True) or {}
    return _CACHE["config"]


def _raw_committees():
    if "committees_raw" not in _CACHE:
        payload = load_json("committees.json", from_config=True) or {}
        _CACHE["committees_raw"] = payload.get("politicians", {})
    return _CACHE["committees_raw"]


def reset_caches():
    """Test seam - the configs are read once per process and memoized."""
    _CACHE.clear()


# ---------------- identity ----------------

def _strip_name(name):
    """Lowercase, punctuation-free, suffix-free form of a disclosed name."""
    text = normalize_name(re.sub(r"[.,\"'’]", " ", str(name or "")))
    return " ".join(token for token in text.split() if token not in NAME_SUFFIXES)


def _alias_index():
    """Every disclosed spelling -> its canonical key."""
    if "aliases" not in _CACHE:
        index = {}
        for canonical, variants in (_config().get("name_aliases") or {}).items():
            key = _strip_name(canonical)
            index[key] = key
            for variant in variants:
                index[_strip_name(variant)] = key
        _CACHE["aliases"] = index
    return _CACHE["aliases"]


def _known_keys():
    """Keys any curated table already recognizes, so the first+last fallback can only ever
    resolve *onto* a curated person - never collapse two uncurated strangers together.

    Reads the tables' *raw* keys, before canonicalization, precisely because
    ``canonical_name`` is what consumes this - going the other way would recurse.
    """
    if "known" not in _CACHE:
        config = _config()
        _CACHE["known"] = {
            *(_strip_name(key) for key in _raw_committees()),
            *(_strip_name(key) for key in (config.get("tracked_filers") or {})),
            *(_strip_name(key) for key in
              ((config.get("external_reference") or {}).get("politicians") or {})),
        }
    return _CACHE["known"]


def canonical_name(raw):
    """One stable key per filer across every spelling the disclosure feeds publish.

    Falls back to the stripped name itself when nothing is curated - that still merges
    punctuation and suffix variants of an unknown filer, which is the whole point, without
    guessing that two different unknown people are the same person.
    """
    stripped = _strip_name(raw)
    if not stripped:
        return ""
    aliases, known = _alias_index(), _known_keys()
    if stripped in aliases:
        return aliases[stripped]
    if stripped in known:
        return stripped
    tokens = stripped.split()
    if len(tokens) > 2:
        # Drop middle names/initials, but only accept the result if it names somebody the
        # curated tables already know: "michael t mccaul" -> "michael mccaul" (curated),
        # while "charles j chuck fleischmann" stays whole rather than inventing a match.
        short = f"{tokens[0]} {tokens[-1]}"
        if short in aliases:
            return aliases[short]
        if short in known:
            return short
    return stripped


# ---------------- curated lookups ----------------

def _canonicalized(mapping):
    """Re-key a curated table by canonical name, so the three tables do not have to agree
    on one spelling of a person to describe the same person. committees.json says
    "gilbert cisneros" and the tracking roster says "gil cisneros"; both resolve here, and
    committees.json keeps its own spelling for ``scorer``, which looks it up directly."""
    return {canonical_name(key): value for key, value in (mapping or {}).items()}


def _committees():
    if "committees" not in _CACHE:
        _CACHE["committees"] = _canonicalized(_raw_committees())
    return _CACHE["committees"]


def _tracked():
    if "tracked" not in _CACHE:
        _CACHE["tracked"] = _canonicalized(_config().get("tracked_filers"))
    return _CACHE["tracked"]


def _external():
    if "external" not in _CACHE:
        reference = _config().get("external_reference") or {}
        _CACHE["external"] = _canonicalized(reference.get("politicians"))
    return _CACHE["external"]


def committee_profile(representative):
    """This filer's curated committee assignments, or None when nobody has curated them."""
    return _committees().get(canonical_name(representative))


def tracked_profile(representative):
    """The tracked-filer roster entry for this filer, or None if they are not tracked."""
    return _tracked().get(canonical_name(representative))


def external_profile(representative):
    """Third-party reference figures for this filer, or None. Never this pipeline's own
    numbers - see the module docstring and the config's ``_source`` block."""
    return _external().get(canonical_name(representative))


def external_source():
    return (_config().get("external_reference") or {}).get("_source") or {}


def tracked_coverage():
    """How much curation actually exists, so an absent badge reads as 'not curated yet'
    rather than as a finding about the filer."""
    return {
        "tracked_filers": len(_tracked()),
        "committee_profiles": len(_committees()),
        "external_reference_politicians": len(_external()),
    }


# ---------------- committee jurisdiction ----------------

def policy_sector_by_ticker():
    """Ticker -> policy_map sector, the same hand-listed mapping ``scorer`` uses. Narrow by
    design (a few dozen bellwether names), which is why it is only the fallback below."""
    policy = load_json("policy_map.json", from_config=True) or {}
    lookup = {}
    for sector, config in (policy.get("sectors") or {}).items():
        for ticker in config.get("tickers") or []:
            lookup.setdefault(ticker, sector)
    return lookup


def committee_overlap(row, sector_lookup=None, policy_lookup=None):
    """"This filer sits on a committee with jurisdiction over this stock's sector" - or
    None when that is not checkable (uncurated filer, unclassified ticker, no match).

    Two independent sector vocabularies, tried widest-coverage first: the research
    pipeline's own sector label for the ticker (covers every scored name), then
    policy_map's curated ticker lists (covers a handful of bellwethers the research
    universe may not score). Returns the evidence, not a verdict - which committee,
    which sector, and which vocabulary matched, so the page can show its work.
    """
    profile = committee_profile(row.get("representative"))
    symbol = row.get("symbol")
    if not profile or not symbol:
        return None
    committees = profile.get("committees") or []
    market_sector = (sector_lookup or {}).get(symbol)
    if market_sector and market_sector in (profile.get("market_sectors") or []):
        return {"committees": committees, "sector": market_sector, "basis": "market_sector"}
    policy_sector = (policy_lookup or {}).get(symbol)
    if policy_sector and policy_sector in (profile.get("sectors") or []):
        return {"committees": committees, "sector": policy_sector, "basis": "policy_sector"}
    return None


# ---------------- news proximity ----------------

def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def news_proximity_index():
    """``({ticker: [headline dates]}, feed_is_live)`` from the policy news feed.

    Gated on the feed reporting ``data_mode == "live"``. ``fetch_news`` publishes a
    three-item placeholder set in demo mode, and scoring a disclosure as "traded ahead of
    the news" against placeholder headlines would manufacture the exact finding this
    screen is careful never to manufacture. In demo mode the component is simply switched
    off and ``unusual_timing`` reports it as inactive rather than scoring it as zero -
    those are different statements and only one of them is true.
    """
    payload = load_json("news.json") or {}
    if (payload.get("data_mode") or "").lower() != "live":
        return {}, False
    index = {}
    for item in payload.get("items") or []:
        published = _parse_date(item.get("published"))
        if not published:
            continue
        for flag in item.get("flags") or []:
            for ticker in flag.get("tickers") or []:
                index.setdefault(ticker, []).append(published)
    return index, True


def preceded_news(row, index, *, lookahead_days):
    """True when a policy headline naming this ticker published within ``lookahead_days``
    *after* the trade - i.e. the trade came first. A headline that broke before the trade
    is not this measurement; it is just a filer reading the news like anyone else."""
    traded = _parse_date(row.get("transaction_date"))
    if not traded:
        return False
    for published in index.get(row.get("symbol")) or ():
        if 0 <= (published - traded).days <= lookahead_days:
            return True
    return False


# ---------------- per-politician activity ----------------

def _midpoint(row):
    lower, upper = row.get("amount_lower"), row.get("amount_upper")
    if lower is None and upper is None:
        return 0.0
    if lower is None or upper is None:
        return float(lower if lower is not None else upper)
    return (lower + upper) / 2


def activity_profiles(rows, *, performance=None, late_filing_days=45, top_n=None):
    """One row per filer: how much they trade, how fast they disclose it, how much of it
    lands in a sector their committee oversees, and how it has performed.

    Deliberately *not* the same ranking as ``politician_performance.leaderboard``, which
    ranks by shrunk market-relative skill. This ranks by disclosed activity - "whose feed
    is worth watching at all" is a different question from "who has been right", and a
    filer can top one list while sitting nowhere on the other. Both are published so
    neither has to stand in for the other.

    Aggregated on ``canonical_name`` so a filer's spelling variants count once. The
    displayed name is whichever raw spelling the feeds used most for them.
    """
    by_key = {}
    for row in rows:
        representative = row.get("representative")
        if not representative:
            continue
        key = canonical_name(representative)
        bucket = by_key.setdefault(key, {
            "names": {}, "trades": 0, "buys": 0, "sells": 0, "symbols": set(),
            "volume_midpoint": 0.0, "largest_trade_amount_upper": 0.0,
            "filing_delays": [], "late_filings": 0, "committee_overlaps": 0,
            "dates": [], "chambers": set(),
        })
        bucket["names"][representative] = bucket["names"].get(representative, 0) + 1
        bucket["trades"] += 1
        transaction_type = str(row.get("transaction_type") or "").lower()
        if "purchase" in transaction_type:
            bucket["buys"] += 1
        elif "sale" in transaction_type or "sold" in transaction_type:
            bucket["sells"] += 1
        if row.get("symbol"):
            bucket["symbols"].add(row["symbol"])
        if row.get("chamber"):
            bucket["chambers"].add(row["chamber"])
        bucket["volume_midpoint"] += _midpoint(row)
        bucket["largest_trade_amount_upper"] = max(
            bucket["largest_trade_amount_upper"], row.get("amount_upper") or 0)
        delay = row.get("filing_delay_days")
        if delay is not None:
            bucket["filing_delays"].append(delay)
            if delay > late_filing_days:
                bucket["late_filings"] += 1
        if "COMMITTEE_OVERLAP" in (row.get("flags") or ()):
            bucket["committee_overlaps"] += 1
        if row.get("transaction_date"):
            bucket["dates"].append(row["transaction_date"])

    scores = (performance or {}).get("politicians") or {}
    profiles = []
    for key, bucket in by_key.items():
        display = max(bucket["names"].items(), key=lambda pair: pair[1])[0]
        delays = bucket["filing_delays"]
        committee = _committees().get(key) or {}
        tracked = tracked_profile(key)
        external = external_profile(key)
        # The performance table is keyed by the raw disclosed name, not the canonical one,
        # so look it up by every spelling this filer arrived under and take the richest.
        stats = max((scores[name] for name in bucket["names"] if name in scores),
                    key=lambda row: row.get("n_priced_buys", 0), default=None)
        profiles.append({
            "politician": display,
            "canonical_name": key,
            "chambers": sorted(bucket["chambers"]),
            "name_variants": sorted(bucket["names"]) if len(bucket["names"]) > 1 else [],
            "trades": bucket["trades"],
            "buys": bucket["buys"],
            "sells": bucket["sells"],
            "distinct_symbols": len(bucket["symbols"]),
            "disclosed_volume_midpoint": round(bucket["volume_midpoint"], 2),
            "largest_trade_amount_upper": bucket["largest_trade_amount_upper"] or None,
            "avg_filing_delay_days": round(sum(delays) / len(delays), 1) if delays else None,
            "late_filings": bucket["late_filings"],
            "late_filing_rate": round(bucket["late_filings"] / len(delays), 3) if delays else None,
            "committee_overlap_trades": bucket["committee_overlaps"],
            "committees": committee.get("committees") or [],
            "first_trade_date": min(bucket["dates"]) if bucket["dates"] else None,
            "last_trade_date": max(bucket["dates"]) if bucket["dates"] else None,
            "tracked": bool(tracked),
            "tracked_tiers": (tracked or {}).get("tiers") or [],
            "performance": ({
                "avg_alpha_pct": stats.get("avg_alpha_pct"),
                "win_rate": stats.get("win_rate"),
                "n_priced_buys": stats.get("n_priced_buys"),
                "confidence": stats.get("confidence"),
            } if stats else None),
            "external": external or None,
        })
    profiles.sort(key=lambda row: (-row["trades"], -row["disclosed_volume_midpoint"],
                                   row["politician"]))
    for index, profile in enumerate(profiles, start=1):
        profile["rank"] = index
    return profiles[:top_n] if top_n else profiles


# ---------------- unusual-timing composite ----------------

def _component_scores(row, config, *, news_index, news_live, late_filing_days):
    """Each component in [0,1], or None where it is not computable for this row. None and
    0.0 mean different things and are kept apart all the way into the payload: 0.0 is
    "measured, unremarkable", None is "could not be measured"."""
    components = {}

    amount_lower = row.get("amount_lower")
    components["size"] = (min(1.0, amount_lower / config["size_reference"])
                          if amount_lower else None)

    components["committee_overlap"] = 1.0 if "COMMITTEE_OVERLAP" in (row.get("flags") or ()) else (
        0.0 if committee_profile(row.get("representative")) else None)

    excess = row.get("excess_return_vs_spy_pct")
    components["excess_return"] = (min(1.0, max(0.0, excess) / config["excess_return_reference"])
                                   if excess is not None else None)

    delay = row.get("filing_delay_days")
    if delay is None:
        components["filing_delay"] = None
    else:
        span = max(1, config["filing_delay_reference"] - late_filing_days)
        components["filing_delay"] = min(1.0, max(0, delay - late_filing_days) / span)

    components["news_proximity"] = (
        1.0 if news_live and preceded_news(row, news_index,
                                           lookahead_days=config["news_lookahead_days"])
        else (0.0 if news_live else None))
    return components


def unusual_timing(rows, *, config=None, late_filing_days=45):
    """Disclosures that are unusual on several independently-computable axes at once.

    Not an allegation, and not a ranking of people - a ranking of *rows*, by how far size,
    committee jurisdiction, market-relative outcome, disclosure lag, and (when the news
    feed is live) headline precedence stack up on the same disclosure.

    **Missing evidence lowers the score; it is not excused.** The denominator is the total
    weight of every component active for the run, not just the ones this row happened to
    support. Averaging over available components only would invert the whole ranking: a
    row measurable on two saturated axes would score a perfect 1.0 and outrank a row that
    is genuinely unusual on four, purely because less was known about it. A component
    switched off run-wide (headline precedence, when the news feed is in demo mode) leaves
    the denominator entirely, since penalizing every row equally for it would only
    compress the scale.

    Equity rows only - a municipal bond ladder has no ticker to check jurisdiction or
    price against - and at most ``max_per_filer`` rows per person, so one filer's bulk
    annual disclosure cannot crowd out every other name in the panel.
    """
    config = {**(_config().get("unusual_timing") or {}), **(config or {})}
    weights = config.get("weights") or {}
    news_index, news_live = news_proximity_index()
    active = [name for name in weights if name != "news_proximity" or news_live]
    total_weight = sum(weights.get(name, 0) for name in active)
    if not total_weight:
        return {"config": {key: value for key, value in config.items() if key != "weights"},
                "weights": weights, "news_component_active": news_live,
                "candidates": 0, "results": []}
    ranked = []
    for row in rows:
        if not row.get("symbol"):
            continue
        components = _component_scores(row, config, news_index=news_index,
                                       news_live=news_live, late_filing_days=late_filing_days)
        available = {name: value for name, value in components.items() if value is not None}
        if len(available) < config.get("minimum_components", 2):
            continue
        score = sum(weights.get(name, 0) * value for name, value in available.items()) / total_weight
        if score <= 0:
            continue
        ranked.append({
            "ticker": row.get("symbol"),
            "asset_description": row.get("asset_description"),
            "representative": row.get("representative"),
            "chamber": row.get("chamber"),
            "transaction_type": row.get("transaction_type"),
            "transaction_date": row.get("transaction_date"),
            "disclosure_date": row.get("disclosure_date"),
            "amount": row.get("amount"),
            "filing_delay_days": row.get("filing_delay_days"),
            "return_since_purchase_pct": row.get("return_since_purchase_pct"),
            "excess_return_vs_spy_pct": row.get("excess_return_vs_spy_pct"),
            "committee_overlap": row.get("committee_overlap") or None,
            "components": {name: round(value, 4) for name, value in available.items()},
            "components_unavailable": sorted(name for name, value in components.items()
                                             if value is None),
            "unusual_score": round(score, 4),
        })
    ranked.sort(key=lambda row: (-row["unusual_score"], row.get("disclosure_date") or ""))
    top_n = config.get("top_n", 15)
    max_per_filer = config.get("max_per_filer", 2)
    selected, per_filer = [], {}
    for entry in ranked:
        key = canonical_name(entry.get("representative"))
        if per_filer.get(key, 0) >= max_per_filer:
            continue
        per_filer[key] = per_filer.get(key, 0) + 1
        selected.append(entry)
        if len(selected) >= top_n:
            break
    for index, entry in enumerate(selected, start=1):
        entry["rank"] = index
    return {
        "config": {key: value for key, value in config.items() if key != "weights"},
        "weights": weights,
        "news_component_active": news_live,
        "candidates": len(ranked),
        "results": selected,
    }


# ---------------- external reference ----------------

def merge_external_into_leaderboard(leaderboard):
    """Attach the third-party 2025 figures to each leaderboard row under their own
    distinctly-named keys (``external_*``), leaving every pipeline-computed field
    untouched. Deliberately not folded into ``performance_score`` or ``avg_alpha_pct``:
    the two are different estimators over different windows and combining them into one
    number would produce a figure neither methodology supports."""
    merged = []
    for row in leaderboard:
        external = external_profile(row.get("politician"))
        entry = dict(row)
        if external:
            entry["external_return_2025_pct"] = external.get("return_2025_pct")
            entry["external_trades_2025"] = external.get("trades_2025")
            entry["external_party"] = external.get("party")
            entry["external_seat"] = external.get("seat")
        tracked = tracked_profile(row.get("politician"))
        entry["tracked"] = bool(tracked)
        entry["tracked_tiers"] = (tracked or {}).get("tiers") or []
        merged.append(entry)
    return merged
