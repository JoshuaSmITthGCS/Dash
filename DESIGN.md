---
version: alpha
name: ValueSignal
description: Design language for the ValueSignal research dashboard — tinted elevated surfaces, one accent, and evidence shown beside every score.
colors:
  primary: "{colors.brand-primary}"
  surface-canvas-bg: "#eceff0"
  surface-shelf-bg: "#e3e8e7"
  surface-card-bg: "#fbfcfc"
  surface-raised-bg: "#ffffff"
  border-subtle: "#e8ecec"
  border-default: "#dbe1e0"
  border-strong: "#c2cbc8"
  text-primary: "#101614"
  text-secondary: "#4b5552"
  text-tertiary: "#5c6864"
  text-faint: "#7f8b87"
  brand-primary: "#17513c"
  brand-secondary: "#2f7a5c"
  brand-soft: "#e3f0e9"
  brand-ink: "#ffffff"
  positive: "#0a6f53"
  positive-soft: "#e2f5ec"
  negative: "#b83c37"
  negative-soft: "#fbeae9"
  warning: "#8a5f0e"
  warning-soft: "#fdf2d8"
  series-stock: "{colors.brand-secondary}"
  series-benchmark: "#4674a8"
  series-benchmark-2: "#75579b"
  series-benchmark-3: "#9a641f"
  series-cash: "#806b62"
  diverging-neg-3: "#2c6b7f"
  diverging-neg-2: "#5f97a6"
  diverging-neg-1: "#a6c5cb"
  diverging-zero: "#dfe4e3"
  diverging-pos-1: "#c9b791"
  diverging-pos-2: "#a68a55"
  diverging-pos-3: "#795c2c"
  sector-tech: "#4674a8"
  sector-health: "#5d9b7c"
  sector-finance: "#7a6da8"
  sector-consumer-disc: "#c47a3a"
  sector-consumer-staples: "#6b8e5f"
  sector-energy: "#b55b4f"
  sector-industrials: "#5a7a9c"
  sector-materials: "#8a7352"
  sector-real-estate: "#6d6d9e"
  sector-utilities: "#4a907a"
  sector-comm: "#9b6c6c"
  chart-grid: "{colors.border-subtle}"
typography:
  sans:
    fontFamily: Instrument Sans
  mono:
    fontFamily: IBM Plex Mono
  eyebrow:
    fontFamily: Instrument Sans
    fontSize: 11px
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: 0.09em
  caption:
    fontFamily: Instrument Sans
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: Instrument Sans
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1.45
  body:
    fontFamily: Instrument Sans
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  title:
    fontFamily: Instrument Sans
    fontSize: 16px
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: -0.015em
  section:
    fontFamily: Instrument Sans
    fontSize: 20px
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: -0.02em
  page:
    fontFamily: Instrument Sans
    fontSize: 26px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: -0.025em
  figure:
    fontFamily: IBM Plex Mono
    fontSize: 38px
    fontWeight: 600
    lineHeight: 1
    letterSpacing: -0.03em
    fontFeature: "'tnum' 1"
  numeric:
    fontFamily: IBM Plex Mono
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: -0.015em
    fontFeature: "'tnum' 1"
rounded:
  sm: 8px
  md: 10px
  lg: 14px
  xl: 18px
  full: 999px
spacing:
  1: 4px
  2: 8px
  3: 12px
  4: 16px
  5: 20px
  6: 24px
  8: 32px
  10: 40px
  12: 48px
  card-padding: 20px
  section-gap: 20px
  row-height: 52px
  rail-width: 224px
  evidence-width: 332px
components:
  card:
    backgroundColor: "{colors.surface-card-bg}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.xl}"
    padding: "{spacing.card-padding}"
  tile:
    backgroundColor: "{colors.surface-raised-bg}"
    textColor: "{colors.text-primary}"
    typography: "{typography.figure}"
    rounded: "{rounded.lg}"
    padding: "{spacing.5}"
  evidence-rail:
    backgroundColor: "{colors.surface-raised-bg}"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.xl}"
    padding: "{spacing.5}"
    width: "{spacing.evidence-width}"
  navigation-rail:
    backgroundColor: "{colors.surface-card-bg}"
    textColor: "{colors.text-secondary}"
    typography: "{typography.label}"
    rounded: "{rounded.xl}"
    padding: "{spacing.4}"
    width: "{spacing.rail-width}"
  coverage-meter:
    backgroundColor: "{colors.surface-shelf-bg}"
    textColor: "{colors.text-tertiary}"
    typography: "{typography.eyebrow}"
    rounded: "{rounded.full}"
    height: 3px
  score-tape:
    backgroundColor: "{colors.surface-card-bg}"
    textColor: "{colors.text-primary}"
    typography: "{typography.eyebrow}"
    height: 104px
  table-header:
    backgroundColor: "{colors.surface-card-bg}"
    textColor: "{colors.text-tertiary}"
    typography: "{typography.eyebrow}"
    padding: "{spacing.3}"
  table-row:
    backgroundColor: "{colors.surface-card-bg}"
    textColor: "{colors.text-primary}"
    typography: "{typography.label}"
    padding: "{spacing.3}"
    height: "{spacing.row-height}"
  table-cell-numeric:
    textColor: "{colors.text-primary}"
    typography: "{typography.numeric}"
  control:
    backgroundColor: "{colors.surface-shelf-bg}"
    textColor: "{colors.text-primary}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "{spacing.3}"
