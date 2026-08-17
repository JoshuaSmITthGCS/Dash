# 002 — Give the primary modal an entrance animation

- **Status**: DONE
- **Commit**: c5038791
- **Severity**: MEDIUM
- **Category**: Missed opportunities / Purpose & frequency
- **Estimated scope**: 1 file (`src/styles/modules/controls.css`), ~15 lines added

## Problem

`.modal-overlay` / `.modal` is the app's primary dialog pair — it backs
`StockDetailModal` (opened from Search, Picks, Watchlist, Portfolio, and
every screen page — the single most-opened dialog in the product) and the
auth login modal (`.login-modal` composes `.modal`). It has **zero**
animation, on any viewport:

```css
/* src/styles/modules/controls.css:18-19 — current */
.modal-overlay { position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; padding: var(--sp-5); background: var(--scrim); backdrop-filter: blur(8px); }
.modal { width: min(100%, 740px); max-height: min(92dvh, 900px); overflow-y: auto; padding: var(--sp-6); border: 1px solid var(--border); border-radius: var(--card-radius); background: var(--surface-primary); box-shadow: 0 20px 60px rgba(0,0,0,.3); }
```

```css
/* src/styles/modules/controls.css:92 — current, mobile bottom-sheet variant, also unanimated */
@media (max-width: 620px) {
  .modal-overlay { padding: 0; align-items: end; }
  .modal { max-height: 92dvh; border-radius: 26px 26px 0 0; padding: var(--sp-5); }
}
```

By contrast, the *other* sheet component in the same file,
`.mobile-sheet` (a different, lower-traffic bottom sheet used for filter
panels), already has a proper entrance:

```css
/* src/styles/modules/controls.css:197-206 — for comparison, already correct */
.mobile-sheet { /* ... */ animation: sheet-in .22s ease-out; }
@keyframes sheet-in { from { opacity: 0; transform: translateY(28px); } to { opacity: 1; transform: translateY(0); } }
```

The content the user came to see (a stock's whole research page, or the
login form) currently just teleports into existence. This is exactly
AUDIT.md's "missed opportunity" category — occasional, high-visibility,
state-appears-from-nothing UI with none of its allowed entrance motion.

## Target

Fade the overlay; fade+scale the modal panel on the default (centered)
layout; fade+slide-up the modal panel on the `max-width: 620px` bottom-sheet
layout, reusing the existing `sheet-in` keyframe so there is exactly one
"panel rises from the bottom" animation in the codebase, not two near-copies.

```css
/* target — src/styles/modules/controls.css:18-19, replacing the current two lines */
.modal-overlay { position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; padding: var(--sp-5); background: var(--scrim); backdrop-filter: blur(8px); animation: modal-overlay-in var(--duration-fast) var(--ease-out); }
.modal { width: min(100%, 740px); max-height: min(92dvh, 900px); overflow-y: auto; padding: var(--sp-6); border: 1px solid var(--border); border-radius: var(--card-radius); background: var(--surface-primary); box-shadow: 0 20px 60px rgba(0,0,0,.3); animation: modal-in var(--duration-normal) var(--ease-out); }
@keyframes modal-overlay-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes modal-in { from { opacity: 0; transform: scale(0.96); } to { opacity: 1; transform: scale(1); } }
```

```css
/* target — src/styles/modules/controls.css:92, inside the existing max-width: 620px block, appended */
@media (max-width: 620px) {
  .evidence-grid { grid-template-columns: 1fr; }
  .modal-overlay { padding: 0; align-items: end; }
  .modal { max-height: 92dvh; border-radius: 26px 26px 0 0; padding: var(--sp-5); animation: sheet-in var(--duration-normal) var(--ease-out); }
  .stock-modal h2 { font-size: var(--fs-2xl); }
}
```

```css
/* target — extend the existing reduced-motion block, do not duplicate it */
@media (prefers-reduced-motion: reduce) { .mobile-sheet { animation: none; }.alert-rule-toggle span { transition: none; } .modal-overlay, .modal { animation: none; } }
```

## Repo conventions to follow

- Duration/easing tokens: `src/styles/variables.css:170-174` —
  `--duration-fast: 150ms`, `--duration-normal: 220ms`, `--ease-out:
  cubic-bezier(.23, 1, .32, 1)`. AUDIT.md's duration budget for
  "Modals, drawers" is 200-500ms — `--duration-normal` (220ms) fits; the
  overlay fade itself can be quicker (`--duration-fast`, 150ms) since a flat
  opacity fade reads fine faster than a scaling panel.
