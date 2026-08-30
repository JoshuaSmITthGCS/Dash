"""Structural trend exposure: how exposed is a company to a multi-year demand driver?

Everything else in this pipeline is backward-looking. This layer answers a different
question, and the central risk in answering it is that naive implementations turn into
performance-chasing - they end up buying whatever has already run.

The evidence on that failure mode is unusually blunt. Ben-David, Franzoni, Kim & Moussawi
(*Review of Financial Studies* 2023) find specialized/thematic ETFs lose about 30%
risk-adjusted over their first five years, persistently generating negative alphas of
roughly -3.1% per year, and that this is "driven by the overvaluation of the underlying
stocks at the time of the launch" rather than by fees. These products launch near hype
peaks because hype is what makes them marketable.

So the design rule is hardcoded rather than configurable: **price momentum contributes
exactly zero to theme exposure**, and a name already in the top valuation decile is
excluded or flagged. Exposure is measured from leading fundamental evidence - segment
revenue, the trend in how a company describes itself in its own filings, supply-chain ties
to confirmed spenders, and the capex plans of the companies actually writing the cheques.

The output is deliberately a *separate screen*, not a modifier on the fundamentals score
and not a blended component. Folding a forward-looking thematic bet into the fundamentals
score would make that score uninterpretable - nobody could tell whether a stock ranked
highly because it was cheap and profitable or because it was tagged with a fashionable
theme. Kept separate, the screen can do the one genuinely useful thing here: surface
companies with high structural exposure whose valuations have *not* already gone euphoric.

Themes are declared as config files in ``pipeline/themes/``. Adding the next big trend is
a new YAML file, not a code change.
"""

import os
from datetime import datetime, timezone

from common import LOG
from peer_groups import peer_group
from theme_trend import biggest_players, evaluate_theme

HERE = os.path.dirname(os.path.abspath(__file__))
THEMES_DIR = os.path.join(HERE, "themes")
SECTOR_PEER_LIMIT_PER_THEME = 20
# Total new sector-peer candidates a run may add, across every theme. A per-theme cap alone
# made the cost of the theme layer linear in the number of themes: each candidate costs up to
# two 10-K documents, which are megabytes each and live in a CI cache with a hard size limit,
# so eleven themes at twenty peers apiece would have quietly multiplied the run's footprint by
# five. The budget is spent round-robin, so a theme is never starved by whichever one happens
# to be evaluated first, and adding the twelfth theme costs nothing new.
TOTAL_SECTOR_PEER_BUDGET = 120
# Published rows per candidate group, per theme. Applied per group rather than to the whole
# theme: a single global cap let the already-recognized leaders crowd out the
# sector-connected names entirely (the shipped screen published 15 rows of which 3 were
# sector-connected, out of 74 scored), which hollows out the one group the screen exists to
# surface. Each group now gets its own slots and each reports its full pre-truncation size.
PUBLISHED_ROWS_PER_GROUP = 20

# Demand-side capex growth for the companies whose spending drives a theme. Both names are
# the same measurement: ``hyperscaler_capex_growth`` is the AI-specific spelling that shipped
# first, ``spender_capex_growth`` the general one a grid, defense, fab or pharma theme should
# use, since "hyperscaler" describes only one theme's cheque-writers.
CAPEX_PULL_THROUGH_SIGNALS = ("hyperscaler_capex_growth", "spender_capex_growth")

# Signals that describe what a company is building. Rewarded.
LEADING_SIGNALS = ("segment_revenue_share", "filing_keyword_density_trend",
                   "transcript_theme_salience", "customer_concentration_to_spenders",
                   *CAPEX_PULL_THROUGH_SIGNALS, "backlog_growth")
# Signals that describe what a share price has already done. Never rewarded: these are the
# mechanism by which a thematic screen becomes a momentum screen wearing a disguise.
FORBIDDEN_SIGNALS = ("price_momentum", "return_12m", "return_1m", "distance_from_52w_high",
                     "social_mentions", "thematic_etf_inclusion", "analyst_upgrades")

# Signals sourced from mandatory SEC disclosure -- ASC 280 segment reporting and the >=10%
# major-customer rule -- rather than inferred from SIC/industry scope, keyword lists, or
# transcript language. Sautner-van Lent-Vilkov-Zhang (J. Finance 2023) and Hassan-Hollander-
# van Lent-Tahoun (QJE 2019) validate firm-level text signals, but the professional standard
# (MSCI Relevance Score, FactSet RBICS, S&P Kensho) still resolves exposure to a disclosed
# revenue-share number first and treats text as a corroborating, subordinate layer. Theme
# signal weights follow that ordering (see pipeline/themes/*.yaml); UNDISCLOSED_EXPOSURE_DISCOUNT
# below is the second half of it, for the case a text signal alone still clears the bar.
DISCLOSURE_SIGNALS = ("segment_revenue_share", "customer_concentration_to_spenders")

# Applied to the exposure score -- not just reported confidence -- when no disclosure-based
# signal resolved for a company. A name scored purely on filing language or transcript
# salience is a narrative match, not a demonstrated one: MSCI's own methodology applies an
# explicit discount factor to exposure inferred from industry mapping rather than reported
# segment revenue, and this is that same discipline.
UNDISCLOSED_EXPOSURE_DISCOUNT = 0.85

DEFAULT_GUARDRAILS = {
    "exclude_if_valuation_percentile_above": 90,
    "require_leading_signal_confirmation": True,
    "max_price_momentum_contribution": 0.0,
}


