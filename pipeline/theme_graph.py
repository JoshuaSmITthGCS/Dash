"""The connectivity graph over an already-scored theme screen.

Everything in ``themes.py`` answers one company/one theme at a time: is this company exposed,
and how much. This module answers the question that only makes sense across every theme at
once - a company that clears several themes might be genuinely diversified across independent
demand drivers, or it might be one supplier to one buildout counted several times because that
buildout happens to be split across several themes for other good reasons (Grid & Electrification
and AI Infrastructure share a root driver and are kept as separate themes anyway, since merging
them would destroy the one thing a reader can currently compare between them - see
``pipeline/themes/ai_infrastructure.yaml``). Left unmeasured, "clears six themes" reads as six
independent bets when it may be one bet counted six times.

Three things follow from that, computed here rather than left to a reader doing the arithmetic
themselves:

  * **Edge weights between a company's cleared themes.** A declared heuristic, not a fitted
    parameter, on the same footing as ``themes.expand_theme_candidates``'s sector-peer heuristic:
    same root driver outweighs a shared supplier role, which outweighs two themes that merely
    happen to share a sector. See ``edge_between``.
  * **Correlated-cluster collapse.** Three or more cleared themes sharing one root driver
    collapse to a single effective theme before anything gets called "diversified" - so a company
    real in one buildout across four of this screen's themes is reported as exposed to one
    effective driver, not four.
  * **A sequential ranking of the themes themselves** (``structural_rank``) and, per theme, an
    edge-weighted cross-theme leaderboard and a tail-exclusivity pick: the highest-opportunity
    name in a theme whose connectivity to every *other* theme is exactly zero, with an honest
    fallback ladder (relaxed-and-caveated, or no pick at all) when no such name exists.

``structural_rank`` reads price the same deliberate way ``theme_trend.evaluate_theme`` does - to
rank a theme's trend, never to rank a company's exposure - and carries the same
``contributes_to_exposure: false`` contract, checked in ``validate_data.py`` exactly like the
``trend`` block already is. Nothing here touches ``theme_exposure_score`` or ``opportunity_score``.

Pure and injectable throughout: every function takes already-computed theme payloads and the
``by_ticker`` index ``themes.build_theme_screen`` already produces, and returns plain dicts. No
network calls, no new fetches - this runs entirely off data the theme screen already computed.
"""

# Five macro demand drivers, coarser than each theme's own `taxonomy_tag`. A theme's
# `root_driver_tag` is declared in its own YAML (see pipeline/themes.py normalize_theme) and is
# `null` for themes that are not a claim about one of these five - cybersecurity and digital
# payments are durable businesses, not a growth-chain root, and forcing them into one of the
# five would be a worse answer than admitting they sit outside this taxonomy.
ROOT_DRIVER_TAXONOMY = {
    "ELECTRIFICATION_DEMAND": "Electricity demand & electrification",
    "DEGLOBALIZATION_SECURITY": "De-globalization & national security",
    "AGING_LABOR_SCARCITY": "Demographic aging & labor scarcity",
    "METABOLIC_CHRONIC_DISEASE": "Metabolic & chronic disease",
    "RESOURCE_WATER_FOOD_SECURITY": "Resource, water & food security",
}

# A company's role in a theme is what themes.assign_role already computes; these are the roles
# treated as "supplies into the chain" (as opposed to "root": the chain's own end product) for
# edge-classification purposes here.
SUPPLIER_ROLES = {"supplier", "enabler", "infrastructure"}
WORKFORCE_ROLES = {"supplier", "enabler"}

EDGE_WEIGHTS = {
    "shared_root_driver": 3.0,
    "shared_supplier": 2.0,
    "shared_workforce_constraint": 1.5,
    "coincidental_sector": 0.5,
}

# >= this many cleared themes sharing one root_driver_tag collapse to one effective theme.
CLUSTER_COLLAPSE_THRESHOLD = 3

# How many of a theme's eligible, ranked candidates the tail-exclusivity picker will walk down
# before settling for the least-connected one available (Tier 2) rather than searching the
# entire, possibly very long, connected-tier pool for a zero that may not exist.
TAIL_CANDIDATE_POOL = 30

