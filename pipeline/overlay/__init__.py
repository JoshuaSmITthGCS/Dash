"""Overlays: filters applied to an already-ranked composite, never inputs to the ranking.

An overlay answers "when", after the composite has answered "which". Nothing in this package
may influence a score, a rank, or a percentile. The separation is enforced by construction:
overlay modules consume the published screen rows and return a decision per row, and the
scoring modules do not import from here.
"""
