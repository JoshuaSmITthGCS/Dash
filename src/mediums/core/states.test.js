import { describe, expect, it } from 'vitest'
import {
  STATES, canonicalMetricState, canonicalArtifactState, healthNotice,
  confidenceOf, provenanceOf, promotionDisclosure,
} from './states.js'

describe('canonicalMetricState', () => {
  it('ranks breached above status, mirroring metricTone()', () => {
    const result = canonicalMetricState({ status: 'ready', breached: true, kill_threshold: 'Mean IC < 0.02' })
    expect(result.state).toBe(STATES.BREACHED)
    expect(result.reason).toBe('Mean IC < 0.02')
  })

  it('maps ready to established with no reason', () => {
    expect(canonicalMetricState({ status: 'ready', breached: false })).toEqual({ state: STATES.ESTABLISHED, reason: null })
  })

  it('maps provisional to accumulating and keeps status_message', () => {
    const result = canonicalMetricState({
      status: 'provisional', breached: false, status_message: '3 holdout folds.',
      observations: null, required_observations: null,
    })
    expect(result.state).toBe(STATES.ACCUMULATING)
    expect(result.reason).toBe('3 holdout folds.')
  })

  it('maps accumulating with observations/required and computes progress', () => {
    const result = canonicalMetricState({ status: 'accumulating', breached: null, observations: 18, required_observations: 24 })
    expect(result.state).toBe(STATES.ACCUMULATING)
    expect(result.observations).toBe(18)
    expect(result.required).toBe(24)
    expect(result.progress).toBeCloseTo(0.75)
  })

  it('maps awaiting_input and unavailable to unavailable', () => {
    expect(canonicalMetricState({ status: 'awaiting_input' }).state).toBe(STATES.UNAVAILABLE)
    expect(canonicalMetricState({ status: 'unavailable' }).state).toBe(STATES.UNAVAILABLE)
  })

  it('never returns a zero-reading for missing data — always a labeled state', () => {
    const result = canonicalMetricState(null)
    expect(result.state).toBe(STATES.UNAVAILABLE)
    expect(result.reason).toBeTruthy()
  })
})

describe('canonicalArtifactState', () => {
  it('success is established with no reason', () => {
    expect(canonicalArtifactState({ status: 'success' })).toEqual({ state: STATES.ESTABLISHED, reason: null })
  })

  it('partial is established but carries its reason_code and a partial flag', () => {
    const result = canonicalArtifactState({ status: 'partial', reason_code: 'SOME_SOURCES_UNAVAILABLE' })
    expect(result.state).toBe(STATES.ESTABLISHED)
    expect(result.partial).toBe(true)
    expect(result.reason).toBe('SOME_SOURCES_UNAVAILABLE')
  })

  it('gated is unavailable but reads as a feature, not a failure', () => {
    const result = canonicalArtifactState({ status: 'gated', disclaimer: 'Killed screens are a successful outcome.' })
    expect(result.state).toBe(STATES.UNAVAILABLE)
    expect(result.reason).toMatch(/successful outcome/)
  })

  it('unavailable/unknown falls back to unavailable', () => {
    expect(canonicalArtifactState({ status: 'unavailable', degraded_reason: 'no run yet' }).state).toBe(STATES.UNAVAILABLE)
    expect(canonicalArtifactState(null).state).toBe(STATES.UNAVAILABLE)
  })
})

describe('healthNotice', () => {
  it('maps the three pipeline-health values', () => {
    expect(healthNotice('healthy').level).toBe('ok')
    expect(healthNotice('degraded').level).toBe('warning')
    expect(healthNotice('error').level).toBe('error')
  })
})

describe('confidenceOf', () => {
  it('defaults to a neutral 0.5 with a stated basis when nothing is flagged', () => {
    const result = confidenceOf({})
    expect(result.level).toBe(0.5)
    expect(result.basis.length).toBeGreaterThan(0)
  })

  it('uses an explicit confidence field first', () => {
    expect(confidenceOf({ confidence: 0.9 }).level).toBe(0.9)
  })

  it('clamps an out-of-range explicit confidence', () => {
    expect(confidenceOf({ confidence: 4 }).level).toBe(1)
    expect(confidenceOf({ confidence: -2 }).level).toBe(0)
  })

  it('lowers confidence for |t| < 2', () => {
    expect(confidenceOf({ tStat: 0.68 }).level).toBeLessThanOrEqual(0.2)
  })

  it('lowers confidence for classification B', () => {
    expect(confidenceOf({ classification: 'B' }).level).toBeLessThanOrEqual(0.4)
  })

  it('never returns a hue — the level is a plain number, not a color', () => {
    const result = confidenceOf({ classification: 'B' })
    expect(typeof result.level).toBe('number')
  })
})

describe('provenanceOf', () => {
  it('reads model_metadata, never the top-level model_version', () => {
    const result = provenanceOf({ model_version: '3.0.0', model_metadata: { semantic_version: '3.2.0', git_commit_sha: 'abc', config_hash: 'def', generated_at: '2026-08-25' } })
    expect(result.semanticVersion).toBe('3.2.0')
    expect(result.complete).toBe(true)
  })

  it('degrades gracefully for the three envelope-less files without fabricating a version', () => {
    const result = provenanceOf({ status: 'success' })
    expect(result.complete).toBe(false)
    expect(result.gitCommitSha).toBeNull()
    expect(result.configHash).toBeNull()
  })
})

describe('promotionDisclosure', () => {
  it('reads live values, never hardcodes the period counts', () => {
    const result = promotionDisclosure({ headline: { ic_periods_accumulated: 3, ic_periods_required: 24 } })
    expect(result.text).toContain('3 of the 24')
    expect(result.periodsAccumulated).toBe(3)
  })

  it('handles a missing artifact without throwing', () => {
    const result = promotionDisclosure(null)
    expect(result.text).toBeTruthy()
    expect(result.periodsAccumulated).toBeNull()
  })
})
