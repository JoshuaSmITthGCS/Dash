/**
 * The canonical four-state + confidence model every medium renders through.
 *
 * Three independent vocabularies exist in the published data (see DATA-INVENTORY.md):
 *   1. Pipeline health        healthy | degraded | error                  (status.json)
 *   2. Artifact build status  success | partial | gated | unavailable     (most screens/*.json)
 *   3. Metric readiness       ready | provisional | accumulating |
 *                             awaiting_input | awaiting_live_sample |
 *                             unavailable, crossed with breached: t/f/null (signal_metrics.json)
 *
 * This module maps all three onto ONE shape every medium's renderers and WallLabel consume,
 * so a medium never has to know which vocabulary a given number came from.
 */

export const STATES = Object.freeze({
  ESTABLISHED: 'established',
  ACCUMULATING: 'accumulating',
  BREACHED: 'breached',
  UNAVAILABLE: 'unavailable',
})

const ACCUMULATING_STATUSES = new Set(['provisional', 'accumulating', 'awaiting_live_sample'])

/**
 * Maps one `signal_metrics.json` row (or any object shaped like one — `status`, `breached`,
 * `observations`, `required_observations`, `status_message`) to a CanonicalState.
 *
 * Breached outranks everything, mirroring `metricTone()` in `src/lib/signalMetrics.js`: a
 * metric that computed cleanly and failed its own kill threshold is the loudest thing on the
 * page, regardless of what its `status` field says. `provisional` maps to accumulating (it
 * carries a number, but a provisional one) and keeps its `status_message` as the caveat text —
 * exactly the distinction `isRead()`/`metricTone()` draw in `src/lib/signalMetrics.js`.
 */
export function canonicalMetricState(metric) {
  if (!metric) return { state: STATES.UNAVAILABLE, reason: 'No metric published.' }
  if (metric.breached === true) {
    return {
      state: STATES.BREACHED,
      reason: metric.kill_threshold || metric.status_message || null,
      observations: metric.observations ?? null,
      required: metric.required_observations ?? null,
    }
  }
  const status = metric.status
  if (status === 'ready') {
    return { state: STATES.ESTABLISHED, reason: null }
  }
  if (ACCUMULATING_STATUSES.has(status)) {
    return {
      state: STATES.ACCUMULATING,
      reason: metric.status_message || null,
      observations: metric.observations ?? null,
      required: metric.required_observations ?? null,
      progress: sampleFraction(metric),
    }
  }
  // 'awaiting_input' | 'unavailable' | anything unrecognized
  return { state: STATES.UNAVAILABLE, reason: metric.status_message || 'Unavailable.' }
}

function sampleFraction(metric) {
  if (!metric.required_observations || metric.observations == null) return null
  return Math.max(0, Math.min(1, metric.observations / metric.required_observations))
}

/**
 * Maps an artifact's own build-status block (`{status, reason_code | degraded_reason}`) to a
 * CanonicalState for the container as a whole. A 'partial' container is itself established
 * (it built and is safe to render) — its individual absent rows are what carry 'unavailable'.
 * A 'gated' artifact (e.g. early-session.json) is a deliberate, successful outcome, not an
 * error — its `reason` should read as a feature, not a failure.
 */
export function canonicalArtifactState(artifact) {
  const status = artifact?.status
  if (status === 'success') return { state: STATES.ESTABLISHED, reason: null }
  if (status === 'partial') {
    return { state: STATES.ESTABLISHED, reason: artifact?.reason_code || null, partial: true }
  }
  if (status === 'gated') {
    return { state: STATES.UNAVAILABLE, reason: artifact?.disclaimer || 'Gated by data quality — a successful outcome, not an error.' }
  }
  return { state: STATES.UNAVAILABLE, reason: artifact?.degraded_reason || artifact?.reason_code || 'Unavailable.' }
}

/** Pipeline health never becomes a per-metric state — it feeds a chrome-level notice only. */
export function healthNotice(status) {
  const level = { healthy: 'ok', degraded: 'warning', error: 'error' }[status] || 'unknown'
  const message = {
    healthy: 'All pipeline stages healthy.',
    degraded: 'One or more pipeline stages are degraded.',
    error: 'A pipeline stage failed on the latest run.',
    unknown: 'Pipeline health unavailable.',
  }[level === 'unknown' ? 'unknown' : status]
  return { level, message }
}

