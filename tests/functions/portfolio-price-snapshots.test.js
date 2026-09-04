import { describe, expect, it, vi } from 'vitest'
import {
  buildPortfolioSnapshot,
  collectScheduledPortfolioSnapshots,
  config,
  groupPortfolioPositions,
  hasFreshAfterHoursQuote,
  hasFreshMarketQuote,
  hasFreshPreMarketQuote,
  isAfterHoursWindow,
  isHalfHourMark,
  isPreMarketWindow,
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

  it('builds an invested-only value point from portfolio quotes', () => {
    const recordedAt = new Date('2026-08-13T15:35:00.000Z')
    const snapshot = buildPortfolioSnapshot(
      [{ ticker: 'AAPL', shares: 2 }, { ticker: 'MSFT', shares: 1 }],
      {
        AAPL: { price: 230, marketTime: '2026-08-13T15:34:00.000Z' },
        MSFT: { price: 510, marketTime: '2026-08-13T15:34:00.000Z' },
      },
      recordedAt,
    )

    expect(snapshot).toMatchObject({
      value: 970,
      investedValue: 970,
      coveragePct: 100,
      source: 'scheduled_portfolio_price_refresh',
      samplingIntervalMinutes: 5,
      marketDate: '2026-08-13',
      positionCount: 2,
    })
  })

  it('records a partial snapshot when one position cannot be priced, instead of dropping the whole update', () => {
    const snapshot = buildPortfolioSnapshot(
      [{ ticker: 'AAPL', shares: 2 }, { ticker: 'FZFXX', shares: 5 }],
      { AAPL: { price: 230, marketTime: '2026-08-13T15:34:00.000Z' } },
      new Date('2026-08-13T15:35:00.000Z'),
    )
    expect(snapshot).toMatchObject({
      value: 460,
      investedValue: 460,
      coveragePct: 50,
      positionCount: 1,
      totalPositionCount: 2,
      unpricedTickers: ['FZFXX'],
    })
    expect(snapshot.prices).toEqual([
      { ticker: 'AAPL', shares: 2, price: 230, value: 460, marketTime: '2026-08-13T15:34:00.000Z' },
    ])
  })

  it('returns null only when nothing in the portfolio can be priced', () => {
    expect(buildPortfolioSnapshot(
      [{ ticker: 'AAPL', shares: 2 }, { ticker: 'MSFT', shares: 1 }],
      {},
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
      payload: { value: 460, source: 'scheduled_portfolio_price_refresh' },
      options: { merge: true },
    })
    expect(sets[1]).toMatchObject({
      ref: { path: 'portfolios/u1/tracking/state' },
      payload: { lastScheduledSnapshotCoveragePct: 100 },
    })
  })
})

describe('after-hours snapshot cadence', () => {
  it('recognizes the Yahoo post-market window and gates it to the half-hour tick', () => {
    expect(isAfterHoursWindow(new Date('2026-08-13T20:30:00.000Z'))).toBe(true) // 4:30pm ET
    expect(isAfterHoursWindow(new Date('2026-08-14T00:00:00.000Z'))).toBe(false) // 8:00pm ET, session over
    expect(isAfterHoursWindow(new Date('2026-08-15T20:30:00.000Z'))).toBe(false) // Saturday
    expect(isHalfHourMark(new Date('2026-08-13T20:30:00.000Z'))).toBe(true)
    expect(isHalfHourMark(new Date('2026-08-13T20:15:00.000Z'))).toBe(false)
  })

  it('requires a fresh post-market print, not just any regular-session timestamp', () => {
    const now = new Date('2026-08-13T20:30:00.000Z')
    expect(hasFreshAfterHoursQuote({ LULU: { postMarketTime: '2026-08-13T20:25:00.000Z' } }, now)).toBe(true)
    expect(hasFreshAfterHoursQuote({ LULU: { marketTime: '2026-08-13T15:34:00.000Z' } }, now)).toBe(false)
  })

  it('prices an after-hours snapshot from the post-market print, not the stale regular close', () => {
    const snapshot = buildPortfolioSnapshot(
      [{ ticker: 'LULU', shares: 3 }],
      { LULU: { price: 250, postMarketPrice: 245, postMarketTime: '2026-08-13T20:29:00.000Z' } },
      new Date('2026-08-13T20:30:00.000Z'),
      { session: 'after_hours' },
    )
    expect(snapshot).toMatchObject({
      value: 735,
      source: 'scheduled_portfolio_price_refresh_after_hours',
      samplingIntervalMinutes: 30,
    })
    expect(snapshot.prices).toEqual([
      { ticker: 'LULU', shares: 3, price: 245, value: 735, marketTime: '2026-08-13T20:29:00.000Z' },
    ])
  })

  it('falls back to the regular price when a held position has no post-market print', () => {
    const snapshot = buildPortfolioSnapshot(
      [{ ticker: 'VTI', shares: 2 }],
      { VTI: { price: 300, marketTime: '2026-08-13T20:00:00.000Z' } },
      new Date('2026-08-13T20:30:00.000Z'),
      { session: 'after_hours' },
    )
    expect(snapshot.prices).toEqual([
      { ticker: 'VTI', shares: 2, price: 300, value: 600, marketTime: '2026-08-13T20:00:00.000Z' },
    ])
  })

  it('skips writing outside the half-hour tick even during the after-hours window', async () => {
    const db = { collectionGroup: vi.fn() }
    const result = await collectScheduledPortfolioSnapshots({ db, now: new Date('2026-08-13T20:15:00.000Z') })
    expect(result).toEqual({ status: 'extended_hours_off_tick', recorded: 0 })
    expect(db.collectionGroup).not.toHaveBeenCalled()
  })

  it('collects an after-hours snapshot on the half-hour using the post-market print', async () => {
    const now = new Date('2026-08-13T20:30:00.000Z')
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
            data: () => ({ ticker: 'LULU', shares: 3 }),
          }],
        })),
      })),
      collection: vi.fn(() => ({ doc: () => root })),
      batch: vi.fn(() => ({
        set: (ref, payload, options) => sets.push({ ref, payload, options }),
        commit: vi.fn(async () => undefined),
      })),
    }
    const quoteFetcher = vi.fn(async () => ({
      quotes: { LULU: { price: 250, postMarketPrice: 245, postMarketTime: '2026-08-13T20:29:00.000Z' } },
      failed: [],
    }))

    const result = await collectScheduledPortfolioSnapshots({ db, quoteFetcher, now })

    expect(result).toMatchObject({ status: 'complete', recorded: 1, skipped: 0 })
    expect(sets[0]).toMatchObject({
      payload: { value: 735, source: 'scheduled_portfolio_price_refresh_after_hours', samplingIntervalMinutes: 30 },
    })
  })
})

