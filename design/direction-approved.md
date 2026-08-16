# Approved visual direction

**Decided:** 2026-08-15 · Phase 0 gate of `docs/REDESIGN-PLAN.md`
**Process:** huashu-design three-direction gate. Three real rendered drafts were built in
`design/directions/` (A · Ledger, B · Tape, C · Studio), each showing Dashboard + a Picks table
fragment + Diversification-as-heatmap, light and dark, using real values from
`public/data/report.json`. Screenshots in `design/directions/shots/`.

## The user's choice, verbatim

Asked which of the three directions Phases 1–6 should build on, the user selected:

> **Mix — tell me which parts**

Asked three follow-up questions to resolve the mix, the user selected:

- Base surface system (palette, depth, radii, card treatment): **C · soft-depth**
- Signature elements to ship: **Coverage meter (from A), Evidence rail (from C), Score tape (from B)**
- Type and density: **14px base, Instrument Sans only**

## What that resolves to

**Base — Direction C, "Studio" (`design/directions/C-studio.html`)**

- Surfaces tinted toward the brand hue rather than neutral gray. Light: canvas `#eceff0`,
  surface `#fbfcfc`, raised `#ffffff`, sunken `#e3e8e7`. Dark: canvas `#0b100e`,
  surface `#141b18`, raised `#1a231f`, sunken `#101614`.
- **Depth strategy is layered tinted shadows, and elevation is the default** — `data-surface="elevated"`
  becomes the shipped default rather than an opt-in preference. Shadows tint toward the surface hue
  (`rgba(16,40,32,…)`), never pure black. Dark mode collapses depth shadows to a `rgba(255,255,255,.05)`
  ring, because depth shadows do not read on dark.
- Radii scale up: `--r-sm: 8px` / `--r-md: 10px` / `--r-lg: 14px` / `--r-xl: 18px`.
- One accent (`#17513c` light / `#7fe3b0` dark) with a lighter `--accent-2` for chart strokes.

**Overridden from C:** its 15px base and calmer density. See type below.

**Signatures — all three graft on**

1. **Coverage meter** (from A). Every score that the model computes from partial data carries a
   thin rule beneath it: solid = share of applicable metrics actually measured, dashed remainder =
   not available. Dashed means *unmeasured*, never zero. This is the visual answer to the
   enrichment-shortlist gap documented in `docs/SYSTEM-SETUP.md` §4.1 and `docs/LIMITATIONS.md`.
2. **Evidence rail** (from C). A persistent right-hand column showing score composition,
   fundamental-category bars, and strengths for whatever row is selected. It is the primary
   answer to "why is this scored that way" and reduces `StockDetailModal` to a mobile/deep-link
   surface. Also relevant to Phase 3 P0 #1 — less content trapped behind a modal that currently
   lacks dialog semantics.
3. **Score tape** (from B). Published scores plotted on a zoomed axis with a 0–100 context strip
   showing how narrow the occupied window is, plus an inline mini-tape per table row on the same
   scale. Rationale: in the 2026-08-14 report all 40 published names score between 79.2 and 88.8 —
   a 9.6-point spread that a rank column hides entirely.

**Type — 14px base, Instrument Sans only**

- `--font-body` and `--font-display` are both Instrument Sans. Numbers stay IBM Plex Mono with
  `tabular-nums`.
- **Delete the Bricolage Grotesque `<link>` from `index.html`** — it is loaded today and referenced
  by nothing. Direction B would have revived it; that direction was not chosen, so it goes.
- Hierarchy comes from size + weight + color, not a second family.
- Scale floor is 11px. The current 7–10px cluster (155 rules, 120 of them at 9px) all moves to
  `--fs-2xs: 11px` or higher, keeping the uppercase + letterspacing treatment where it existed.
- Density stays at today's setting; C's extra air is not adopted. `data-density` compact/spacious
  keep working off the new spacing scale.

## Corrections applied while writing `DESIGN.md`

Contrast was checked for every ink level against all four light surfaces and all four dark
surfaces. One value failed: `text-tertiary` at C's `#64706c` gave 4.16:1 on the shelf surface
(`#e3e8e7`), which is where it lands on control fills and hovered table rows. It was darkened to
**`#5c6864`** (4.69:1 shelf, 5.02 canvas, 5.65 card, 5.80 raised). Every other ink, brand, and
semantic color in the approved palette clears AA on all eight surfaces as drafted.

## Merged reference

`design/directions/D-approved.html` renders the resolved mix — C's surfaces at 14px carrying all
three signatures. It is the visual reference for `DESIGN.md` and for Phase 5's page-by-page pass.

## Scope note

This decision governs `src/` and `index.html` only. No pipeline, schema, or `public/data/*` change
follows from it.