# Cross-theme leaderboard length, matching theme_trend.biggest_players' own limit - "who are the
# most connected names here" is answered at the same depth as "who are the biggest names here".
CONNECTIVITY_LEADER_LIMIT = 8

# Weights for the sequential ranking (see structural_rank's docstring for the "soft tier gate"
# simplification this implements).
STRUCTURAL_RANK_WEIGHTS = {"evidence": 0.40, "excess_return": 0.35, "breadth": 0.25}

# Clamp bound, in percentage points, for normalizing trend.direction.relative_strength_median
# into the [0, 1] range the composite's other two legs already live in.
EXCESS_RETURN_CLAMP = 30.0


def edge_between(theme_a, theme_b):
    """Classify and weight the edge a company's dual membership creates between two themes.

    ``theme_a``/``theme_b`` are dicts carrying ``root_driver_tag`` and ``role`` - the company's
    own role in *that* theme, not the theme's in general. Order-independent.

    This is a heuristic derived from data the screen already computes (root driver tag, role),
    not a hand-curated relationship graph - the same honesty the sector-peer-expansion docstring
    in ``themes.py`` insists on for its own heuristic: declared as what it actually is, not as a
    claim of doing the more rigorous thing.
    """
    tag_a, tag_b = theme_a.get("root_driver_tag"), theme_b.get("root_driver_tag")
    if tag_a is not None and tag_a == tag_b:
        return "shared_root_driver", EDGE_WEIGHTS["shared_root_driver"]

    role_a, role_b = theme_a.get("role"), theme_b.get("role")
    if role_a in SUPPLIER_ROLES and role_b in SUPPLIER_ROLES:
        return "shared_supplier", EDGE_WEIGHTS["shared_supplier"]

    # One side traces to labor scarcity and the company's role *in that theme* is supplying or
    # enabling it - a workforce-substitution edge, distinguished from a supplier edge because it
    # is a weaker, single-direction claim: the other theme need not share anything with a
    # labor-scarcity driver, or even be a supplier-type role itself, for this to apply.
    for labor_theme in (theme_a, theme_b):
        if (labor_theme.get("root_driver_tag") == "AGING_LABOR_SCARCITY"
                and labor_theme.get("role") in WORKFORCE_ROLES):
            return "shared_workforce_constraint", EDGE_WEIGHTS["shared_workforce_constraint"]

    return "coincidental_sector", EDGE_WEIGHTS["coincidental_sector"]


def ticker_edges(cleared):
    """Every pairwise edge among one ticker's cleared (eligible) themes.

    ``cleared`` is a list of ``{theme_id, root_driver_tag, role, theme_exposure_score}``. A
    ticker cleared in N themes produces up to C(N, 2) edges - this is deliberate, not an
    oversight: it is what lets ``connectivity_score`` below grow faster than theme count for a
    company genuinely spread across several *independent* drivers, which is exactly the pattern
    ``collapse_clusters`` exists to catch when those drivers are not actually independent.
    """
    edges = []
    for i in range(len(cleared)):
        for j in range(i + 1, len(cleared)):
            edge_type, weight = edge_between(cleared[i], cleared[j])
            edges.append({
                "theme_a": cleared[i]["theme_id"],
                "theme_b": cleared[j]["theme_id"],
                "edge_type": edge_type,
                "weight": weight,
            })
    return edges