describe('pre-market snapshot cadence', () => {
  it('recognizes the Yahoo pre-market window and gates it to the half-hour tick', () => {
    expect(isPreMarketWindow(new Date('2026-08-13T08:00:00.000Z'))).toBe(true) // 4:00am ET, session start
    expect(isPreMarketWindow(new Date('2026-08-13T12:00:00.000Z'))).toBe(true) // 8:00am ET
    expect(isPreMarketWindow(new Date('2026-08-13T13:30:00.000Z'))).toBe(false) // 9:30am ET, regular takes over
    expect(isPreMarketWindow(new Date('2026-08-13T07:45:00.000Z'))).toBe(false) // 3:45am ET, before the session
    expect(isPreMarketWindow(new Date('2026-08-15T12:00:00.000Z'))).toBe(false) // Saturday
  })

  it('requires a fresh pre-market print, not just any regular-session timestamp', () => {
    const now = new Date('2026-08-13T12:00:00.000Z')
    expect(hasFreshPreMarketQuote({ LULU: { preMarketTime: '2026-08-13T11:55:00.000Z' } }, now)).toBe(true)
    expect(hasFreshPreMarketQuote({ LULU: { marketTime: '2026-08-12T20:00:00.000Z' } }, now)).toBe(false)
  })

  it('prices a pre-market snapshot from the pre-market print, not the prior close', () => {
    const snapshot = buildPortfolioSnapshot(
      [{ ticker: 'LULU', shares: 3 }],
      { LULU: { price: 240, preMarketPrice: 244, preMarketTime: '2026-08-13T11:59:00.000Z' } },
      new Date('2026-08-13T12:00:00.000Z'),
      { session: 'pre_market' },
    )
    expect(snapshot).toMatchObject({
      value: 732,
      source: 'scheduled_portfolio_price_refresh_pre_market',
      samplingIntervalMinutes: 30,
    })
    expect(snapshot.prices).toEqual([
      { ticker: 'LULU', shares: 3, price: 244, value: 732, marketTime: '2026-08-13T11:59:00.000Z' },
    ])
  })

  it('falls back to the regular price when a held position has no pre-market print', () => {
    const snapshot = buildPortfolioSnapshot(
      [{ ticker: 'VTI', shares: 2 }],
      { VTI: { price: 300, marketTime: '2026-08-12T20:00:00.000Z' } },
      new Date('2026-08-13T12:00:00.000Z'),
      { session: 'pre_market' },
    )
    expect(snapshot.prices).toEqual([
      { ticker: 'VTI', shares: 2, price: 300, value: 600, marketTime: '2026-08-12T20:00:00.000Z' },
    ])
  })

  it('skips writing outside the half-hour tick even during the pre-market window', async () => {
    const db = { collectionGroup: vi.fn() }
    const result = await collectScheduledPortfolioSnapshots({ db, now: new Date('2026-08-13T12:15:00.000Z') })
    expect(result).toEqual({ status: 'extended_hours_off_tick', recorded: 0 })
    expect(db.collectionGroup).not.toHaveBeenCalled()
  })

  it('collects a pre-market snapshot on the half-hour using the pre-market print', async () => {
    const now = new Date('2026-08-13T12:00:00.000Z')
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
            data: () => ({ ticker: 'LULU', shares: 3 }),
          }],
        })),
      })),
      collection: vi.fn(() => ({ doc: () => root })),
      batch: vi.fn(() => ({
        set: (ref, payload, options) => sets.push({ ref, payload, options }),
        commit: vi.fn(async () => undefined),
      })),
    }
    const quoteFetcher = vi.fn(async () => ({
      quotes: { LULU: { price: 240, preMarketPrice: 244, preMarketTime: '2026-08-13T11:59:00.000Z' } },
      failed: [],
    }))

    const result = await collectScheduledPortfolioSnapshots({ db, quoteFetcher, now })

    expect(result).toMatchObject({ status: 'complete', recorded: 1, skipped: 0 })
    expect(sets[0]).toMatchObject({
      payload: { value: 732, source: 'scheduled_portfolio_price_refresh_pre_market', samplingIntervalMinutes: 30 },
    })
  })
})