def is_theme_level(signal):
    """True when a signal's reading is a property of the theme, not of the company.

    A signal that declares a ``universe`` is measured on that universe - the cheque-writers -
    so every company scored against the theme receives the identical reading. That is correct
    as a description of the demand driver and useless as a way to tell two candidates apart:
    a number with no cross-sectional variation cannot be evidence that *this* company is
    exposed. Distinguished here so the confirmation guardrail can insist on company-specific
    evidence, rather than treating a theme-wide constant as corroboration.
    """
    return bool((signal or {}).get("universe"))


# ---------------- config loading ----------------

def _read_config(path):
    """Load one theme file. YAML when PyYAML is installed, JSON always."""
    import json
    if path.endswith(".json"):
        with open(path) as handle:
            return json.load(handle)
    try:
        import yaml
    except ImportError:
        LOG.warn(f"PyYAML not installed; skipping {os.path.basename(path)} "
                 "(install pyyaml or convert the theme to .json)")
        return None
    with open(path) as handle:
        return yaml.safe_load(handle)


def load_themes(directory=THEMES_DIR, *, include_inactive=False):
    """Every theme declared in ``directory``, validated and normalized.

    A malformed theme is skipped with a warning rather than sinking the run: one bad config
    file should not take the whole screen offline.
    """
    if not os.path.isdir(directory):
        return []
    themes = []
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith((".yaml", ".yml", ".json")):
            continue
        path = os.path.join(directory, filename)
        try:
            payload = _read_config(path)
        except Exception as exc:  # noqa: BLE001
            LOG.warn(f"theme {filename} unreadable ({type(exc).__name__}: {exc})")
            continue
        if not payload:
            continue
        theme = payload.get("theme", payload)
        problems = validate_theme(theme)
        if problems:
            LOG.warn(f"theme {filename} rejected: {'; '.join(problems)}")
            continue
        if not include_inactive and theme.get("status", "active") == "retired":
            continue
        themes.append(normalize_theme(theme))
    return themes


def validate_theme(theme):
    """Structural problems that make a theme unusable, including guardrail violations."""
    problems = []
    if not isinstance(theme, dict):
        return ["not a mapping"]
    if not theme.get("id"):
        problems.append("missing id")
    signals = theme.get("signals") or []
    if not signals:
        problems.append("no signals declared")
    for signal in signals:
        name = (signal or {}).get("name")
        if not name:
            problems.append("signal without a name")
        elif name in FORBIDDEN_SIGNALS:
            # Not a warning - a rejection. This is the guardrail the whole layer exists for.
            problems.append(f"signal '{name}' is price/hype-derived and cannot contribute "
                            "to theme exposure")
        elif name in CAPEX_PULL_THROUGH_SIGNALS and not (signal or {}).get("universe"):
            # Without a universe the provider has nobody's capex to read, so the signal never
            # answers - it silently contributes nothing while the declared weights imply it
            # does. Rejected at load time rather than discovered as missing coverage later.
            problems.append(f"signal '{name}' needs a `universe` of the companies whose "
                            "spending drives the theme")
    if len(signals) - sum(1 for signal in signals if is_theme_level(signal)) < 1:
        # A theme measured only on its cheque-writers ranks every candidate identically.
        problems.append("no company-specific signal declared; every candidate would score "
                        "the same")
    guardrails = theme.get("guardrails") or {}
    momentum_cap = guardrails.get("max_price_momentum_contribution", 0.0)
    if momentum_cap:
        problems.append("max_price_momentum_contribution must be 0")
    return problems


def normalize_theme(theme):
    """Fill defaults and normalize signal weights to sum to one."""
    signals = [dict(signal) for signal in theme.get("signals") or []]
    total = sum(float(signal.get("weight", 0)) for signal in signals)
    for signal in signals:
        weight = float(signal.get("weight", 0))
        signal["weight"] = round(weight / total, 4) if total else round(1 / len(signals), 4)
        signal["leading"] = bool(signal.get("leading", signal.get("name") in LEADING_SIGNALS))
        signal["theme_level"] = is_theme_level(signal)
    return {
        **theme,
        "status": theme.get("status", "active"),
        "signals": signals,
        "guardrails": {**DEFAULT_GUARDRAILS, **(theme.get("guardrails") or {})},
        "scoring": {"output": "theme_exposure_score", "min_signals_required": 2,
                    **(theme.get("scoring") or {})},
        "keywords": theme.get("keywords") or {},
        "seed_tickers": [str(t).upper() for t in theme.get("seed_tickers") or []],
        "sic_codes": theme.get("sic_codes") or [],
        "sectors": [str(sector).strip().lower() for sector in theme.get("sectors") or []],
        "industries": [str(term).strip().lower() for term in theme.get("industries") or []],
        "taxonomy_tag": theme.get("taxonomy_tag"),
        # One of five macro demand drivers (see theme_graph.ROOT_DRIVER_TAXONOMY), coarser than
        # taxonomy_tag on purpose: it exists so theme_graph can tell "these two themes are the
        # same buildout wearing two costumes" (same root_driver_tag) apart from "these two themes
        # happen to share a supplier" (different root_driver_tag, connected some other way).
        # Null for themes that are not claims about one of those five drivers - cybersecurity and
        # digital payments are durable businesses, not a growth-chain root, and forcing them into
        # one of the five would be a worse answer than admitting they are outside this taxonomy.
        "root_driver_tag": theme.get("root_driver_tag"),
        "chain": theme.get("chain") or {},
        "roles": {
            role: {
                "industries": [str(term).strip().lower()
                               for term in (rule or {}).get("industries") or []],
                "tickers": [str(ticker).upper() for ticker in (rule or {}).get("tickers") or []],
            }
            for role, rule in (theme.get("roles") or {}).items()
        },
    }


