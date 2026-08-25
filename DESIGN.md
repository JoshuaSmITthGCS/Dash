---
version: 1.0.0
name: ValueSignal — The Study
description: Design language for the ValueSignal research surface — a naturalist's study at night, specimens lit from within. Warm graphite and antique brass, an engraved slab-serif nameplate for the figures that matter, a technical mono for every measured value, and a verdigris "specimen light" reserved for one honest signal: the pipeline is live right now.
colors:
  primary: "{colors.brand-primary}"
  surface-canvas: "#0f0d0b"
  surface-shelf: "#17130f"
  surface-card: "#1c1712"
  surface-raised: "#241d16"
  surface-sheet: "#2c241b"
  border-subtle: "rgba(201, 163, 95, 0.08)"
  border-default: "rgba(201, 163, 95, 0.16)"
  border-strong: "rgba(201, 163, 95, 0.30)"
  text-primary: "#ece4d8"
  text-secondary: "#a89686"
  text-tertiary: "#87786a"
  text-faint: "#5a4f45"
  brand-primary: "#c9a35f"
  brand-secondary: "color-mix(in srgb, var(--brand-primary) 78%, black)"
  brand-soft: "rgba(201, 163, 95, 0.12)"
  brand-ink: "#0a0806"
  instrument-glow: "#6fae9c"
  instrument-glow-soft: "rgba(111, 174, 156, 0.16)"
  medallion-ring: "rgba(255, 232, 196, 0.12)"
  positive: "#7fae6e"
  positive-soft: "rgba(127, 174, 110, 0.14)"
  negative: "#d1685a"
  negative-soft: "rgba(209, 104, 90, 0.14)"
  warning: "#c99a3f"
  warning-soft: "rgba(201, 154, 63, 0.14)"
  series-stock: "{colors.brand-secondary}"
  series-benchmark: "#60a5fa"
  series-benchmark-2: "#fb923c"
  series-benchmark-3: "#a78bfa"
  series-cash: "#fbbf24"
  diverging-zero: "#4a4137"
  sector-tech: "#ec4899"
  sector-health: "#22c55e"
  sector-finance: "#3b82f6"
typography:
  display:
    fontFamily: Bitter
    role: "page titles, hero figures, card titles — short strings, large sizes only"
  body:
    fontFamily: Source Sans 3
    role: "paragraphs, labels, dense UI microcopy — legibility over expression"
  mono:
    fontFamily: JetBrains Mono
    role: "every number, every measured value, timestamps, tabular figures"
  eyebrow:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: 600
    textTransform: uppercase
    letterSpacing: .09em
  figure:
    fontFamily: JetBrains Mono
    fontSize: "clamp(44px, 7vw, 76px)"
    fontWeight: 600
    fontFeature: "'tnum' 1, 'zero' 1"
rounded:
  sm: 3px
  md: 5px
  lg: 7px
  xl: 9px
  full: 999px
spacing:
  card-padding: 20px
  section-gap: 20px
  row-height: 52px
effects:
  case-shadow: "inset 0 1px 0 rgba(255,232,196,.05), 0 1px 2px rgba(6,4,2,.5), 0 6px 16px rgba(6,4,2,.35)"
  case-shadow-elevated: "inset 0 1px 0 rgba(255,232,196,.08), 0 2px 4px rgba(6,4,2,.55), 0 18px 40px rgba(6,4,2,.45), 0 0 0 1px rgba(201,163,95,.12)"
  specimen-light-pulse: "opacity 1 → .55, 2.4s ease-in-out infinite (instrument-glow only, live-data indicator)"
components:
  card:
    backgroundColor: "{colors.surface-card}"
    border: "1px solid {colors.border-default}"
    boxShadow: "{effects.case-shadow}"
    rounded: "{rounded.lg}"
    padding: "{spacing.card-padding}"
  evidence-rail:
    backgroundColor: "{colors.surface-raised}"
    border: "1px solid {colors.border-strong}"
    boxShadow: "{effects.case-shadow-elevated}"
    rounded: "{rounded.lg}"
  rating-badge:
    boxShadow: "inset 0 0 0 1px currentColor"
    rounded: "{rounded.sm}"
  status-indicator-live:
    color: "{colors.instrument-glow}"
    animation: "{effects.specimen-light-pulse}"
---

# ValueSignal — The Study

## Overview

ValueSignal publishes precomputed equity research: a 0–100 score per company, the
components it was built from, and the evidence behind it. The design language exists to
serve that fact — figures lead, the evidence that produced them sits beside them rather
than behind a click, and the gaps in the data are drawn rather than footnoted.