/**
 * Qualitative confidence — a continuous 0..1 scalar plus its basis, never hue, never a
 * three-level bucket, never blur over an interval. Renderers map `level` to their own channel
 * (chalk pressure, dither density, tube chroma, registration offset, transparency).
 *
 * Sources, in descending priority: an explicit `confidence` field on the row itself; whether
 * the metric `requires_live_sample` (wired-but-waiting metrics read as lower confidence until
 * they're read at all); the SAMPLE_BUCKETS split; a declared |t| < 2 statistical-insignificance
 * flag. Falls back to 0.5 (deliberately neutral, not zero — "unknown" is not "no confidence").
 */
export function confidenceOf(context = {}) {
  const basis = []
  if (typeof context.confidence === 'number') {
    basis.push('explicit confidence field')
    return { level: clamp01(context.confidence), basis }
  }
  let level = 0.5
  if (context.tStat != null && Math.abs(context.tStat) < 2) {
    level = Math.min(level, 0.2)
    basis.push('|t| < 2 — statistically meaningless per the registered hurdle')
  }
  if (context.metric?.requires_live_sample && !isReadStatus(context.metric.status)) {
    level = Math.min(level, 0.3)
    basis.push('requires a live sample not yet accumulated')
  }
  if (context.classification === 'B') {
    level = Math.min(level, 0.4)
    basis.push('classification B — transparent factor tilt, no demonstrated residual alpha')
  }
  if (context.icPeriodsAccumulated != null && context.icPeriodsRequired) {
    const fraction = clamp01(context.icPeriodsAccumulated / context.icPeriodsRequired)
    level = Math.min(level, 0.15 + fraction * 0.35)
    basis.push(`${context.icPeriodsAccumulated} of ${context.icPeriodsRequired} IC periods observed`)
  }
  if (!basis.length) basis.push('no qualitative flag on this row')
  return { level: clamp01(level), basis }
}

function isReadStatus(status) {
  return status === 'ready' || status === 'provisional'
}

function clamp01(value) {
  return Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0.5))
}

/**
 * Provenance for one artifact's footer/title-block. Degrades gracefully for the three files
 * that ship without a `model_metadata` block (shadow-portfolios.json, early-session.json,
 * every etf/<ticker>.json) — never fabricates a version string for them.
 */
export function provenanceOf(artifact) {
  const meta = artifact?.model_metadata
  if (!meta) {
    return {
      semanticVersion: artifact?.model_version || null,
      gitCommitSha: null,
      configHash: null,
      generatedAt: artifact?.generated_at || null,
      complete: false,
    }
  }
  return {
    semanticVersion: meta.semantic_version || artifact?.model_version || null,
    gitCommitSha: meta.git_commit_sha || null,
    configHash: meta.config_hash || null,
    generatedAt: meta.generated_at || artifact?.generated_at || null,
    complete: true,
  }
}

/**
 * The "no signal has been promoted / classification B" disclosure — closes the gap noted in
 * NOTES.md: today this sentence exists only in docs/. Every medium's ProvenanceStrip renders
 * this object's `text` at equal-or-greater prominence to every other protected disclosure.
 * Reads live from `research_evidence.json`'s `headline` block; never a hardcoded string.
 */
export function promotionDisclosure(researchEvidence) {
  const headline = researchEvidence?.headline
  if (!headline) {
    return { text: 'Promotion status unavailable — the research-evidence artifact has not published a headline yet.', periodsAccumulated: null, periodsRequired: null }
  }
  const accumulated = headline.ic_periods_accumulated ?? 0
  const required = headline.ic_periods_required ?? 24
  return {
    text: `No signal has been promoted. The IC harness has observed ${accumulated} of the ${required} eligible periods required. No IC, Sharpe, drawdown, or hit-rate statistic here should be read as a validated result.`,
    validationStatus: headline.validation_status || null,
    periodsAccumulated: accumulated,
    periodsRequired: required,
    scoreIsNotAProbability: headline.score_is_not_a_probability || null,
  }
}
