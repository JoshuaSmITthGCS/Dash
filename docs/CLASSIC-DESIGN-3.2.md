---
version: beta
name: ValueSignal HUD
description: Design language for the ValueSignal research command center — dark glass panels, cyan edge-glow, real-time data visualization. Jarvis-style tech aesthetic with premium execution.
colors:
  primary: "{colors.brand-primary}"
  surface-void: "#0a0e14"
  surface-panel: "#0f1419"
  surface-elevated: "#141922"
  surface-overlay: "#1a202c"
  border-dim: "rgba(0, 212, 255, 0.08)"
  border-default: "rgba(0, 212, 255, 0.2)"
  border-glow: "rgba(0, 212, 255, 0.4)"
  text-primary: "#e6f1ff"
  text-secondary: "#8b9bb3"
  text-tertiary: "#5c6b7f"
  text-faint: "#3d4a5c"
  brand-primary: "#00d4ff"
  brand-secondary: "#0099cc"
  brand-soft: "rgba(0, 212, 255, 0.12)"
  brand-ink: "#0a0e14"
  positive: "#00ff88"
  positive-soft: "rgba(0, 255, 136, 0.12)"
  negative: "#ff3366"
  negative-soft: "rgba(255, 51, 102, 0.12)"
  warning: "#ffaa00"
  warning-soft: "rgba(255, 170, 0, 0.12)"
  tier-a: "#00ff88"
  tier-a-soft: "rgba(0, 255, 136, 0.12)"
  tier-b: "#00d4ff"
  tier-b-soft: "rgba(0, 212, 255, 0.12)"
  tier-c: "#ffaa00"
  tier-c-soft: "rgba(255, 170, 0, 0.12)"
  tier-d: "#ff8800"
  tier-d-soft: "rgba(255, 136, 0, 0.12)"
  tier-e: "#ff3366"
  tier-e-soft: "rgba(255, 51, 102, 0.12)"
  series-stock: "{colors.brand-primary}"
  series-benchmark: "#8b5cf6"
  series-benchmark-2: "#ec4899"
  series-benchmark-3: "#f59e0b"
  series-cash: "#6b7280"
  diverging-neg-3: "#0ea5e9"
  diverging-neg-2: "#06b6d4"
  diverging-neg-1: "#22d3ee"
  diverging-zero: "#475569"
  diverging-pos-1: "#fbbf24"
  diverging-pos-2: "#f59e0b"
  diverging-pos-3: "#f97316"
  sector-tech: "#00d4ff"
  sector-health: "#00ff88"
  sector-finance: "#8b5cf6"
  sector-consumer-disc: "#ec4899"
  sector-consumer-staples: "#10b981"
  sector-energy: "#f59e0b"
  sector-industrials: "#06b6d4"
  sector-materials: "#a78bfa"
  sector-real-estate: "#f472b6"
  sector-utilities: "#14b8a6"
  sector-comm: "#8b5cf6"
  chart-grid: "{colors.border-dim}"
  glow-cyan: "0 0 4px rgba(0, 212, 255, 0.4)"
  glow-green: "0 0 4px rgba(0, 255, 136, 0.4)"
  glow-red: "0 0 4px rgba(255, 51, 102, 0.4)"
typography:
  sans:
    fontFamily: Geist Sans
  mono:
    fontFamily: Geist Mono
  eyebrow:
    fontFamily: Geist Mono
    fontSize: 10px
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: 0.12em
    textTransform: uppercase
    fontVariant: small-caps
  caption:
    fontFamily: Geist Sans
    fontSize: 11px
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: Geist Sans
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.45
  body:
    fontFamily: Geist Sans
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
  title:
    fontFamily: Geist Sans
    fontSize: 15px
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: -0.01em
  section:
    fontFamily: Geist Sans
    fontSize: 18px
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: -0.015em
  page:
    fontFamily: Geist Sans
    fontSize: 24px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: -0.02em
  figure:
    fontFamily: Geist Mono
    fontSize: 32px
    fontWeight: 600
    lineHeight: 1
    letterSpacing: -0.02em
    fontFeature: "'tnum' 1, 'zero' 1"
  numeric:
    fontFamily: Geist Mono
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: -0.01em
    fontFeature: "'tnum' 1, 'zero' 1"
rounded:
  none: 0px
  sm: 2px
  md: 4px
  lg: 6px
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
  card-padding: 16px
  section-gap: 16px
  row-height: 44px
  rail-width: 220px
  evidence-width: 320px
