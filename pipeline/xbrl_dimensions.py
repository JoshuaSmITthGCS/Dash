"""Dimensional XBRL fact extraction from a raw filing document.

``SecEdgarClient.company_facts`` and ``company_concept`` call the SEC's ``companyfacts``
and ``companyconcept`` APIs, and both APIs collapse every context down to its numeric value
and drop the ``segment`` dimensions entirely - the aggregator is documented to serve "the
default (non-dimensional) value" only. A fact tagged against a segment axis (customer
concentration by benchmark, revenue by geography, backlog by satisfaction period) either
never appears in that response or appears alongside an unrelated undimensioned total, and
there is no way to tell which happened from the response shape alone. Both look like
"the company didn't tag it."

The dimensions survive in the filing itself. Every XBRL instance - and every Inline XBRL
document, which is what ``filing_document`` actually fetches for a modern 10-K/10-Q, since
the primary document *is* the instance with facts embedded via ``ix:`` tags - carries
``<context>`` elements whose ``<segment>`` block lists the axis/member pairs a fact was
reported against. This module reads those contexts directly, so a fact with segment
qualifiers is returned *as* a dimensioned fact instead of being silently dropped or folded
into a total it does not belong to.
"""

import re
import xml.etree.ElementTree as ET

_SCALE_UNSAFE = re.compile(r"[^0-9eE+\-.]")


def _local(tag):
    """Strip a namespace URI off an ElementTree tag: ``{ns}Foo`` -> ``foo``."""
    return tag.rsplit("}", 1)[-1].lower()


def _local_name(value):
    """Strip a prefix off a QName-shaped value: ``us-gaap:FooMember`` -> ``foomember``."""
    return str(value or "").rsplit(":", 1)[-1].strip().lower()


def _find_by_local(node, name):
    return [child for child in node.iter() if _local(child.tag) == name]


def parse_contexts(root):
    """Every ``<context>`` in the document, keyed by its ``id``.

    Each entry carries the axis/member dimensions the context's segment declares (empty for
    an undimensioned, entity-wide context) and the period it covers.
    """
    contexts = {}
    for node in _find_by_local(root, "context"):
        context_id = node.get("id")
        if not context_id:
            continue
        dimensions = {}
        for member in _find_by_local(node, "explicitmember"):
            axis = _local_name(member.get("dimension"))
            value = _local_name(member.text)
            if axis and value:
                dimensions[axis] = value
        period = {}
        for tag in ("instant", "startdate", "enddate"):
            found = next(iter(_find_by_local(node, tag)), None)
            if found is not None and found.text:
                period[tag.replace("date", "_date")] = found.text.strip()
        contexts[context_id] = {"dimensions": dimensions, "period": period}
    return contexts


def _scaled_value(raw_text, element):
    if raw_text is None:
        return None
    cleaned = _SCALE_UNSAFE.sub("", raw_text.strip())
    if not cleaned or cleaned in {"-", "."}:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    scale = element.get("scale")
    if scale is not None:
        try:
            value *= 10 ** int(scale)
        except ValueError:
            pass
    if element.get("sign") == "-":
        value = -value
    return value


def _matches_concept(node, target, taxonomy):
    """True if ``node`` reports ``target`` (bare local name, already lowercased).

    An Inline XBRL fact's ``name`` attribute carries a taxonomy prefix (``us-gaap:Foo``),
    so a same-named concept in a different taxonomy (``srt:Foo``, ``dei:Foo``) is rejected
    rather than matched. A plain instance's own element tag carries no prefix to check, so
    it is accepted on local-name match alone.
    """
    name_attr = node.get("name")
    if name_attr:
        prefix, _, local_name = str(name_attr).rpartition(":")
        if _local_name(local_name) != target:
            return False
        return not prefix or prefix.strip().lower() == taxonomy.lower()
    return _local(node.tag) == target


def dimensional_facts(document_text, concept, taxonomy="us-gaap"):
    """Every reported value of ``concept`` in a filing, each tagged with its dimensions.

    Covers both a standalone XBRL instance (``<us-gaap:Concept contextRef="c1">``) and
    Inline XBRL (``<ix:nonFraction name="us-gaap:Concept" contextRef="c1">`` /
    ``ix:nonNumeric`` for non-numeric facts embedded in the rendered filing). Returns
    ``[]`` rather than raising on a document that is not well-formed XML, since a filing
    that fails to parse this way is exactly as unavailable as one with no matching tag.
    """
    target = concept.lower()
    try:
        root = ET.fromstring(document_text)
    except ET.ParseError:
        return []
    contexts = parse_contexts(root)
    facts = []
    for node in root.iter():
        if not _matches_concept(node, target, taxonomy):
            continue
        context_id = node.get("contextRef")
        if context_id is None:
            context_id = next((v for k, v in node.attrib.items() if k.lower() == "contextref"), None)
        context = contexts.get(context_id, {"dimensions": {}, "period": {}})
        is_text_fact = _local(node.tag) == "nonnumeric"
        value = (node.text or "").strip() if is_text_fact else _scaled_value(node.text, node)
        if value is None or value == "":
            continue
        facts.append({
            "value": value,
            "context": context_id,
            "dimensions": dict(context["dimensions"]),
            "period": dict(context["period"]),
        })
    return facts


def facts_matching(facts, dimensions):
    """Facts whose context carries every requested axis:member pair (others allowed too).

    ``dimensions`` values are matched case-insensitively and without a taxonomy prefix, so
    callers can pass either ``"CustomerConcentrationRiskMember"`` or the local name alone.
    """
    required = {_local_name(axis): _local_name(member) for axis, member in dimensions.items()}
    return [fact for fact in facts
            if all(fact["dimensions"].get(axis) == member for axis, member in required.items())]


def undimensioned_facts(facts):
    """Facts reported against the entity-wide, un-segmented context only."""
    return [fact for fact in facts if not fact["dimensions"]]


def facts_on_axis(facts, axis):
    """Facts dimensioned on ``axis`` (any member), keyed by the member they were reported for.

    Used to sum a concept's bands - e.g. remaining performance obligation broken out by
    ``SatisfactionPeriodAxis`` into "within 12 months" / "beyond 12 months" - when no
    undimensioned total exists.
    """
    axis = _local_name(axis)
    by_member = {}
    for fact in facts:
        member = fact["dimensions"].get(axis)
        if member:
            by_member.setdefault(member, []).append(fact)
    return by_member
