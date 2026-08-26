import { canonicalMetricState, confidenceOf } from './states.js'
import { headlineFor } from './headline.js'
import { cap, warnIfUnknownCapability } from './capability.js'
import { useMedium } from './MediumContext.jsx'

/**
 * The wall-label contract (master doc): every chart, table, and headline number carries what it
 * measures in plain language, its period/unit, a reference point, the read (one line from
 * evidence on screen), the quantitative state per the active medium, qualitative confidence as
 * a separate channel, and the action where one exists.
 *
 * `<WallLabel metric={row} action={optionalControl}>{chartElement}</WallLabel>` derives all of
 * that itself from the metric row — a page never composes label copy by hand, which is what
 * makes hand-written disclosure strings structurally impossible. It renders through the active
 * medium's `components.LabelFrame(parts)` render prop, so every medium gets the same structured
 * data and decides its own typography/material for it.
 *
 * `metric` is expected to be shaped like a `signal_metrics.json` row: { id, label, reads, unit,
 * cadence, kill_threshold, kill_threshold_value, backtest_reference, source, status, breached,
 * observations, required_observations, status_message }. Any object with that shape works —
 * this component doesn't care which published file it came from.
 */
export default function WallLabel({ metric, action = null, capabilityId = null, children = null }) {
  const manifest = useMedium()
  const canonical = canonicalMetricState(metric)
  const confidence = confidenceOf({ metric })

  const capId = capabilityId || (metric?.id ? `metric.report.${metric.id.replace(/_/g, '-')}` : null)
  if (import.meta.env?.DEV) warnIfUnknownCapability(capId)

  const parts = {
    title: metric?.label || 'Untitled metric',
    mediumLine: [metric?.unit, metric?.cadence].filter(Boolean).join(' · ') || null,
    // The actual numeral — `display` (pre-formatted, e.g. "-0.038" or "0.036 (95% CI -0.010 to
    // 0.078)") when the row publishes one, else the raw `value`. Distinct from `read`, which is
    // always prose (the metric's `reads` sentence) — a medium's "big numeral" slot must render
    // `value`, never `read`, or it silently shows a sentence where a number belongs.
    value: metric?.display ?? (metric?.value != null ? String(metric.value) : null),
    read: metric?.reads || null,
    reference: metric?.kill_threshold || metric?.backtest_reference || null,
    provenance: metric?.source || null,
    state: canonical,
    confidence,
    action,
    reason: canonical.reason,
    // Optional, additive: a metric's own detail block sometimes carries a prior observation
    // (e.g. signal_metrics.json rows' `detail.series`). Passed through only when the row
    // genuinely publishes one — a medium's erasure/prior-value device (Chalkboard's smudge)
    // must never fabricate a "previous" reading that wasn't actually published.
    previous: metric?.previous_value ?? metric?.detail?.previous_value ?? null,
    // Precomputed here (not in the medium) so headline.js's declarative/interrogative grammar
    // stays testable independent of any renderer — Newspaper's primary consumer, but additive
    // and available to any medium's LabelFrame.
    headline: headlineFor(metric),
    // Optional, additive: some rows genuinely publish a bootstrap confidence interval (e.g.
    // ic_bootstrap_ci's `detail.ic_ci_95`). Passed through only when actually present — Star
    // Chart's error-ellipse device must never invent an interval a metric doesn't publish.
    confidenceInterval: metric?.detail?.ic_ci_95 ?? metric?.detail?.confidence_interval_95 ?? null,
  }

  const LabelFrame = manifest?.components?.LabelFrame
  if (!LabelFrame) {
    // Dev-time fallback so an in-progress medium (LabelFrame not implemented yet) still renders
    // something legible instead of crashing the screen. Never used once a medium ships.
    return (
      <div {...cap(capId)} data-wall-label-fallback="true">
        <strong>{parts.title}</strong>
        {parts.mediumLine && <div>{parts.mediumLine}</div>}
        {parts.read && <p>{parts.read}</p>}
        <div>{canonical.state}{canonical.reason ? ` — ${canonical.reason}` : ''}</div>
        {children}
      </div>
    )
  }

  return <LabelFrame parts={parts} capabilityId={capId}>{children}</LabelFrame>
}
