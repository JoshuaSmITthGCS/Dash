import { describe, expect, it } from 'vitest'
import { actionHeadline, getRecommendation, positionImpact } from './recommendation'

describe('getRecommendation', () => {
  it('trusts the guidance the pipeline already published', () => {
    const stock = {
      ticker: 'AAA', confidence: 0.8,
      recommendation: {
        action: 'TRIM', suggested_trim_pct: 33, agreement_count: 2, confidence: 'moderate',
        reasons: ['profitability score 40/100'], summary: 'Multiple factors disagree.',
      },
    }
    const result = getRecommendation(stock)
    expect(result.action).toBe('TRIM')
    expect(result.suggestedTrimPct).toBe(33)
    expect(result.agreementCount).toBe(2)
    expect(result.source).toBe('pipeline')
  })

  it('falls back to the browser engine for rows published before the field existed', () => {
    const stock = {
      ticker: 'BBB', confidence: 0.8,
      components: { fundamentals: 28 },
      debt_to_equity: 3.1,
      current_ratio: 0.6,
      technical_detail: { return_5d: -8, return_20d: -22, return_60d: -30 },
    }
    const result = getRecommendation(stock)
    expect(result.source).toBe('client')
    expect(['TRIM', 'SELL']).toContain(result.action)
    expect(result.suggestedTrimPct).toBeGreaterThan(0)
  })

  it('never acts on a broken chart alone', () => {
    const stock = {
      ticker: 'CCC', confidence: 0.8,
      components: { fundamentals: 82 },
      technical_detail: { return_5d: -8, return_20d: -22, return_60d: -30 },
    }
    expect(getRecommendation(stock).action).toBe('HOLD')
  })

  it('gates prescriptive company action when canonical confidence is low', () => {
    const result = getRecommendation({
      confidence: 0.8,
      recommendation: { action: 'SELL', suggested_trim_pct: 100, agreement_count: 2 },
      analysis_v2: { structural: { confidence: 0.39, coverage: 0.8, missing_metrics: ['forward_eps_revision_30d'] } },
    })
    expect(result.action).toBe('WATCH')
    expect(result.summary).toMatch(/insufficient evidence/i)
  })

  it('returns nothing for a missing stock', () => {
    expect(getRecommendation(null)).toBeNull()
  })

  it('makes no action call at all below the confidence floor', () => {
    // The screenshot case: "Data confidence 0%" beside a live action label. Confidence
    // measures how much evidence resolved, so a low band withholds the call rather than
    // inverting it - "we cannot say" is not the same verdict as "sell".
    const result = getRecommendation({
      ticker: 'LOW', confidence: 0.2,
      recommendation: { action: 'HOLD', agreement_count: 2 },
    })
    expect(result.action).toBe('INSUFFICIENT_DATA')
    expect(result.summary).toMatch(/below the 40% floor/i)
    expect(result.source).toBe('confidence_gate')
  })

  it('treats a row with no confidence measurement as insufficient, not as zero', () => {
    const result = getRecommendation({ ticker: 'LIGHT', recommendation: { action: 'HOLD' } })
    expect(result.action).toBe('INSUFFICIENT_DATA')
    expect(result.summary).toMatch(/no data-confidence measurement/i)
  })

  it('allows monitoring language but no prescriptive action in the watch band', () => {
    const result = getRecommendation({
      ticker: 'MID', confidence: 0.5,
      recommendation: { action: 'SELL', suggested_trim_pct: 100 },
    })
    expect(result.action).toBe('WATCH')
    expect(result.suggestedTrimPct).toBe(0)
  })

  it('leaves a fund alone - ETFs are scored by a different model with no such measure', () => {
    const result = getRecommendation({
      ticker: 'VOO', is_etf: true, recommendation: { action: 'HOLD', agreement_count: 1 },
    })
    expect(result.action).toBe('HOLD')
  })

  it('downgrades a published Sell to Trim when there is no evidence the price won’t recover', () => {
    const stock = {
      ticker: 'DDD', confidence: 0.8,
      recommendation: { action: 'SELL', suggested_trim_pct: 100, agreement_count: 2 },
      analyst_target_upside: 18,
    }
    const result = getRecommendation(stock)
    expect(result.action).toBe('TRIM')
    expect(result.summary).toMatch(/downgraded from sell/i)
  })

  it('keeps a published Sell when the consensus target is at or below today’s price', () => {
    const stock = {
      ticker: 'EEE', confidence: 0.8,
      recommendation: { action: 'SELL', suggested_trim_pct: 100, agreement_count: 2, summary: 'Broken thesis.' },
      analyst_target_upside: -6,
    }
    const result = getRecommendation(stock)
    expect(result.action).toBe('SELL')
    expect(result.summary).toBe('Broken thesis.')
  })
})

describe('actionHeadline', () => {
  it('appends the share of the position only when there is one to act on', () => {
    expect(actionHeadline({ action: 'TRIM', suggestedTrimPct: 50 })).toBe('TRIM 50%')
    expect(actionHeadline({ action: 'HOLD', suggestedTrimPct: 0 })).toBe('HOLD')
  })
})

describe('positionImpact', () => {
  it('translates a percentage into shares and dollars', () => {
    const impact = positionImpact({ suggestedTrimPct: 25 }, { shares: 40, price: 100 })
    expect(impact.shares).toBe(10)
    expect(impact.proceeds).toBe(1000)
    expect(impact.remainingShares).toBe(30)
  })

  it('has nothing to say about a hold', () => {
    expect(positionImpact({ suggestedTrimPct: 0 }, { shares: 40, price: 100 })).toBeNull()
  })
})