---

# ValueSignal

## Overview

ValueSignal publishes precomputed equity research: a 0–100 score per company, the components it was built from, and the evidence behind it. Every number on screen comes from a committed JSON snapshot, and much of the model's honesty work is admitting what it could not measure. The design language exists to serve that: figures lead, the evidence that produced them sits beside them rather than behind a click, and the gaps in the data are drawn rather than footnoted.

Surfaces are tinted toward the brand hue and lifted on hue-matched shadows. This is an Operate-mode product — the reader is completing a task, not being persuaded — so density stays high, color stays scarce, and structure comes from elevation and space rather than lines.

## Colors

Every surface belongs to one hue family; only lightness changes between levels. Do not introduce a second hue for a panel, sidebar, or section — a differently-tinted region reads as a separate application.

The four surface levels stack in one order: `surface-canvas-bg` is the page, `surface-card-bg` is a container on it, `surface-raised-bg` is a container that must sit above its neighbours (tiles, the evidence rail, popovers, selected states), and `surface-shelf-bg` is inset — use it for control fills, table row hover, and meter tracks, so an input reads as receiving content rather than emitting it.

Text uses four levels. `text-primary` carries values and headings, `text-secondary` carries supporting copy, `text-tertiary` carries metadata and labels, and `text-faint` is decorative only — never body copy, never the sole carrier of meaning. `text-tertiary` is the floor for any text a reader must read; it meets AA on `surface-card-bg` and `surface-raised-bg`.

`brand-primary` is the only chromatic decision in the interface chrome. Use it for the active navigation state, primary actions, and selection. Use `brand-secondary` for data marks — chart strokes, meter fills, tape marks — because a stroke needs more luminance against a surface than a fill needs behind text.

`positive`, `negative`, and `warning` state a condition. They never act as series colors in a chart, and they never carry meaning alone: a breached threshold gets an icon and a label as well as the color.

Categorical series use `series-*` in fixed order, so the same series keeps the same hue across every chart. Correlations, factor loadings, and any other signed quantity use the seven-step `diverging-*` scale with `diverging-zero` as the neutral midpoint, so a value near zero reads as absent rather than weak.

## Themes

Light is the default theme and its values are the normative ones in the frontmatter. Dark is a full inversion of the same roles — same hue, same hierarchy, different lightness — selected by `data-theme="dark"` on the root element.

| Token | Dark value |
|---|---|
| `surface-canvas-bg` | `#0b100e` |
| `surface-shelf-bg` | `#101614` |
| `surface-card-bg` | `#141b18` |
| `surface-raised-bg` | `#1a231f` |
| `border-subtle` | `#1f2823` |
| `border-default` | `#28322d` |
| `border-strong` | `#3a443c` |
| `text-primary` | `#e9eeeb` |
| `text-secondary` | `#a5b0ab` |
| `text-tertiary` | `#8b9791` |
| `text-faint` | `#75817c` |
| `brand-primary` | `#7fe3b0` |
| `brand-secondary` | `#5cba8e` |
| `brand-soft` | `#16281f` |
| `brand-ink` | `#07130d` |
| `positive` | `#58d795` |
| `positive-soft` | `#0f2a1c` |
| `negative` | `#ff746d` |
| `negative-soft` | `#2c1614` |
| `warning` | `#eab83f` |
| `warning-soft` | `#2a2310` |
| `series-benchmark` | `#86aef7` |
| `series-benchmark-2` | `#c5a1ee` |
| `series-benchmark-3` | `#f0bd70` |
| `series-cash` | `#c6aca4` |
| `diverging-neg-3` | `#6fb4ce` |
| `diverging-neg-2` | `#457d90` |
| `diverging-neg-1` | `#2a4c56` |
| `diverging-zero` | `#222b27` |
| `diverging-pos-1` | `#4a3f27` |
| `diverging-pos-2` | `#856d36` |
| `diverging-pos-3` | `#cba95d` |

