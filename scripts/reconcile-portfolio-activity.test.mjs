import { readFile } from 'node:fs/promises'
import { describe, expect, it } from 'vitest'
import { parseArguments } from './reconcile-portfolio-activity.mjs'
import { planActivityReconciliation } from './lib/portfolio-reconciliation.mjs'
import { diffAgainstStatement } from './lib/portfolio-audit.mjs'
import { REFERENCE_PORTFOLIO } from '../src/lib/referencePortfolio.js'

describe('parseArguments', () => {
  it('requires --input', () => {
    expect(() => parseArguments(['--email', 'x@example.com'])).toThrow(/--input/)
  })

  it('requires an account selector', () => {
    expect(() => parseArguments(['--input', 'events.json'])).toThrow(/--email/)
  })

  it('defaults to a dry run', () => {
    const options = parseArguments(['--email', 'x@example.com', '--input', 'events.json'])
    expect(options.commit).toBe(false)
  })

  it('accepts --verify alongside --commit', () => {
    const options = parseArguments(['--email', 'x@example.com', '--input', 'e.json', '--commit', '--verify', 's.json'])
    expect(options.commit).toBe(true)
    expect(options.verify).toBe('s.json')
  })
})

// End-to-end against the real committed fixtures: the since-seed delta applied to the Aug 25
// REFERENCE_PORTFOLIO should reproduce exactly what the Sep 9 Positions page shows. This is
// the acceptance check from docs/PLAN-TRADE-LEDGER.md WP2, run here without any Firestore
// credentials by treating REFERENCE_PORTFOLIO as the starting "stored positions".
describe('the since-seed fixture reproduces the Sep 9 statement, starting from the Aug 25 seed', () => {
  it('planned positions match every ticker, share count, and cost basis in the Sep 9 statement', async () => {
    const seedPositions = REFERENCE_PORTFOLIO.map((position, index) => ({
      id: `${position.ticker}-reference-${index}`,
      ticker: position.ticker,
      shares: position.shares,
      costBasis: position.costBasis,
      purchaseDate: position.purchaseDate,
    }))
    const deltaFile = JSON.parse(await readFile('scripts/fixtures/fidelity-activity-since-seed.json', 'utf8'))
    const statement = JSON.parse(await readFile('scripts/fixtures/fidelity-positions-2026-09-09.json', 'utf8'))

    const { errors, positionsAfter } = planActivityReconciliation(seedPositions, deltaFile.events)
    expect(errors).toEqual([])

    const findings = diffAgainstStatement(positionsAfter, statement)
    expect(findings).toEqual([])
  })

  it('the plan\'s total realized gain matches the fixture\'s stated total', async () => {
    const seedPositions = REFERENCE_PORTFOLIO.map((position, index) => ({
      id: `${position.ticker}-reference-${index}`, ticker: position.ticker, shares: position.shares, costBasis: position.costBasis,
    }))
    const deltaFile = JSON.parse(await readFile('scripts/fixtures/fidelity-activity-since-seed.json', 'utf8'))
    const { writes } = planActivityReconciliation(seedPositions, deltaFile.events)
    const total = writes.filter((write) => write.data?.type === 'realized_gain').reduce((sum, write) => sum + write.data.amount, 0)
    expect(total).toBeCloseTo(21.59, 1)
  })

  it('is fully idempotent: re-planning against the post-reconciliation activity ids writes nothing', async () => {
    const seedPositions = REFERENCE_PORTFOLIO.map((position, index) => ({
      id: `${position.ticker}-reference-${index}`, ticker: position.ticker, shares: position.shares, costBasis: position.costBasis,
    }))
    const deltaFile = JSON.parse(await readFile('scripts/fixtures/fidelity-activity-since-seed.json', 'utf8'))
    const first = planActivityReconciliation(seedPositions, deltaFile.events)
    const existingActivityIds = new Set(first.writes.filter((write) => write.collection === 'activity').map((write) => write.id))
    const second = planActivityReconciliation(seedPositions, deltaFile.events, { existingActivityIds })
    expect(second.writes).toEqual([])
  })
})

describe('printPlan formatting does not throw on real write shapes', () => {
  it('renders a plan built from the real since-seed fixture without error', async () => {
    const { planActivityReconciliation: plan } = await import('./lib/portfolio-reconciliation.mjs')
    const { printPlan } = await import('./reconcile-portfolio-activity.mjs')
    const deltaFile = JSON.parse(await readFile('scripts/fixtures/fidelity-activity-since-seed.json', 'utf8'))
    const seedPositions = REFERENCE_PORTFOLIO.map((position, index) => ({
      id: `${position.ticker}-reference-${index}`, ticker: position.ticker, shares: position.shares, costBasis: position.costBasis,
    }))
    const result = plan(seedPositions, deltaFile.events)
    const logs = []
    const spy = (...args) => logs.push(args.join(' '))
    const original = console.log
    console.log = spy
    try {
      printPlan(result)
    } finally {
      console.log = original
    }
    expect(logs.join('\n')).toContain('LULU')
    expect(logs.join('\n')).toContain('NTNX')
    expect(logs.join('\n')).toContain('TSM')
    expect(logs.join('\n')).toContain('Total realized gain/loss')
  })

  it('renders cleanly when there is nothing to plan', async () => {
    const { printPlan } = await import('./reconcile-portfolio-activity.mjs')
    const logs = []
    const original = console.log
    console.log = (...args) => logs.push(args.join(' '))
    try {
      printPlan({ writes: [], errors: [], skipped: [], summary: { skipped: 0 } })
    } finally {
      console.log = original
    }
    expect(logs.join('\n')).toContain('Plan: 0 buy')
  })
})
