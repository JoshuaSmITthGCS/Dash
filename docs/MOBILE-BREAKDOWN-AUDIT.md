# Mobile Breakdown & Audit

ValueSignal has **no separate mobile app or mobile-only route tree** — it is one responsive
React codebase (`src/App.jsx` renders one `<Routes>` block for every screen size). "Mobile" is
a rendering mode: a CSS breakpoint plus a handful of `matchMedia`-gated components that swap in
phone-appropriate markup and interaction patterns. This document is the complete inventory of
everything that changes when the app renders below that breakpoint. Companion documents:
`docs/DESKTOP-BREAKDOWN-AUDIT.md` (the other half of the same split),
`docs/APP-BREAKDOWN-AUDIT.md` (whole product), `docs/SCORING-METRICS-BREAKDOWN.md` (scores are
identical on both surfaces — nothing here changes what number renders, only how).

## 1. The breakpoint

**`max-width: 900px`**, applied consistently across `src/styles/global.css` (the shell layout
switch at lines 497-509, the mobile control-sheet switch at 650, the desktop-only utility class
at 1296-1297, and every component-level responsive block in the file). Below 900px:

- `.shell` collapses from a two-column grid to a single block (`display: block`).
- `.rail` (the desktop sidebar) is hidden entirely (`display: none`).
- `.mobile-header` and `.mobile-nav` (both `display: none` by default, `global.css:64`) become
  visible.
- Content padding switches to account for `env(safe-area-inset-*)` (notch/home-indicator safe
  areas) and a bottom-nav-height reservation (`calc(104px + env(safe-area-inset-bottom))`).

A second, narrower breakpoint at **`max-width: 360px`** (small phones) makes further
adjustments: tighter content padding, a narrower mobile-nav bar, smaller hero score digits.

## 2. Navigation — a genuinely different, curated set

`src/App.jsx:51-58` defines `MOBILE_NAV` as its own 5-item array, deliberately smaller than the
12-item desktop `NAV` (see `docs/DESKTOP-BREAKDOWN-AUDIT.md` §2):

| Order | Label | Route | Note |
|---|---|---|---|
| 1 | Research | `/research` | |
| 2 | Search | `/search` | |
| 3 | **Report** | `/` | `primary: true` — visually emphasized center tab (`mobile-nav-report` class, `global.css:1303`: raised, bordered, brand-colored when active) |
| 4 | Portfolio | `/portfolio` | |
| 5 | Watchlist / Planning | `/watchlist`, `/planning` | |

Rendered as a fixed bottom tab bar (`.mobile-nav`, `global.css:502-509` and again at
`738-841` in the later "phone-native visual layer" block — the file layers a second, more
polished pass of mobile-specific styling on top of the functional one, explicitly commented as
changing presentation only, not routes/data/behavior): `position: fixed`, rounded floating
pill shape, `backdrop-filter: blur()`, safe-area-aware bottom offset. Each tab target is
`min-width: 58px; min-height: 54px` — comfortably above the platform's stated
`interface.minimum_touch_target_px: 44` accessibility floor (`pipeline/config/settings.json`).