def collapse_clusters(cleared, threshold=CLUSTER_COLLAPSE_THRESHOLD):
    """Group a ticker's cleared themes by root driver; collapse any group of >= threshold.

    A root driver with three or more cleared themes collapses to one effective theme,
    represented by the member with the highest exposure score - this is the fix for "one macro
    theme in four costumes" the brief's methodology asks for: a company real in one buildout
    across several of this screen's themes should not be reported as diversified across that
    many independent bets.

    Untagged (``root_driver_tag`` is ``None``) themes never collapse into each other: a null tag
    means "not a claim about one of the five drivers", not "the same unnamed driver as every
    other untagged theme", so grouping them would manufacture a false cluster.
    """
    by_tag = {}
    for theme in cleared:
        tag = theme.get("root_driver_tag")
        if tag is None:
            continue
        by_tag.setdefault(tag, []).append(theme)

    collapsed_groups = []
    collapsed_away = set()
    for tag, members in by_tag.items():
        if len(members) < threshold:
            continue
        representative = max(members, key=lambda member: member.get("theme_exposure_score") or 0)
        collapsed_groups.append({
            "root_driver_tag": tag,
            "root_driver_label": ROOT_DRIVER_TAXONOMY.get(tag, tag),
            "original_themes": [member["theme_id"] for member in members],
            "representative": representative["theme_id"],
        })
        collapsed_away.update(member["theme_id"] for member in members
                              if member["theme_id"] != representative["theme_id"])

    effective_theme_count = len(cleared) - len(collapsed_away)
    return effective_theme_count, collapsed_groups


def ticker_connectivity(theme_lookup, cleared_entries):
    """One ticker's full connectivity block: edges, raw connectivity score, and the collapsed,
    honest diversification count.

    ``cleared_entries`` are this ticker's *eligible* rows from the theme screen's ``by_ticker``
    index - the full per-run index, not the published/truncated rows, so a ticker's connectivity
    here can never disagree with what the existing "Where the themes cross" panel already counts
    from the same source.
    """
    cleared = [{
        "theme_id": entry["theme_id"],
        "display_name": entry.get("display_name"),
        "role": entry.get("role"),
        "theme_exposure_score": entry.get("theme_exposure_score"),
        "root_driver_tag": (theme_lookup.get(entry["theme_id"]) or {}).get("root_driver_tag"),
    } for entry in cleared_entries]

    edges = ticker_edges(cleared)
    score = round(sum(edge["weight"] for edge in edges), 2)
    effective_theme_count, collapsed_groups = collapse_clusters(cleared)

    return {
        "cleared_theme_count": len(cleared),
        "effective_theme_count": effective_theme_count,
        "connectivity_score": score,
        "edges": edges,
        "collapsed_groups": collapsed_groups,
    }


def theme_incident_score(ticker, theme_id, connectivity_by_ticker):
    """Sigma edge weight of this ticker's edges touching ``theme_id`` specifically.

    Not the same number as the ticker's overall ``connectivity_score``, which also counts edges
    between two *other* themes the ticker clears that have nothing to do with this one. This is
    the number the tail-exclusivity picker tests against zero: "connected to every other theme
    this ticker clears" would be the wrong question for a per-theme pick, since it would punish a
    name for connectivity entirely outside the theme being picked for.
    """
    connectivity = connectivity_by_ticker.get(ticker)
    if not connectivity:
        return 0.0, []
    incident = [edge for edge in connectivity["edges"] if theme_id in (edge["theme_a"], edge["theme_b"])]
    return round(sum(edge["weight"] for edge in incident), 2), incident


def _normalize_excess_return(relative_strength_median):
    """``trend.direction.relative_strength_median`` (unbounded percentage points) rescaled to
    [0, 1], clamped at +/- EXCESS_RETURN_CLAMP so one outlier theme cannot dominate the composite
    other themes are compared against."""
    if relative_strength_median is None:
        return None
    clamped = max(-EXCESS_RETURN_CLAMP, min(EXCESS_RETURN_CLAMP, relative_strength_median))
    return round((clamped + EXCESS_RETURN_CLAMP) / (2 * EXCESS_RETURN_CLAMP), 4)


def _tier_label(verdict_label):
    """Display grouping only - see structural_rank's docstring. Not a ranking gate."""
    if verdict_label in ("broadening", "cooling", "unmeasured"):
        return verdict_label
    return "mixed"   # narrow leadership / strong but already priced / mixed, all read as "mixed"


