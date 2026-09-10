import { describe, expect, it } from 'vitest'
import {
  buildPortfolioPriceData,
  mergePortfolioQuotes,
  latestRecordedPrices,
  mergePositionSnapshots,
  mergeRecordedPrices,
  snapshotPriceRows,
  normalizePortfolioPosition,
  PER_SHARE_COST,
} from './portfolioPosition'
import { dailyMove } from './marketPresentation'

describe('buildPortfolioPriceData', () => {
  it('uses screen-universe quotes as fallback and prefers full research', () => {
    const screen = [
      { ticker: 'EXPE', price: 298.03, score: 70.4 },
      { ticker: 'CRUS', price: 120 },
    ]
    const research = [{ ticker: 'CRUS', price: 127.33, score: 84.3 }]

    const result = buildPortfolioPriceData(screen, [], research)

    expect(result.EXPE.price).toBe(298.03)
    expect(result.CRUS).toEqual(research[0])
  })
})

describe('mergePositionSnapshots', () => {
  it('uses a newer brokerage snapshot while retaining published history', () => {
    const result = mergePositionSnapshots({
      ACGL: { ticker: 'ACGL', price: 95, history: { dates: ['2026-08-13'], closes: [95] } },
    }, [{
      ticker: 'ACGL', snapshotPrice: 98.8, snapshotPreviousClose: 98.03,
      snapshotRecordedAt: '2026-08-14T18:29:00.000Z',
    }], '2026-08-14T16:00:00.000Z')

    expect(result.ACGL).toMatchObject({
      price: 98.8,
      previousClose: 98.03,
      positionSnapshot: true,
    })
    expect(result.ACGL.history.closes).toEqual([95])
  })

  it('does not replace a newer published price', () => {
    const result = mergePositionSnapshots({ ACGL: { ticker: 'ACGL', price: 101 } }, [{
      ticker: 'ACGL', snapshotPrice: 98.8, snapshotRecordedAt: '2026-08-14T18:29:00.000Z',
    }], '2026-08-15T16:00:00.000Z')

    expect(result.ACGL).toEqual({ ticker: 'ACGL', price: 101 })
  })
})

describe('mergePortfolioQuotes', () => {
  it('overlays only the price fields while preserving full research data', () => {
    const research = {
      CRUS: { ticker: 'CRUS', name: 'Cirrus Logic', price: 127.33, score: 84.3, history: { closes: [1, 2] } },
    }

    const result = mergePortfolioQuotes(research, {
      CRUS: { ticker: 'CRUS', price: 131.45, previousClose: 127.33, marketTime: '2026-08-04T15:09:19Z' },
    })

    expect(result.CRUS).toMatchObject({
      price: 131.45,
      previousClose: 127.33,
      score: 84.3,
      portfolioQuote: true,
    })
    expect(result.CRUS.history).toEqual({ closes: [1, 2] })
  })
})

describe('normalizePortfolioPosition', () => {
  it('uses the Firestore document id instead of a stale embedded id', () => {
    const { position } = normalizePortfolioPosition('real-document-id', {
      id: 'stale-id', ticker: 'AAPL', shares: 1, costBasis: 100,
    })

    expect(position.id).toBe('real-document-id')
  })

  it.each([
    ['EXPE', 0.164, 50],
    ['CRUS', 1.344, 175.67],
    ['VGT', 1.692, 200],
  ])('repairs the known legacy total-cost record for %s', (ticker, shares, totalCost) => {
    const { position, firestoreUpdates } = normalizePortfolioPosition(`${ticker}-id`, {
      ticker, shares, costBasis: totalCost,
    })

    expect(position.costBasis).toBeCloseTo(totalCost / shares)
    expect(position.costBasisUnit).toBe(PER_SHARE_COST)
    expect(position.costBasisInputMode).toBe('total')
    expect(firestoreUpdates).toMatchObject({ costBasisUnit: PER_SHARE_COST })
  })

  it('does not reinterpret unrelated or explicitly normalized positions', () => {
    const unrelated = normalizePortfolioPosition('one', {
      ticker: 'AAPL', shares: 0.5, costBasis: 200,
    })
    const normalized = normalizePortfolioPosition('two', {
      ticker: 'VGT', shares: 1.692, costBasis: 200, costBasisUnit: PER_SHARE_COST,
    })

    expect(unrelated.position.costBasis).toBe(200)
    expect(unrelated.firestoreUpdates).toBeNull()
    expect(normalized.position.costBasis).toBe(200)
    expect(normalized.firestoreUpdates).toBeNull()
  })
})