In dark mode `brand-primary` becomes light enough to act as ink, so text placed on it uses `brand-ink`. Depth shadows do not read on dark — replace the layered shadow with a single `rgba(255,255,255,.05)` ring and keep the same elevation ordering.

## Typography

One family carries the interface. Hierarchy comes from size, weight, and text color used together — never size alone. Three tiers can share a single size: a value at 600 weight on `text-primary`, its label at 500 on `text-secondary`, its metadata at 400 on `text-tertiary`.

Every number a reader may compare — table columns, tiles, counters, chart labels, prices — is set in `mono` with tabular figures, so digits stay in column and nothing shifts when a value updates.

`eyebrow` is set uppercase with its letterspacing; that treatment is what makes 11px legible as a label, so do not use `eyebrow` at sentence case or without tracking. 11px is the floor for any text in the product, including table headers, units, and sublabels.

Set `text-wrap: balance` on headings and `text-wrap: pretty` on body and captions.

## Layout

Three columns: navigation rail, content, evidence rail. The rail is narrower than the evidence rail because navigation serves the content while evidence is its peer. Both rails are sticky; the content column scrolls.

Rhythm is uneven by design. Group tightly-related rows at `spacing.2`–`spacing.3`, then separate groups with `spacing.5`–`spacing.6`. Equal gaps everywhere read as unstructured.

All padding and margin values come from the spacing scale. Padding is symmetrical unless content genuinely demands otherwise.

Density is a user preference expressed through `card-padding`, `section-gap`, and `row-height`; the compact and spacious settings shift those three tokens and nothing else, so a page laid out on the scale adapts without page-specific rules.

Below the rail breakpoint the navigation rail collapses to the mobile navigation and the evidence rail becomes a sheet. Interactive targets are at least 44×44px on touch.

## Elevation & Depth

Elevation is the depth strategy. Do not mix it with borders-for-structure — borders separate cells and outline inputs; shadows carry stacking.

Two levels only. Level 1 is resting elevation for cards, tiles, and rail surfaces. Level 2 is for surfaces that must clearly float above their neighbours: the evidence rail, popovers, sheets, and the correlation surface. A third level means the hierarchy is wrong.

Shadows tint toward the surface hue. A pure-black shadow on a tinted surface reads as dirt.

Elevation is the shipped default, not an opt-in preference.

## Shapes

Radius scales with the size of the element: `sm` for inputs, buttons, and chips, `md` for controls and grouped rows, `lg` for tiles, `xl` for cards and rails, `full` for pills and status chips.

Nested rounded elements follow `outerRadius = innerRadius + padding`. A tile inside a card at the same radius is the most common reason a layout looks slightly wrong for no nameable reason.

## Components

**Coverage meter.** Any score computed from partial inputs carries a coverage meter. The solid segment is the share of applicable metrics actually measured; the remaining segment is drawn as a dashed track. Dashed means *not available*, never zero, and the label says so. A score without a coverage meter asserts that everything applicable was measured.

**Evidence rail.** The rail answers "why is this scored this way" for the selected row: score composition, category bars, and the stated strengths. Categories the pipeline could not measure render as the same dashed track, not as an empty bar. Selecting a row anywhere in the content column updates the rail; the rail never becomes the only route to information, so the same content stays reachable on mobile and by deep link.

**Score tape.** Published scores occupy a narrow band of the 0–100 range, so any plot of them shows the occupied window zoomed, above a full-range context strip that makes the zoom visible. Table rows carry the same window as an inline mark. Never plot published scores on a bare 0–100 axis — the distribution disappears.

**Data table.** One table system. Semantic `table` markup on desktop with sortable headers; at the mobile breakpoint it delegates to cards for short lists and a virtualized list for long ones. Rows separate on `border-subtle`, not on alternating fills. Numeric columns are right-aligned and set in `numeric`.

**Charts.** Charts are hand-written SVG that inherit theme tokens; there is no chart library. Every chart states one axis, carries a legend when it draws two or more series, and offers a table view of the same data. A chart's accessible name describes what it shows; the table view carries the values.

**States.** Every interactive element defines default, hover, active, focus-visible, and disabled. Every data surface defines loading, empty, and error. An empty state explains why it is empty and what would fill it.

## Do's and Don'ts

- Do keep numbers in `mono` with tabular figures wherever they can be compared.
- Do draw unmeasured data as a dashed track and label it as unavailable.
- Do use one accent, and let gray carry structure.
- Don't set any text below 11px.
- Don't use `positive`, `negative`, or `warning` as series colors.
- Don't communicate a state through color alone.
- Don't give a panel or sidebar a different surface hue from the canvas.
- Don't plot published research scores on a bare 0–100 axis.
- Don't add a third elevation level.
