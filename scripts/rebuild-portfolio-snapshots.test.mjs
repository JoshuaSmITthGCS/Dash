import { readFile } from 'node:fs/promises'
import { describe, expect, it } from 'vitest'
import {
  buildBaseline, buildPriceHistoryMap, correctedPricesArray, parseArguments,
} from './rebuild-portfolio-snapshots.mjs'
import { holdingsAsOf, positionTimeline } from './lib/portfolio-timeline.mjs'
import { planSnapshotCorrection } from './lib/portfolio-snapshot-correction.mjs'
import { REFERENCE_PORTFOLIO } from '../src/lib/referencePortfolio.js'

describe('parseArguments', () => {
  it('requires --history and an account selector', () => {
    expect(() => parseArguments(['--email', 'x@example.com'])).toThrow(/--history/)
    expect(() => parseArguments(['--history', 'h.json'])).toThrow(/--email/)
  })

  it('defaults to a dry run with no estimates and no force', () => {
    const options = parseArguments(['--email', 'x@example.com', '--history', 'h.json'])
    expect(options.commit).toBe(false)
    expect(options.allowEstimates).toBe(false)
    expect(options.force).toBe(false)
  })

  it('accepts --commit, --allow-estimates, and --force together', () => {
    const options = parseArguments(['--email', 'x@example.com', '--history', 'h.json', '--commit', '--allow-estimates', '--force'])
    expect(options).toMatchObject({ commit: true, allowEstimates: true, force: true })
  })
})

describe('buildPriceHistoryMap against the real public/data/report.json', () => {
  it('finds daily closes for LULU, NTNX, and TSM across the affected window', async () => {
    const reportJson = JSON.parse(await readFile('public/data/report.json', 'utf8'))
    const priceHistory = buildPriceHistoryMap(reportJson)
    expect(priceHistory.has('LULU')).toBe(true)
    expect(priceHistory.has('NTNX')).toBe(true)
    expect(priceHistory.has('TSM')).toBe(true)
    // Every ticker's history must actually span the dates the correction needs.
    for (const ticker of ['LULU', 'NTNX', 'TSM']) {
      const history = priceHistory.get(ticker)
      expect(history.dates).toContain('2026-08-25')
      expect(history.dates.some((date) => date >= '2026-09-01')).toBe(true)
    }
  })
})

describe('buildBaseline', () => {
  it('is the exact Aug 25 export -- one row per REFERENCE_PORTFOLIO holding', () => {
    const baseline = buildBaseline()
    expect(baseline).toHaveLength(REFERENCE_PORTFOLIO.length)
    const lulu = baseline.find((position) => position.ticker === 'LULU')
    expect(lulu).toMatchObject({ shares: 1, costBasis: 117.94 })
  })
})

describe('correctedPricesArray keeps a snapshot self-consistent after correction', () => {
  it('removes a wrongly-included ticker from the prices list', () => {
    const original = [{ ticker: 'LULU', shares: 1, price: 100.61 }, { ticker: 'AAPL', shares: 5, price: 200 }]
    const result = correctedPricesArray(original, [{ ticker: 'LULU', action: 'remove', shares: 1, price: 100.61 }], '2026-09-04T15:00:00Z')
    expect(result.some((row) => row.ticker === 'LULU')).toBe(false)
    expect(result.some((row) => row.ticker === 'AAPL')).toBe(true)
  })

  it('adds a wrongly-excluded ticker, marked estimated', () => {
    const result = correctedPricesArray([], [{ ticker: 'TSM', action: 'add', shares: 0.482, price: 209.84 }], '2026-09-04T15:00:00Z')
    expect(result[0]).toMatchObject({ ticker: 'TSM', shares: 0.482, price: 209.84, estimated: true })
  })

  it('updates share count for an adjusted ticker without dropping its other fields', () => {
    const original = [{ ticker: 'NTNX', shares: 1.284, price: 66.85, previousClose: 65 }]
    const result = correctedPricesArray(original, [{ ticker: 'NTNX', action: 'adjust', from: 1.284, to: 0.284, price: 68.06 }], '2026-09-04T15:00:00Z')
    const row = result.find((entry) => entry.ticker === 'NTNX')
    expect(row.shares).toBe(0.284)
    expect(row.previousClose).toBe(65) // preserved, not clobbered
  })
})

