# Desktop Breakdown & Audit

The desktop rendering mode of the same single React codebase described in
`docs/APP-BREAKDOWN-AUDIT.md` — everything above the 900px breakpoint documented in
`docs/MOBILE-BREAKDOWN-AUDIT.md`. This document is the complete inventory of what's specific to
the wide-viewport surface: the persistent sidebar, the full navigation set, dense tabular
layouts, and the desktop-only affordances that have no mobile equivalent by design. Scores
themselves are identical on both surfaces — see `docs/SCORING-METRICS-BREAKDOWN.md`.

## 1. The layout shell

`.shell` (`global.css:30`) is a two-column CSS grid — `248px minmax(0, 1fr)` — a fixed-width
sidebar rail beside a fluid content column, active whenever the viewport is wider than 900px
(below that, `.shell` collapses to `display: block` and the rail disappears entirely — see
`docs/MOBILE-BREAKDOWN-AUDIT.md` §1). A later theme layer narrows the rail slightly to 232px
(`global.css:957`) without changing the two-column structure. Content is capped at
`width: min(100%, 1380px)` with `28px 38px` padding (`.content`, `global.css:63`) — desktop
never uses the mobile bottom-nav height reservation or safe-area insets, since there's no home
indicator to clear.

## 2. Navigation — the full 12-item set

`src/App.jsx:36-49`, `NAV` array, rendered inside `<aside className="rail">` as
`.desktop-nav` (`global.css:43`, `min-height: 44px` per link):

| Order | Label | Route | Auth-gated |
|---|---|---|---|
| 1 | Financial Report | `/` | No |
| 2 | Research | `/research` | No |
| 3 | Search | `/search` | No |
| 4 | Portfolio | `/portfolio` | Yes |
| 5 | Watchlist | `/watchlist` | No |
| 6 | Finances | `/finances` | Yes |
| 7 | Planning | `/planning` | Yes |
| 8 | Screens | `/screens/momentum` | No |
| 9 | Methodology | `/methodology` | No |
| 10 | Glossary | `/glossary` | No |
| 11 | Settings | `/settings` | No |
| 12 | Alerts | `/alerts` | Yes |

This is more than double `MOBILE_NAV`'s 5 items (`docs/MOBILE-BREAKDOWN-AUDIT.md` §2) — the
sidebar has room for every top-level surface, including several (Finances, Glossary,
Methodology, standalone Screens entry) that mobile users reach only by drilling in from a page
that does appear on their bottom tab bar. Auth-gated items are filtered out of the array
entirely for signed-out users (`item.requireAuth && !currentUser) return null`, `App.jsx:100`)
rather than shown disabled.

Below the nav, a permanent `.rail-note` reminds: "Fundamentals first. Evidence, not hype.
General research only." — always visible on desktop; mobile has no equivalent persistent
footer note (space-constrained).

## 3. Desktop-only components and affordances

| Component / class | File | What it is |
|---|---|---|
| `ProfilePanel` | `App.jsx:60-83` | Avatar, display name, account-theme label, settings/account/logout icon buttons — rendered only inside the sidebar. Mobile's header shows only an avatar and settings/privacy icons, no name or theme label |
| `.desktop-control-panel` | `MobileSheet.jsx` (`ResponsiveControlPanel`), hidden via `global.css:651` below 900px | Filter/control panels render inline on desktop; the same controls become a triggered bottom sheet on mobile (`docs/MOBILE-BREAKDOWN-AUDIT.md` §3) |
| Desktop `<table>` markup | Paired with `.research-mobile-list`/`.portfolio-mobile-list` etc. across research/portfolio components | Dense multi-column tabular views — sortable columns, more fields per row than a card can hold — shown above 900px; the same component renders card markup below it |
| `.capability-grid` | `Methodology.jsx`, styling `global.css:494` (2-col at ≤900px), `:553` (1-col at ≤680px) | Provider/parser coverage grid (`/methodology`) — full multi-column grid on desktop, progressively collapses on narrower viewports rather than becoming a different component |
| `.desktop-only` | `global.css:1296-1297` | Explicit utility class (`display: none !important` below 900px) for elements that are desktop-exclusive by design, not just space-optimized |
| `.skip-link` | `App.jsx:92`, styled `global.css:26-27` | "Skip to content" link, off-screen until keyboard-focused — a keyboard-navigation affordance most relevant on desktop, where sidebar/nav tabbing before reaching content is a real cost |

## 4. Interaction model differences from mobile

- **Hover states** exist throughout desktop nav links and buttons (`.navlink:hover`-style
  rules in `global.css`) with no mobile equivalent — touch has no hover, so mobile relies on
  `:active` press states instead.
- **No pull-to-refresh** — `PullToRefreshIndicator.jsx` is mounted only in the mobile-gesture
  flow; desktop's refresh affordance is an explicit button (`.refresh-control` /
  `home-refresh-feedback`), not a gesture.
- **No windowed-list gating by device** — desktop's `<table>` renders all rows directly
  (relying on browser table layout rather than `@tanstack/react-virtual` windowing); the
  virtualization path in `ResultCards.jsx`/`MobileVirtualList.jsx` is mobile-only, gated by the
  same `if (!mobile) return null` that suppresses card rendering on desktop (see
  `docs/MOBILE-BREAKDOWN-AUDIT.md` §3) — desktop tables are assumed to handle the same row
  counts without a windowing layer.
- **Keyboard-first affordances** — the skip link (§3) and standard tab-order navigation through
  the sidebar are desktop/keyboard-user-first patterns; mobile's bottom nav is reached by touch,
  not tab order, so no equivalent skip mechanism is needed there.

## 5. What desktop does *not* get that mobile does

- No bottom-sheet modal pattern — desktop control panels are always inline; there is no
  desktop equivalent of `MobileSheet`'s focus-trapped overlay because there's no space
  constraint forcing controls off-screen.
- No safe-area-inset handling — desktop has no notch/home-indicator geometry to account for.
- No phone-native visual layer (`global.css:738-956`, described in
  `docs/MOBILE-BREAKDOWN-AUDIT.md` §5) — the floating pill nav, blur/saturate backdrop filters,
  and active-tab glow effects are mobile-specific polish with no desktop counterpart; desktop's
  sidebar nav uses flat, non-glassmorphic styling throughout.

## 6. Known desktop-specific gaps

- No dedicated desktop visual-regression harness — `scripts/mobile-screenshots.mjs` (see
  `docs/MOBILE-BREAKDOWN-AUDIT.md` §6) only captures the 390/430px mobile-acceptance widths;
  there is no equivalent automated screenshot suite proving desktop layouts render correctly
  across viewport widths (1280/1440/1920, etc.) after a change.
- No documented keyboard-shortcut system beyond standard tab order and the single skip link —
  no power-user hotkeys for navigation between screens.
- Sidebar width is fixed (248px, later 232px) rather than user-resizable or collapsible; users
  on very wide monitors get a capped 1380px content column with no way to use the remaining
  horizontal space for a denser view.
