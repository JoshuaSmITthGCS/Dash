import { describe, expect, it } from 'vitest'
import { readFile } from 'node:fs/promises'
import { parseArguments, printReport } from './audit-portfolio-ledger.mjs'
import { runPortfolioAudit } from './lib/portfolio-audit.mjs'
import { REFERENCE_PORTFOLIO } from '../src/lib/referencePortfolio.js'

describe('parseArguments', () => {
  it('requires an account selector unless --help', () => {
    expect(() => parseArguments([])).toThrow(/--email/)
    expect(() => parseArguments(['--help'])).not.toThrow()
  })

  it('accepts --statement and --json', () => {
    const options = parseArguments(['--email', 'x@example.com', '--statement', 's.json', '--json'])
    expect(options.statement).toBe('s.json')
    expect(options.json).toBe(true)
  })
})

describe('printReport does not throw on real report shapes', () => {
  it('renders a clean report against the reconciled Sep 9 statement', async () => {
    const statement = JSON.parse(await readFile('scripts/fixtures/fidelity-positions-2026-09-09.json', 'utf8'))
    const { planActivityReconciliation } = await import('./lib/portfolio-reconciliation.mjs')
    const deltaFile = JSON.parse(await readFile('scripts/fixtures/fidelity-activity-since-seed.json', 'utf8'))
    const seedPositions = REFERENCE_PORTFOLIO.map((position, index) => ({
      id: `${position.ticker}-reference-${index}`, ticker: position.ticker, shares: position.shares, costBasis: position.costBasis,
      importedAt: '2026-08-25T11:55:00.000Z',
    }))
    const { positionsAfter } = planActivityReconciliation(seedPositions, deltaFile.events)
    const report = runPortfolioAudit({ positions: positionsAfter, statement })
    expect(report.ok).toBe(true)

    const logs = []
    const original = console.log
    console.log = (...args) => logs.push(args.join(' '))
    try {
      printReport(report, statement.recordedAt)
    } finally {
      console.log = original
    }
    expect(logs.join('\n')).toContain('No critical or warning findings')
  })

  it('renders a report with findings across all three severities without throwing', () => {
    const report = runPortfolioAudit({
      positions: [{ id: 'LULU-reference', ticker: 'LULU', shares: 1, importedAt: '2026-09-05T00:00:00Z' }],
      closedPositions: [{ ticker: 'LULU', closedAt: '2026-09-03T00:00:00Z' }],
      activities: [{ type: 'position_removed', ticker: 'XYZ', source: 'manual_holding_removal', recordedAt: '2026-01-01T00:00:00Z' }],
    })
    expect(report.ok).toBe(false)
    const logs = []
    const original = console.log
    console.log = (...args) => logs.push(args.join(' '))
    try {
      printReport(report, null)
    } finally {
      console.log = original
    }
    const text = logs.join('\n')
    expect(text).toContain('CRITICAL')
    expect(text).toContain('LULU')
    expect(text).toContain('resurrected_position')
  })
})
