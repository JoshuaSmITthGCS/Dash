/**
 * Presentation rules for the signal-metrics artifact (pipeline/signal_metrics.py).
 *
 * The split this module exists to make is the useful one: metrics that can be read today
 * against metrics that cannot be read until a live sample accumulates. Mixing the two is
 * what makes a dashboard feel empty at eighteen days live - the sample-starved half sits
 * blank next to the half that already has answers, and the blanks set the tone.
 *
 * Separated, the first bucket is a working report on signal quality and the second is an
 * honest waiting room with its own progress counters.
 */

export const SAMPLE_BUCKETS = [
  {
    id: 'now',
    requiresLiveSample: false,
    title: 'Computable now',
    subtitle: 'Backtest data answers these today. No waiting, no live track record needed.',
  },
  {
    id: 'sample',
    requiresLiveSample: true,
    title: 'Needs live sample',
    subtitle: 'Wired and waiting. Each one starts reading the day it has enough observations.',
  },
]

const STATUS_LABELS = {
  ready: 'Read now',
  provisional: 'Provisional',
  accumulating: 'Accumulating',
  awaiting_input: 'Needs a run',
  awaiting_live_sample: 'Needs live data',
  unavailable: 'Unavailable',
}

/** Ready and provisional both carry a number; everything else is a state, not a reading. */
export function isRead(metric) {
  return metric?.status === 'ready' || metric?.status === 'provisional'
}

export function statusLabel(status) {
  return STATUS_LABELS[status] || 'Unavailable'
}

/**
 * Tone drives colour. A breached kill threshold outranks a healthy status: a metric that
 * computed cleanly and failed its own test is the most important thing on the page.
 */
export function metricTone(metric) {
  if (metric?.breached) return 'breached'
  if (isRead(metric)) return 'ready'
  if (metric?.status === 'accumulating') return 'accumulating'
  return 'pending'
}

export function metricValueText(metric) {
  if (metric?.display != null) return metric.display
  if (metric?.value == null) return '–'
  return typeof metric.value === 'number' ? metric.value.toFixed(3) : String(metric.value)
}

/** "12 of 120 observations" – the honest denominator on anything still accumulating. */
export function sampleProgress(metric) {
  if (metric?.observations == null) return null
  if (!metric.required_observations) return `${metric.observations} observations`
  return `${metric.observations} of ${metric.required_observations} observations`
}

export function splitBySampleRequirement(report) {
  const groups = report?.groups || []
  const metrics = report?.metrics || []
  return SAMPLE_BUCKETS.map((bucket) => {
    const rows = metrics.filter((metric) => Boolean(metric.requires_live_sample) === bucket.requiresLiveSample)
    return {
      ...bucket,
      total: rows.length,
      read: rows.filter(isRead).length,
      breached: rows.filter((metric) => metric.breached).length,
      groups: groups
        .map((group) => ({ ...group, metrics: rows.filter((metric) => metric.group === group.id) }))
        .filter((group) => group.metrics.length > 0),
    }
  })
}

/**
 * Group A first, then whichever group holds a breached metric, then the rest in order.
 * A failing kill threshold should never be two collapsed sections down the page.
 */
export function defaultOpenGroups(bucket) {
  const breached = (bucket?.groups || []).filter((group) => group.metrics.some((metric) => metric.breached))
  const first = bucket?.groups?.[0]
  return new Set([...(first ? [first.id] : []), ...breached.map((group) => group.id)])
}

/**
 * When every metric in a group is blocked on the same thing, that sentence belongs to the
 * group, not to each card. Repeating "no scored panel found, run this command" eleven times
 * buries eleven different metrics under one piece of operational advice.
 */
export function sharedStatusMessage(metrics = []) {
  if (metrics.length < 2) return null
  const messages = metrics.map((metric) => metric.status_message)
  return messages.every((message) => message && message === messages[0]) ? messages[0] : null
}

export function liveSampleNote(report) {
  const live = report?.live_sample
  if (!live || !live.days) return 'No live point-in-time history has been recorded yet.'
  const days = `${live.days} live day${live.days === 1 ? '' : 's'}`
  const window = live.first_date && live.last_date ? ` (${live.first_date} to ${live.last_date})` : ''
  return `${days}${window} across ${live.refreshes} recorded refresh${live.refreshes === 1 ? '' : 'es'}.`
}
