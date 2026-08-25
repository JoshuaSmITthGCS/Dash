import { describe as group, expect, it } from 'vitest'
import { describe, parseArguments } from './sync-portfolio-firebase.mjs'
import {
  planReferencePortfolioSync,
  referenceIntradaySnapshot,
  referenceSyncRecord,
  referenceTrackingState,
  summarizeReferenceSync,
  REFERENCE_PORTFOLIO,
  REFERENCE_PORTFOLIO_RECORDED_AT,
  REFERENCE_PORTFOLIO_VERSION,
} from '../src/lib/referencePortfolio.js'

group('sync-portfolio-firebase arguments', () => {
  it('requires an account to be named', () => {
    expect(() => parseArguments([])).toThrow(/--email <address> or --uid/)
  })

  it('rejects naming the account twice', () => {
    expect(() => parseArguments(['--email', 'a@b.c', '--uid', 'x'])).toThrow(/not both/)
  })

  it('rejects an unknown flag rather than ignoring it', () => {
    expect(() => parseArguments(['--uid', 'x', '--dry-run'])).toThrow(/Unrecognized argument: --dry-run/)
  })

  // Dry run is the default because this import deletes holdings absent from the export.
  it('does not commit unless asked', () => {
    expect(parseArguments(['--uid', 'x'])).toMatchObject({ uid: 'x', commit: false })
    expect(parseArguments(['--uid', 'x', '--commit']).commit).toBe(true)
  })
})

group('sync-portfolio-firebase plan output', () => {
  it('marks each operation and carries the acquisition date', () => {
    const output = describe(planReferencePortfolioSync(
      [{ id: 'old', ticker: 'ZZZZ', shares: 1, costBasis: 5 }],
      [
        { ticker: 'AMZN', shares: 0.386, costBasis: 258.52, costBasisTotal: 99.79, purchaseDate: '2026-08-21' },
        { ticker: 'VOO', shares: 0.146, costBasis: 633.36, costBasisTotal: 92.47, purchaseDate: null },
      ],
    ))

    expect(output).toContain('+ AMZN')
    expect(output).toContain('2026-08-21')
    expect(output).toContain('$99.79')
    expect(output).toContain('undated') // VOO has no buy in the history
    expect(output).toContain('- ZZZZ   removed (not in the export)')
  })
})

// The CLI and the in-app sync write to the same collection, so they must produce identical
// documents. These builders are the single definition both call.
group('shared reference sync records', () => {
  it('stamps an add with importedAt and an update with syncedAt', () => {
    const at = '2026-08-25T12:00:00.000Z'
    const [add] = planReferencePortfolioSync([], [{ ticker: 'AMZN', shares: 1, costBasis: 2, purchaseDate: '2026-08-21' }])
    const [update] = planReferencePortfolioSync(
      [{ id: 'amzn-1', ticker: 'AMZN', shares: 9, costBasis: 9 }],
      [{ ticker: 'AMZN', shares: 1, costBasis: 2, purchaseDate: '2026-08-21' }],
    )

    expect(referenceSyncRecord(add, at)).toMatchObject({ id: 'AMZN-reference', importedAt: at, purchaseDate: '2026-08-21' })
    expect(referenceSyncRecord(add, at).syncedAt).toBeUndefined()
    expect(referenceSyncRecord(update, at)).toMatchObject({ syncedAt: at, shares: 1 })
  })

  it('builds an invested-only snapshot that matches the export totals', () => {
    const { id, document } = referenceIntradaySnapshot()

    expect(id).toBe('2026-08-25T11-55')
    expect(document.recordedAt).toBe(REFERENCE_PORTFOLIO_RECORDED_AT)
    expect(document.positionCount).toBe(REFERENCE_PORTFOLIO.length)
    expect(document.investedValue).toBeCloseTo(5668.16, 8)
    expect(document.prices).toHaveLength(REFERENCE_PORTFOLIO.length)
    expect(document.prices.some((row) => ['FZFXX', 'Pending activity'].includes(row.ticker))).toBe(false)
  })

  // Firestore rejects undefined, so an absent previous close has to reach it as null.
  it('carries a null previous close rather than an undefined one', () => {
    referenceIntradaySnapshot().document.prices.forEach((row) => {
      expect(row.previousClose).toBeNull()
    })
  })

  it('marks the account against the version that produced the write', () => {
    expect(referenceTrackingState('2026-08-25T12:00:00.000Z')).toEqual({
      referencePortfolioVersion: REFERENCE_PORTFOLIO_VERSION,
      referencePortfolioImportedAt: '2026-08-25T12:00:00.000Z',
    })
  })

  it('counts a plan the way both callers report it', () => {
    expect(summarizeReferenceSync(planReferencePortfolioSync(
      [{ id: 'gone', ticker: 'ZZZZ', shares: 1 }, { id: 'amzn', ticker: 'AMZN', shares: 1 }],
      [{ ticker: 'AMZN', shares: 2 }, { ticker: 'DELL', shares: 1 }],
    ))).toEqual({ added: 1, updated: 1, removed: 1 })
  })
})