effects:
  glass-panel: "backdrop-filter: blur(12px) saturate(150%)"
  edge-glow: "box-shadow: 0 0 1px rgba(0, 212, 255, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.05)"
  data-glow: "filter: drop-shadow(0 0 2px currentColor)"
  scan-line: "background-image: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0, 212, 255, 0.03) 2px, rgba(0, 212, 255, 0.03) 4px)"
  grid-overlay: "background-image: radial-gradient(circle, rgba(0, 212, 255, 0.06) 1px, transparent 1px); background-size: 20px 20px"
components:
  panel:
    backgroundColor: "{colors.surface-panel}"
    backdropFilter: "blur(12px) saturate(150%)"
    border: "1px solid {colors.border-default}"
    boxShadow: "{effects.edge-glow}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.md}"
    padding: "{spacing.card-padding}"
  tile:
    backgroundColor: "{colors.surface-elevated}"
    border: "1px solid {colors.border-dim}"
    boxShadow: "0 0 1px rgba(0, 212, 255, 0.2)"
    textColor: "{colors.text-primary}"
    typography: "{typography.figure}"
    rounded: "{rounded.sm}"
    padding: "{spacing.4}"
  evidence-rail:
    backgroundColor: "{colors.surface-elevated}"
    backdropFilter: "blur(16px) saturate(150%)"
    border: "1px solid {colors.border-glow}"
    boxShadow: "0 0 2px rgba(0, 212, 255, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.08)"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.md}"
    padding: "{spacing.5}"
    width: "{spacing.evidence-width}"
  navigation-rail:
    backgroundColor: "{colors.surface-panel}"
    border: "1px solid {colors.border-default}"
    boxShadow: "inset 0 1px 0 rgba(255, 255, 255, 0.03)"
    textColor: "{colors.text-secondary}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "{spacing.4}"
    width: "{spacing.rail-width}"
  coverage-meter:
    backgroundColor: "{colors.surface-void}"
    border: "1px solid {colors.border-dim}"
    fillColor: "{colors.brand-primary}"
    glowEffect: "{effects.data-glow}"
    textColor: "{colors.text-tertiary}"
    typography: "{typography.eyebrow}"
    rounded: "{rounded.full}"
    height: 4px
  score-tape:
    backgroundColor: "{colors.surface-panel}"
    border: "1px solid {colors.border-default}"
    textColor: "{colors.text-primary}"
    typography: "{typography.eyebrow}"
    height: 96px
    glowMarks: true
  table-header:
    backgroundColor: "transparent"
    borderBottom: "1px solid {colors.border-dim}"
    textColor: "{colors.text-tertiary}"
    typography: "{typography.eyebrow}"
    padding: "{spacing.3}"
  table-row:
    backgroundColor: "transparent"
    borderBottom: "1px solid {colors.border-dim}"
    textColor: "{colors.text-primary}"
    typography: "{typography.label}"
    padding: "{spacing.2} {spacing.3}"
    height: "{spacing.row-height}"
    hoverGlow: "background: rgba(0, 212, 255, 0.04)"
  table-cell-numeric:
    textColor: "{colors.brand-primary}"
    typography: "{typography.numeric}"
    fontFeature: "'tnum' 1, 'zero' 1"
  control:
    backgroundColor: "{colors.surface-void}"
    border: "1px solid {colors.border-default}"
    textColor: "{colors.text-primary}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "{spacing.3}"
    focusGlow: "0 0 0 2px rgba(0, 212, 255, 0.4)"
  status-indicator:
    size: 6px
    glowRadius: 4px
    animation: "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite"
---

# ValueSignal HUD

## Overview

ValueSignal publishes precomputed equity research: a 0–100 score per company, the components it was built from, and the evidence behind it. Every number on screen comes from a committed JSON snapshot, and much of the model's honesty work is admitting what it could not measure. The design language exists to serve that: figures lead, the evidence that produced them sits beside them rather than behind a click, and the gaps in the data are drawn rather than footnoted.

This is a **tech command center** — dark glass panels with cyan edge-glow, real-time data visualization, and HUD-style precision. Density stays maximal, motion is fluid and purposeful, and every number glows with data authority. This is an Operate-mode product built for a power-user who lives in the data.

## Visual Philosophy

