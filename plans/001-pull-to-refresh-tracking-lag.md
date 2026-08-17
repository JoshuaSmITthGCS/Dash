# 001 — Fix pull-to-refresh indicator lagging the finger

- **Status**: DONE
- **Commit**: c5038791
- **Severity**: HIGH
- **Category**: Interruptibility & Performance
- **Estimated scope**: 2 files, ~4 lines

## Problem

`usePullToRefresh.js` calls `setPullDistance(resisted)` on every native
`touchmove` event during an active drag (`src/lib/usePullToRefresh.js:31`) —
this is a genuine 1:1 finger-tracking gesture, not a settle animation.

That state feeds a CSS custom property that a *transitioned* layout property
reads:

```css
/* src/styles/modules/dashboard.css:20 — current */
.pull-to-refresh { display: flex; justify-content: center; height: var(--ptr-distance, 0px); overflow: hidden; transition: height .15s ease; }
```

```jsx
/* src/components/PullToRefreshIndicator.jsx:7 — current */
<div className="pull-to-refresh" style={{ '--ptr-progress': progress, '--ptr-distance': `${Math.min(pullDistance, 70)}px` }} aria-hidden="true">
```

Because `height` is transitioned, every new `touchmove` frame retargets a
150ms transition that is still mid-flight from the *previous* frame — the
indicator chases the finger instead of tracking it, and `height` is a
layout-triggering property (forces reflow every frame; `transform`/`opacity`
would not). The one correct place for a transition is the snap-back after
release, where `pullDistance` resets to 0 in one jump
(`src/lib/usePullToRefresh.js:39`) and a quick ease-out settle is exactly
right.

## Target

Track the gesture with **no transition** while dragging; add the transition
back only for the release snap. React doesn't have a native `:active-drag`
selector, so this needs a JS-driven class toggle keyed off the existing
`tracking` ref writes.

```css
/* target — src/styles/modules/dashboard.css:20 */
.pull-to-refresh { display: flex; justify-content: center; height: var(--ptr-distance, 0px); overflow: hidden; }
.pull-to-refresh.pull-to-refresh--settling { transition: height var(--duration-fast) var(--ease-out); }
```

```js
/* target — src/lib/usePullToRefresh.js: expose whether we're mid-drag vs settling */
export function usePullToRefresh({ onRefresh, enabled = true, refreshing = false }) {
  const [pullDistance, setPullDistance] = useState(0)
  const [armed, setArmed] = useState(false)
  const [settling, setSettling] = useState(false)
  const startY = useRef(null)
  const tracking = useRef(false)
  // ...
  const onTouchMove = (event) => {
    if (!tracking.current || startY.current == null) return
    const delta = event.touches[0].clientY - startY.current
    if (delta <= 0 || window.scrollY > 0) { setSettling(true); setPullDistance(0); setArmed(false); return }
    setSettling(false)
    const resisted = Math.min(MAX_PULL, delta * 0.5)
    setPullDistance(resisted)
    setArmed(resisted >= TRIGGER_DISTANCE)
  }

  const onTouchEnd = () => {
    if (tracking.current && armed) onRefresh?.()
    tracking.current = false
    startY.current = null
    setSettling(true)
    setPullDistance(0)
    setArmed(false)
  }
  // ...
  return { pullDistance, armed, active: pullDistance > 0 || refreshing, settling }
}
```

```jsx
/* target — src/components/PullToRefreshIndicator.jsx */
export default function PullToRefreshIndicator({ pullDistance, armed, refreshing, settling }) {
  if (!refreshing && pullDistance <= 0) return null
  const progress = refreshing ? 1 : Math.min(1, pullDistance / 70)
  return (
    <div
      className={`pull-to-refresh${settling ? ' pull-to-refresh--settling' : ''}`}
      style={{ '--ptr-progress': progress, '--ptr-distance': `${Math.min(pullDistance, 70)}px` }}
      aria-hidden="true"
    >
      <span className={`pull-to-refresh-badge${armed || refreshing ? ' armed' : ''}`}>
        <Icon name="sync" size={16} className={refreshing ? 'refresh-spin' : ''} />
      </span>
    </div>
  )
}
```