def assign_role(theme, row):
    """Where a company sits in this theme's chain: root, enabler, supplier, infrastructure,
    service.

    A theme is a sequence, not a bag. The company selling the end product and the company
    selling it the equipment are exposed to the same driver at different points, they lead at
    different times, and a screen that reports only "exposed" cannot tell you which stage the
    money is currently arriving at. Declared per theme rather than globally, because the role
    is a property of the relationship: a utility is the root of an electrification chain and a
    customer of a grid-equipment chain.

    Named tickers win over industry rules, since the whole point of naming one is that its
    classification does not capture what it does here.
    """
    ticker = str(row.get("ticker") or "").upper()
    industry = str(row.get("industry") or "").strip().lower()
    rules = theme.get("roles") or {}
    for role, rule in rules.items():
        if ticker and ticker in set(rule.get("tickers") or ()):
            return role
    if not industry:
        return None
    for role, rule in rules.items():
        if any(term in industry for term in rule.get("industries") or ()):
            return role
    return None


def in_theme_scope(theme, row):
    """Whether a company is even a candidate for this theme, by declared scope.

    A filing-language screen with no scope will happily rank a regional bank as top exposure
    to an AI hardware buildout: banks describe their own data centers, and a theme-wide capex
    reading then supplies the corroborating signal, so the row clears the minimum on evidence
    that says nothing about building accelerators. Scope bounds the population up front -
    declaring where a supply chain can physically live, which is a statement about the theme
    rather than a score adjustment, and cheap: an out-of-scope name never triggers a filing
    fetch at all.

    Two levels, because one is not enough. ``sectors`` is the outer bound, and it is coarse:
    a chip-equipment maker, a trucking company and a landscaping distributor are all
    "Industrials", so sector alone still admits names that build none of it. ``industries``
    matches the finer Yahoo classification (``Semiconductors``, ``Electrical Equipment &
    Parts``, ``Utilities - Regulated Water``), as case-insensitive substrings so a theme
    declares ``semiconductor`` once instead of chasing every spelling of
    "Semiconductor Equipment & Materials". Both must pass when both are declared.

    A theme's own ``seed_tickers`` are always in scope. They are the anchors the config author
    declared by name, and a vendor taxonomy built for the whole market routinely understates
    what one of them does: Eaton, whose data-center power business is the reason the AI theme
    names it, is filed under "Specialty Industrial Machinery" alongside pump and compressor
    makers. Admitting that industry wholesale to keep one anchor would drag in every machinery
    company in the market; naming the anchor is the narrower, more honest exception. It still
    only makes the company a candidate - its filing evidence decides everything after that.

    A row whose industry never resolved falls back to the sector bound rather than being
    dropped, since an absent classification is not evidence of anything. Themes that declare
    no scope are unbounded, exactly as before.
    """
    if str(row.get("ticker") or "").upper() in set(theme.get("seed_tickers") or ()):
        return True
    sectors = theme.get("sectors") or ()
    if sectors and str(row.get("sector") or "").strip().lower() not in set(sectors):
        return False
    industries = theme.get("industries") or ()
    industry = str(row.get("industry") or "").strip().lower()
    if not industries or not industry:
        return True
    return any(term in industry for term in industries)


# ---------------- signal normalization ----------------

def normalize_signal(name, value):
    """Map one raw signal reading onto 0-100. None passes through as unanswered.

    Each signal has its own natural scale, so each gets its own mapping rather than a shared
    percentile - a 40% revenue share and a 40% rise in keyword density are not the same claim.
    """
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if name == "segment_revenue_share":
        # A fraction of revenue. Half the business in the theme is already near-total exposure.
        return round(min(100.0, max(0.0, value * 200)), 1)
    if name in ("filing_keyword_density_trend", "transcript_theme_salience"):
        # Year-over-year change in how much of the company's own language is about this.
        return round(min(100.0, max(0.0, 50 + value * 100)), 1)
    if name == "customer_concentration_to_spenders":
        # Share of revenue from named customers who are confirmed theme spenders.
        return round(min(100.0, max(0.0, value * 250)), 1)
    if name in (*CAPEX_PULL_THROUGH_SIGNALS, "backlog_growth"):
        # Demand-side growth rate: 30% growth reads as a strong pull-through signal.
        return round(min(100.0, max(0.0, 50 + value * 165)), 1)
    return round(min(100.0, max(0.0, value)), 1)


SOURCE_REASON = {
    "published_leader": "already a published top research score",
    "portfolio": "one of your holdings",
    "sector_peer": "a peer-group neighbour of this theme's anchors, not yet a published "
                   "research score",
}

ROLE_REASON = {
    "root": "the root of this chain, selling the product the theme is named for",
    "enabler": "an enabler, selling what makes the core product usable at scale",
    "supplier": "a supplier into this chain",
    "infrastructure": "infrastructure - what has to be built before the rest of the chain works",
    "service": "a service provider to this chain",
}


def _percent(value, digits=0):
    return f"{value * 100:+.{digits}f}%"