def structural_rank(theme_payload):
    """A theme's position in the ranked index.

    ``composite_score = 0.40 x evidence_strength + 0.35 x normalized_excess_return + 0.25 x
    breadth``, all already-computed readings: ``mean_confidence_eligible`` (evidence, added to
    ``themes.build_theme_screen``'s payload alongside ``eligible_count``/``count`` specifically
    so this composite is measured across every eligible candidate, not just the published
    slice), ``trend.direction.relative_strength_median`` (excess return - price-derived, which is
    why this whole block carries the same ``contributes_to_exposure: false`` contract the
    ``trend`` block does and stays walled off from ``theme_exposure_score``), and
    ``eligible_count / count`` (breadth - literally how the brief itself defines the term).
    ``participation_rate`` is published for tie-breaking, matching the brief's own tie-break rule.

    On the brief's "soft tier gate": read literally, "trend status tiers the ranking, but a
    mixed/unmeasured theme with top-decile evidence can still outrank a broadening one" is only
    mathematically coherent as a single continuous composite, not a true partition-then-rank
    gate - a real gate would put every broadening theme above every mixed one regardless of
    evidence. This implements the coherent reading: one composite, computed identically for every
    theme, with ``tier`` published purely as a display grouping derived from the same trend
    verdict, never as a separate ranking pass.

    Any leg that has not resolved yet (most often excess_return, when a theme has too few priced
    members) is dropped and the remaining legs' weights renormalize - the same degrade-gracefully
    convention ``themes.score_theme_exposure`` already uses for missing signals. Returns ``None``
    when no leg resolves at all.
    """
    rows = theme_payload.get("rows") or []
    trend = theme_payload.get("trend") or {}
    verdict_label = (trend.get("verdict") or {}).get("label")
    count = theme_payload.get("count") or 0
    eligible_count = theme_payload.get("eligible_count") or 0

    evidence = theme_payload.get("mean_confidence_eligible")
    excess_return = _normalize_excess_return((trend.get("direction") or {}).get("relative_strength_median"))
    breadth = round(eligible_count / count, 4) if count else None
    participation_rate = (trend.get("breadth") or {}).get("outperforming_share")

    legs = [(evidence, STRUCTURAL_RANK_WEIGHTS["evidence"]),
            (excess_return, STRUCTURAL_RANK_WEIGHTS["excess_return"]),
            (breadth, STRUCTURAL_RANK_WEIGHTS["breadth"])]
    resolved = [(value, weight) for value, weight in legs if value is not None]
    if not resolved:
        return None
    total_weight = sum(weight for _, weight in resolved)
    composite = round(sum(value * weight for value, weight in resolved) / total_weight, 4)

    return {
        "contributes_to_exposure": False,
        "evidence_strength": evidence,
        "excess_return_normalized": excess_return,
        "breadth": breadth,
        "participation_rate": participation_rate,
        "composite_score": composite,
        "tier": _tier_label(verdict_label),
        "rows_ranked": len(rows),
    }


def connectivity_leaders(theme_payload, connectivity_by_ticker, limit=CONNECTIVITY_LEADER_LIMIT):
    """A theme's eligible, published members ranked by their overall connectivity score - the
    brief's "edge-weighted leaderboard": a name leads this list because its edges into other
    themes are real (same root driver, or a genuine supplier role elsewhere), not because it
    matched the most keyword lists.
    """
    leaders = []
    for row in theme_payload.get("rows") or []:
        if not row.get("eligible"):
            continue
        connectivity = connectivity_by_ticker.get(row["ticker"])
        if not connectivity:
            continue
        leaders.append({
            "ticker": row["ticker"],
            "role": row.get("role"),
            "theme_exposure_score": row.get("theme_exposure_score"),
            "connectivity_score": connectivity["connectivity_score"],
            "effective_theme_count": connectivity["effective_theme_count"],
            "cleared_theme_count": connectivity["cleared_theme_count"],
        })
    leaders.sort(key=lambda item: (item["connectivity_score"], item["theme_exposure_score"] or 0),
                reverse=True)
    return leaders[:limit]