The room is **a naturalist's study at night** — the kind of period room a natural-history
museum reconstructs: specimen cases, ledgers, brass instruments, catalog cards, engraved
plaques. Not a trading terminal, not a glass-and-neon control room, not a generic SaaS
dashboard. A place where evidence is cataloged, lit, and kept — read at a desk, not glanced
at on a wall.

This is an **Operate**-mode surface (per impeccable's modes): scanability, density, and
correct behavior outrank expression. The room's character comes from color, material, and
two typefaces used with restraint — not from decoration layered on top of the data.

## Why this replaced the prior direction

Two visual systems existed in this repository before this one, and neither is what ships now:

1. **"Studio"** (`design/direction-approved.md`, 2026-08-15) — tinted green surfaces,
   soft-depth shadows, Instrument Sans. This was the last *properly executed* redesign
   (see `docs/REDESIGN-STATUS.md`, rescored 18/20) and its structural work — the token
   architecture, `DataTable`, the coverage meter / evidence rail / score tape signatures,
   accessibility fixes, chart primitives — is exactly what this pass builds on. Only the
   **skin** (palette, type, shape, materials) is replaced here; every one of those signature
   concepts survives, reskinned.
2. **"ValueSignal HUD"** — a cyan-glass, glow-everywhere sci-fi command-center concept.
   This was drafted (an earlier version of this file, plus `src/pages/CommandCenter.jsx`,
   `HUDDemo.jsx`, `src/lib/hudAdvanced.jsx`/`hudUltra.jsx`, and three `hud-*.css` modules)
   but **never properly shipped**: `CommandCenter` was never routed, `/hud-demo` was
   dev-only, and the actual live app kept Studio's surfaces underneath a document that
   described something else entirely. One real bug did ship from it — `initAdvancedHUD()`
   injected an unstyled cyan scan-line/grid overlay into every page via raw DOM
   manipulation outside React's tree — now removed along with the rest of that lineage.

Read this as the second properly-decided direction, not a first draft: it inherits
Studio's engineering, discards its and HUD's visual language, and is the one this document
now governs.

## Colors

The room is **warm graphite**, not blue-black — every surface carries a faint amber
undertone, the way a room lit by a few warm bulbs reads at night.

**Surface levels** (darkest to brightest): `surface-canvas` (`#0f0d0b`, the room itself) →
`surface-shelf` (`#17130f`, inset fills, hovered rows) → `surface-card` (`#1c1712`, a case
standing in the room — the default card) → `surface-raised` (`#241d16`, lifted above the
case floor) → `surface-sheet` (`#2c241b`, modals — brought to the desk).

**Ink** — parchment-warm, four levels: `text-primary` (`#ece4d8`) for headline figures and
catalog copy, `text-secondary` (`#a89686`) for labels, `text-tertiary` (`#87786a`) for
metadata and table headers, `text-faint` (`#5a4f45`, decorative only — never body, never
alone).

**Brand — antique brass** (`#c9a35f`): the room's one warm metal. Interactive states,
primary actions, tier-A marks, focus rings, chart primary series. `brand-secondary` is
`color-mix(in srgb, var(--brand-primary) 78%, black)` — **derived, never hand-maintained**,
so a future accent change only touches one value.

**Instrument glow — verdigris** (`#6fae9c`): reserved for exactly one meaning — *the
pipeline is measuring right now*. It is not a second brand color and never appears as a
state judgment; `positive`/`negative`/`warning` (patina green / oxide red / aged ochre)
carry every good/bad reading. One accent glows for aliveness, three carry verdict, and they
never trade places.

**Chart series, diverging scale, and the 11-sector palette are unchanged from the prior
pass on purpose.** They were CVD-validated (`docs/REDESIGN-STATUS.md` §3 — a deuteranope
could not distinguish two benchmark series before that fix) and chart color is orthogonal
to surface skin. Re-deriving them without re-running that validation would be a silent
accessibility regression, so this pass left them alone.

## Typography

**Three voices, not one, and each earns its keep by where it appears:**

- **Bitter** (slab serif) — page titles, hero figures, card titles. Short strings, large
  sizes, where a face with a point of view reads as a nameplate rather than a paragraph.
  A slab serif specifically: the register of an encyclopedia entry or a specimen label,
  not a literary one.
- **Source Sans 3** — body copy, labels, dense table cells, every piece of UI chrome.
  Plain on purpose. Operate mode wants a workhorse here, not a second personality; the
  room's character already lives in Bitter and in the data.
- **JetBrains Mono** — every number, every timestamp, every measured value. Tabular
  figures, `font-feature-settings: 'tnum' 1, 'zero' 1'` throughout, so digits stay in
  column and a zero is never mistaken for an "o".

The 11px floor, the 8-step size scale, and "hierarchy from size + weight + color, never
size alone" all carry over unchanged from the prior pass — verified with
`design/typefloor.mjs` (0 violations across the routes checked this pass, DOM and scaled
SVG both).

## Materials

**A card is a specimen case, not a floating tile.** `surface-card` sits one level above
the room (`surface-canvas`), separated by a warm hairline border
(`rgba(201,163,95,.16)`) and a shadow that carries the room's own warmth — a faint inset
highlight along the top edge (light catching glass), a soft near-black drop shadow, never
a colored halo. Two elevation levels only, exactly as before: standard cards, and the
evidence rail / modals above them with a stronger shadow plus a faint brass ring. A third
level is still a hierarchy bug.

**Shape is an instrument bezel, not a friendly app corner.** Radii dropped from the prior
pass's 8/10/14/18px to **3/5/7/9px** — a vitrine case and a gauge housing are cut square,
not rounded for approachability. `data-corners` compact/extra-rounded still work, scaled
proportionally.

**Tier and rating marks read as engraved medallions** — an inset ring (`box-shadow: inset
0 0 0 1px currentColor`) rather than a flat filled pill, so a tier reads as stamped, not
colored in.

**One panel gets a plaque bracket.** The Dashboard hero case carries a thin corner bracket
at two corners only — the scale a vitrine label actually uses, and sparingly, the same
restraint principle the prior HUD draft stated and then didn't follow (scan-lines on every
panel). One case in the whole app earns this; everything else is quieter.

