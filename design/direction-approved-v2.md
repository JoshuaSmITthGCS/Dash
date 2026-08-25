# Approved visual direction — v2, "The Study"

**Decided:** 2026-08-25 · supersedes `direction-approved.md` (2026-08-15, "Studio")
**Process:** impeccable's direction-dice flow, run interactively in a Claude Code on the
web session. No huashu-design three-draft gate this round (that process was already spent
choosing Studio); instead: a grounded 7-candidate shortlist derived from how a serious
fundamentals investor actually reads data (SEC filings, financial print, ledgers, engraved
certificates, academic research, lab instruments, departure boards), rolled externally via
`concept-seed.mjs --scope direction --mode operate` (seed key `543385d9`) to avoid building
the model's own top-ranked pick by default.

## What was found before deciding

The session opened by screenshotting the live app to ground the request ("make it more
techy, unique, financial-dashboard, artsy") and found two prior, conflicting visual
systems already in the repo:

- **"Studio"** (`direction-approved.md`, 2026-08-15) — the properly-executed, rescored
  18/20 redesign actually shipping in `variables.css`/`base.css` (green accent,
  soft-depth cards, 18px radii).
- **"ValueSignal HUD"** — a cyan-glass concept that had overwritten `DESIGN.md` and
  variables.css's *comments and font tokens* (though not Studio's actual color values,
  which stayed live via `PreferencesContext`'s inline accent override) without ever being
  wired into the real pages. `CommandCenter.jsx` was unrouted; `/hud-demo` was dev-only;
  but `initAdvancedHUD()` (`src/main.jsx`) *did* inject a live, unstyled cyan overlay via
  raw DOM manipulation on every page load — a real, shipped bug from an abandoned
  direction, not a harmless dead file.

Asked which to build on — the shipped Studio look, the documented-but-unshipped HUD
concept, or a fresh direction — the user chose **fresh direction, discarding the HUD
document** as inauthoritative (it never earned its place in the live app) while Studio's
*engineering* (token architecture, `DataTable`, coverage meter / evidence rail / score
tape, accessibility work) stays as the foundation this pass builds on.

## The roll

Seven grounded candidates, ordered by resonance for a fundamentals-first individual
investor's actual reading habits:

1. SEC EDGAR / regulatory filing typography
2. Financial newspaper agate stock tables
3. **Ben Graham-style analyst's ledger / accountant's columnar workpad** ← assigned (index 3)
4. Engraved stock certificate / guilloché bond ornament
5. Academic quant working-paper typesetting
6. Scientific-instrument readout / technical drafting
7. Split-flap departure board

No challenger catalog was reachable this session (network egress to the roll service
was unavailable), so this was a degraded roll: the assignment stands at full strength,
but no catalog challengers or quality-bar boards were dealt.

## The steer

Presented as three options (the assigned Ledger direction, the model's own top pick — "The
Filing Room," an EDGAR-flavored alternative — and the category-standard safe default), the
user chose the assigned Ledger direction, then interrupted with a one-line steer before the
build started: **"More techy but also more museum."**

Resolved as: merge the Ledger's evidence-first, workpad character with a museum
specimen-cabinet register — cases, plaques, catalog labels, spot-lit display — and push the
technical-instrument side harder (crisp instrument-bezel shape language, a dedicated
"specimen light" live-data accent, gauge-bezel treatment on the confidence ring) rather
than softening toward antique-paper warmth alone. The result is named **"The Study"** — a
naturalist's study at night, not a paper ledger and not a display case in isolation.

## What carried over from Studio, untouched

Per `docs/REDESIGN-STATUS.md`'s guardrails and this pass's own judgment: the token
architecture itself (`variables.css` custom properties + `data-*` attributes), `DataTable`,
every chart's hand-rolled SVG + table-view pattern, `useDialog`'s focus trap, empty-state
guards, motion-preference handling, the 11px type floor, and — deliberately — the chart
series/diverging/sector color values (CVD-validated; re-deriving them without re-running
that validation would be a silent accessibility regression this pass had no way to check).

## What changed

Every token in `variables.css` (`colors`, `typography`, `rounded`, `effects`, `motion`),
`ACCENTS` in `src/lib/PreferencesContext.jsx` (new 8-accent brass/patina/mineral palette,
each `inkDark` contrast-checked ≥6.8:1), `index.html`'s fonts (Bitter + Source Sans 3 + JetBrains
Mono replacing the unlinked "Geist Sans/Mono" tokens — Geist was referenced in
`variables.css` but never actually loaded anywhere in the repo, a separate pre-existing
drift this pass also fixed), and the removal of the entire unshipped HUD lineage:
`CommandCenter.jsx`, `HUDDemo.jsx`, `hudAdvanced.jsx`, `hudUltra.jsx`, `hudEffects.js`, and
the three `hud-*.css` modules, plus the `/hud-demo` route and `initAdvancedHUD()` call site.
A new `study-effects.css` module (under 60 lines) carries the handful of new, purposeful
touches: the specimen-light live indicator, medallion-style tier badges, one hero panel's
plaque bracket, and the confidence ring's gauge bezel.

## Corrections applied while writing `DESIGN.md`

- `--brand-secondary` was hardcoded to a fixed cyan hex despite both `variables.css`'s own
  comment and `PreferencesContext.jsx`'s comment claiming it derived from
  `--brand-primary` — meaning every non-default accent choice left chart secondary marks
  mismatched to the user's selected color. Fixed: it now genuinely derives via
  `color-mix(in srgb, var(--brand-primary) 78%, black)`.
- Contrast was checked (WCAG relative-luminance formula, not eyeballed) for every new ink
  level against the new canvas and card surfaces, and for every new accent's `inkDark`
  against its own `dark` value. All clear AA; the tightest is `text-tertiary` on canvas at
  4.55:1 (matching the prior pass's own precedent of ~4.06:1 for the equivalent token).
- `theme-color` meta (`index.html`, the anti-FOUC inline script, `manifest.webmanifest`)
  and `PreferencesContext.jsx`'s theme-color sync were three separate hardcoded values,
  two of them stale from the Studio era (`#0b100e`) and one from the HUD era (`#0a0e14`).
  All three now read the same value as the new canvas token.

## Scope note

This decision governs `src/`, `index.html`, and `public/manifest.webmanifest` only. No
pipeline, schema, or `public/data/*` change. Chart color science (series/diverging/sector
palettes) is explicitly out of scope for this pass — see above.
