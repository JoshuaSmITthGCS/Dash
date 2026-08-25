import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import {
  buildPortfolioExport,
  parsePortfolioImport,
  planPortfolioImport,
} from './portfolioImport'
import { REFERENCE_PORTFOLIO } from './referencePortfolio'

const file = (positions, extra = {}) => JSON.stringify({ schemaVersion: 1, positions, ...extra })
const holding = (over = {}) => ({ ticker: 'AMZN', shares: 0.386, costBasisTotal: 99.79, purchaseDate: '2026-08-21', ...over })

describe('parsePortfolioImport', () => {
  it('reads a well-formed file and totals it', () => {
    const parsed = parsePortfolioImport(file([holding(), holding({ ticker: 'DELL', costBasisTotal: 100 })]))

    expect(parsed.ok).toBe(true)
    expect(parsed.positions.map((row) => row.ticker)).toEqual(['AMZN', 'DELL'])
    expect(parsed.meta.costBasisTotal).toBeCloseTo(199.79, 8)
  })

  it('accepts a bare array as well as a wrapped object', () => {
    expect(parsePortfolioImport(JSON.stringify([holding()])).ok).toBe(true)
  })

  // Brokerage exports disagree about whether cost is per share or a total, so both are read
  // and the other is derived rather than demanded.
  it('takes cost per share or as a total', () => {
    const perShare = parsePortfolioImport(file([{ ticker: 'AAA', shares: 4, costBasis: 25 }]))
    const total = parsePortfolioImport(file([{ ticker: 'AAA', shares: 4, costBasisTotal: 100 }]))

    expect(perShare.positions[0]).toMatchObject({ costBasis: 25, costBasisTotal: 100 })
    expect(total.positions[0]).toMatchObject({ costBasis: 25, costBasisTotal: 100 })
  })

  it('reports every problem at once instead of only the first', () => {
    const parsed = parsePortfolioImport(file([
      { shares: 1, costBasisTotal: 10 },
      { ticker: 'BBB', shares: -2, costBasisTotal: 10 },
      { ticker: 'CCC', shares: 1 },
      { ticker: 'DDD', shares: 1, costBasisTotal: 10, purchaseDate: '08/21/2026' },
    ]))

    expect(parsed.ok).toBe(false)
    expect(parsed.errors).toHaveLength(4)
    expect(parsed.errors[0]).toMatch(/row 1: no ticker/)
    expect(parsed.errors[1]).toMatch(/greater than zero/)
    expect(parsed.errors[2]).toMatch(/needs costBasisTotal or costBasis/)
    expect(parsed.errors[3]).toMatch(/is not YYYY-MM-DD/)
  })

  // Two rows for one ticker disagree about a single holding; keeping either would import a
  // portfolio the file does not describe.
  it('refuses a repeated ticker rather than picking one', () => {
    const parsed = parsePortfolioImport(file([holding(), holding({ shares: 99 })]))

    expect(parsed.ok).toBe(false)
    expect(parsed.errors.join(' ')).toMatch(/Repeated ticker: AMZN/)
  })

  it('rejects a file that is not JSON, or carries no holdings', () => {
    expect(parsePortfolioImport('{oops').errors[0]).toMatch(/Not valid JSON/)
    expect(parsePortfolioImport('{"positions":[]}').errors[0]).toMatch(/no holdings/)
    expect(parsePortfolioImport('{"holdings":[]}').errors[0]).toMatch(/Expected a JSON array/)
  })

  it('warns about undated holdings without failing them', () => {
    const parsed = parsePortfolioImport(file([holding({ purchaseDate: '' })]))

    expect(parsed.ok).toBe(true)
    expect(parsed.warnings[0]).toMatch(/No purchase date on AMZN/)
  })

  // Quantity-derived and stale by construction: a value left over from an earlier import
  // would keep rendering old dollars until a live quote arrived, reading as a failed save.
  it('nulls the snapshot pair when the file states no price', () => {
    const parsed = parsePortfolioImport(file([{ ticker: 'AAA', shares: 2, costBasisTotal: 10 }]))

    expect(parsed.positions[0].snapshotPrice).toBeNull()
    expect(parsed.positions[0].snapshotValue).toBeNull()
  })

  it('derives a market value from price and quantity when only price is given', () => {
    const parsed = parsePortfolioImport(file([{ ticker: 'AAA', shares: 2, costBasisTotal: 10, price: 12.5 }]))

    expect(parsed.positions[0].snapshotValue).toBeCloseTo(25, 8)
  })
})

describe('planPortfolioImport', () => {
  const stored = [
    { id: 'amzn-1', ticker: 'AMZN', shares: 0.2, costBasis: 250, purchaseDate: '2026-08-21' },
    { id: 'old-1', ticker: 'ZZZZ', shares: 5, costBasis: 3 },
  ]

  it('treats the file as the whole portfolio in replace mode', () => {
    const operations = planPortfolioImport(stored, parsePortfolioImport(file([holding()])), 'replace')

    expect(operations.map((row) => row.kind)).toEqual(['update', 'remove'])
    expect(operations[1].record.ticker).toBe('ZZZZ')
  })

  it('never removes in merge mode', () => {
    const operations = planPortfolioImport(stored, parsePortfolioImport(file([holding()])), 'merge')

    expect(operations.map((row) => row.kind)).toEqual(['update'])
  })

  it('plans nothing from a file that failed validation', () => {
    expect(planPortfolioImport(stored, parsePortfolioImport('{oops'), 'replace')).toEqual([])
  })

  // A date already stored wins, so importing a file that omits dates cannot erase them.
  it('keeps a stored purchase date the file does not carry', () => {
    const [operation] = planPortfolioImport(
      [{ id: 'a', ticker: 'AAA', shares: 1, costBasis: 5, purchaseDate: '2026-01-02' }],
      parsePortfolioImport(file([{ ticker: 'AAA', shares: 2, costBasisTotal: 20 }])),
      'merge',
    )

    expect(operation.record.purchaseDate).toBe('2026-01-02')
    expect(operation.record.shares).toBe(2)
  })
})

describe('export/import round trip', () => {
  it('reads back a file this app produced', () => {
    const parsed = parsePortfolioImport(JSON.stringify(buildPortfolioExport(REFERENCE_PORTFOLIO)))

    expect(parsed.ok).toBe(true)
    expect(parsed.meta.count).toBe(REFERENCE_PORTFOLIO.length)
    expect(parsed.meta.costBasisTotal).toBeCloseTo(5549.26, 8)
    expect(parsed.meta.marketValue).toBeCloseTo(5668.16, 8)
  })

  // The file served at /holdings/ for upload. If it ever stops matching the baseline or stops
  // parsing, uploading it would quietly write the wrong portfolio.
  it('ships a holdings file that parses and matches the baseline', () => {
    const parsed = parsePortfolioImport(readFileSync('public/holdings/fidelity-2026-08-25.json', 'utf8'))

    expect(parsed.ok).toBe(true)
    expect(parsed.meta.count).toBe(46)
    expect(parsed.meta.costBasisTotal).toBeCloseTo(5549.26, 8)
    expect(parsed.meta.marketValue).toBeCloseTo(5668.16, 8)
    expect(planPortfolioImport(REFERENCE_PORTFOLIO.map((position, index) => ({
      ...position, id: `${position.ticker}-${index}`,
    })), parsed, 'replace').filter((operation) => operation.kind !== 'update')).toEqual([])
  })
})