## Motion

Mechanical and precise — a needle settling, not a bounce. `--ease-out` is now
`cubic-bezier(.16,1,.3,1)`, a sharper settle than the prior pass's softer curve. The one
new motion in this pass is the **specimen-light pulse** — `--instrument-glow` breathing at
2.4s on the pipeline's own "live" indicator (`DataStatus`'s default, non-demo,
non-stale state) — gated through the existing `prefers-reduced-motion` block like every
other animation in the app. Nothing else changed: chart draw-on, modal entrance, pull-to-
refresh tracking, and `AnimatedNumber`'s reduced-motion check all carry over from the
Phase 6 motion pass untouched.

## Components

**Coverage meter, evidence rail, score tape** — unchanged in behavior, reskinned in
material. These are product truth (see PRODUCT.md's terminology section), not a visual
choice, and this pass did not touch what they mean, only what they're made of.

**`DataStatus`'s live indicator** is the one place `--instrument-glow` appears: a small
pulsing dot reading "the pipeline is measuring right now," never a verdict. Stale/warning
still reads `--warning`; demo data still reads its own state; nothing about the underlying
logic changed.

**Data table, charts, dialogs, empty states** — unchanged. `DataTable`'s virtualization,
`useDialog`'s focus trap, every chart's table-view fallback, and the empty-state guards
documented in `docs/REDESIGN-STATUS.md` all carry over exactly as built.

## Do's and don'ts

- Do keep every number in `JetBrains Mono` with tabular figures.
- Do draw unmeasured data as a dashed track, labeled as unavailable — never as a zero.
- Don't set any text below 11px, anywhere, including inside SVG.
- Don't use `positive`/`negative`/`warning` as series colors, or color alone to carry
  meaning.
- Don't use `instrument-glow` for anything except "the pipeline is live" — it is not a
  second brand color, and it never judges good or bad.
- Don't add a third elevation level.
- Don't round a corner past `--r-xl` (9px) — this room is cut square, not soft.
- Don't touch the chart series / diverging / sector palettes without re-running the CVD
  validation that approved them.
- Don't reintroduce raw DOM manipulation for visual effects (the `initAdvancedHUD` bug
  this pass removed) — every visual state lives in React and CSS custom properties.

---

**Theme note:** the app renders one intentional dark world. `data-theme="light"` is set on
`<html>` by a legacy preference toggle but no light palette is defined anywhere in
`variables.css` — a light selection silently renders these same dark values. This was true
before this pass (verified: no `[data-theme="light"]` block existed in the prior system
either) and is left as-is rather than fixed as a side effect of a visual-language pass;
building a real light theme is a separate, larger decision.

**Migration note:** this is a visual-language redesign. All data structures, component
logic, information architecture, and content are preserved. Only the presentation layer
changes: colors, typography, shape, materials, and the one new motion state. The product's
evidence-first philosophy is unchanged — see PRODUCT.md.