def _signal_reason(name, raw, score):
    """One resolved signal as a sentence about the company, not a metric name.

    A row that reports "2 leading signals" has told the reader nothing they can check. The
    point of publishing evidence is that the reader can disagree with it, which requires
    saying what was actually measured and which way it pointed.
    """
    if raw is None:
        return None
    try:
        raw = float(raw)
    except (TypeError, ValueError):
        return None
    if name == "filing_keyword_density_trend":
        direction = "more" if raw >= 0 else "less"
        return (f"its latest 10-K devotes {_percent(abs(raw))[1:]} {direction} of its language "
                "to this theme than the prior year's")
    if name == "transcript_theme_salience":
        return (f"its earnings calls discuss this theme {_percent(raw)} more than a year ago"
                if raw >= 0 else
                f"its earnings calls discuss this theme {_percent(abs(raw))[1:]} less than a "
                "year ago")
    if name == "segment_revenue_share":
        return f"{raw * 100:.0f}% of its reported revenue comes from the theme's segment"
    if name == "customer_concentration_to_spenders":
        return (f"{raw * 100:.0f}% of its disclosed above-10% customer revenue comes from "
                "companies confirmed to be spending on this theme")
    if name == "backlog_growth":
        return f"its remaining performance obligation (order backlog) is {_percent(raw)} year over year"
    if name in CAPEX_PULL_THROUGH_SIGNALS:
        return (f"the theme's named spenders grew capital expenditure {_percent(raw)} - a "
                "theme-wide reading, identical for every candidate, so it describes the "
                "demand and not this company")
    return f"{name.replace('_', ' ')} resolved at {score}/100"


def explain_exposure(theme, result, row):
    """Why this company appears in this section, in clauses a reader can check.

    Assembled from what the scoring actually did rather than written alongside it, so the
    explanation cannot drift from the score: every clause below is derived from the same
    ``result`` the row publishes. The order is the order a sceptical reader needs - how it got
    here, what it does in the chain, what its own filings said, what was measured about the
    theme rather than about it, why it is flagged, and how much of the evidence was missing.
    """
    clauses = []
    source = SOURCE_REASON.get(row.get("candidate_source"))
    if source:
        clauses.append(f"In this theme because it is {source}")
    role = ROLE_REASON.get(row.get("role"))
    if role:
        clauses.append(f"Placed as {role}")

    contributions = result.get("signals") or []
    fired = set(result.get("leading_signals_fired") or [])
    company = [item for item in contributions if not item.get("theme_level")]
    confirmed = [item for item in company if item["name"] in fired]
    for item in (confirmed or company):
        reason = _signal_reason(item["name"], item.get("raw"), item.get("score"))
        if reason:
            clauses.append(reason[0].upper() + reason[1:])
    if company and not confirmed:
        clauses.append("None of its own signals cleared the confirmation bar, so the exposure "
                       "is measured but not confirmed")
    for item in contributions:
        if item.get("theme_level"):
            reason = _signal_reason(item["name"], item.get("raw"), item.get("score"))
            if reason:
                clauses.append(reason[0].upper() + reason[1:])

    for exclusion in result.get("excluded_by") or []:
        clauses.append(f"Flagged, not promoted: {exclusion}")

    confidence = result.get("confidence")
    answered = result.get("signals_answered")
    declared = len(theme.get("signals") or [])
    if confidence is not None and declared:
        clauses.append(f"{answered} of {declared} declared signals resolved, carrying "
                       f"{confidence * 100:.0f}% of this theme's signal weight")
    if result.get("disclosure_backed") is False:
        clauses.append(
            "No disclosed segment revenue or major-customer link resolved for this company - "
            f"exposure rests on filing/transcript language alone, scored at "
            f"{UNDISCLOSED_EXPOSURE_DISCOUNT * 100:.0f}% of what the same signals would carry "
            "with disclosure behind them")
    return clauses


