import { describe, expect, it } from 'vitest'
import { buildStockCopyText } from './stockCopyText.js'

const baseStock = {
  ticker: 'SAM', name: 'Boston Beer Company', sector: 'Consumer Staples', industry: 'Brewers',
  score: 73, stance: 'hold', data_coverage: 0.74, price: 250.5,
  technical_detail: { return_20d: -0.4 },
  peg: 1.8, forward_pe: 22.3, return_on_invested_capital: 0.14,
}

describe('buildStockCopyText', () => {
  it('returns an empty string without a ticker', () => {
    expect(buildStockCopyText(null)).toBe('')
    expect(buildStockCopyText({})).toBe('')
  })

  it('opens with identity, score, and coverage', () => {
    const text = buildStockCopyText(baseStock)
    expect(text).toContain('SAM — Boston Beer Company')
    expect(text).toContain('Brewers')
    expect(text).toContain('Research score: 73 (hold)')
    expect(text).toContain('Data coverage: 74%')
    expect(text).toContain('Price: $250.50')
    expect(text).toContain('20-day move: -0.4%')
  })

  it('says the score is unpublished rather than printing a blank', () => {
    const text = buildStockCopyText({ ticker: 'IBM', name: 'IBM' })
    expect(text).toContain('Research score: not published')
  })

  it('includes every resolved metric, grouped under its section', () => {
    const text = buildStockCopyText(baseStock)
    expect(text).toContain('VALUATION')
    expect(text).toContain('PEG: 1.80')
    expect(text).toContain('Forward P/E: 22.30')
    expect(text).toContain('PROFITABILITY & CASH')
    expect(text).toContain('ROIC: 14.0%')
  })

  it('omits a metric the resolver would not show (suppressed/replaced/unavailable/unresolved)', () => {
    const text = buildStockCopyText({
      ticker: 'X', name: 'X Corp', score: 50,
      analysis_v2: { metric_status: { peg: { status: 'suppressed' } } },
      peg: 1.8, forward_pe: null,
    })
    expect(text).not.toContain('PEG:')
    expect(text).not.toContain('Forward P/E:')
  })

  it('includes insider activity only once real filings were reviewed', () => {
    const withInsider = buildStockCopyText({
      ticker: 'X', name: 'X Corp', score: 50,
      insider_activity: { records_reviewed: 4, recent_acquisitions: 3, recent_disposals: 1 },
    })
    expect(withInsider).toContain('INSIDER ACTIVITY (Form 4)')
    expect(withInsider).toContain('3 buys · 1 sell (4 filings reviewed)')

    const withoutInsider = buildStockCopyText({ ticker: 'X', name: 'X Corp', score: 50 })
    expect(withoutInsider).not.toContain('INSIDER ACTIVITY')
  })

  it('includes disclosed positioning only when a screen entry is passed in', () => {
    const stock = { ticker: 'X', name: 'X Corp', score: 50 }
    const withInfo = buildStockCopyText(stock, {
      institutional_flag: 'CLUSTER_ACCUMULATION',
      congress_flags: ['CLUSTER_TRADE'],
      score: 2.4,
    })
    expect(withInfo).toContain('DISCLOSED POSITIONING (Congress / institutional)')
    expect(withInfo).toContain('Curated managers accumulating')
    expect(withInfo).toContain('3+ representatives, 14-day span')
    expect(withInfo).toContain('Combined score: 2.40')

    const withoutInfo = buildStockCopyText(stock)
    expect(withoutInfo).not.toContain('DISCLOSED POSITIONING')
  })

  it('includes strengths and risks when published', () => {
    const text = buildStockCopyText({
      ticker: 'X', name: 'X Corp', score: 50,
      strengths: ['Strong balance sheet'], risks: ['Customer concentration'],
    })
    expect(text).toContain('EVIDENCE FOR')
    expect(text).toContain('+ Strong balance sheet')
    expect(text).toContain('RISKS / GAPS')
    expect(text).toContain('- Customer concentration')
  })

  it('never throws on a bare row with nothing published beyond a ticker', () => {
    expect(() => buildStockCopyText({ ticker: 'ZZZ' })).not.toThrow()
  })
})
