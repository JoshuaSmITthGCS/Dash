import { describe, expect, it, vi } from 'vitest'
import {
  buildPortfolioSnapshot,
  collectScheduledPortfolioSnapshots,
  config,
  groupPortfolioPositions,
  hasFreshMarketQuote,
  isRegularMarketWindow,
  marketDate,
} from '../../netlify/functions/portfolio-price-snapshots.mjs'

describe('scheduled portfolio price snapshots', () => {
  it('is deployed on an exact five-minute cron', () => {
    expect(config).toEqual({ schedule: '*/5 * * * *' })
  })

  it('recognizes the regular New York market window across UTC offsets', () => {
    expect(isRegularMarketWindow(new Date('2026-08-13T13:30:00.000Z'))).toBe(true)
    expect(isRegularMarketWindow(new Date('2026-08-13T20:00:00.000Z'))).toBe(false)
    expect(isRegularMarketWindow(new Date('2026-08-15T15:00:00.000Z'))).toBe(false)
    expect(marketDate(new Date('2026-08-14T01:00:00.000Z'))).toBe('2026-08-13')
  })

  it('groups duplicate holdings per user and rejects invalid positions', () => {
    expect(groupPortfolioPositions([
      { uid: 'u1', ticker: ' aapl ', shares: 2 },
      { uid: 'u1', ticker: 'AAPL', shares: 1.5 },
      { uid: 'u2', ticker: 'MSFT', shares: 4 },
      { uid: 'u2', ticker: '$BAD', shares: 2 },
      { uid: 'u3', ticker: 'SPY', shares: 0 },
    ])).toEqual({
      u1: [{ ticker: 'AAPL', shares: 3.5 }],
      u2: [{ ticker: 'MSFT', shares: 4 }],
    })
  })

  it('builds an account-value point from only portfolio quotes and tracked cash', () => {
    const recordedAt = new Date('2026-08-13T15:35:00.000Z')
    const snapshot = buildPortfolioSnapshot(
      [{ ticker: 'AAPL', shares: 2 }, { ticker: 'MSFT', shares: 1 }],
      {
        AAPL: { price: 230, marketTime: '2026-08-13T15:34:00.000Z' },
        MSFT: { price: 510, marketTime: '2026-08-13T15:34:00.000Z' },
      },
      25,
      recordedAt,
    )

    expect(snapshot).toMatchObject({
      value: 995,
      investedValue: 970,
      cashValue: 25,
      coveragePct: 100,
      source: 'scheduled_portfolio_price_refresh',
      samplingIntervalMinutes: 5,
      marketDate: '2026-08-13',
      positionCount: 2,
    })
  })

  it('does not store a misleading partial portfolio value', () => {
    expect(buildPortfolioSnapshot(
      [{ ticker: 'AAPL', shares: 2 }, { ticker: 'MSFT', shares: 1 }],
      { AAPL: { price: 230 } },
      0,
      new Date('2026-08-13T15:35:00.000Z'),
    )).toBeNull()
  })

  it('requires at least one current market-tape timestamp before writing', () => {
    const now = new Date('2026-08-13T15:35:00.000Z')
    expect(hasFreshMarketQuote({ AAPL: { marketTime: '2026-08-13T15:34:00.000Z' } }, now)).toBe(true)
    expect(hasFreshMarketQuote({ AAPL: { marketTime: '2026-08-12T20:00:00.000Z' } }, now)).toBe(false)
  })

  it('writes the server-owned snapshot and tracking heartbeat for each complete portfolio', async () => {
    const now = new Date('2026-08-13T15:35:00.000Z')
    const userRef = { id: 'u1', parent: { id: 'portfolios' } }
    const sets = []
    const makeDocument = (path) => ({ path })
    const root = {
      collection: (name) => ({ doc: (id) => makeDocument(`portfolios/u1/${name}/${id}`) }),
    }
    const db = {
      collectionGroup: vi.fn(() => ({
        get: vi.fn(async () => ({
          docs: [{
            ref: { parent: { parent: userRef } },
            data: () => ({ ticker: 'AAPL', shares: 2 }),
          }],
        })),
      })),
      collection: vi.fn(() => ({ doc: () => root })),
      getAll: vi.fn(async () => [{
        exists: true,
        data: () => ({ cashTrackingEnabled: true, cashBalance: 40 }),
      }]),
      batch: vi.fn(() => ({
        set: (ref, payload, options) => sets.push({ ref, payload, options }),
        commit: vi.fn(async () => undefined),
      })),
    }
    const quoteFetcher = vi.fn(async () => ({
      quotes: { AAPL: { price: 230, marketTime: '2026-08-13T15:34:00.000Z' } },
      failed: [],
    }))

    const result = await collectScheduledPortfolioSnapshots({ db, quoteFetcher, now })

    expect(result).toMatchObject({ status: 'complete', recorded: 1, skipped: 0 })
    expect(quoteFetcher).toHaveBeenCalledWith(['AAPL'])
    expect(sets).toHaveLength(2)
    expect(sets[0]).toMatchObject({
      ref: { path: 'portfolios/u1/intradaySnapshots/2026-08-13T15-35' },
      payload: { value: 500, source: 'scheduled_portfolio_price_refresh' },
      options: { merge: true },
    })
    expect(sets[1]).toMatchObject({
      ref: { path: 'portfolios/u1/tracking/state' },
      payload: { lastScheduledSnapshotCoveragePct: 100 },
    })
  })
})