def score_theme_exposure(theme, signal_values, *, valuation_percentile=None):
    """Score one company against one theme. Pure - takes readings, returns a verdict.

    ``signal_values`` maps signal name to its raw reading. Returns a dict carrying the score,
    which signals answered, and whether any guardrail excluded the name. An excluded company
    still gets a score, because knowing that a euphorically-valued name has real exposure is
    useful; it is simply flagged so it cannot be presented as an opportunity.
    """
    guardrails = theme["guardrails"]
    contributions, leading_fired, theme_level_fired = [], [], []
    for signal in theme["signals"]:
        name = signal["name"]
        if name in FORBIDDEN_SIGNALS:
            continue
        score = normalize_signal(name, signal_values.get(name))
        if score is None:
            continue
        theme_level = signal.get("theme_level", is_theme_level(signal))
        contributions.append({"name": name, "score": score, "weight": signal["weight"],
                              "leading": signal["leading"], "theme_level": theme_level,
                              "raw": signal_values.get(name)})
        if signal["leading"] and score > 50:
            # Kept apart deliberately: a theme-level reading is identical for every candidate,
            # so counting it as confirmation would confirm every company at once.
            (theme_level_fired if theme_level else leading_fired).append(name)

    company_answered = sum(1 for item in contributions if not item["theme_level"])
    required = theme["scoring"].get("min_signals_required", 2)
    if len(contributions) < required:
        return {
            "theme_id": theme["id"], "theme_exposure_score": None, "eligible": False,
            "reason": f"only {len(contributions)} of {required} required signals resolved",
            "signals": contributions, "signals_answered": len(contributions),
            "company_signals_answered": company_answered,
            "disclosure_backed": any(item["name"] in DISCLOSURE_SIGNALS for item in contributions),
        }

    total_weight = sum(item["weight"] for item in contributions)
    score = round(sum(item["score"] * item["weight"] for item in contributions) / total_weight, 1)
    # Confidence is how much of the declared signal weight actually answered, so a theme
    # scored from one cheap signal cannot masquerade as a fully-evidenced one.
    declared = sum(signal["weight"] for signal in theme["signals"]
                   if signal["name"] not in FORBIDDEN_SIGNALS)
    confidence = round(total_weight / declared, 2) if declared else 0.0

    # A company with no disclosed segment revenue or major-customer link still clears
    # min_signals_required on filing/transcript language plus a capex or backlog reading --
    # confidence reports that gap but the score itself does not, which is exactly how a
    # narrative-only name would come to rank alongside a disclosure-backed one. See
    # DISCLOSURE_SIGNALS above.
    disclosure_backed = any(item["name"] in DISCLOSURE_SIGNALS for item in contributions)
    if not disclosure_backed:
        score = round(score * UNDISCLOSED_EXPOSURE_DISCOUNT, 1)

    exclusions = []
    ceiling = guardrails.get("exclude_if_valuation_percentile_above")
    # The valuation percentile here is "expensive-ness": 100 means the richest in its sector.
    if ceiling is not None and valuation_percentile is not None and valuation_percentile > ceiling:
        exclusions.append(f"valuation already in the top {100 - ceiling}% of its sector - "
                          "the pattern thematic funds are documented to buy into")
    if guardrails.get("require_leading_signal_confirmation") and not leading_fired:
        exclusions.append(
            "no company-specific leading signal fired; exposure rests on lagging evidence or "
            "on a theme-wide reading every candidate shares"
            if theme_level_fired else
            "no leading signal fired; exposure rests on lagging evidence only")

    return {
        "theme_id": theme["id"],
        "theme_exposure_score": score,
        "confidence": confidence,
        "disclosure_backed": disclosure_backed,
        "eligible": not exclusions,
        "excluded_by": exclusions,
        # Company-specific only: what this company's own filings say, which is the claim the
        # confirmation guardrail and the UI's "leading signals" column both mean.
        "leading_signals_fired": leading_fired,
        "theme_level_signals_fired": theme_level_fired,
        "signals": contributions,
        "signals_answered": len(contributions),
        "company_signals_answered": company_answered,
    }


# ---------------- candidate selection ----------------

def expand_theme_candidates(themes, research, ranked, portfolio_symbols,
                             *, limit_per_theme=SECTOR_PEER_LIMIT_PER_THEME,
                             total_peer_budget=TOTAL_SECTOR_PEER_BUDGET):
    """Widen the theme-scoring candidate set beyond published leaders + holdings.

    Scoring a theme only against the published leaderboard means a stock that isn't
    already a top fundamentals score - exactly the kind of name a sector-tailwind thesis
    is trying to catch before it re-rates - never gets evaluated against a theme at all.
    This adds a bounded set of sector/peer-group neighbours of each theme's seed tickers,
    drawn only from names already scored this run: no new market-data fetches, and the
    SEC EDGAR theme-signal lookups this feeds are free and cached per ticker regardless.

    This is a heuristic, not the TNIC product-space peer expansion the theme config
    declares (`expand_via_tnic`) - sector/peer-group membership is a cheap, honest proxy
    that costs no new data, not a claim of doing the more rigorous thing. A peer-group
    match only makes a ticker a *candidate*; the theme's own signal scoring and
    guardrails (min_signals_required, valuation exclusion) still decide whether it
    actually shows up as exposed.

    Every candidate is tagged with where it came from (`candidate_source`:
    "published_leader" | "portfolio" | "sector_peer") so the frontend can distinguish
    "already a top pick" from "connected, not yet re-rated".

    Peers are additionally held to the theme's declared sector scope, so a business-profile
    peer group (banks, insurers, REITs) cannot pull a name into a theme whose supply chain it
    could not plausibly sit in.
    """
    portfolio_set = set(portfolio_symbols or ())
    # Funds are excluded outright. A theme is a claim about a company's place in a supply
    # chain, and a fund has neither a place in one nor a 10-K to read: it would resolve no
    # signal, and its role and industry would be a category error rather than a missing value.
    by_ticker = {row["ticker"]: row for row in research
                 if row.get("ticker") and not row.get("is_etf")}

    tagged = {row["ticker"]: {**row, "candidate_source": "published_leader"}
              for row in ranked if not row.get("is_etf")}
    for ticker in portfolio_set - set(tagged):
        row = by_ticker.get(ticker)
        if row:
            tagged[ticker] = {**row, "candidate_source": "portfolio"}

    shortlists = []
    for theme in themes:
        seed_groups = set()
        for ticker in theme.get("seed_tickers") or ():
            seed_row = by_ticker.get(ticker)
            if seed_row:
                group_id, _ = peer_group(seed_row)
                seed_groups.add(group_id)
        if not seed_groups:
            continue
        peers = [
            row for ticker, row in by_ticker.items()
            if ticker not in tagged and peer_group(row)[0] in seed_groups
            and in_theme_scope(theme, row)
        ]
        peers.sort(key=lambda row: row.get("score") or 0, reverse=True)
        shortlists.append(peers[:limit_per_theme])

    # Round-robin across themes rather than draining one list at a time: the budget is shared,
    # so taking each theme's best unclaimed peer in turn spends it on the strongest candidate
    # of every theme before the second-best of any.
    spent, exhausted = 0, False
    while shortlists and spent < total_peer_budget and not exhausted:
        exhausted = True
        for peers in shortlists:
            while peers:
                row = peers.pop(0)
                if row["ticker"] in tagged:
                    continue
                tagged[row["ticker"]] = {**row, "candidate_source": "sector_peer"}
                spent, exhausted = spent + 1, False
                break
            if spent >= total_peer_budget:
                break
    if spent >= total_peer_budget:
        LOG.info(f"Theme peer expansion stopped at the shared budget of {total_peer_budget} "
                 "candidates; lower-ranked peers were not evaluated this run")

    return list(tagged.values())