## Repo conventions to follow

- Duration/easing tokens live in `src/styles/variables.css:170-174`:
  `--duration-fast: 150ms`, `--duration-normal: 220ms`, `--duration-slow:
  350ms`, `--ease-default: cubic-bezier(.4, 0, .2, 1)`, `--ease-out:
  cubic-bezier(.23, 1, .32, 1)`. Use `--duration-fast` + `--ease-out` for the
  settle (release/snap = entering-a-rest-state, `ease-out` per the decision
  order in AUDIT.md §2).
- The existing reduced-motion carve-out for this exact component already
  exists and must be preserved verbatim:
  `src/styles/modules/dashboard.css:36-38`:
  ```css
  @media (prefers-reduced-motion: reduce) {
    .refresh-progress-fill { transition: none; }
  }
  ```
  Add the same pattern for `.pull-to-refresh--settling`.

## Steps

1. In `src/lib/usePullToRefresh.js`, add a `settling` state variable
   (`useState(false)`), initialized `false`.
2. In `onTouchMove`, when the gesture is actively dragging (the `resisted =
   Math.min(...)` branch), call `setSettling(false)` before `setPullDistance`.
   When the drag cancels (`delta <= 0 || window.scrollY > 0`), call
   `setSettling(true)` before resetting `pullDistance`/`armed`.
3. In `onTouchEnd`, call `setSettling(true)` before resetting
   `pullDistance`/`armed`.
4. Add `settling` to the hook's return object.
5. In `src/components/PullToRefreshIndicator.jsx`, accept a `settling` prop
   and append `' pull-to-refresh--settling'` to the `className` when true, as
   shown in Target above.
6. Find the call site(s) that render `<PullToRefreshIndicator>` (grep
   `PullToRefreshIndicator` in `src/pages/Dashboard.jsx` and
   `src/pages/Portfolio.jsx`) and pass through the new `settling` value from
   `usePullToRefresh`'s return.
7. In `src/styles/modules/dashboard.css`, replace the `.pull-to-refresh` rule
   at line 20 with the two-rule Target above (base rule loses `transition:
   height .15s ease`; a new `.pull-to-refresh--settling` rule adds
   `transition: height var(--duration-fast) var(--ease-out);`).
8. Add a `prefers-reduced-motion` rule turning off
   `.pull-to-refresh--settling`'s transition, next to the existing block at
   `src/styles/modules/dashboard.css:36-38`.

## Boundaries

- Do NOT touch `.pull-to-refresh-badge`'s `transform: scale(...) rotate(...)`
  rule (`dashboard.css:24`) — that's already a per-frame direct transform
  update on the element itself (not a child, not layout-triggering) and is
  correct as-is.
- Do NOT touch `.refresh-progress-fill` or `.refresh-spin` — separate
  findings, not in scope here.
- Do NOT add a new animation/motion library. Plain CSS + the existing hook
  pattern only.
- If `usePullToRefresh.js` or `PullToRefreshIndicator.jsx` has drifted from
  the code quoted above (line numbers or logic differ), STOP and report
  instead of improvising.

## Verification

- **Mechanical**: `npm run lint && npm test && npm run build` — all green.
  There is no existing test file for `usePullToRefresh.js` or
  `PullToRefreshIndicator.jsx`; do not add one unless a step above says to
  (this plan is a behavior-preserving perf fix, not new testable logic beyond
  what a feel-check can verify).
- **Feel check**: On a touch device or Chrome DevTools device toolbar
  (throttle CPU 4x to make the difference obvious), open `/` or `/portfolio`
  at the top of the page, and drag down slowly with touch emulation:
  - The indicator height should track the touch point with no visible delay
    — compare before/after by recording the drag in slow motion.
  - On release without reaching the trigger distance, the indicator should
    smoothly retract over ~150ms rather than snapping instantly or lagging.
  - Toggle `prefers-reduced-motion` (DevTools Rendering panel) and confirm
    the retract on release is instant (no transition) rather than removed
    entirely — the pull still visually resolves, just without the settle
    animation.
- **Done when**: dragging the indicator produces no visible chase-lag between
  finger and indicator at any point during the drag, and the release retract
  still animates smoothly.