- AUDIT.md §3: modals are the one case where `transform-origin: center` (the
  default) is correct — do not add a `transform-origin` override. Never
  `scale(0)` — this plan uses `scale(0.96)`, inside the recommended
  0.9-0.97 band.
- Exemplar for the mobile slide-up: `.mobile-sheet`'s `sheet-in` keyframe,
  `src/styles/modules/controls.css:206`. Reuse it verbatim by name for
  `.modal` inside the `max-width: 620px` block — do not write a second,
  near-identical keyframe.
- Exemplar for the reduced-motion carve-out: the existing combined selector
  at `src/styles/modules/controls.css:209`. Extend that line; do not add a
  new `@media (prefers-reduced-motion: reduce)` block elsewhere in the file
  (there is already exactly one in this file — keep it that way).

## Steps

1. In `src/styles/modules/controls.css`, replace lines 18-19 (the
   `.modal-overlay` and `.modal` rules) with the Target block above — same
   properties, plus one `animation: ...` declaration appended to each rule.
2. Immediately after those two rules (still outside any media query), add
   the two `@keyframes` blocks (`modal-overlay-in`, `modal-in`) shown in
   Target.
3. Inside the `@media (max-width: 620px)` block (line ~92), add
   `animation: sheet-in var(--duration-normal) var(--ease-out);` to the
   existing `.modal { ... }` override in that block (do not touch
   `.modal-overlay`'s override in that block — the overlay's base-rule fade
   already applies at every viewport).
4. Extend the existing reduced-motion selector at line 209 to also match
   `.modal-overlay, .modal` (comma-separated selector list, `animation:
   none`), exactly as shown in Target. Do not create a second
   `@media (prefers-reduced-motion: reduce)` block.
5. Confirm `@keyframes sheet-in` (line 206) is unchanged — this plan only
   adds a new consumer of it, it does not modify it.

## Boundaries

- Do NOT add an exit/close animation. `StockDetailModal.jsx` renders the
  overlay conditionally with a plain React unmount (no delayed-unmount
  state machine exists yet) — adding exit motion would need that
  infrastructure and is out of scope for this plan.
- Do NOT touch `.auth-overlay`/`.login-modal`'s own rules beyond what they
  inherit from `.modal-overlay`/`.modal` by composition — they get the new
  entrance for free since they extend those base classes in the markup.
- Do NOT touch `.mobile-sheet` or `.mobile-sheet-layer` — already correct,
  not in scope.
- Do NOT add a JS animation library or a `data-mounted` mechanism.
- If `.modal-overlay`/`.modal`'s current declarations differ from what's
  quoted in Problem (drift since the commit stamp), STOP and report instead
  of improvising.

## Verification

- **Mechanical**: `npm run lint && npm test && npm run build` — all green.
  No JS changed, so no new test coverage is expected; this is a pure CSS
  addition.
- **Feel check**: run `npx vite --port 5175 --strictPort`, open the app, and
  open `StockDetailModal` (e.g. via Search or Picks) at three widths:
  - **Desktop (>620px)**: the overlay fades in fast, the panel fades+scales
    up from 0.96→1 over ~220ms — it should read as "settling into place,"
    not a bounce or a snap.
  - **Mobile (≤620px)**: the panel should rise from the bottom edge exactly
    like the existing `.mobile-sheet` filter panel does elsewhere in the
    app — open both back to back and confirm they feel like the same
    motion language.
  - In DevTools Animations panel, set playback to 10% and confirm the panel
    animation uses `transform`/`opacity` only (no `width`/`height` in the
    recorded animation) and starts fast, slowing into rest (ease-out, not
    ease-in).
  - Toggle `prefers-reduced-motion` (DevTools Rendering panel) and confirm
    the modal now appears with no animation at all (this is acceptable for
    a one-shot open — AUDIT.md's "keep transitions that aid comprehension"
    guidance is about repeatable/ongoing feedback, not a single appear
    event).
  - Open the login modal (log out, or use an incognito session) and confirm
    it also fades+scales in — it composes `.modal`, so no separate change
    should have been needed for it.
- **Done when**: `StockDetailModal` and the login modal both animate in on
  every viewport, the reduced-motion preference suppresses it, and no
  existing test/lint/build regressed.
