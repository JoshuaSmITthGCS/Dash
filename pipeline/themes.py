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

HERE = os.path.dirname(os.path.abspath(__file__))
THEMES_DIR = os.path.join(HERE, "themes")
SECTOR_PEER_LIMIT_PER_THEME = 20
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
    }


def in_theme_scope(theme, row):
    """Whether a company is even a candidate for this theme, by declared sector scope.

    A filing-language screen with no scope will happily rank a regional bank as top exposure
    to an AI hardware buildout: banks describe their own data centers, and a theme-wide capex
    reading then supplies the corroborating signal, so the row clears the minimum on evidence
    that says nothing about building accelerators. ``sectors`` in the theme file bounds the
    population up front - declaring where a supply chain can physically live, which is a
    statement about the theme rather than a score adjustment, and cheap: an out-of-scope name
    never triggers a filing fetch at all.

    Themes that declare no scope are unbounded, exactly as before.
    """
    scope = theme.get("sectors") or ()
    if not scope:
        return True
    return str(row.get("sector") or "").strip().lower() in set(scope)


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
        }

    total_weight = sum(item["weight"] for item in contributions)
    score = round(sum(item["score"] * item["weight"] for item in contributions) / total_weight, 1)
    # Confidence is how much of the declared signal weight actually answered, so a theme
    # scored from one cheap signal cannot masquerade as a fully-evidenced one.
    declared = sum(signal["weight"] for signal in theme["signals"]
                   if signal["name"] not in FORBIDDEN_SIGNALS)
    confidence = round(total_weight / declared, 2) if declared else 0.0

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
                             *, limit_per_theme=SECTOR_PEER_LIMIT_PER_THEME):
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
    by_ticker = {row["ticker"]: row for row in research if row.get("ticker")}

    tagged = {row["ticker"]: {**row, "candidate_source": "published_leader"} for row in ranked}
    for ticker in portfolio_set - set(tagged):
        row = by_ticker.get(ticker)
        if row:
            tagged[ticker] = {**row, "candidate_source": "portfolio"}

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
        for row in peers[:limit_per_theme]:
            tagged[row["ticker"]] = {**row, "candidate_source": "sector_peer"}

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
    per_ticker = {}

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
                "candidate_source": row.get("candidate_source"),
                "fundamental_score": fundamental,
                "valuation_percentile": valuation_percentile,
                "opportunity_score": opportunity_score(result["theme_exposure_score"],
                                                       fundamental, valuation_percentile),
            }
            per_theme[theme["id"]].append(entry)
            per_ticker.setdefault(ticker, []).append({
                "theme_id": theme["id"], "display_name": theme.get("display_name"),
                "theme_exposure_score": result["theme_exposure_score"],
                "opportunity_score": entry["opportunity_score"],
                "eligible": result["eligible"],
                # Carried into the index so a cross-theme reader can see how much of each
                # theme's declared signal weight actually answered, rather than reading two
                # exposures resting on one signal apiece as corroboration.
                "confidence": result.get("confidence"),
            })

    theme_payloads = []
    for theme in themes:
        candidates = sorted(per_theme[theme["id"]], key=_ranking_key, reverse=True)
        leaders = [item for item in candidates
                   if item.get("candidate_source") in LEADER_SOURCES]
        connected = [item for item in candidates
                     if item.get("candidate_source") not in LEADER_SOURCES]
        theme_payloads.append({
            "id": theme["id"],
            "display_name": theme.get("display_name", theme["id"]),
            "thesis": theme.get("thesis"),
            "status": theme.get("status"),
            "version": theme.get("version"),
            "sectors": theme.get("sectors") or [],
            "guardrails": theme["guardrails"],
            "signals": [{"name": signal["name"], "weight": signal["weight"],
                         "leading": signal["leading"],
                         "theme_level": signal.get("theme_level", is_theme_level(signal)),
                         "source": signal.get("source")}
                        for signal in theme["signals"]],
            "count": len(candidates),
            "eligible_count": sum(1 for item in candidates if item["eligible"]),
            # Pre-truncation sizes, so the UI can say how much of each group it is showing
            # rather than implying the published rows are all that scored.
            "group_counts": {"leaders": len(leaders), "connected": len(connected)},
            "published_rows_per_group": limit_per_group,
            "rows": leaders[:limit_per_group] + connected[:limit_per_group],
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
