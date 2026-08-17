# Motion audit plans

Written by the `improve-animations` skill against commit `c5038791`, as
Phase 6's motion pass (`docs/REDESIGN-PLAN.md` §"Motion pass, plan-then-
execute", `docs/REDESIGN-STATUS.md` §2). Run non-interactively: the vetted
findings below were not put to the user for selection; the top 3 by
leverage were promoted directly to plans, per the skill's own
non-interactive default.

| # | Title | Severity | Category | Status |
|---|---|---|---|---|
| [001](001-pull-to-refresh-tracking-lag.md) | Fix pull-to-refresh indicator lagging the finger | HIGH | Interruptibility & Performance | TODO |
| [002](002-modal-entrance-animation.md) | Give the primary modal an entrance animation | MEDIUM | Missed opportunities | TODO |
| [003](003-animated-number-reduced-motion.md) | Respect prefers-reduced-motion in AnimatedNumber | MEDIUM | Accessibility | TODO |

## Recommended execution order

1, then 2 and 3 in either order — none of the three share a file or depend
on each other. All are safe to execute in parallel if using isolated
worktrees.

## Findings observed but not planned

Two lower-leverage findings came out of the same audit and are recorded
here so they aren't silently dropped, but weren't promoted to a plan:

- **LOW — Performance.** `.refresh-progress-fill` (`dashboard.css:32`) and
  `.live-countdown-progress > i > span` (`app-frame.css:92`) animate `width`
  (a layout property) instead of `transform: scaleX()`. Textbook-correct fix,
  but both update at most once per minute or once per data refresh (verified
  against their call sites, `LiveTrackingCountdown.jsx` and `Bits.jsx:108`)
  — not a gesture or high-frequency update like plan 001's finding, so the
  real-world cost is a single reflow on an already-infrequent event. Revisit
  only if bundled with other work in the same files.
- **LOW — Cohesion.** Hand-typed durations/easings (`.15s`/`.18s`/`.2s`/
  `.35s`, bare `ease`) are scattered across chevron-rotate and hover rules in
  `controls.css`, `analytics.css`, `portfolio.css`, `research.css`, and
  `dashboard.css`, instead of the existing `--duration-fast/normal/slow` +
  `--ease-default`/`--ease-out` tokens (`src/styles/variables.css:170-174`).
  A real consolidation opportunity, but diffuse (10+ unrelated sites) for
  cosmetic benefit only — no user-visible feel difference, since the
  hand-typed values (150-200ms, roughly `ease`) are already close to the
  token values they'd be replaced with.

## Not audited

Chart entrance/draw animations (`chart-enter`, `chart-draw` keyframes in
`app-frame.css`/`workspace.css`) and the score-dial/gauge arc animation
(`gauge-fill-arc`, `portfolio-routes.css:140`) were reviewed and found
correctly built already — gated by `data-chart-animation`/`data-motion`,
`ease-out`, transform/stroke-only, no findings. Not included above per
AUDIT.md's guidance that "the motion here is already right" is a valid
audit result.