# ---------------- screen assembly ----------------

def opportunity_score(exposure, fundamental_score, valuation_percentile):
    """Rank inside a theme: exposure x business quality x valuation discipline.

    This is the direct inversion of what thematic products do. They weight by theme purity
    and buy at whatever the price is; this rewards a name only when real exposure comes with
    a business that stands up and a valuation that has not already run.
    """
    if exposure is None or fundamental_score is None:
        return None
    # valuation_percentile is expensive-ness, so cheapness is its complement. An unknown
    # percentile scores neutral rather than optimistic.
    cheapness = 50.0 if valuation_percentile is None else (100.0 - valuation_percentile)
    return round(exposure * 0.45 + fundamental_score * 0.35 + cheapness * 0.20, 1)


# How many rows per group get the fuller "why is it here rather than one place lower"
# treatment. Only the top of a list is read that closely, and the explanation is the most
# expensive thing on a row to compute and to publish.
RANK_EXPLAINED_ROWS = 5


def _cheapness(valuation_percentile):
    return 50.0 if valuation_percentile is None else 100.0 - valuation_percentile


# The valuation leg is not a percentile despite its name. ``peer_groups.canonical_percentiles``
# publishes a *tier* - cheapest / middle / most expensive third - and hands downstream models
# its midpoint, precisely because a rank over a few dozen noisy composite scores cannot support
# a two-significant-figure percentage (see that module's own docstring, and the published
# valuation gap it was written to stop). So this leg is described as the tier it actually is:
# writing "cheaper than 83% of its sector" would reintroduce the false precision that fix
# removed, and every name in the cheapest third would claim the same invented figure.
VALUATION_TIERS = ((70.0, "in the cheapest third of its sector"),
                   (35.0, "in the middle third of its sector"),
                   (0.0, "in the most expensive third of its sector"))


def describe_cheapness(valuation_percentile):
    if valuation_percentile is None:
        return "no peer valuation tier resolved, scored neutral"
    cheapness = _cheapness(valuation_percentile)
    for floor, label in VALUATION_TIERS:
        if cheapness >= floor:
            return label
    return VALUATION_TIERS[-1][1]


SHORT_TIERS = {"in the cheapest third of its sector": "the cheapest third",
               "in the middle third of its sector": "the middle third",
               "in the most expensive third of its sector": "the most expensive third",
               "no peer valuation tier resolved, scored neutral": "no resolved tier"}


def _rank_components(item):
    """The three legs of the opportunity score: value, weight, and how to say it.

    ``display`` reads on its own in a breakdown; ``short`` reads inside a sentence that has
    already named the leg, so a comparison does not say "business quality 93 against business
    quality 81".
    """
    exposure = item.get("theme_exposure_score")
    quality = item.get("fundamental_score")
    cheapness_text = describe_cheapness(item.get("valuation_percentile"))
    return [
        ("exposure", exposure, 45,
         f"exposure {exposure:.0f}" if exposure is not None else None,
         f"{exposure:.0f}" if exposure is not None else None),
        ("business quality", quality, 35,
         f"business quality {quality:.0f}" if quality is not None else None,
         f"{quality:.0f}" if quality is not None else None),
        ("valuation", _cheapness(item.get("valuation_percentile")), 20,
         cheapness_text, SHORT_TIERS.get(cheapness_text, cheapness_text)),
    ]


def explain_rank(item, index, group, source_row=None):
    """Why this row sits at this position, and how solid the inputs to that are.

    The exposure score says how exposed a company is; it does not say why the company above
    it is above it. That question is answered by three numbers pulling in different
    directions - real exposure, a business that stands up, and a price that has not already
    run - so the answer is the decomposition, plus whichever leg actually separated this row
    from the next one.

    The third clause is the one that matters most on this screen. Statement metrics are only
    fetched for a shortlist of the universe, and the sector-connected group exists precisely
    to surface companies that are *not* already published leaders - so most of it is ranked
    on a business-quality reading with no financial statements behind it. A ranking that
    leans on that number without saying so is overstating what it knows.
    """
    source_row = source_row or {}
    clauses = []
    total = len(group)
    score = item.get("opportunity_score")
    legs = [leg for leg in _rank_components(item) if leg[1] is not None and leg[3]]
    if score is not None and legs:
        breakdown = ", ".join(f"{leg[3]} ({leg[2]}% of that score)" for leg in legs)
        clauses.append(f"Ranks #{index + 1} of {total} on an opportunity score of {score}: "
                       f"{breakdown}")

    following = group[index + 1] if index + 1 < total else None
    if following is not None and score is not None:
        if item.get("eligible") and not following.get("eligible"):
            clauses.append(
                f"The next name ({following.get('ticker')}) is flagged rather than promoted, so "
                "it ranks below this one whatever it scores")
        elif following.get("opportunity_score") is not None:
            gaps = []
            for mine, theirs in zip(_rank_components(item), _rank_components(following)):
                if mine[1] is not None and theirs[1] is not None:
                    gaps.append((abs(mine[1] - theirs[1]), mine, theirs))
            gaps.sort(key=lambda gap: gap[0], reverse=True)
            if gaps and gaps[0][0] >= 1:
                _, mine, theirs = gaps[0]
                ticker, beaten = following.get("ticker"), following["opportunity_score"]
                if mine[1] > theirs[1]:
                    clauses.append(
                        f"It ranks above {ticker} ({beaten}) mainly on {mine[0]}: "
                        f"{mine[4]} against {theirs[4]}")
                else:
                    # The largest single gap runs against this row, which is the more
                    # interesting case: it is ahead on the total while losing the leg that
                    # separates them most, so the other two legs are carrying it.
                    others = " and ".join(leg[0] for leg in _rank_components(item)
                                          if leg[0] != mine[0])
                    clauses.append(
                        f"It ranks above {ticker} ({beaten}) despite losing to it on "
                        f"{mine[0]} ({mine[4]} against {theirs[4]}); {others} make up the "
                        "difference")
            else:
                clauses.append(
                    f"It is separated from {following.get('ticker')} "
                    f"({following['opportunity_score']}) by rounding rather than by any one leg")

    coverage = source_row.get("data_coverage")
    extended = source_row.get("extended_coverage")
    if not extended:
        percent = f" - {coverage * 100:.0f}% of that model's evidence resolved" if coverage else ""
        clauses.append(
            "Its research rating reads \"Insufficient data\" because no financial statements "
            f"were pulled for it this run{percent}. Statements go to a shortlist of the "
            "universe, and this screen exists to surface names that are not already published "
            "leaders, so the business-quality leg above rests on price-based multiples rather "
            "than on returns on capital, leverage or accounting quality")
    elif coverage:
        clauses.append(f"The business-quality leg is backed by statements: {coverage * 100:.0f}% "
                       "of the research model's evidence resolved for this company")
    return clauses