// Number(null) is 0 and Number.isFinite(0) is true, so an absent value read through a bare
// finite check becomes a real zero. A brokerage export states quantity and cost but often no
// price and never a previous close, so this is the normal case, not an edge one.
describe('mergePositionSnapshots treats absent numbers as absent, not zero', () => {
  const holding = (over = {}) => ({
    ticker: 'INTU', shares: 1.055, snapshotPrice: 369.9147,
    snapshotPreviousClose: null, snapshotRecordedAt: '2026-08-25T11:55:00.000Z', ...over,
  })

  it('leaves previousClose null when the export carries none', () => {
    const merged = mergePositionSnapshots({}, [holding()], '2026-08-24T19:38:00.000Z')

    expect(merged.INTU.previousClose).toBeNull()
    expect(merged.INTU.price).toBeCloseTo(369.9147, 6)
  })

  // The whole point of leaving it null: dailyMove derives one from published closes, but only
  // if it is genuinely absent. A zero looked present and disabled every day move instead.
  it('lets the day move fall through to published closes', () => {
    const research = [{ ticker: 'INTU', price: 370.83, history: { closes: [361.87, 367, 370.83] } }]
    const merged = mergePositionSnapshots(
      buildPortfolioPriceData([], [], research), [holding()], '2026-08-24T19:38:00.000Z',
    )

    expect(dailyMove(merged.INTU).available).toBe(true)
    expect(dailyMove(merged.INTU).previousClose).toBe(367)
  })

  it('keeps a real previous close when the export does carry one', () => {
    const merged = mergePositionSnapshots({}, [holding({ snapshotPreviousClose: 358.29 })], null)

    expect(merged.INTU.previousClose).toBeCloseTo(358.29, 6)
  })

  // A holding with no price must stay unpriced rather than render as $0.00.
  it('skips a holding whose price is absent instead of pricing it at zero', () => {
    expect(mergePositionSnapshots({}, [holding({ snapshotPrice: null })], null).INTU).toBeUndefined()
    expect(mergePositionSnapshots({}, [holding({ snapshotPrice: '' })], null).INTU).toBeUndefined()
  })
})

describe('the account\'s own recorded price history', () => {
  const snapshots = [
    {
      recordedAt: '2026-08-25T11:55:00.000Z', source: 'fidelity_positions_export',
      prices: [{ ticker: 'LULU', price: 122.78, previousClose: null }, { ticker: 'MU', price: 910 }],
    },
    {
      recordedAt: '2026-09-08T20:00:00.000Z', source: 'performance_view',
      prices: [{ ticker: 'LULU', price: 131.4, previousClose: 129 }],
    },
  ]

  describe('latestRecordedPrices', () => {
    it('takes the newest observation per ticker, by its own timestamp', () => {
      const latest = latestRecordedPrices(snapshots)
      expect(latest.LULU).toMatchObject({ price: 131.4, previousClose: 129, recordedAt: '2026-09-08T20:00:00.000Z' })
      expect(latest.MU).toMatchObject({ price: 910, recordedAt: '2026-08-25T11:55:00.000Z' })
    })

    it('is not fooled by document order — a later-applied export can carry an earlier date', () => {
      const latest = latestRecordedPrices([...snapshots].reverse())
      expect(latest.LULU.price).toBe(131.4)
    })

    it('ignores observations with no prices, and prices that are absent rather than zero', () => {
      expect(latestRecordedPrices([{ recordedAt: '2026-09-08T20:00:00.000Z', value: 100 }])).toEqual({})
      expect(latestRecordedPrices([{
        recordedAt: '2026-09-08T20:00:00.000Z', prices: [{ ticker: 'LULU', price: null }],
      }])).toEqual({})
    })

    it('survives a malformed collection rather than throwing', () => {
      expect(latestRecordedPrices()).toEqual({})
      expect(latestRecordedPrices([null, { prices: 'nope' }])).toEqual({})
    })
  })

  describe('mergeRecordedPrices', () => {
    const recorded = latestRecordedPrices(snapshots)

    it('replaces a brokerage-export seed price stamped on the position document', () => {
      const seeded = { LULU: { ticker: 'LULU', price: 122.78, positionSnapshot: true, quoteMarketTime: '2026-08-25T11:55:00.000Z' } }
      const merged = mergeRecordedPrices(seeded, recorded, '2026-08-20T00:00:00.000Z')
      expect(merged.LULU).toMatchObject({ price: 131.4, recordedPrice: true, positionSnapshot: false })
    })

    it('yields to a research price published after the last observation', () => {
      const published = { LULU: { ticker: 'LULU', price: 140, history: { closes: [1, 2] } } }
      const merged = mergeRecordedPrices(published, recorded, '2026-09-09T12:00:00.000Z')
      expect(merged.LULU.price).toBe(140)
    })

    it('beats a research price published before the last observation, keeping its metadata', () => {
      const published = { LULU: { ticker: 'LULU', name: 'Lululemon', price: 140, history: { closes: [1, 2] } } }
      const merged = mergeRecordedPrices(published, recorded, '2026-09-01T12:00:00.000Z')
      expect(merged.LULU).toMatchObject({ price: 131.4, name: 'Lululemon' })
      expect(merged.LULU.history.closes).toEqual([1, 2])
    })

    it('never overrides a live quote refresh', () => {
      const live = { LULU: { ticker: 'LULU', price: 145, portfolioQuote: true } }
      expect(mergeRecordedPrices(live, recorded, '2026-08-01T00:00:00.000Z').LULU.price).toBe(145)
    })

    it('prices a holding the research does not cover at all', () => {
      expect(mergeRecordedPrices({}, recorded, '2026-09-09T12:00:00.000Z').MU.price).toBe(910)
    })
  })

  describe('snapshotPriceRows', () => {
    it('records the per-ticker detail behind an account total', () => {
      expect(snapshotPriceRows([
        { ticker: 'lulu', shares: 1, currentPrice: 131.4, currentValue: 131.4, priceInfo: { previousClose: 129, quoteMarketTime: '2026-09-08T20:00:00.000Z' } },
        { ticker: 'NOPRICE', shares: 2, currentPrice: null },
      ], '2026-09-08T20:00:00.000Z')).toEqual([{
        ticker: 'LULU', shares: 1, price: 131.4, value: 131.4, previousClose: 129,
        marketTime: '2026-09-08T20:00:00.000Z',
      }])
    })
  })
})