The mobile header (`.mobile-header`, replaces the sidebar's brand lockup) carries: brand mark,
an alert badge (`AlertBadge.jsx`, only rendered for signed-in users), a privacy-mode toggle
(eye/eye-off icon — hides dollar balances), a settings shortcut, and an avatar. Desktop's
equivalent (`ProfilePanel`) additionally shows a display name and account-theme label that the
mobile header omits for space.

## 3. Mobile-only components

| Component | File | What it does |
|---|---|---|
| `MobileSheet` / `ResponsiveControlPanel` | `src/components/MobileSheet.jsx` | Renders desktop controls inline (`.desktop-control-panel`) but swaps to a bottom-sheet modal (focus-trapped, Escape-to-close, restores focus on close) triggered by a `.mobile-sheet-trigger` button below 900px |
| `ResultCards` | `src/components/ResultCards.jsx` | Returns `null` outright on desktop (`if (!mobile) return null`, line 52) — this is a real conditional mount, not just CSS-hidden. Renders card-per-row instead of the desktop `<table>`; auto-switches to windowed virtualization (`@tanstack/react-virtual`) above 50 rows so a long research list doesn't mount hundreds of DOM nodes on a phone |
| `MobileVirtualList` | `src/components/MobileVirtualList.jsx` | Same mobile-only + virtualize-above-50 pattern as `ResultCards`, generalized for other list surfaces |
| `PullToRefreshIndicator` | `src/components/PullToRefreshIndicator.jsx` | Renders a spinning sync badge whose progress (`--ptr-progress`) tracks pull distance, armed state at 70px pull |
| `.research-mobile-list` / `.research-mobile-card`, `.portfolio-mobile-list` | (CSS classes, `global.css`) | Many components render both desktop-table and mobile-card markup in the same JSX and let CSS pick which is visible — a lighter-weight pattern than the fully-gated components above, used where the data shape doesn't need touch-specific interaction |

## 4. `matchMedia` gating — where JS, not just CSS, decides

Two components query `window.matchMedia('(max-width: 900px)')` directly and hold the result in
state with a `change` listener (`ResultCards.jsx:44-51`, `MobileVirtualList.jsx:25-32`) rather
than relying on CSS visibility — because they change *what mounts*, not just what's visible:
mounting a 500-row `<table>` off-screen on a phone would still cost the parse/layout work CSS
`display: none` doesn't save you from. `src/lib/PreferencesContext.jsx:130` uses the same
`matchMedia` pattern for `(prefers-color-scheme: dark)`, unrelated to layout.

## 5. Mobile-specific visual system

`global.css` lines 738-956 are an explicitly-labeled "phone-native visual layer" — a second,
more considered pass of mobile styling layered on top of the functional breakpoint rules,
commented as changing **presentation only**: pill-shaped mobile header with drop-shadowed brand
mark, floating rounded-pill bottom nav with blur/saturate backdrop filter, active-tab glow
effects (`filter: drop-shadow(...)` on the active icon), and a further `360px` sub-breakpoint
tightening padding and nav-item width for small phones.

The score dial used on stock detail and dashboard views (`interface.score_dial` in
`settings.json`) is a single shared SVG-arc component sized identically on both surfaces
(220px viewBox) — mobile does not get a simplified score visualization, it gets the same
confidence-encoded arc (opacity = confidence, dash length = score) at a size that already works
in a narrower column.

## 6. Mobile acceptance testing — the evidence artifact for "does this actually work on a phone"

`scripts/mobile-screenshots.mjs` (run via `npm run screenshots:mobile`), driven by
`playwright-core`:

- Widths: `interface.mobile_acceptance_widths` in `settings.json` → **`[390, 430]`** —
  iPhone-class viewport widths, not arbitrary "small" numbers.
- Heights: 844 / 932, matched to those widths.
- Both light and dark themes, for Home, Planning, Research, and a stock-detail route.
- Output: PNGs to `docs/mobile-screenshots/`, summarized in
  `pipeline/reports/mobile_visual_check.json` — this is the actual regression-detection
  artifact behind "mobile still looks right," not a manual claim.

This is real, automated, screenshot-based mobile QA — not a description of intent.

## 7. Known mobile-specific gaps

- No native app (iOS/Android) — "mobile" here means responsive web only, no App Store/Play
  Store presence, no push notifications outside the browser/PWA capability the hosting
  platform provides.
- No offline mode — a phone with no connectivity gets whatever `useData.js`'s localStorage
  cache last held, not a dedicated offline UI state.
- Desktop-only capability grids and dense multi-column tables (see
  `docs/DESKTOP-BREAKDOWN-AUDIT.md` §3) do not have a bespoke mobile-native equivalent beyond
  the card-list pattern — some information-dense views (e.g., the provider/parser coverage
  grid on `/methodology`) are simply narrower on a phone, not restructured.
- Mobile screenshot acceptance currently covers 4 routes (Home, Planning, Research, one stock
  detail) — not the full route map in §5 of `docs/APP-BREAKDOWN-AUDIT.md`.