def tail_pick(theme_payload, connectivity_by_ticker, theme_lookup):
    """The cleanest single-theme name in a theme, with an honest fallback ladder.

    Walks the theme's published, eligible rows in opportunity-score order (already the screen's
    own ranking - this does not introduce a second ranking criterion) looking for the first name
    whose connectivity to every *other* theme it clears is exactly zero (**Tier 1**). None found
    in the pool -> the least-connected name available, with a ``caveat`` naming every theme it is
    secondarily exposed to and why (**Tier 2**, never reported as a clean pick). No eligible
    candidate at all -> **Tier 4**, no pick, with the real reason - the honest finding the brief
    itself calls out for a theme like OT/industrial cybersecurity, produced here from data rather
    than asserted.

    There is deliberately no Tier 3: every eligible candidate is already ordered by the same
    opportunity_score the rest of the screen ranks on, so there is no separate "relax the
    ranking" step between "relax the exclusivity bar" (2) and "no pick" (4).
    """
    theme_id = theme_payload["id"]
    candidates = sorted(
        (row for row in (theme_payload.get("rows") or []) if row.get("eligible")),
        key=lambda row: row.get("opportunity_score") if row.get("opportunity_score") is not None else -1,
        reverse=True,
    )[:TAIL_CANDIDATE_POOL]

    if not candidates:
        return {
            "tier": 4,
            "ticker": None,
            "caveat": None,
            "reason": "no candidate cleared this theme's guardrails to pick from",
        }

    scored = [(row, *theme_incident_score(row["ticker"], theme_id, connectivity_by_ticker))
              for row in candidates]

    for row, incident, _edges in scored:
        if incident == 0:
            return {"tier": 1, "ticker": row["ticker"], "caveat": None,
                    "opportunity_score": row.get("opportunity_score")}

    row, incident, edges = min(scored, key=lambda item: item[1])
    parts = []
    for edge in edges:
        other_id = edge["theme_b"] if edge["theme_a"] == theme_id else edge["theme_a"]
        other_name = (theme_lookup.get(other_id) or {}).get("display_name", other_id)
        parts.append(f"{other_name} ({edge['edge_type'].replace('_', ' ')})")
    caveat = ("Secondary exposure to " + "; ".join(parts)) if parts else None
    return {"tier": 2, "ticker": row["ticker"], "caveat": caveat,
            "opportunity_score": row.get("opportunity_score")}


def build_connectivity(theme_payloads, by_ticker):
    """The full connectivity layer over an already-built theme screen.

    ``theme_payloads`` is ``build_theme_screen(...)["themes"]``; ``by_ticker`` is that same
    call's ``by_ticker`` index. Pure - no network calls, no re-scoring, just graph arithmetic
    over numbers the theme screen already published.
    """
    theme_lookup = {theme["id"]: theme for theme in theme_payloads}

    connectivity_by_ticker = {}
    for ticker, entries in (by_ticker or {}).items():
        cleared_entries = [entry for entry in (entries or []) if entry.get("eligible")]
        if not cleared_entries:
            continue
        connectivity_by_ticker[ticker] = ticker_connectivity(theme_lookup, cleared_entries)

    per_theme = {}
    for theme in theme_payloads:
        per_theme[theme["id"]] = {
            "structural_rank": structural_rank(theme),
            "connectivity_leaders": connectivity_leaders(theme, connectivity_by_ticker),
            "tail_pick": tail_pick(theme, connectivity_by_ticker, theme_lookup),
        }

    def _rank_key(theme_id):
        rank = per_theme[theme_id]["structural_rank"]
        return rank["composite_score"] if rank else -1.0

    ranked_themes = sorted((theme["id"] for theme in theme_payloads), key=_rank_key, reverse=True)

    return {
        "root_driver_taxonomy": ROOT_DRIVER_TAXONOMY,
        "methodology": (
            "Edge weights are a declared heuristic, not a fitted parameter: two eligible themes "
            "sharing one company's exposure score 3.0 (shared root driver), 2.0 (both a "
            "supplier/enabler/infrastructure role, different root drivers), 1.5 (one side a "
            "labor-scarcity theme the company supplies or enables), or 0.5 (neither - "
            "coincidental). connectivity_score sums every pairwise edge among the themes a "
            "ticker clears; effective_theme_count first collapses any run of three or more "
            "cleared themes sharing a root driver into one effective theme, so a company real in "
            "one buildout across several of this screen's themes is not counted as diversified "
            "across that many independent drivers."
        ),
        "by_ticker": connectivity_by_ticker,
        "per_theme": per_theme,
        "ranked_themes": ranked_themes,
    }