def _ranking_key(item):
    """Eligible names first (guardrails passed), then by opportunity, then by raw exposure."""
    return (
        item["eligible"],
        item["opportunity_score"] if item["opportunity_score"] is not None else -1,
        item["theme_exposure_score"],
    )


# The two groups the screen is read as: names the leaderboard already surfaces (or the user
# already owns), and names connected to the theme that it does not.
LEADER_SOURCES = ("published_leader", "portfolio")


def report_scope(themes, rows):
    """Log how many candidates each level of scope admits, and complain when one admits none.

    The industry terms are matched against a vendor's classification strings, so a renamed or
    mistyped term would otherwise fail silently and invisibly: the theme would simply publish
    nothing, which is indistinguishable from a theme whose signals did not resolve. Comparing
    the two levels makes that specific failure legible - a sector bound admitting a crowd
    while the industry terms admit nobody is a broken term list, not a quiet market.
    """
    rows = list(rows)
    classified = sum(1 for row in rows if row.get("industry"))
    for theme in themes:
        sector_only = sum(1 for row in rows
                          if in_theme_scope({**theme, "industries": []}, row))
        admitted = sum(1 for row in rows if in_theme_scope(theme, row))
        LOG.info(f"{theme['id']}: {admitted} candidates in scope "
                 f"({sector_only} by sector, {classified}/{len(rows)} rows classified)")
        if theme.get("industries") and sector_only and not admitted:
            LOG.warn(f"{theme['id']}: industry scope admitted none of {sector_only} "
                     "sector-eligible candidates - check the `industries` terms against the "
                     "classification the provider actually returns")


