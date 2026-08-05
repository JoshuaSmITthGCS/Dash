import { describe, expect, it } from 'vitest'
import { alertRuleLabel, normalizeAlertRule, validateAlertRule } from './alertRules.js'

describe('alert rules', () => {
  it('normalizes tickers and rejects missing thresholds', () => {
    const rule = normalizeAlertRule({ type: 'price_cross', ticker: ' msft ', threshold: '' })
    expect(rule.ticker).toBe('MSFT')
    expect(validateAlertRule(rule)).toEqual({ valid: false, error: 'Enter a threshold greater than zero.' })
  })

  it('validates and labels every server-supported rule shape', () => {
    const checked = validateAlertRule({ type: 'percent_move', ticker: 'aapl', direction: 'below', periodDays: 5, threshold: 4 })
    expect(checked.valid).toBe(true)
    expect(alertRuleLabel(checked.rule)).toBe('AAPL 5-day move below 4%')
  })

  it('allows pipeline stale rules without a ticker', () => {
    expect(validateAlertRule({ type: 'pipeline_stale', staleHours: 36 }).valid).toBe(true)
  })
})
