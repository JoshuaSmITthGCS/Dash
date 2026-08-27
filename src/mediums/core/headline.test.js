import { describe, expect, it } from 'vitest'
import { headlineFor } from './headline.js'

describe('headlineFor', () => {
  it('is declarative for an established metric, sourced from reads', () => {
    const result = headlineFor({ status: 'ready', breached: false, reads: 'Momentum leg has led the composite for six weeks.' })
    expect(result.declarative).toBe(true)
    expect(result.headline).toBe('Momentum leg has led the composite for six weeks')
  })

  it('is NEVER declarative for an accumulating metric — the interrogative rule', () => {
    const result = headlineFor({
      status: 'accumulating', breached: false, label: 'Momentum leg IC',
      observations: 17, required_observations: 24, cadence: 'Monthly',
    })
    expect(result.declarative).toBe(false)
    expect(result.headline).toMatch(/^Is /)
    expect(result.headline).toContain('17 of 24')
    expect(result.headline).toContain('monthly periods')
  })

  it('is interrogative for provisional too', () => {
    const result = headlineFor({ status: 'provisional', breached: false, label: 'Probability of backtest overfitting' })
    expect(result.declarative).toBe(false)
    expect(result.headline).toMatch(/^Is /)
  })

  it('is declarative with a standfirst for breached', () => {
    const result = headlineFor({ status: 'ready', breached: true, kill_threshold: 'Mean IC < 0.02', reads: 'Spearman correlation of score against forward return.' })
    expect(result.declarative).toBe(true)
    expect(result.standfirst).toBe('Breached: Mean IC < 0.02.')
  })

  it('is non-declarative with a reason for unavailable', () => {
    const result = headlineFor({ status: 'unavailable', status_message: 'Run pipeline/signal_metrics.py.' })
    expect(result.declarative).toBe(false)
    expect(result.headline).toContain('Not yet reported')
    expect(result.headline).toContain('Run pipeline/signal_metrics.py.')
  })

  it('never crashes on a missing metric', () => {
    expect(() => headlineFor(null)).not.toThrow()
    expect(headlineFor(null).declarative).toBe(false)
  })

  it('falls back to a non-declarative-safe established headline when reads is missing', () => {
    const result = headlineFor({ status: 'ready', breached: false, label: 'Some Metric' })
    expect(result.headline).toContain('Some Metric')
  })
})