def build_theme_screen(themes, rows, signal_provider, *, limit_per_group=PUBLISHED_ROWS_PER_GROUP):
    """Score every row against every theme and assemble the leaderboard payload.

    ``signal_provider(ticker, theme)`` returns raw signal readings, so the network side is
    fully injectable: production passes an EDGAR-backed provider, tests pass a dict.

    Tickers are the outer loop and themes the inner one. That ordering is what lets the EDGAR
    provider hold one company's filing text while every theme is measured against it: with the
    loops the other way round, each 10-K is re-read and re-normalized once per theme, so the
    cost of adding the sixth theme would be six full passes over every filing rather than one.

    ``limit_per_group`` caps each candidate group separately rather than the theme as a whole,
    so sector-connected names get published slots instead of being crowded out by leaders that
    outrank them on a fundamentals score the theme screen is not about.
    """
    generated_at = datetime.now(timezone.utc).isoformat()
    by_ticker = {row.get("ticker"): row for row in rows if row.get("ticker")}
    per_theme = {theme["id"]: [] for theme in themes}
    trend_inputs = {}
    per_ticker = {}
    report_scope(themes, by_ticker.values())

    for ticker, row in by_ticker.items():
        valuation_percentile = row.get("valuation_expensiveness_percentile")
        if valuation_percentile is None and row.get("sector_valuation_percentile") is not None:
            # sector_valuation_percentile is cheapness; the guardrail wants its inverse.
            valuation_percentile = 100 - row["sector_valuation_percentile"]
        for theme in themes:
            if not in_theme_scope(theme, row):
                continue
            try:
                values = signal_provider(ticker, theme) or {}
            except Exception as exc:  # noqa: BLE001
                LOG.warn(f"{ticker}/{theme['id']}: signal provider failed ({type(exc).__name__})")
                continue
            if not values:
                continue
            result = score_theme_exposure(theme, values,
                                          valuation_percentile=valuation_percentile)
            if result["theme_exposure_score"] is None:
                continue
            fundamental = (row.get("components") or {}).get("fundamentals")
            entry = {
                **result,
                "ticker": ticker,
                "name": row.get("name", ticker),
                "sector": row.get("sector"),
                "industry": row.get("industry"),
                "role": assign_role(theme, row),
                "candidate_source": row.get("candidate_source"),
                "fundamental_score": fundamental,
                "valuation_percentile": valuation_percentile,
                "opportunity_score": opportunity_score(result["theme_exposure_score"],
                                                       fundamental, valuation_percentile),
            }
            # Every published row carries its own reason. A screen that ranks companies
            # against a thesis and cannot say why each one is on the list is asking to be
            # taken on trust, which is the opposite of what this layer is for.
            # Kept for the rank explanation: whether this company's business-quality leg has
            # financial statements behind it, which on this screen is usually the difference
            # between a rating and "Insufficient data".
            entry["research_coverage"] = row.get("data_coverage")
            entry["statements_available"] = bool(row.get("extended_coverage"))
            entry["why"] = explain_exposure(
                theme, result, {**row, "role": entry["role"],
                                "candidate_source": entry["candidate_source"]})
            # The scored row plus the research fields the trend layer reads. Kept beside the
            # published entry rather than merged into it: price behavior must not travel with
            # an exposure row, where it would be one careless spread away from the score.
            per_theme[theme["id"]].append(entry)
            trend_inputs.setdefault(theme["id"], []).append({**row, **entry})
            per_ticker.setdefault(ticker, []).append({
                "theme_id": theme["id"], "display_name": theme.get("display_name"),
                "theme_exposure_score": result["theme_exposure_score"],
                "opportunity_score": entry["opportunity_score"],
                "eligible": result["eligible"],
                # Carried into the index so a cross-theme reader can see how much of each
                # theme's declared signal weight actually answered, rather than reading two
                # exposures resting on one signal apiece as corroboration - and which part of
                # each chain the company plays, since a supplier to three chains and the root
                # of one are different propositions wearing the same crossing count.
                "confidence": result.get("confidence"),
                "role": entry["role"],
            })

    theme_payloads = []
    for theme in themes:
        candidates = sorted(per_theme[theme["id"]], key=_ranking_key, reverse=True)
        # Confidence, averaged across every eligible candidate this run actually scored - not
        # just the published slice. theme_graph.structural_rank reads this rather than
        # recomputing it from published rows alone, since a theme with more eligible candidates
        # than fit in published_rows_per_group would otherwise have its evidence leg measured
        # from a truncated sample instead of the population count.count/eligible_count already
        # use.
        eligible_candidates = [item for item in candidates if item["eligible"]]
        mean_confidence_eligible = (
            round(sum(item.get("confidence") or 0 for item in eligible_candidates)
                  / len(eligible_candidates), 4)
            if eligible_candidates else None
        )
        leaders = [item for item in candidates
                   if item.get("candidate_source") in LEADER_SOURCES]
        connected = [item for item in candidates
                     if item.get("candidate_source") not in LEADER_SOURCES]
        # Rank explanations are attached per group, after sorting, because the question is
        # positional: it can only be answered against the row this one beat.
        for group in (leaders, connected):
            for index, item in enumerate(group[:RANK_EXPLAINED_ROWS]):
                item["rank_reason"] = explain_rank(
                    item, index, group,
                    source_row={"data_coverage": item.get("research_coverage"),
                                "extended_coverage": item.get("statements_available")})
        theme_payloads.append({
            "id": theme["id"],
            "display_name": theme.get("display_name", theme["id"]),
            "thesis": theme.get("thesis"),
            "status": theme.get("status"),
            "version": theme.get("version"),
            "sectors": theme.get("sectors") or [],
            "industries": theme.get("industries") or [],
            "taxonomy_tag": theme.get("taxonomy_tag"),
            "root_driver_tag": theme.get("root_driver_tag"),
            "chain": theme.get("chain") or {},
            "guardrails": theme["guardrails"],
            "signals": [{"name": signal["name"], "weight": signal["weight"],
                         "leading": signal["leading"],
                         "theme_level": signal.get("theme_level", is_theme_level(signal)),
                         "source": signal.get("source")}
                        for signal in theme["signals"]],
            "count": len(candidates),
            "eligible_count": len(eligible_candidates),
            "mean_confidence_eligible": mean_confidence_eligible,
            # Pre-truncation sizes, so the UI can say how much of each group it is showing
            # rather than implying the published rows are all that scored.
            "group_counts": {"leaders": len(leaders), "connected": len(connected)},
            "published_rows_per_group": limit_per_group,
            "rows": leaders[:limit_per_group] + connected[:limit_per_group],
            # Two questions the exposure leaderboard cannot answer, kept in their own blocks:
            # is this trend actually moving (and already paid for), and who are its biggest
            # names. Both are computed across every scored member, not the published slice.
            "trend": evaluate_theme(trend_inputs.get(theme["id"]) or []),
            "biggest_players": biggest_players(trend_inputs.get(theme["id"]) or []),
        })

    return {
        "generated_at": generated_at,
        "themes": theme_payloads,
        "by_ticker": per_ticker,
        "principle": "A separate screen, never a modifier on the fundamentals score. Price "
                     "momentum contributes zero by construction, and names already in the top "
                     "valuation decile are flagged rather than promoted - specialized ETFs "
                     "have historically lost about 30% risk-adjusted over five years by doing "
                     "the opposite (Ben-David, Franzoni, Kim & Moussawi, RFS 2023).",
    }


def empty_screen(reason):
    """A well-formed but empty screen, so the frontend contract holds when signals are absent."""
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "themes": [],
            "by_ticker": {}, "unavailable_reason": reason,
            "principle": "Theme exposure requires SEC filing signals; none were available."}
