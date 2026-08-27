/**
 * Newspaper headline generation from `reads` + `status` — never freehand. Lives in core (not in
 * the Newspaper medium's own files) so Phase 3's headline-rule assertion (10) can unit-test the
 * function directly, independent of any DOM.
 *
 * The interrogative rule: insufficient evidence makes assertion structurally impossible. A
 * metric whose status is accumulating NEVER gets a declarative headline — the template branches
 * on state before it ever touches the metric's `reads` string.
 */
import { STATES, canonicalMetricState } from './states.js'

function sentenceCase(text) {
  if (!text) return text
  const trimmed = text.trim().replace(/[.!?]+$/, '')
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1)
}

/**
 * Best-effort split of a metric label into a subject/predicate pair for the interrogative
 * template, e.g. "Momentum leg IC" -> subject "the momentum leg IC". Falls back to the label
 * itself (still wrapped in a non-declarative question, never promoted to an assertion) when the
 * label doesn't parse into anything more specific.
 */
function subjectFromLabel(label) {
  if (!label) return 'this metric'
  const cleaned = label.trim()
  return /^(the|a|an)\s/i.test(cleaned) ? cleaned : `the ${cleaned.charAt(0).toLowerCase()}${cleaned.slice(1)}`
}

function periodNoun(cadence) {
  if (!cadence) return 'periods'
  const lower = cadence.toLowerCase()
  if (lower.includes('week')) return 'weekly periods'
  if (lower.includes('month')) return 'monthly periods'
  if (lower.includes('quarter')) return 'quarterly periods'
  if (lower.includes('day')) return 'daily periods'
  return 'periods'
}

/**
 * Builds the headline object for one metric row. Returns { headline, standfirst, declarative }.
 * `declarative` is exposed so a caller (and Phase 3's DOM assertion) can check directly whether
 * a given headline asserted something, rather than pattern-matching the rendered text.
 */
export function headlineFor(metric) {
  const canonical = canonicalMetricState(metric)

  if (canonical.state === STATES.BREACHED) {
    return {
      headline: sentenceCase(metric?.reads) || `${metric?.label || 'This metric'} has breached its kill threshold.`,
      standfirst: metric?.kill_threshold ? `Breached: ${metric.kill_threshold}.` : 'Kill threshold breached.',
      declarative: true,
    }
  }

  if (canonical.state === STATES.ACCUMULATING) {
    const subject = subjectFromLabel(metric?.label)
    const observations = canonical.observations
    const required = canonical.required
    const noun = periodNoun(metric?.cadence)
    if (observations != null && required != null) {
      return {
        headline: `Is ${subject}? ${observations} of ${required} ${noun} observed.`,
        standfirst: null,
        declarative: false,
      }
    }
    return {
      headline: `Is ${subject}? Not yet enough evidence to say.`,
      standfirst: null,
      declarative: false,
    }
  }

  if (canonical.state === STATES.UNAVAILABLE) {
    return {
      headline: `Not yet reported — ${canonical.reason || 'no data published.'}`,
      standfirst: null,
      declarative: false,
    }
  }

  // established
  const declarative = sentenceCase(metric?.reads)
  if (declarative) return { headline: declarative, standfirst: null, declarative: true }
  // Non-declarative fallback when `reads` doesn't parse into a usable sentence — still never
  // an assertion the data doesn't support.
  return { headline: `${metric?.label || 'This metric'} is read now.`, standfirst: null, declarative: true }
}