**Jarvis-style tech aesthetic with premium execution.** Not cluttered sci-fi, not arcade UI. Clean geometric precision, restrained use of glow, sophisticated data density. Every visual decision serves data legibility and speed of comprehension.

## Colors

The interface lives in **near-black space** with **cyan accents** as the primary chromatic signal. All surfaces belong to the same dark-blue-tinted family; only slight luminance shifts create depth. A differently-tinted region would read as a separate application.

**Surface levels** (darkest to brightest):
- `surface-void` (#0a0e14) — page background, input fills, meter tracks
- `surface-panel` (#0f1419) — primary container background
- `surface-elevated` (#141922) — panels that must float above neighbors
- `surface-overlay` (#1a202c) — popovers, tooltips, modals

**Text hierarchy** (brightest to dimmest):
- `text-primary` (#e6f1ff) — values, headings, critical data
- `text-secondary` (#8b9bb3) — supporting copy, labels
- `text-tertiary` (#5c6b7f) — metadata, sublabels, table headers
- `text-faint` (#3d4a5c) — decorative only, never sole carrier of meaning

**Cyan glow system** — the signature of the interface:
- `brand-primary` (#00d4ff) — active states, primary CTAs, data marks, live indicators
- `brand-secondary` (#0099cc) — secondary data marks, hover states
- `border-glow` (rgba cyan 40%) — edge-glow on floating panels
- `border-default` (rgba cyan 20%) — standard panel borders
- `border-dim` (rgba cyan 8%) — subtle dividers, table borders

**Semantic states** (glowing, high-contrast):
- `positive` (#00ff88) — success, gains, tier-A scores — glows green
- `negative` (#ff3366) — errors, losses, tier-E scores — glows red
- `warning` (#ffaa00) — caution, tier-C/D scores — glows amber

Semantic colors **never act as series colors** in charts. They state conditions only, and always appear with an icon or label, never color alone.

**Data series** (vibrant, distinct hues for multi-series charts):
- `series-stock` (cyan), `series-benchmark` (purple), `series-benchmark-2` (pink), `series-benchmark-3` (amber), `series-cash` (gray)
- Fixed order across all charts — same series keeps same hue

**Diverging scale** (for correlations, factor loadings, signed quantities):
- Seven steps from cyan (negative) through gray (zero) to amber (positive)
- `diverging-zero` (#475569) at the neutral midpoint — values near zero read as absent rather than weak

**Sector palette** — bright, saturated hues for categorical data. Each sector keeps its color across all views.

## Materials & Effects

**Glass panels** replace traditional cards. Every container is a dark glass surface with:
- `backdrop-filter: blur(12px) saturate(150%)` — frosted glass effect
- `border: 1px solid rgba(0, 212, 255, 0.2)` — cyan edge
- `box-shadow: 0 0 1px rgba(0, 212, 255, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.05)` — outer glow + inner highlight refraction
- No shadows in the traditional sense — **glow defines depth**, not drop-shadow offset

**Edge-glow intensity** signals hierarchy:
- Standard panels: 20% opacity cyan border
- Elevated panels (evidence rail, modals): 40% opacity cyan border + stronger outer glow
- Interactive hover: glow intensifies to 60%

**Data glow** — numbers and live indicators carry subtle halos:
- `filter: drop-shadow(0 0 2px currentColor)` on chart strokes, live counters, status dots
- Animated pulse on truly real-time elements (2s ease-in-out infinite)

**Scan-line overlay** (optional, applied to large panels for HUD feel):
- Horizontal repeating gradient, subtle cyan tint, 4px repeat
-Animates downward at 60s duration for "active scan" effect

**Grid overlay** (optional, applied to page background):
- Radial dot grid, 20px spacing, rgba cyan 6% opacity
- Reinforces geometric precision without cluttering data

**Reduced transparency fallback:**
- Users with `prefers-reduced-transparency` see solid dark backgrounds (#0f1419) with no blur
- Edge-glow persists (it's `box-shadow`, not transparency-dependent)

## Typography

**Two families, strict separation:**
- **Geist Sans** — labels, headings, body copy, UI chrome
- **Geist Mono** — all numbers, all data, timestamps, coordinates, any value the user might compare

**Every number** uses:
- `font-family: 'Geist Mono'`
- `font-feature-settings: 'tnum' 1, 'zero' 1` — tabular numerals + slashed zero
- This ensures digits stay in column, nothing shifts when values update, and zero is unambiguous

**Hierarchy** comes from size + weight + color together, never size alone. Three elements can share one size:
- A value at 600 weight on `text-primary` (the data)
- Its label at 500 on `text-secondary` (what it measures)
- Its metadata at 400 on `text-tertiary` (when it was measured)

**Small-caps eyebrows** — section headers and table headers use:
- `Geist Mono`, 10px, 500 weight, 12% letter-spacing, uppercase, small-caps variant
- This treatment makes 10px legible; never use eyebrow style without tracking

**11px floor** — no text renders below 11px anywhere in the product. Table headers, units, sublabels — all ≥11px.

**Wrapping discipline:**
- `text-wrap: balance` on headings
- `text-wrap: pretty` on body and captions
- Monospace data never wraps — if it doesn't fit, reduce scale or widen container

## Layout

**Three columns** (preserved from original architecture):
- **Navigation rail** (220px) — left, sticky, dark panel
- **Content column** — center, scrolling, where data lives
- **Evidence rail** (320px) — right, sticky, elevated glass panel

The navigation rail is narrower than the evidence rail because navigation serves the content while evidence is its peer. Both rails are sticky; the content column scrolls.

**Rhythm is tight and intentional.** Group tightly-related rows at `spacing.2` (8px), separate groups with `spacing.4`–`spacing.5` (16–20px). Equal gaps everywhere read as unstructured. All padding and margin values come from the spacing scale.

**Density is maximal** — card-padding reduced to 16px (from 20px), row-height reduced to 44px (from 52px), section-gap reduced to 16px (from 20px). This is a cockpit, not a gallery. User density preference still supported (compact/spacious modes shift these three tokens).

**Mobile breakpoint** — below 768px, navigation rail collapses to bottom nav, evidence rail becomes a slide-up sheet, content becomes full-width. Interactive targets remain ≥44×44px on touch.

## Depth & Hierarchy

**Glow defines depth, not shadow offset.** There are two hierarchy levels:

1. **Standard panels** — `border: 1px solid rgba(0, 212, 255, 0.2)`, subtle outer glow
2. **Elevated panels** — `border: 1px solid rgba(0, 212, 255, 0.4)`, stronger outer glow + backdrop-blur intensified

Navigation rail, content cards, and tiles = standard. Evidence rail, popovers, modals = elevated.

A third level means the hierarchy is wrong.

**Borders are structural** — 1px cyan borders separate cells, outline inputs, divide table rows. Glow carries stacking. Do not mix border-for-structure with glow-for-depth in the same element.

## Shapes

**Geometric precision** — rounded corners are minimal:
- `none` (0px) — table cells, hairline dividers
- `sm` (2px) — tiles, small controls
- `md` (4px) — panels, cards, inputs
- `lg` (6px) — modals, large containers
- `full` (999px) — pills, status indicators, meter tracks

**Nested rounding** follows `outerRadius = innerRadius + padding`. A tile inside a panel: if panel is 4px and padding is 16px, tile should be 2px (not 4px).

## Motion

**Fluid, purposeful, restrained.** Not infinite loops everywhere, not arcade effects. Motion serves **data updates, state transitions, and user feedback** — nothing decorates.

**Allowed motion patterns:**
- **Data counter animations** — numbers tick up/down on value change (Motion `animate` + `useMotionValue`)
- **Glow pulse** — status indicators pulse at 2s interval (CSS `animation: pulse`)
- **Chart line drawing** — SVG path `stroke-dashoffset` animation on first render
- **Panel slide-ins** — evidence rail, modals enter with `y: 24, opacity: 0` → `y: 0, opacity: 1`
- **Hover intensify** — glow brightens 20% on hover (CSS `transition: box-shadow 0.2s`)
- **Scan-line sweep** — optional slow downward animation on large panels (60s linear)

**Forbidden:**
- Infinite floating/bobbing on static elements
- Random particle effects
- Excessive hover trails
- Multiple simultaneous scan-lines
- Motion on every single component

**Reduced motion** — users with `prefers-reduced-motion: reduce` see:
- Instant state changes (no transitions)
- Static glow (no pulse)
- No scan-line animations
- Charts render complete (no drawing effect)

## Components

All component definitions from the original system are preserved. Visual treatment updated to glass-panel aesthetic.

**Coverage meter.** Any score computed from partial inputs carries a coverage meter. The solid segment (glowing cyan fill) is the share of applicable metrics actually measured; the remaining segment is a dashed track (dim cyan). Dashed means *not available*, never zero, and the label says so. A score without a coverage meter asserts that everything applicable was measured.

**Evidence rail.** The rail answers "why is this scored this way" for the selected row: score composition, category bars, and the stated strengths. Categories the pipeline could not measure render as dashed tracks (dim cyan), not as empty bars. Selecting a row anywhere in the content column updates the rail; the rail never becomes the only route to information, so the same content stays reachable on mobile and by deep link.

The evidence rail is an **elevated glass panel** — stronger glow, intensified backdrop-blur, floats above content.

**Score tape.** Published scores occupy a narrow band of the 0–100 range, so any plot of them shows the occupied window zoomed, above a full-range context strip that makes the zoom visible. Table rows carry the same window as an inline mark. Never plot published scores on a bare 0–100 axis — the distribution disappears.

Marks on the score tape **glow** — small dots with `filter: drop-shadow(0 0 2px currentColor)`.

**Data table.** One table system. Semantic `table` markup on desktop with sortable headers; at the mobile breakpoint it delegates to cards for short lists and a virtualized list for long ones.

Rows have **no background** (transparent), separated by 1px dim cyan borders (`border-bottom: 1px solid rgba(0, 212, 255, 0.08)`). Hover state applies subtle cyan tint (`background: rgba(0, 212, 255, 0.04)`). No alternating fills, no thick dividers.

Numeric columns are **right-aligned**, set in `Geist Mono` with tabular numerals, and colored `brand-primary` (cyan) to make data pop against the dark background.

**Charts.** Charts are hand-written SVG that inherit theme tokens; there is no chart library. Every chart states one axis, carries a legend when it draws two or more series, and offers a table view of the same data. A chart's accessible name describes what it shows; the table view carries the values.

Chart lines and data points **glow** — `stroke` has `filter: drop-shadow(0 0 2px currentColor)` applied. Grid lines are dim cyan (`rgba(0, 212, 255, 0.08)`). Animated path drawing on first render (via `stroke-dashoffset` transition).

**States.** Every interactive element defines default, hover, active, focus-visible, and disabled. Every data surface defines loading, empty, and error. An empty state explains why it is empty and what would fill it.

Focus states use **cyan glow ring** — `box-shadow: 0 0 0 2px rgba(0, 212, 255, 0.4)` instead of traditional outline.

Loading states use **animated skeleton loaders** with subtle cyan shimmer (not generic spinners).

## HUD Elements

**Status indicators** — small glowing dots (6px) with animated pulse:
- Live/active: glowing cyan, 2s pulse
- Stale/inactive: dim gray, no pulse
- Error: glowing red, faster pulse (1.5s)

**Timestamps** — always visible in top-right of panels:
- `Geist Mono`, 11px, `text-tertiary`
- Format: `14:23:45 UTC` or relative (`2m ago`)

**Corner brackets** (optional) — SVG corner accents on key panels:
- Thin cyan lines (1px), 12px long, positioned at panel corners
- Reinforces "terminal window" HUD feel
- Use sparingly (hero panels only)

## Do's and Don'ts

**Preserved from original system:**
- Do keep numbers in `mono` with tabular figures wherever they can be compared.
- Do draw unmeasured data as a dashed track and label it as unavailable.
- Don't set any text below 11px.
- Don't use `positive`, `negative`, or `warning` as series colors.
- Don't communicate a state through color alone.
- Don't plot published research scores on a bare 0–100 axis.
- Don't add a third elevation level.

**New rules for HUD aesthetic:**
- Do use cyan glow to define depth and interactivity.
- Do apply `backdrop-filter` to all panels.
- Do set all data in `Geist Mono` with slashed-zero.
- Do provide `prefers-reduced-transparency` and `prefers-reduced-motion` fallbacks.
- Don't overuse glow — one accent glow per visual group.
- Don't add scan-lines to every surface — hero panels only.
- Don't use rounded corners >6px — geometric precision matters.
- Don't add infinite animations to static data.
- Don't use pure black (#000) — always blue-tinted near-black.
- Don't let motion distract from data legibility.

---

**Migration note:** This is a visual-language redesign. All data structures, component logic, information architecture, and content are preserved. Only the presentation layer changes: colors, typography, materials, and motion. The product's data-first philosophy remains unchanged.
