# DESIGN.md — Twelve Mediums

Phase 1 gate deliverable for the ValueSignal interface rebuild. Governed by
`valuesignal-rebuild-MASTER-rev11.md` (rules, phases, gates — wins on conflict) and its
companion `valuesignal-ui-laws-and-visual-map.md` (UX-law grounding, resource map, per-theme
visual specs). Read both before editing this file. Reference images live in `design-refs/`
(the master's own named references — chalkboard pub board, beige-box computer, outrun scene,
chrome/holographic lettering, TradeHub) and `design-refs/session-refs/` (five additional taste
references). Still-missing named references (`stocky.webp`, the slate-board game-interface
chalk reference, six Fidelity mobile screenshots) are substituted with the companion doc's prose
specs — noted per-theme below where relevant, never blocking.

**Naming**: the twelve presentations are called **mediums** in code (see `NOTES.md`); this
document still says "theme" in prose per the master's own vocabulary.

**What never varies, regardless of medium** (repeated here because every section below is a
theme *trading against* these, never replacing them): routing and URLs (see
`ROUTE-INVENTORY.md` §2's six destinations) · a metric's `label`/`reads`/every disclosure, sourced
from the schema, never hand-written · the four-state model (Established · Accumulating ·
Breached · Unavailable-with-reason) · qualitative confidence as a second, separate, non-hue,
non-blur, non-three-level channel · 44px touch targets · tabular-figure mono numerals, never
filtered/glowed/textured · the banned list (root doc, "Banned in every theme" — checked again in
the closing self-audit below).

---

## Costume tests (definitions, applied per theme in §Closing)

1. **Greyscale** — strip all color; still recognizably its medium?
2. **Swap** — drop another theme's chart renderer in; does anything look wrong?
3. **Furniture** — mask every number and chart; is the surrounding interface still recognizably
   that medium?
4. **Navigation** — show only the navigation; can you name the theme?
5. **One-word** — show a stranger a screenshot; can they name the medium in one word?

---

# 1 · COCKPIT — instrument panel

**Based on**: aircraft and test-equipment panels — machined bezels, detented switches, calibrated
scales, annunciators that only light on a real condition, phosphor readouts updating in place.
Dark, calm-under-glow (not saturated).

### Tokens
| Token | Value | Use |
|---|---|---|
| `--ink-primary` | `#e8f2f5` | phosphor-white readout text |
| `--surface-ground` | `#0a0d10` | panel base, near-black |
| `--surface-bezel` | `#14181c` | bezel/bracket fill |
| `--state-established` | `#4fd1c5` | lit channel, steady phosphor teal |
| `--state-breach` | `#ff5c5c` | the one alert accent — annunciator red |
| `--rule-hairline` | `#2a3138` | thin luminous rules, corner brackets |

### Type roles
Condensed technical display (headings/labels) · mono numerals dominant (Share Tech Mono or
JetBrains Mono, tabular) · letterspaced micro-labels for annunciator tags. Floor 16px body,
11px micro-labels never below the shared floor once rendered-size-checked (typefloor CTM rule).

### Ten material dimensions
1. **Mark-making**: lit tube/needle-style readouts on tick scales — value marks map to real
   positions on a calibrated arc, never a decorative fill.
2. **Containers**: bezels and corner brackets, never cards — a bracket has four independent
   corners, no fill, no shadow.
3. **Controls**: detented switch (a two-state toggle rendered as a physical throw), calibrated
   dial for range selection.
4. **Navigation**: channel selector — left rail desktop, bottom bracket bar at 390px.
5. **Entry**: none — no fake boot sequence (explicit master rule).
6. **Transitions**: none; a channel swap is instant, like flipping a switch.
7. **Empty/loading/error**: an unlit channel bezel with its `reason` printed in the readout
   font — dark glass, not a spinner.
8. **Vocabulary**: channel, readout, bezel, annunciator, calibrated, in range / out of range.
9. **Layout rhythm**: tight, instrument-panel grids; margins are bezel width, not whitespace.
10. **Texture**: none beneath data — a faint machined-metal grain on bezel fill only, under the
    per-theme byte budget.

### Must-include walkthrough
| Master bullet | Status | How |
|---|---|---|
| Tick scales mapping to actual values | done | `dial` chart-contract type renders a labeled arc scale; value position is computed, not eyeballed |
| Bezels/corner brackets as containers, never cards | done | `components.Container` = `TacticalFrame`-style 4-corner bracket, no card chrome |
| Glow only when a value is live | done | `--glow` token applied only to the active channel's readout, off for stale/unavailable |
| An unlit channel with its `reason` | done | `state.unavailable` renders a dark bezel + printed reason string, no icon-only state |
| Attribution strip as a readout | done | first-viewport evidence strip (ROUTE-INVENTORY §3) renders as *44 ready · 9 breached · 17 days live · model 3.2.0* in the readout font, always reading the live artifact |
| Thresholds as marked limits on the scale | done | `chartContract` `thresholds[]` renders as tick marks with `kind: 'kill'` styled distinctly from `'target'`/`'band'` |

### Chart renderer + performance plan
Custom SVG only — no CRT layer (explicit master rule). Tick-scale geometry precomputed once per
mount (polar math, same technique as the existing `ScoreGauge`), no per-frame recalculation.
`dial`, `bullet`, and `line` (rendered as a scrolling phosphor trace) are the primary types;
`heatmap` renders as a bracket-grid of lit/unlit cells. Glow is a static `--glow` box-shadow
token, never a live filter.

### Four-state + confidence
Established = full luminance · Accumulating = dimmed with an in-progress arc sweep (not a
spinner — the arc itself fills) · Breached = the one alert accent, red · Unavailable = unlit
channel + printed reason. **Confidence channel: blur glyph beside the readout** — a small
separate glyph, never blur over the value or interval itself (master's banned-blur-on-intervals
rule respected: the blur is on a glyph, not the data mark).

### Motion + reduced-motion
State-driven only. The in-progress arc sweep is the one non-static element and it is itself the
accumulating-state encoding (governed motion, not decoration) — under `prefers-reduced-motion`
it freezes to a static partial arc at the correct fill fraction, losing nothing.

### Vocabulary map
channel · readout · bezel · annunciator · in range / out of range · calibrated

### Named risk + control
**Risk**: Cockpit and Neon are the two closest themes in the set (both dark, both have lit
indicators) — Cockpit could slide into "Neon without the sun." **Control**: Cockpit's light is
information (a live-value readout, on whenever a channel is live); Neon's light is exclusively
an alert (glow means breach, nothing else, per Neon's own rule). See closest-pairs analysis.

### ASCII wireframe (390px, Home)
```
┌────────────────────────────────────────────┐
│ [CH-01]      COCKPIT · REPORT       [≡ NAV]│
├──────────────┬───────────────┬─────────────┤
│ 44 READY     │  9 BREACHED   │ 18d LIVE    │
├──────────────┴───────────────┴─────────────┤
│  PORTFOLIO VALUE           $XX,XXX.XX      │
│  ▲ +X.X%  today          AS OF 14:32:07    │
├──────────────────────────────────────────── ┤
│  ╭──────────────────────────────────────╮  │
│  │  TWR vs SPY          [readout trace]  │  │
│  │  ⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓⎓  │  │
│  ╰──────────────────────────────────────╯  │
├──────────────────────────────────────────── ┤
│ [HOME][RESEARCH][SCREENS][PORT][MKT][EVID] │
└────────────────────────────────────────────┘
```

### Nav + entry diagram, interaction counts
Bottom bracket bar (6 channels) at 390px, left rail at desktop. No entry page — 0 additional
interactions to reach any destination from cold load. Settings/Alerts reachable via one bracket
tap each, same budget as every other medium.

### Laws traded + compensation
Trades discoverability slightly against Jakob's Law (a bracket bar reads less immediately as
"navigation" than a labeled tab bar to a first-time user) — compensated by keeping the six
labels in plain English inside the brackets, not iconography alone.

### Library basis
Custom SVG, no chart library. No CRT layer at all (explicit exclusion — Cockpit is not
Neon/Beige Box's phosphor-tint family; it's calibrated glass, not a screen effect).

---

# 2 · NEON — synthwave sign

**Based on**: `design-refs/outrun-scene.png` (banded gradient sun, wireframe palm/grid horizon,
CRT scanlines) and `design-refs/chrome-holo-lettering.png` (chrome/holographic outlined display
lettering). Dark, saturated — but the aesthetic's normal devices (glow, saturation, scanlines)
are converted into *encodings*, not atmosphere, per the master's explicit design problem
statement for this theme.

### Tokens
| Token | Value | Use |
|---|---|---|
| `--ink-primary` | `#eafcff` | body/numeral ink |
| `--surface-ground` | `#0d0a2e` | deep indigo ground |
| `--brand-cyan` | `#3ff0ff` | tube/ink primary — **measured for contrast, not assumed** |
| `--brand-magenta` | `#ff3fd8` | tube/ink secondary |
| `--state-breach` | (glow, not a fill color) | glow is reserved exclusively for breach — see below |
| `--sun-band-lit` | `#ff9d3f` | banded-sun lit segment |

### Type roles
Chrome-outlined display face for the hero figure ONLY (never body text, never table numerals) ·
mono numerals never glowed (Share Tech Mono/VT323 for display labels only) · body sans, plain,
legible on indigo.

### Ten material dimensions
1. **Mark-making**: lit neon tube strokes for series lines; the banded sun as the hero graphic.
2. **Containers**: flat panel substrate behind data, grid-horizon decoration kept strictly
   behind and never distorting the plot.
3. **Controls**: a neon tab strip, active tab lit (this IS glow — but a nav-chrome exception the
   master doesn't ban, since "glow reserved for breach" governs *data* marks; nav-chrome
   affordance lighting is conventional UI feedback, not a data encoding — documented here so
   Phase 3's glow-exclusivity assertion can scope correctly).
4. **Navigation**: neon tab strip along the bottom.
5. **Entry**: title card, arcade attract-screen style, carrying the as-of date.
6. **Transitions**: none.
7. **Empty/loading/error**: a dead tube with its `reason` printed beneath — literally a
   half-broken sign.
8. **Vocabulary**: sign, tube, lit, dark, run, marquee.
9. **Layout rhythm**: generous dark space around each lit element — saturation inversely
   proportional to area, per the standing rule.
10. **Texture**: static scanline ground texture beneath data only, never over a figure.

### Must-include walkthrough
| Master bullet | Status | How |
|---|---|---|
| Banded sun as the evidence indicator | done | hero graphic's horizontal bands = observations/required, live-computed fraction, not decorative |
| Neon tubes as the state channel | done | lit tube = established; **unlit segments = missing observations** (accumulating), count-driven not styled; dead tube + reason = unavailable |
| Glow reserved exclusively for breach | done | `--glow` token applied ONLY where `state === 'breached'`; Phase 3 assertion 12 scans every element's computed box-shadow/filter/text-shadow and asserts the nearest capability is breached |
| Chrome/holographic lettering for hero figure only | done | one CSS custom property scoped to the single hero numeral, never applied to body/table text |
| Grid horizon as flat, never distorting substrate | done | grid rendered as a flat CSS/SVG background layer behind the chart SVG, zero shared transform with the data marks — the standing Law-of-Prägnanz rule against perspective grids that bend data |
| Title card entry with as-of date | done | entry component reads `report.json`'s as-of timestamp live |
| Scanlines as static ground texture, beneath data only | done | one precomputed tiling texture asset, `z-index` strictly below the data layer, never animated |

### Chart renderer + performance plan
`line` renders as tube-stroke (a thick rounded stroke + one static bloom PNG/SVG asset behind
it, never a live blur filter). `dial`/`fan` reuse the banded-sun geometry for anything that's
naturally "observations of required." Bloom assets precomputed at build time, one per tube
color, reused across mounts — never recomputed per frame.

### Four-state + confidence
Established = lit tube, full chroma · Accumulating = unlit tube segments proportional to missing
observations (literal, countable) · Breached = glow, and glow means only this · Unavailable =
dead tube + reason. **Confidence channel: tube chroma** — washes toward white-grey at low
confidence, saturates at high — continuous, never hue-as-confidence (chroma/saturation is not
hue) and never a three-level bucket.

### Motion + reduced-motion
Glow does not pulse, breathe, or animate — static, per the explicit master rule. Mandatory calm
setting kills glow-area and scanlines while keeping the tube encoding itself (lit/unlit segments
stay meaningful without any glow). Never the default medium.

### Vocabulary map
sign · tube · lit · dark · run · marquee

### Named risk + control
**Risk 1 (fatigue/legibility)**: saturated dark theme with light-emitting metaphors risks eye
fatigue on extended use. **Control**: mandatory calm setting (kills glow + scanlines, keeps
encoding), total accent coverage capped under ~10% per the standing rule, never the default
medium at first run. **Risk 2 (contrast trap)**: cyan-on-indigo is exactly the kind of pairing
that looks fine and measures badly. **Control**: `scripts/color-accessibility-check.mjs`
(parameterized to `src/mediums/neon/tokens.css` in Phase 3) must show ≥4.5:1 before this tokens
file ships; the token table above is a starting point, not a final measured value.

### ASCII wireframe (390px, Home)
```
┌────────────────────────────────────────────┐
│  ░░░░░░  V A L U E S I G N A L  ░░░░░░░░░  │
│         ╱▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔╲             │
│        │ ▓▓▓▓▓▓░░░░░░░░░░░░░ │ SUN=EVIDENCE│
│         ╲▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁╱             │
├────────────────────────────────────────────┤
│  ┃┃┃┃┃┃┃┃┃┃  ░░░░░░  ┃┃┃  ← tube state row │
│  PORTFOLIO   $XX,XXX.XX   ▲ +X.X%          │
├────────────────────────────────────────────┤
│  ═══════════════════ TWR tube-line ═══════ │
├────────────────────────────────────────────┤
│  [HOME][RESEARCH][SCREENS][PORT][MKT][EVID]│
└────────────────────────────────────────────┘
```

### Nav + entry diagram, interaction counts
Title card entry on first load per session (1 interaction, skippable, persisted). Neon tab strip
along the bottom, 0 additional interactions between the six destinations once past entry.

### Laws traded + compensation
Trades the Aesthetic–Usability hazard hardest of any theme — Neon is the most seductive surface
in the set, so it carries the heaviest epistemic load: literal band-fill and tube-segment counts
instead of any purely decorative confidence cue.

### Library basis
Static bloom assets, not live filters. Scanlines from a CRT-layer reference
(`mdombrov-33/vault66-crt-effect`) but **only its scanline + phosphor-tint layers** — curvature,
flicker, and glitch explicitly disabled per the master's hard constraint.

---

# 3 · POSTER — screen-printed

**Based on**: risograph and screen-printed poster/zine culture. Light, saturated — two spot inks
plus black.

### Tokens
| Token | Value | Use |
|---|---|---|
| `--ink-black` | `#161311` | body ink |
| `--surface-paper` | `#f6f1e6` | paper white ground |
| `--ink-spot-1` | `#e8432f` | spot ink A (risograph red) |
| `--ink-spot-2` | `#1f7a6c` | spot ink B (risograph teal) |
| `--state-breach` | overprint of spot-1 + spot-2 | breach = the one condition earning a real overprint |

### Type roles
Heavy grotesque display (masthead, headlines) · mono numerals (tabular) held at full contrast
against the halftone ground, never dithered themselves.

### Ten material dimensions
1. **Mark-making**: halftone dot density instead of fills — confidence and value both read
   through dot size/spacing, never a flat color fill.
2. **Containers**: printed panels with trim and registration marks.
3. **Controls**: a rubber-stamp-style toggle, a masthead issue selector.
4. **Navigation**: masthead across the top.
5. **Entry**: a cover with issue number and as-of date.
6. **Transitions**: none.
7. **Empty/loading/error**: an unprinted area (blank paper) with the `reason` set in masthead
   type — absence reads as literally unprinted, not as a fill error.
8. **Vocabulary**: issue, print run, registration, plate.
9. **Layout rhythm**: print-grid columns, generous trim margins.
10. **Texture**: print-bite/paper-tooth beneath data only, deterministic per metric id.

### Must-include walkthrough
| Master bullet | Status | How |
|---|---|---|
| Halftone dot density instead of fills | done | canvas halftone renderer computes dot radius from value, deterministic seed from metric id |
| Exactly two spot inks plus black | done | token contract hard-caps the palette at 2 spot + black — no third chromatic added anywhere |
| Overprint only where two real conditions coincide | done | overprint mark is a rendering rule keyed to an actual dual-condition (e.g. breach + high-confidence), never decorative layering |
| Registration offset as the confidence channel | done | offset magnitude ∝ (1 − confidence), capped, deterministic seed, **never applied to text** |
| Trim and registration marks | done | static SVG corner marks on every printed panel container |
| Cover entry with issue number + as-of date | done | issue number = a stable per-session counter or the model's semantic version; as-of from live data |

### Chart renderer + performance plan
Canvas halftone renderer (dot grid computed once per chart mount from a deterministic seed,
cached as an offscreen bitmap — never recomputed per frame). Registration offset is a single
`transform: translate()` on a duplicate ink layer, capped at a small max pixel value, seeded
identically to the halftone dots so screenshots don't churn.

### Four-state + confidence
Established = fine, dense halftone in perfect register · Accumulating = coarse, open dots with
the count printed beside them · Breached = second ink overprinted (the theme's one alert
device) · Unavailable = unprinted area with `reason`. **Confidence: registration offset** —
larger offset at lower confidence, capped, never on text (explicit risk control below).

### Motion + reduced-motion
None (static medium by nature — a poster doesn't move). Fully compliant with
`prefers-reduced-motion` trivially.

### Vocabulary map
issue · print run · registration · plate

### Named risk + control
**Risk**: legibility at 390px, and misregistration reading as a rendering bug rather than a
deliberate confidence signal. **Control**: cap the offset to a small, named maximum; never apply
it to text (numerals/labels always register perfectly); seed deterministically from metric id;
name the device in a persistent legend ("registration offset shows confidence") so it reads as
intentional on first encounter, not broken.

### ASCII wireframe (390px, Home)
```
┌────────────────────────────────────────────┐
│▓▓▓  V A L U E S I G N A L   — ISSUE 12  ▓▓▓│
├────────────────────────────────────────────┤
│ ░░ 44 READY ░░  ▓▓ 9 BREACH ▓▓  18d LIVE   │
├────────────────────────────────────────────┤
│  PORTFOLIO VALUE        $XX,XXX.XX         │
│  ░░░▓▓▓░░░ +X.X% today   AS OF <date>      │
├────────────────────────────────────────────┤
│  · · · · TWR halftone plot · · · · · · ·   │
│  ·  ·   · ·    ·  ·  ·   ·  · ·  ·  ·      │
├────────────────────────────────────────────┤
│ ▢HOME ▢RESEARCH ▢SCREENS ▢PORT ▢MKT ▢EVID  │
└────────────────────────────────────────────┘
```

### Nav + entry diagram, interaction counts
Cover entry on first load per session (1 interaction, skippable, persisted, deep-link bypass
structural). Masthead nav thereafter, 0 additional interactions between destinations.

### Laws traded + compensation
Trades a little Fitts's Law precision at 390px — masthead tabs are print-convention-sized, not
maximized for thumb reach — compensated by keeping all six tabs text-labeled and full-width
tappable (44px height even where the visual mark is smaller).

### Library basis
Custom canvas halftone renderer — no chart library. Deterministic registration offset, not a
live physics/randomness library.

---

# 4 · TICKER — the wire feed

**Based on**: stock tickers, wire feeds, split-flap boards. Dark, flat, zero chrome.

### Tokens
| Token | Value | Use |
|---|---|---|
| `--ink-primary` | `#e4e4e4` | body/numeral |
| `--surface-ground` | `#050505` | flat near-black |
| `--rule-hairline` | `#232323` | row separators, zero card chrome |
| `--state-breach` | `#ff4d4d` | leftmost-rule accent |
| `--state-gain` | `#37d67a` | directional glyph |
| `--state-loss` | `#ff6b6b` | directional glyph |

### Type roles
Monospace everywhere, including labels (not just numerals) — tabular, tight leading.

### Ten material dimensions
1. **Mark-making**: inline sparklines with the threshold drawn directly on them.
2. **Containers**: no cards at all — hairline rules only, rows are the only structure.
3. **Controls**: a session bar with channel tabs.
4. **Navigation**: session bar across the top.
5. **Entry**: none.
6. **Transitions**: values flip in place; rows reorder visibly and slowly enough to follow.
7. **Empty/loading/error**: a printed no-report line with the `reason`, in the same monospace
   row grammar as every other row — absence is just another row, not a different widget.
8. **Vocabulary**: feed, wire, session, print.
9. **Layout rhythm**: dense rows, fixed-width status column in every row.
10. **Texture**: none — flat is the material.

### Must-include walkthrough
| Master bullet | Status | How |
|---|---|---|
| Monospace everywhere including labels | done | one mono face token used for every text role, no display face at all |
| No cards, hairline rules only | done | `components.Container` renders a `<div>` with a single bottom hairline, no radius/shadow/fill |
| Fixed-width status column with glyph + N/M | done | every row's rightmost column is a fixed-char-width status cell: glyph + `observations/required` |
| Breached rows accented in the leftmost rule | done | `--state-breach` applied as a 2px left border, never as a background fill (never shares the loss color per the standing rule — breach and loss are visually distinct devices) |
| Values that flip in place, rows reorder slowly | done | one of the two governed-motion exceptions in the whole rebuild (Ticker's flip-and-reorder); real values only, pauses on touch/focus, full static readability under reduced-motion |
| Printed no-report line with reason | done | same row grammar, `state.unavailable` renders as a row, not a modal or empty-state block |

### Chart renderer + performance plan
Canvas rows for scroll performance (per the master — dense feeds need canvas-level row
virtualization, reusing the existing `@tanstack/react-virtual` dependency for windowing, with
canvas or lightweight DOM rows underneath). Sparklines are the one SVG chart type used inline,
tiny, precomputed per row.

### Four-state + confidence
Established = normal row · Accumulating = status glyph + `N/M` fraction in the fixed column ·
Breached = accent in the leftmost rule · Unavailable = printed no-report row with `reason`.
**Confidence channel: transparency overlay** on the row's numeral column — a separate, named,
non-hue channel.

### Motion + reduced-motion
The governed exception: flip-and-reorder, real values only, slow enough to read in one pass,
pauses on touch and focus, manual scroll in both directions always available, **full static
readability under `prefers-reduced-motion`** — every value that was ever visible in motion must
still be reachable/visible in the reduced pass (Phase 3 assertion 8 checks this by set
inclusion). Mandatory calm setting; never the default medium (fatigue risk, per master).

### Vocabulary map
feed · wire · session · print

### Named risk + control
**Risk**: fatigue from a dense, moving, monospace-everywhere surface held open for long
sessions. **Control**: mandatory calm setting that stops the flip/reorder motion entirely while
keeping every value statically legible; Ticker is never the default medium.

### ASCII wireframe (390px, Home)
```
┌────────────────────────────────────────────┐
│ SESSION  HOME RSCH SCRN PORT MKT EVID  18d │
├────────────────────────────────────────────┤
│ PORT.VAL  XX,XXX.XX  ▲+X.X%  R  44/64 rdy  │
│ TWR/SPY   ⟋⟍⟋⟍⟋⟍⟋⟍   +X.X%  R  ready      │
│▎DFL.SHRP  0.238       BREACH  B  9 breach  │
│ IC-1D     -0.038      ↓       A  60 obs    │
│ COAST-FI  n/a          —      U  no data   │
├────────────────────────────────────────────┤
│  no-report: early-session — gated, shadow  │
└────────────────────────────────────────────┘
```

### Nav + entry diagram, interaction counts
Session bar across the top holds all six destination tabs as channels — 0 additional
interactions, no entry page.

### Laws traded + compensation
Trades Miller's Law hardest — Ticker is the explicit exception to "one primary work per
viewport," by design (a wire feed's whole point is density) — compensated by the fixed-width
status column giving every row the identical scan pattern, so density doesn't cost
comprehension.

### Library basis
Custom canvas rows for scroll performance — no chart library, no roughViz-style dependency.

---

# 5 · BOOK — printed reference

**Based on**: Value Line sheets, annual reports, statistical abstracts, scholarly footnoting,
letterpress page structure. Light.

### Tokens
| Token | Value | Use |
|---|---|---|
| `--ink-primary` | `#1c1a17` | body ink, near-black |
| `--surface-page` | `#f7f4ec` | ivory page |
| `--rule-hairline` | `#c9c2b2` | thin axes, table rules |
| `--ink-editorial` | `#8a1f11` | the one editorial red |

### Type roles
Serif with real (old-style) figures for body/prose, mono for tables/numerals, generous leading,
short measures (narrow column widths — a print convention, not a layout accident).

### Ten material dimensions
1. **Mark-making**: small-multiple grids, thin axes, no fills.
2. **Containers**: ruled tables with folios (page numbers).
3. **Controls**: a thumb index down the edge.
4. **Navigation**: running heads + thumb index.
5. **Entry**: a table of contents.
6. **Transitions**: none — page turns are instant.
7. **Empty/loading/error**: a bracketed editorial note, e.g. `[not yet reported — {reason}]`.
8. **Vocabulary**: chapter, folio, footnote, plate, appendix.
9. **Layout rhythm**: print conventions — running heads, folios, generous leading, footnote
   rules at the foot of each section.
10. **Texture**: none beyond paper-white ground; no grain layer needed at this density.

### Must-include walkthrough
| Master bullet | Status | How |
|---|---|---|
| Table of contents as entry | done | entry lists the six destinations as chapters with page-number-style folios |
| Thumb index down the edge | done | a persistent edge rail of destination initials, tap-target 44px each |
| Running heads and folios | done | every screen carries a running head (current destination + section) and a folio (position indicator) |
| Numbered footnotes at the foot, daggers/superscripts on the plot | done | disclosures render as numbered footnotes; a chart's annotation point carries a superscript linking to its footnote |
| Small-multiple grids, thin axes, no fills | done | `chart` contract renders line/bar as thin-stroke, no-fill by default in this medium's renderer |
| Roman/italic as the state encoding, not color | done | established = roman; accumulating = italic + footnote count; breached = **bold** + editorial-red dagger; unavailable = bracketed note — four typographic weights, zero reliance on hue |

### Chart renderer + performance plan
Custom SVG, print conventions — thin 1px strokes, no fills, small-multiple layout (many small
charts sharing one axis scale rather than one large chart). Cheap to render; no precompute
needed beyond the shared seed for any deterministic element.

### Four-state + confidence
Established = roman type, solid rule · Accumulating = italic + superscript footnote with the
count · Breached = **bold** + editorial-red dagger (†) · Unavailable = bracketed note,
`[not yet reported — {reason}]`. **Confidence: a signed editor's note per section** — plain-text,
attributed, distinct from the quantitative state marks above it.

### Motion + reduced-motion
None. Print doesn't move; trivially compliant.

### Vocabulary map
chapter · folio · footnote · plate · appendix

### Named risk + control
**Risk**: small type at high information density. **Control**: 16px body floor is a hard rule
(not "as small as print allows"); density comes from leading and rule placement, never from
shrinking type below the shared floor — typefloor's CTM-aware check applies here exactly as
everywhere else, including any SVG footnote markers.

### ASCII wireframe (390px, Home)
```
┌────────────────────────────────────────────┐
│ Ch.1 · REPORT              ValueSignal · 4 │
├────────────────────────────────────────────┤
│ Evidence — 44 ready, 9 breached¹, 18d live  │
├────────────────────────────────────────────┤
│  Portfolio value      $XX,XXX.XX            │
│  change today  +X.X%     as of <date>       │
├────────────────────────────────────────────┤
│  Fig. 1 — TWR vs S&P 500                    │
│  ┌───────────────────────┐                  │
│  │  thin-line small-mult  │                 │
│  └───────────────────────┘                  │
├────────────────────────────────────────────┤
│ ¹ Deflated Sharpe 0.238, below the 0.95     │
│   kill threshold. See Evidence, p.6.        │
└────────────────────────────────────────────┘
```

### Nav + entry diagram, interaction counts
Table-of-contents entry on first load per session (1 interaction, skippable, deep-link bypass
structural). Thumb index + running heads thereafter, 0 additional interactions between
destinations.

### Laws traded + compensation
Trades some Fitts's Law reach — a thumb index is a period-accurate device, not maximized for
one-handed reach at every screen height — compensated by keeping the index itself full-height
and 44px per target regardless of content length.

### Library basis
Custom SVG, print conventions — no chart library.

---

# 6 · BLUEPRINT — engineering drawing

**Based on**: drafting sets — title blocks, revision stamps, dimension lines, tolerance bands,
zone markers, index sheets. Dark. Uniquely apt: the kill thresholds *are* tolerances, and the
validation state *is* a revision history.

### Tokens
| Token | Value | Use |
|---|---|---|
| `--ink-primary` | `#eaf6ff` | drafted-line white |
| `--surface-ground` | `#0b1e33` | deep indigo drafting-table blue |
| `--rule-cyan` | `#7fd4ff` | cyan-white hairlines |
| `--state-breach` | `#ff6b57` | out-of-tolerance mark |
| `--grid-construction` | `#132a44` | faint construction grid, lowest luminance step |

### Type roles
Drafting geometric sans, all-caps micro-labels, mono numerals (dimensioned figures).

### Ten material dimensions
1. **Mark-making**: dimensioned tolerance bands with the limit labeled directly on the line.
2. **Containers**: a sheet border with zone markers (like a drawing's edge coordinates).
3. **Controls**: a revision-stamp-style toggle.
4. **Navigation**: zone tabs along the sheet edge.
5. **Entry**: a sheet index with revision states.
6. **Transitions**: none.
7. **Empty/loading/error**: a not-yet-specified dimension — a dashed leader line ending in "?"
   rather than a number.
8. **Vocabulary**: sheet, zone, revision, tolerance, title block.
9. **Layout rhythm**: drafted grid, consistent pen-width scale (heavier lines for primary
   dimensions, hairline for construction).
10. **Texture**: faint construction grid at the lowest luminance step, beneath data only.

### Must-include walkthrough
| Master bullet | Status | How |
|---|---|---|
| Thresholds as dimensioned tolerance bands, limit labeled | done | `chartContract` `thresholds[]` renders as a dimension line with its `kill_threshold_value` printed at the line end, exactly like an engineering tolerance |
| Leader-line callouts | done | `annotations[]` render as a leader line + label, shared contract requirement |
| Sheet border with zone markers | done | `components.Container` = a bordered sheet with edge coordinate labels (A1, B2, …) |
| Title block: model version, config hash, as-of, revision state | done | the first-viewport evidence strip renders as a literal title block in the bottom-right corner, drafting convention |
| Dashed construction lines for accumulating, count dimensioned | done | accumulating state renders a dashed line with the `N of M` printed as a dimension figure |
| Sheet index as entry | done | entry lists the six destinations as sheet numbers with revision letters |

### Chart renderer + performance plan
Custom SVG with a drafted pen-width scale (2–3 stroke weights, applied consistently: heavy for
primary dimension, hairline for construction/grid). Tolerance-band rendering and leader-line
placement are geometry-only, cheap to compute, no precompute needed.

### Four-state + confidence
Established = solid drawn line · Accumulating = dashed construction line, count dimensioned ·
Breached = out-of-tolerance mark (a hatched/flagged dimension) · Unavailable = not-yet-specified
dimension (dashed leader to "?"). **Confidence**: rendered via line weight/pen-width scale — a
lower-confidence figure draws with the lighter (construction) pen weight even when its state is
established, a separate channel from the four-state dash pattern.

### Motion + reduced-motion
None; drafted lines are static by convention. Trivially compliant.

### Vocabulary map
sheet · zone · revision · tolerance · title block

### Named risk + control
**Risk**: over-precision — a drafting metaphor can imply engineering certainty the model doesn't
have. **Control**: the tolerance-band device is used *only* for actual kill thresholds (real
numeric limits), never invented for figures that don't have one; the title block's revision
state explicitly shows "unpromoted" rather than a false "Rev. A, final."

### ASCII wireframe (390px, Home)
```
┌────────────────────────────────────────────┐
│ A1  SHEET 01/06 — REPORT           ZONE ►  │
├────────────────────────────────────────────┤
│ ├──44 READY──┤├──9 BREACH──┤├─18d LIVE──┤  │
├────────────────────────────────────────────┤
│ ⌐ PORTFOLIO VALUE          $XX,XXX.XX  ⌐   │
│   +X.X% ────dimensioned────  AS OF <date>  │
├────────────────────────────────────────────┤
│  TWR vs SPY  ┄┄┄┄┄┄┄┄┄┄┄●━━━━━━━━━━━━━━━   │
│              tolerance band, limit 0.95    │
├──────────────────────────────┬─────────────┤
│  ZONE: HOME RSCH SCRN PORT   │ TITLE BLOCK │
│  MKT EVID                    │ v3.2.0 REV- │
└──────────────────────────────┴─────────────┘
```

### Nav + entry diagram, interaction counts
Sheet-index entry on first load per session (1 interaction, skippable, deep-link bypass
structural). Zone tabs along the sheet edge thereafter, 0 additional interactions between
destinations.

### Laws traded + compensation
Trades a little Jakob's Law familiarity — zone tabs read as drafting notation before they read
as "navigation" to a first-time visitor — compensated by plain-English zone labels (not just
coordinate codes) alongside the drafting-accurate A1/B2-style corner marks.

### Library basis
Custom SVG with a drafted pen-width scale — no chart library.

---

# 7 · STAR CHART — astronomical plate

**Based on**: star atlases and observatory plates — magnitude circles, coordinate graticules,
open circles for unconfirmed objects, error ellipses, seeing-condition notes. Dark, calm.

### Tokens
| Token | Value | Use |
|---|---|---|
| `--ink-primary` | `#eef2ff` | plate-white ink |
| `--surface-ground` | `#050818` | deep blue-black |
| `--graticule` | `#1a2440` | faint coordinate grid |
| `--state-breach` | `#ff8a65` | cross-hair notation |

### Type roles
Small caps for labels, italic for designations (catalog-style naming), mono numerals.

### Ten material dimensions
1. **Mark-making**: magnitude circles scaled by **area, never radius** (the correct
   astronomical convention — radius-scaling exaggerates large values); error ellipses for
   confidence intervals.
2. **Containers**: a faint graticule, every object plotted at a real coordinate — no card
   containers at all in the plot area.
3. **Controls**: a corner legend key that doubles as navigation.
4. **Navigation**: corner legend.
5. **Entry**: a plate index by epoch.
6. **Transitions**: none.
7. **Empty/loading/error**: a catalogued position with nothing plotted — the coordinate exists
   in the index but no mark appears on the plate, with the `reason` in the legend.
8. **Vocabulary**: observation, plate, epoch, designation, magnitude.
9. **Layout rhythm**: calm, generous dark space around each plotted mark — sparse by design,
   matching the reference material.
10. **Texture**: none beyond the graticule itself.

### Must-include walkthrough
| Master bullet | Status | How |
|---|---|---|
| Magnitude scaled by area, never radius | done | the `dial`/`scatter`-family renderer computes mark size as `sqrt(value)` scaling so rendered *area* is proportional, not radius |
| Faint graticule, every object at a real coordinate | done | every metric/figure gets a deterministic coordinate from its capabilityId hash — nothing floats unplaced |
| Error ellipses for confidence intervals | done | where a metric publishes a bootstrap CI (e.g. `ic_bootstrap_ci`), the mark renders as an ellipse sized to the interval, not a circle |
| Open circles for unconfirmed, count beside them | done | accumulating state = open (unfilled) circle + the `N of M` count printed beside it, exactly the master's specified device |
| Corner legend key doubling as navigation | done | `nav.model: 'legend'` — the corner legend both explains marks and holds the six destination links |
| Plate index as entry | done | entry lists destinations as plates by epoch (as-of date) |

### Chart renderer + performance plan
Custom SVG; ellipse geometry computed directly from each metric's published interval bounds
(no invented ellipses for metrics without a real CI — those render as plain circles). Cheap,
static per mount.

### Four-state + confidence
Established = filled point · Accumulating = open circle with the count beside it · Breached =
cross-hair notation over the mark · Unavailable = a catalogued position with nothing plotted
(coordinate reserved, mark absent, reason in the legend). **Confidence: a seeing-conditions band
in the legend** — a plain-text astronomical-observing-conditions note, a separate channel from
the four marks above.

### Motion + reduced-motion
None; the plate is static by convention (calm theme, explicitly). Trivially compliant.

### Vocabulary map
observation · plate · epoch · designation · magnitude

### Named risk + control
**Risk**: sparse layout at 390px could waste vertical space or force excessive scrolling for a
64-metric plate. **Control**: the graticule tiles into a scrollable multi-plate view rather than
one giant sparse canvas — density is managed by paging plates (by group A–H), not by cramming.

### ASCII wireframe (390px, Home)
```
┌────────────────────────────────────────────┐
│ ·  ·    PLATE I — REPORT   ·      ·    ·   │
│    ·         ·        ·        ·           │
│  ·      ⊙ PORT.VAL         ·       ·       │
│              $XX,XXX.XX  ·                 │
│    ·    ·    +X.X%  ·         ·      ·     │
│  ·  ○ TWR (18 of 24 obs)  ·        ·       │
│         ·        ·    ⊕ DFL.SHARPE ·       │
│    ·  breached, ✛           ·      ·       │
├────────────────────────────────────────────┤
│ LEGEND: ⊙ established ○ accum ✛ breach     │
│ HOME RSCH SCRN PORT MKT EVID   ·  epoch:now│
└────────────────────────────────────────────┘
```

### Nav + entry diagram, interaction counts
Plate-index entry on first load per session (1 interaction, skippable, deep-link bypass
structural). Corner legend thereafter, 0 additional interactions between destinations.

### Laws traded + compensation
Trades discoverability against Jakob's Law hardest of the twelve — a corner legend is the least
conventional nav placement in the set — compensated by making the legend persistent (never
collapsed) and thumb-reachable per the master's corner-affordance ban (no destination hides
behind a corner-only tap at 390px — the legend itself must be reachable, not just visible).

### Library basis
Custom SVG; ellipse geometry from interval bounds — no chart library.

---

# 8 · NEWSPAPER — graphics desk

**Based on**: newspaper graphics desks — mastheads, headlines that state the finding,
standfirsts, bylines, printed corrections, column rules, prose annotation pointing into the
plot. Light, warm.

### Tokens
| Token | Value | Use |
|---|---|---|
| `--ink-primary` | `#1a1714` | body/headline ink |
| `--surface-ground` | `#faf6ee` | warm white |
| `--rule-column` | `#d8cfba` | column rules |
| `--accent-standfirst` | `#8a2a1f` | the one accent — standfirst flag |

### Type roles
Headline serif (display), body serif, mono numerals in tables.

### Ten material dimensions
1. **Mark-making**: journalistic line and bar with prose annotation pointing directly into the
   plot (an arrow + a sentence, not a legend).
2. **Containers**: column rules as the container device — vertical rules, not boxes.
3. **Controls**: masthead section tabs.
4. **Navigation**: masthead section tabs.
5. **Entry**: a front page with a lead story (the top actionable ticker, rendered live).
6. **Transitions**: none.
7. **Empty/loading/error**: "not yet reported" with the `reason`, styled as a wire-service
   placeholder line.
8. **Vocabulary**: headline, standfirst, byline, correction, masthead.
9. **Layout rhythm**: column grid, generous rule-separated sections.
10. **Texture**: none — newsprint-white ground is enough; no grain layer needed.

### Must-include walkthrough
| Master bullet | Status | How |
|---|---|---|
| Headline above every chart, generated from `reads`/`status`, never freehand | done | `core/headline.js` — the one shared, unit-tested headline generator; Newspaper is its primary consumer |
| The interrogative rule: accumulating makes assertion structurally impossible | done | `headline.js`'s `accumulating` branch is a deterministic template, never a declarative sentence — Phase 3 assertion 10 checks no accumulating metric ever gets a declarative headline |
| Standfirst flag for breached | done | breached metrics render a standfirst-style flag line above the headline |
| Bylined confidence note | done | confidence renders as a signed byline-style line, e.g. "Confidence: low, per {basis}." |
| Column rules as containers | done | `components.Container` = a vertical column rule, not a box |
| Masthead section tabs | done | `nav.model: 'top'`, masthead-styled |
| Front page entry, lead story = top actionable ticker | done | entry reads live data for the actual top-ranked/most-actionable name, never a placeholder |
| "Not yet reported" with reason | done | `state.unavailable` renders as a wire-service placeholder line, reason inline |

### Chart renderer + performance plan
Custom SVG; journalistic line/bar with a required text annotation (arrow + one sentence) pointing
at the event that explains the shape — this is the standing annotation-required rule made
literal in Newspaper's own material. No precompute needed; headline strings are the one
generated-text surface, unit-tested independently of rendering.

### Four-state + confidence
Established = declarative headline, e.g. "Momentum leg has led the composite for six weeks" ·
Accumulating = interrogative headline, e.g. "Is the momentum leg leading? 17 of 24 periods
observed" · Breached = standfirst flag + declarative headline · Unavailable = "Not yet reported —
{reason}". **Confidence: a bylined confidence note**, separate line, separate channel from the
headline's declarative/interrogative grammar.

### Motion + reduced-motion
None; a newspaper page doesn't move. Trivially compliant.

### Vocabulary map
headline · standfirst · byline · correction · masthead

### Named risk + control
**Risk**: a generated headline could accidentally overstate a marginal or accumulating result if
the template logic is loose. **Control**: `headline.js` is unit-tested directly (not just via
DOM assertion) with the fixed rule "no declarative headline for `status: accumulating`," and its
fallback for an unparsable `reads` string is itself non-declarative rather than defaulting to an
assertion.

### ASCII wireframe (390px, Home)
```
┌────────────────────────────────────────────┐
│  THE VALUESIGNAL REPORT · 18 DAYS LIVE      │
│  HOME | RESEARCH | SCREENS | PORT | MKT     │
├────────────────────────────────────────────┤
│ PORTFOLIO UP $X TODAY, DRIVEN BY TECH NAMES │
│ Standfirst: 9 of 64 checks still breached.  │
│ By the Evidence Desk. As of <date>.         │
├────────────────────────────────────────────┤
│ │ Is the swing composite earning its keep?  │
│ │ 60 of 60 weekly obs. → see chart, right.  │
│ │  ⟋⟍⟋⟍⟋⟍⟋⟍⟋⟍⟋⟍   ← rank IC, still weak    │
├────────────────────────────────────────────┤
│ NOT YET REPORTED: prospective IC — 0 of 24  │
│ eligible periods observed.                  │
└────────────────────────────────────────────┘
```

### Nav + entry diagram, interaction counts
Front-page entry on first load per session (1 interaction, skippable, deep-link bypass
structural), rendering the actual top-actionable ticker as the lead story. Masthead section tabs
thereafter, 0 additional interactions between destinations.

### Laws traded + compensation
Trades nothing significant against the standing laws — Newspaper is close to Jakob's Law
familiar territory (people already know how to read a newspaper front page) — its risk is purely
editorial (see above), not navigational.

### Library basis
Custom SVG; headline strings generated from `reads`/`status` — no chart library, no third-party
headline-generation dependency.

---

# 9 · CHALKBOARD — hand-lettered slate

**Based on**: `design-refs/chalkboard-pub-board.jpg` (the hand-lettered pub board) and the
companion doc's second reference (a slate-board game interface — not separately imported this
session; substituted with the master's detailed prose spec, which is complete). Dark slate.

### Tokens
| Token | Value | Use |
|---|---|---|
| `--chalk-white` | `#f4f1e8` | body chalk |
| `--surface-slate` | `#2b3339` | slate ground — never pure black |
| `--frame-wood` | `#5b4634` | wooden frame surround |
| `--chalk-gain` | `#8fd19e` | gain chalk |
| `--chalk-loss` | `#e3897a` | loss chalk |
| `--chalk-alert` | `#f2c14e` | the one alert chalk |

### Type roles
Hand-lettered display for **headings only** (varied letterforms line to line); clean mono for
every label and figure — hand-lettering never touches a number or a data label, the master's
explicit risk control.

### Ten material dimensions
1. **Mark-making**: chalk strokes — broken grainy edge, pressure variation, always slightly
   transparent to the slate beneath.
2. **Containers**: hand-drawn boxes, corners overshooting slightly.
3. **Controls**: a chalk tray along the bottom edge.
4. **Navigation**: chalk tray, thumb-reachable.
5. **Entry**: none — the board is already written on when you walk in.
6. **Transitions**: none.
7. **Empty/loading/error**: a blank hand-drawn box with a "?" and the `reason` beneath.
8. **Vocabulary**: board, chalk, worked example, margin, wipe, do not erase.
9. **Layout rhythm**: banner ribbons as section headings, ornamental flourishes/rules separating
   blocks, everything inside the wooden frame.
10. **Texture**: slate grain beneath data, never pure black at any luminance step.

### Must-include walkthrough
| Master bullet | Status | How |
|---|---|---|
| Chalk-stroke rendering, broken edge, pressure variation, always slightly transparent | done | rough.js renderer, roughness/bowing bound to confidence, `seedFor(metricId)` deterministic |
| Freehand axes/gridlines, ruled but never perfectly straight | done | same rough.js renderer applied to axis geometry, not just data strokes |
| Banner ribbons as section headings, hand-drawn | done | `components.SectionHeading` = a ribbon-shaped hand-drawn container |
| Dotted leader lines from every label to its value | done | **the single most useful device for the 64-metric list**, per the master — every `WallLabel` instance in this medium draws a dotted rough.js line from label to value, Uniform Connectedness applied literally |
| Hand-drawn boxes as containers, corners overshooting | done | `components.Container` = rough.js rectangle with intentional corner overshoot |
| Hand-drawn arrows as annotation | done | `annotations[].kind: 'arrow'` renders as a rough.js arrow stroke |
| Key figure outlined, drop-shadowed, double-underlined | done | the Home first-viewport portfolio value gets this exact treatment — outline + drop shadow + double underline, chalk-white |
| Erasure smudges as the previous-period mark | done | a prior value renders as a half-wiped stroke (lower opacity, blurred edge) **behind** the current value in stacking order, at a luminance step that can't be confused with it — Phase 3 assertion 11 checks both the stacking order and the luminance delta |
| DO NOT ERASE corner: model version, config hash, as-of | done | the provenance strip renders literally in a corner marked "DO NOT ERASE" |
| Chalk tray navigation, thumb-reachable | done | `nav.model: 'bottom'`, styled as a tray holding six chalk-stick destination marks |
| Wooden frame around the slate | done | outermost app-shell border, `--frame-wood`, applied once at the shell level |

### Chart renderer + performance plan
rough.js, roughness/bowing parameters bound to the metric's `confidenceOf()` level — heavy,
confident strokes for high confidence, light and sketchy for low. SVG filter work (any
`feTurbulence`/displacement rough.js needs internally) is precomputed once per mount, never
animated, never applied to numerals (the standing numerals-stay-clean rule, doubly explicit in
this theme's own risk section).

### Four-state + confidence
Established = firm confident stroke · Accumulating = faint dotted chalk with the count written
beside it · Breached = circled in the alert chalk and double-underlined · Unavailable = blank
hand-drawn box, "?", reason beneath. **Confidence: chalk pressure** — heavy for high, light for
low, a variable distinct from completeness (an established-but-low-confidence metric still
draws faint, even though it's not "accumulating").

### Motion + reduced-motion
None. Trivially compliant.

### Vocabulary map
board · chalk · worked example · margin · wipe · do not erase

### Named risk + control
**Risk 1**: the erasure smudge being mistaken for a current value. **Control**: fixed stacking
order (smudge always behind, asserted mechanically in Phase 3) + a mandatory luminance-step gap
between smudge opacity and current-value opacity, not just a hopeful visual convention.
**Risk 2**: hand-lettering hurting legibility if it leaks into labels or figures. **Control**:
varied letterforms are a heading-only material — the type-role table above is the enforcement
point, and `WallLabel`'s structured-parts contract makes it structurally impossible for
hand-lettering to reach a numeral (numerals always render through the shared mono face).

### ASCII wireframe (390px, Home)
```
╔════════════════════════════════════════════╗
║ ┌ REPORT ┐  (hand ribbon)                   ║
║  44 ready ····· 9 breached ····· 18d live   ║
║ ┌──────────────────────────────────────┐    ║
║ │  PORTFOLIO VALUE                      │    ║
║ │  ‾‾$XX,XXX.XX‾‾   (double-underlined) │    ║
║ │  ~~~$XX,XXX~~~ (smudge, prior, faint) │    ║
║ └──────────────────────────────────────┘    ║
║  TWR vs SPY ·········→ +X.X% ·····          ║
║  ╱╲_╱╲___╱╲___ (chalk line, freehand axis)  ║
║ [DO NOT ERASE: v3.2.0 · <hash> · <date>]    ║
╟──────────────────────────────────────────────╢
║ ✎HOME ✎RSCH ✎SCRN ✎PORT ✎MKT ✎EVID (tray)  ║
╚════════════════════════════════════════════╝
```

### Nav + entry diagram, interaction counts
No entry — the board is already written on. Chalk tray at the bottom, 0 additional interactions
between the six destinations from cold load.

### Laws traded + compensation
Trades nothing against navigation laws (chalk tray is a conventional bottom bar in different
material) — its only real risk is legibility, addressed above via the type-role hard rule.

### Library basis
rough.js directly, with pressure bound to confidence, deterministic seeds from metric id — not
`roughViz` (which is D3 v5-coupled and would pull a second charting stack the app doesn't need).

---

# 10 · BEIGE BOX — mid-90s desktop

**Based on**: `design-refs/beige-box-computer.png` (cream-plastic desktop, dark-phosphor CRT).
Warm grey plastic.

### Tokens
| Token | Value | Use |
|---|---|---|
| `--ink-primary` | `#1e1c18` | window body text |
| `--surface-plastic` | `#d9d3c4` | warm-grey plastic chrome |
| `--surface-phosphor` | `#16221a` | content-area phosphor tint |
| `--bevel-highlight` | `#f4f0e6` | hard 1px bevel highlight |
| `--bevel-shadow` | `#8a8374` | hard 1px bevel shadow |
| `--state-breach` | `#c23b2e` | alert-box marker |

### Type roles
Bitmap-flavored mono, held above the 16px floor and never below it (explicit master rule — this
face is the one most tempted to go too small).

### Ten material dimensions
1. **Mark-making**: 1-bit dithered fills, hard 1px axes.
2. **Containers**: windows with title bars, one per metric group.
3. **Controls**: bevelled buttons, hard 1px highlight + shadow, never soft shadows.
4. **Navigation**: menu bar across the very top — the most literal "menu at the top" in the set.
5. **Entry**: a desktop of icons, destinations as icons.
6. **Transitions**: none.
7. **Empty/loading/error**: greyed-out disabled control, reason in the status bar.
8. **Vocabulary**: window, menu, dialog, status bar, disabled, desktop.
9. **Layout rhythm**: chunky hard-edged bevels, resize grips, dotted focus rectangles.
10. **Texture**: phosphor tint on content areas, plastic grain on chrome, beneath data only.

### Must-include walkthrough
| Master bullet | Status | How |
|---|---|---|
| Menu bar across the very top as navigation | done | `nav.model: 'menu-bar'`, destinations as menus; **at 390px it resolves to a thumb-reachable trigger** (Fitts's Law compensation, below) |
| Windows with title bars, one per metric group | done | `components.Container` = a titled window, used per section |
| Bevelled controls, hard 1px highlight/shadow, never soft | done | extracted from `98.css`'s bevel geometry pattern, never the library imported wholesale |
| Status bar carrying as-of + selected-item reason | done | persistent bottom status bar, live-bound to the current selection's `reason`/as-of |
| Progress bar for accumulating evidence, showing 17 of 24 | done | native `<progress>`-styled bar, `value`/`max` bound directly to `observations`/`required` |
| Greyed-out disabled controls, reason in status bar | done | `state.unavailable` = a disabled-styled control; hovering/selecting it writes its `reason` into the status bar |
| 1-bit dithering as the confidence channel | done | dither density (dot pattern spacing) bound to `confidenceOf()`, distinct from the value's own fill |
| Desktop entry, destinations as icons | done | entry renders the six destinations as desktop icons |
| Phosphor tint content areas, plastic grain chrome | done | two separate texture layers, both strictly beneath data |

### Chart renderer + performance plan
1-bit dithered canvas fills for anything that would otherwise be a flat color fill; hard 1px SVG
axes for line/bar. Dither pattern precomputed per confidence bucket (continuous value, but the
rendered dither texture can be one of a small precomputed set interpolated by density — cheap).

### Four-state + confidence
Established = normal window · Accumulating = progress bar showing real `N of M` · Breached = an
alert-box marker (title-bar icon + colored border) · Unavailable = greyed-out disabled control,
reason in the status bar. **Confidence: 1-bit dither density** on a fill, separate from the
value/state encodings above it.

### Motion + reduced-motion
None. Trivially compliant. No CRT curvature, no flicker (explicit master rule) — tint and
scanline-free grain only.

### Vocabulary map
window · menu · dialog · status bar · disabled · desktop

### Named risk + control
**Risk**: kitsch, and beige-on-beige contrast failing easily. **Control**: bevels are hard 1–2px
edges only, never drop shadows (keeps it structural, not decorative-nostalgic); every beige pair
including disabled-against-its-window is measured by
`scripts/color-accessibility-check.mjs` (parameterized in Phase 3) before shipping — no pair
ships on assumption.

### ASCII wireframe (390px, Home)
```
┌────────────────────────────────────────────┐
│ File Edit View Screens Portfolio Help  [≡] │ ← menu bar (390px: tap ≡)
├────────────────────────────────────────────┤
│ ┌ Report ──────────────────────────── □ ─┐ │
│ │ Portfolio Value        $XX,XXX.XX      │ │
│ │ ▓▓▓▓▓▓░░░░ +X.X% today   as of <date>  │ │
│ ├─────────────────────────────────────────┤ │
│ │ [██████████████░░░░░░] 18 of 24 obs    │ │
│ │ TWR vs SPY chart (dithered fill)       │ │
│ └─────────────────────────────────────────┘ │
├────────────────────────────────────────────┤
│ Ready. Deflated Sharpe: BREACHED (0.238)   │
└────────────────────────────────────────────┘
```

### Nav + entry diagram, interaction counts
Desktop-of-icons entry on first load per session (1 interaction, skippable, deep-link bypass
structural). Menu bar thereafter — **at 390px the top menu bar resolves to one thumb-reachable
trigger** (a bottom-anchored button that opens the menu sheet), so reaching any destination
after entry is still 1 tap, not buried in a top-corner-only affordance (explicit master
constraint: no destination hides behind a corner-only tap at 390px).

### Laws traded + compensation
**The live Fitts's Law violation named explicitly in the companion doc**: a top menu bar is the
correct medium but the wrong ergonomics at 390px. **Compensation**: it resolves to a
thumb-reachable trigger (bottom-anchored, 44px) that opens the same menu content as a sheet —
the medium is preserved (it's still, structurally, "the menu bar"), the ergonomics are fixed.

### Library basis
`98.css` bevel geometry, title-bar structure, disabled treatment, and dotted focus rectangles are
**extracted as patterns into this medium's manifest** — the library itself is never imported
wholesale (it's a global-CSS framework that would fight the token system and leak into other
mediums). CRT layer used for tint only, curvature/flicker/glitch disabled.

---

# 11 · GALLERY — paintings on a wall

**Default medium.** Based on museum wall-labels and hanging conventions — title/medium/date
placards, engraved plaques, frames whose material signals importance, rooms in sequence,
conservation notices. Marks are neo-expressionist in *influence* — loaded brush, visible
bristle, raw gesture — never a specific artist's actual work. Light.

### Tokens
| Token | Value | Use |
|---|---|---|
| `--ink-primary` | `#1c1a17` | wall-label ink, near-black |
| `--surface-wall` | `#f2ede2` | eggshell wall |
| `--frame-plain` | `#6b6459` | plain moulding |
| `--frame-gilt` | `#b08d3e` | gilt — reserved for the primary work only |
| `--state-breach` | `#a53b2c` | the one decisive alert mark |

### Type roles
Characterful display for titles (a humanist display face), humanist body for wall-label copy,
mono numerals (tabular, per the numerals-never-vary rule).

### Ten material dimensions
1. **Mark-making**: real brush strokes with bristle edge and loaded-brush variation — not fills.
2. **Containers**: a frame around every work, gilt reserved for the primary, plain moulding
   elsewhere.
3. **Controls**: an engraved-placard-style toggle.
4. **Navigation**: room directory from a thumb-reachable plaque, plus next-room progression.
5. **Entry**: a foyer with the exhibition dates (as-of timestamp).
6. **Transitions**: none.
7. **Empty/loading/error**: an empty frame with a placard giving the `reason`.
8. **Vocabulary**: room, plaque, gilt, moulding, exhibition, conservation.
9. **Layout rhythm**: generous margins, one framed work commanding the viewport.
10. **Texture**: none beneath data beyond the wall's own eggshell tone.

### Must-include walkthrough
| Master bullet | Status | How |
|---|---|---|
| Charts as real brush strokes, bristle edge, loaded-brush variation | done | rough.js renderer, low roughness for confident strokes, higher for sketches — bristle variation via multiple overlapping rough.js passes |
| A frame around every work, gilt reserved for the primary | done | `components.Container` takes a `primary` boolean; only the Home first-viewport figure ever receives `--frame-gilt` |
| A wall label beside each work | done | this IS `WallLabel`'s native rendering in this medium — museum label styling is Gallery's literal `components.LabelFrame` |
| An empty frame with a placard giving the reason | done | `state.unavailable` = a frame with nothing hung + a placard carrying `reason` |
| A foyer entry page, exhibition dates from as-of | done | entry reads the live as-of timestamp for its "exhibition dates" |
| Hand-marked annotation — circled outlier, underline, arrow | done | `annotations[]` kinds map directly: `circle`→circled outlier, `underline`→threshold crossing, `arrow`→explaining event |

### Chart renderer + performance plan
rough.js, low roughness for confident (established) strokes, progressively higher roughness for
lower-confidence/sketch states — this is Gallery's confidence-adjacent material device, distinct
from its actual confidence channel (transparency, below). Seeded deterministically from metric
id; SVG filter passes precomputed once per mount.

### Four-state + confidence
Established = confident solid stroke · Accumulating = unfinished sketch with the count in the
margin · Breached = one decisive mark in the alert color · Unavailable = empty frame + placard.
**Confidence: transparency overlay** — a wash over the work, separate from the roughness
variation used for state.

### Motion + reduced-motion
None. Trivially compliant.

### Vocabulary map
room · plaque · gilt · moulding · exhibition · conservation

### Named risk + control
**Risk**: as the default medium, Gallery carries the heaviest Aesthetic–Usability burden of the
whole rebuild — it's the first thing most people see, so its beauty must not read as more
confidence than the model has earned. **Control**: the empty-frame-with-reason and
unfinished-sketch devices are not optional flourishes here; they're load-bearing on first
impression, and the museum-label wall-label contract (provenance line always present) is applied
with zero exceptions, including on the Home first-viewport figure.

### ASCII wireframe (390px, Home)
```
┌────────────────────────────────────────────┐
│  ⟐ GALLERY — ROOM 1: THE REPORT             │
├────────────────────────────────────────────┤
│  ╔══════════════════════════════════════╗  │  ← gilt frame, primary
│  ║   PORTFOLIO VALUE                     ║  │
│  ║   $XX,XXX.XX     ▲ +X.X% today       ║  │
│  ╚══════════════════════════════════════╝  │
│  Oil on canvas · as of <date> · Room 1      │
├────────────────────────────────────────────┤
│  ┌ TWR vs S&P 500 ────────────────────┐    │  ← plain moulding
│  │  [loaded-brush stroke line chart]   │    │
│  └──────────────────────────────────────┘   │
│  Charcoal & wash · 18 of 24 obs accumulating│
├────────────────────────────────────────────┤
│  ⟐ Next room: Research →     [plaque: ≡]   │
└────────────────────────────────────────────┘
```

### Nav + entry diagram, interaction counts
Foyer entry on first load per session (1 interaction, skippable, deep-link bypass structural).
Room directory from a thumb-reachable plaque + next-room progression thereafter — 0 additional
interactions to jump directly to any destination via the plaque, or 1 tap "next room" to move
sequentially.

### Laws traded + compensation
Trades a little Hick's Law simplicity by offering *both* a jump-anywhere plaque and a
sequential "next room" progression — two ways to move — compensated by making the plaque the
primary, always-visible affordance and "next room" a secondary, optional one, so the decision
isn't doubled for someone who just wants the fastest path.

### Library basis
rough.js directly (not `roughViz`, which is D3 v5-coupled) — low roughness for confident
strokes, higher for sketch/accumulating states.

---

# 12 · CLASSIC — what you have now

**Built last, in an isolated pass (Phase 2c).** Preserves the current 3.2.0 presentation intact;
source is `docs/CLASSIC-DESIGN-3.2.md` (the relocated original design doc) and
`docs/HOMEPAGE-LAYOUT.md` (the section-by-section Home spec). The only medium permitted to reuse
existing components and CSS. **Listed first in the medium picker** ("what you have now"), even
though authored last.

### Tokens
Existing token set in `src/styles/variables.css`, used as-is. **Known bug, grandfathered**: the
"light" `data-theme` currently renders the same dark HUD palette as dark (no
`[data-theme="light"]` block exists in the shipped CSS) — see `NOTES.md`. Not fixed in this
rebuild; Classic's manifest documents the bug rather than silently repairing it, since 0f
forbids reopening shared layout before this pass and a repair here is exactly the kind of
"quietly pulled back toward the old structure" the master warns against watching for in reverse.

### Type roles
Existing stack: Geist Sans (display/body), Geist Mono (numerals) — currently loaded
render-blocking from jsdelivr; self-hosted subset in Phase 2a's shared font work, same faces.

### Ten material dimensions
1. **Mark-making**: existing hand-rolled SVG charts (`GrowthChart`, `Sparkline`,
   `ScoreExplainability`, etc.) — no chart library, ported as-is.
2. **Containers**: existing card/shelf system — glass panels with cyan edge-glow per
   `docs/CLASSIC-DESIGN-3.2.md`.
3. **Controls**: existing button/select/toggle components.
4. **Navigation**: bottom navigation, current five destinations reordered to the new six
   (`ROUTE-INVENTORY.md` §2) — Home/Portfolio/Research/Markets + a More sheet absorbing
   Screens/Evidence/Alerts/Settings, same interaction budget.
5. **Entry**: none, as today.
6. **Transitions**: existing motion — chart entrance, gauge arc fill — already correctly gated
   by `data-chart-animation`/`data-motion` per the pre-existing motion audit.
7. **Empty/loading/error**: existing `<Loading/>`/`<Empty/>` components, ported as-is.
8. **Vocabulary**: existing product vocabulary from `PRODUCT.md` — research score, coverage,
   confidence, theme exposure, evidence rail — unchanged.
9. **Layout rhythm**: floating pill headers, sectioned shelves, value capsules, horizontal
   rails, hairline elevation — all existing.
10. **Texture**: existing glass/blur treatment on floating chrome only (permitted per the
    master's Liquid Glass scoping — content layer never gets glass).

### Must-include walkthrough
| Master bullet | Status | How |
|---|---|---|
| Bottom navigation, current five destinations in order | substitute | five becomes six per `ROUTE-INVENTORY.md` §2 — consolidated routes still apply, "Classic keeps its look, not the old route sprawl" (master's own words) |
| Floating pill headers | done | ported as-is |
| Sectioned shelves, value capsules, horizontal rails | done | ported as-is |
| Hairline elevation | done | ported as-is, remains the default depth cue |
| Existing token set | done | ported as-is, including the grandfathered light-theme bug (documented, not fixed here) |

### Chart renderer + performance plan
Existing hand-rolled SVG components become the `classic/renderer` implementation of the shared
`chartContract` — a thin adapter layer maps contract props onto the existing component APIs
rather than rewriting them, satisfying "reuse existing components" while still exposing the same
interface the other eleven mediums implement (needed for Phase 3's renderer-distinctness and
numeral-legibility assertions to run uniformly across all twelve).

### Four-state + confidence
Existing `signalMetrics.js` status labels and `metricTone()` — this is in fact the *source*
`core/states.js` wraps, so Classic's four-state mapping is definitionally identical to the
canonical one; no adapter needed here. Confidence channel: existing transparency/tone treatment
in `MetricCard`.

### Motion + reduced-motion
Existing motion profile, already state-driven and already gated by
`prefers-reduced-motion`/`data-motion` correctly per the pre-existing audit (three flagged
issues — AnimatedNumber, `.refresh-progress-fill`/`.live-countdown-progress` animating `width`
instead of `transform: scaleX()`, hand-typed durations — are fixed in Phase 2a's shared layer
since they affect primitives every medium uses, not Classic specifically).

### Vocabulary map
Existing `PRODUCT.md` vocabulary — research score, coverage, confidence, theme exposure,
momentum guardrails, evidence rail.

### Named risk + control
**Risk**: porting Classic last is explicitly the step most likely to pull shared `core/`
components back toward the old structure, since it's the first time anyone reopens the existing
page files. **Control**: the 2c drift check — `git diff --stat src/mediums/core/` must be ~zero
after the Classic port; any change made "to make Classic work" gets reverted and reimplemented
inside `src/mediums/classic/` instead.

### ASCII wireframe (390px, Home)
```
┌────────────────────────────────────────────┐
│  ValueSignal            ⚙ 👤               │
├────────────────────────────────────────────┤
│  ╭ Evidence ─────────────────────────────╮ │
│  │ 44 ready · 9 breached · 18d live       │ │
│  ╰─────────────────────────────────────────╯ │
│  ╭ Portfolio ────────────────────────────╮ │
│  │  $XX,XXX.XX        ▲ +X.X% today      │ │
│  │  [chart: TWR vs SPY, glass panel]     │ │
│  ╰─────────────────────────────────────────╯ │
│  ╭ Top signal ───╮ ╭ Action needed ──────╮ │
│  │ TICKER  92     │ │ 3 positions        │ │
│  ╰────────────────╯ ╰──────────────────────╯ │
├────────────────────────────────────────────┤
│ [Home][Portfolio][Research][Markets][More] │
└────────────────────────────────────────────┘
```

### Nav + entry diagram, interaction counts
No entry, as today. Bottom bar with 4 direct destinations + a More sheet absorbing the remaining
2 (Screens, Evidence) plus Alerts/Settings — identical interaction budget to the other eleven
mediums (every destination reachable in ≤1 additional tap from steady state).

### Laws traded + compensation
None beyond what the current build already trades — Classic is deliberately the control group,
not a new design decision.

### Library basis
The existing component/CSS set, ported and adapted to implement the shared contracts (manifest
shape, chart-renderer interface, `data-capability-id` instrumentation) without being rewritten.

---

## Closing — costume tests, closest pairs, banned-list self-audit

### Costume tests, per theme (summary — full reasoning is in each theme's own section above)

| Theme | Greyscale | Swap | Furniture | Navigation | One-word |
|---|---|---|---|---|---|
| Cockpit | passes — bracket geometry reads without color | fails obviously — a bezel dropped into Neon's tube-line reads instantly wrong | passes — masked numerals still read as instrument panel | passes — bracket bar names itself | "cockpit" / "panel" |
| Neon | passes — tube geometry + banded sun read without color (glow itself is monochrome-safe, it's a shape+brightness device) | fails — a tube-line in Cockpit's bezel reads instantly wrong | passes — masked figures still read as a sign | passes — tab strip + title card unmistakable | "neon" / "arcade" |
| Poster | passes — halftone dot pattern reads in greyscale by definition | fails — a halftone chart in Ticker's flat rows reads instantly wrong | passes — trim/registration marks read without data | passes — masthead unmistakable | "poster" / "print" |
| Ticker | passes — hairline rows read without color | fails — a wire-feed row inside Gallery's frame reads instantly wrong | passes — fixed-width status column reads empty | passes — session bar unmistakable | "ticker" / "feed" |
| Book | passes — ruled tables read without color | fails — a small-multiple grid inside Neon's tube styling reads instantly wrong | passes — folios/running heads read without data | passes — thumb index unmistakable | "book" / "ledger" |
| Blueprint | passes — dimension lines read without color | fails — a tolerance band inside Poster's halftone reads instantly wrong | passes — sheet border/zone markers read without data | passes — zone tabs unmistakable | "blueprint" / "drafting" |
| Star Chart | passes — graticule + open/filled circles read without color | fails — a magnitude circle inside Beige Box's window reads instantly wrong | passes — graticule reads without data | passes — corner legend unmistakable | "star chart" / "astronomy" |
| Newspaper | passes — column rules read without color | fails — a generated headline inside Chalkboard's ribbon reads instantly wrong | passes — column rules read without data | passes — masthead unmistakable | "newspaper" / "press" |
| Chalkboard | passes — chalk-stroke geometry reads without color (white-on-slate is already near-greyscale) | fails — a dotted leader line inside Book's ruled table reads instantly wrong | passes — hand-drawn boxes read without data | passes — chalk tray unmistakable | "chalkboard" / "slate" |
| Beige Box | passes — bevel geometry reads without color | fails — a bevelled window inside Star Chart's graticule reads instantly wrong | passes — title bars/status bar read without data | passes — menu bar unmistakable | "windows 95" / "desktop" |
| Gallery | passes — brush-stroke geometry + frame moulding read without color | fails — a brush-stroke chart inside Blueprint's sheet border reads instantly wrong | passes — frames/plaques read without data | passes — room plaque unmistakable | "museum" / "gallery" |
| Classic | passes — existing card geometry reads without color | fails — existing glass card inside any other medium's container reads instantly wrong | passes — existing shelf structure reads without data | passes — bottom nav unmistakable | "app" / "dashboard" |

### Closest pairs — required deep dives

**Neon vs. Cockpit** (both dark, both have lit indicators): Neon's light is exclusively an alert
device — nothing glows except a breach, and glow is static, never state-of-the-system. Cockpit's
light is exclusively a liveness device — anything currently live glows steadily, and the *state*
of a channel is read from its lit/dim/unlit tri-state, not from whether it's glowing at all.
Material: Neon is chrome/holographic lettering + tube strokes + a banded sun; Cockpit is
machined bezels + tick-scale readouts + corner brackets — no shared component. Controls: Neon has
a lit tab strip (bottom); Cockpit has a detented switch + calibrated dial (rail/bracket-bar).
Navigation: Neon's is a tab strip with an entry title card; Cockpit's is a bracket bar with
explicitly no entry (the master forbids a fake boot sequence). The swap test above confirms it —
either renderer dropped into the other's shell reads as instantly wrong.

**Poster vs. Neon** (both saturated): Poster is light/paper, exactly two spot inks plus black,
static by nature (print doesn't move); Neon is dark/screen, cyan+magenta+indigo, and its one
"moving" quality (tube state) is itself static motion-wise (glow doesn't pulse). Poster's
confidence channel is a physical registration offset (misprinted plates); Neon's is tube chroma
washing toward grey. Poster's containers are printed panels with trim marks; Neon's are a flat
grid substrate behind lit tubes. Navigation: masthead (top) vs. neon tab strip (bottom). No
shared rendering technique (canvas halftone vs. SVG tube-stroke + static bloom), no shared
palette architecture (2-spot-plus-black vs. cyan/magenta on indigo), no shared container
metaphor. They diverge on material, control set, and navigation exactly as required.

### Banned-list self-audit

Checked against the root master doc's "Banned in every theme" list for every section above:
purple→blue gradients — none used outside Neon's own explicitly-permitted sun/chrome/frame
chrome · cream+serif+terracotta combination — not used anywhere · glass/frost in the content
layer — Classic's glass is chrome-only (floating headers), never content, per the Liquid Glass
scoping section; no other medium uses glass at all · glow anywhere but Neon's breach state — the
Cockpit "glow only when live" device is a liveness readout, not a decorative glow-as-atmosphere
device, and is named explicitly as compliant in Cockpit's own must-include table, distinct from
Neon's breach-only rule · equal-weight cards holding heterogeneous charts — every medium's
container is a frame/plate/sheet/window/chalk-box bound to one distinct object, never a "soup"
card · promo tiles, decorative icons, rainbow palettes, 3+-slice donuts (retired to the
`composition` contract type), unlabeled radial gauges, radar charts (retired to `profile`),
stepped charts on continuous data, animated count-up numerals, sparklines-as-texture, "AI
Insights ✨" panels, drop-shadow-only depth, breach sharing the loss color (Ticker's explicit
rule), hue-as-confidence, blur-over-intervals, three-level confidence scales, texture/glow/scan-
lines/material over text or data, perspective grids that distort data, fake wood grain/CRT
curvature/nostalgia kitsch, raw value-over-time lines conflating deposits with return (the TWR
chart is explicitly protected from this in every medium that renders it) — **none found across
the twelve sections above.**

### Radar note

`ResearchRadarChart`'s use case (factor-loading profile in the Stock Detail Sheet) is re-expressed
via the shared `profile` chart-contract type (sorted bar/dot profile of loadings) in every
medium — radar itself is on the banned list and is never implemented by any of the twelve
renderers.

### Ship-six recommendation (restated for the user's decision)

Per the master's own recommendation: build all twelve manifests (this document covers all
twelve), but **ship six at launch — Classic, Gallery, Newspaper, Chalkboard, Beige Box,
Ticker** — and keep Cockpit, Neon, Poster, Book, Blueprint, Star Chart behind a flag until usage
data says which of them people actually open. This is a recommendation, not a decision made on
the user's behalf — Phase 2 builds all twelve regardless (master: "zero capability loss," no
deletion step exists), and the flag is a launch-sequencing choice the user can revisit anytime
after seeing them built.