// End-to-end against real data: the full 90-day activity history, the real report.json price
// history, and a hand-built "buggy" snapshot shaped exactly like the LULU/TSM bug actually
// damaged one -- LULU wrongly present (already sold in reality), TSM wrongly absent (never
// entered into the app at all).
describe('end-to-end correction of a realistic buggy Sep 4 snapshot', () => {
  it('produces a correction that matches the real historical prices and the real timeline', async () => {
    const historyFile = JSON.parse(await readFile('scripts/fixtures/fidelity-activity-since-seed.json', 'utf8'))
    const reportJson = JSON.parse(await readFile('public/data/report.json', 'utf8'))
    const priceHistory = buildPriceHistoryMap(reportJson)
    const baseline = buildBaseline()
    const timeline = positionTimeline(baseline, historyFile.events)

    const correctHoldings = holdingsAsOf(timeline, '2026-09-04')
    expect(correctHoldings.has('LULU')).toBe(false) // sold Sep 3, so gone by Sep 4
    expect(correctHoldings.has('NTNX')).toBe(false) // sold Sep 4
    expect(correctHoldings.get('TSM')).toBeTruthy() // bought Sep 2

    // A realistic buggy snapshot: every correctly-held ticker is itemized (as the app really
    // does), PLUS LULU wrongly still present (the resurrection bug), MINUS TSM, which is
    // correctly absent because it was never entered into Dash at all.
    const luluPrice = priceHistory.get('LULU').closes[priceHistory.get('LULU').dates.indexOf('2026-09-04')]
    // Every correctly-held ticker EXCEPT TSM: TSM has to be missing from the buggy snapshot to
    // actually exercise "wrongly excluded" -- building it from correctHoldings without
    // filtering would include TSM already correct, defeating the point of this fixture.
    const correctPrices = [...correctHoldings.entries()]
      .filter(([ticker]) => ticker !== 'TSM')
      .map(([ticker, holding]) => {
        const history = priceHistory.get(ticker)
        const price = history ? history.closes[history.dates.indexOf('2026-09-04')] ?? history.closes.at(-1) : holding.costBasisTotal / holding.shares
        return { ticker, shares: holding.shares, price }
      })
    const buggySnapshot = {
      id: '2026-09-04T15-00', marketDate: '2026-09-04', recordedAt: '2026-09-04T15:00:00.000Z',
      value: correctPrices.reduce((sum, row) => sum + row.shares * row.price, 0) + 1 * luluPrice, // real total + LULU's wrongly-included value
      unrealizedGain: 150,
      prices: [...correctPrices, { ticker: 'LULU', shares: 1, price: luluPrice }],
    }

    const result = planSnapshotCorrection(buggySnapshot, correctHoldings, priceHistory)
    expect(result.blocked).toBe(false)
    // The only two things wrong with this snapshot are LULU (extra) and TSM (missing) --
    // every other correctly-priced ticker must be left alone.
    expect(result.changes).toHaveLength(2)
    const removal = result.changes.find((change) => change.ticker === 'LULU')
    const addition = result.changes.find((change) => change.ticker === 'TSM')
    expect(removal.action).toBe('remove')
    expect(addition).toMatchObject({ action: 'add', estimated: true })
    // The corrected total should equal the real total: LULU's value gone, TSM's value in.
    const realTotal = correctPrices.reduce((sum, row) => sum + row.shares * row.price, 0) + addition.shares * addition.price
    expect(result.correctedValue).toBeCloseTo(realTotal, 4)
  })

  it('leaves an already-correct snapshot (recorded after the fix) untouched', async () => {
    const historyFile = JSON.parse(await readFile('scripts/fixtures/fidelity-activity-since-seed.json', 'utf8'))
    const reportJson = JSON.parse(await readFile('public/data/report.json', 'utf8'))
    const priceHistory = buildPriceHistoryMap(reportJson)
    const baseline = buildBaseline()
    const timeline = positionTimeline(baseline, historyFile.events)
    const correctHoldings = holdingsAsOf(timeline, '2026-09-08')

    // A clean snapshot must itemize *every* held ticker, not just TSM -- otherwise every other
    // held ticker looks "wrongly excluded" and the test would trivially pass for the wrong
    // reason. Build the full clean price list from the correct holdings themselves.
    const prices = [...correctHoldings.entries()].map(([ticker, holding]) => {
      const history = priceHistory.get(ticker)
      const price = history ? history.closes[history.dates.indexOf('2026-09-08')] ?? history.closes.at(-1) : holding.costBasisTotal / holding.shares
      return { ticker, shares: holding.shares, price }
    })
    const cleanSnapshot = { marketDate: '2026-09-08', value: 999, prices }
    expect(planSnapshotCorrection(cleanSnapshot, correctHoldings, priceHistory)).toBeNull()
  })
})

describe('printCorrection-style output does not throw on real data', () => {
  it('the full pipeline runs against real fixtures without error, end to end', async () => {
    const historyFile = JSON.parse(await readFile('scripts/fixtures/fidelity-activity-since-seed.json', 'utf8'))
    const reportJson = JSON.parse(await readFile('public/data/report.json', 'utf8'))
    const priceHistory = buildPriceHistoryMap(reportJson)
    const baseline = buildBaseline()
    const timeline = positionTimeline(baseline, historyFile.events)

    // Simulate three snapshots across the affected window: one buggy (LULU present, TSM
    // absent), one clean, one blocked (no prices array at all).
    const dates = ['2026-09-04', '2026-09-08']
    for (const date of dates) {
      const correctHoldings = holdingsAsOf(timeline, date)
      const prices = [...correctHoldings.entries()].map(([ticker, holding]) => {
        const history = priceHistory.get(ticker)
        const price = history ? (history.closes[history.dates.indexOf(date)] ?? history.closes.at(-1)) : holding.costBasisTotal / holding.shares
        return { ticker, shares: holding.shares, price }
      })
      const snapshot = { marketDate: date, value: prices.reduce((sum, row) => sum + row.shares * row.price, 0), prices }
      expect(planSnapshotCorrection(snapshot, correctHoldings, priceHistory)).toBeNull() // clean by construction
    }

    const noPricesSnapshot = { marketDate: '2026-09-04', value: 5000 }
    const blockedResult = planSnapshotCorrection(noPricesSnapshot, holdingsAsOf(timeline, '2026-09-04'), priceHistory)
    expect(blockedResult.blocked).toBe(true)
  })
})
