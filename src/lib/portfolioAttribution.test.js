import { describe, expect, it } from 'vitest'
import { ATTRIBUTION_PERIODS, explainPortfolioMove } from './portfolioAttribution.js'

const benchmarkHistory = { closes: [500, 505] } // +1% today

const position = (ticker, overrides = {}) => ({
  ticker, name: `${ticker} Inc`, allocationPct: 50,
  priceInfo: {
    sector: 'Technology',
    history: { closes: [100, 102] }, // +2% today
    technical_detail: { beta: 1.2 },
  },
  ...overrides,
})

describe('portfolio move attribution', () => {
  it('is unavailable without a benchmark price history', () => {
    const result = explainPortfolioMove([position('AAPL')], null)
    expect(result.available).toBe(false)
    expect(result.reason).toMatch(/benchmark/i)
  })

  it('splits each holding into a market component and an idiosyncratic component', () => {
    const result = explainPortfolioMove([position('AAPL')], benchmarkHistory)
    const [holding] = result.holdings

    // weight 0.5, dailyReturn 2%, beta 1.2, benchmark 1% -> market = 0.5*1.2*1 = 0.6
    expect(holding.marketComponentPct).toBeCloseTo(0.6, 6)
    // contribution = 0.5 * 2 = 1.0; idiosyncratic = 1.0 - 0.6 = 0.4
    expect(holding.contributionPct).toBeCloseTo(1.0, 6)
    expect(holding.idiosyncraticComponentPct).toBeCloseTo(0.4, 6)
  })

  it('market plus idiosyncratic always reconciles exactly to total return', () => {
    const positions = [
      position('AAPL', { allocationPct: 30 }),
      position('MSFT', { allocationPct: 70, priceInfo: { sector: 'Technology', history: { closes: [200, 198] }, technical_detail: { beta: 0.8 } } }),
    ]
    const result = explainPortfolioMove(positions, benchmarkHistory)

    expect(result.reconciles).toBe(true)
    expect(result.marketPct + result.idiosyncraticPct).toBeCloseTo(result.totalReturnPct, 9)
  })

  it('assumes a beta of 1 and flags it when a holding has no computed beta', () => {
    const noBeta = position('NEWCO', { priceInfo: { sector: 'Technology', history: { closes: [50, 51] } } })
    const result = explainPortfolioMove([noBeta], benchmarkHistory)

    expect(result.holdings[0].beta).toBe(1)
    expect(result.holdings[0].betaIsAssumed).toBe(true)
  })

  it('ranks top contributors and top detractors separately', () => {
    const winner = position('WIN', { allocationPct: 50, priceInfo: { sector: 'Technology', history: { closes: [100, 110] }, technical_detail: { beta: 1 } } })
    const loser = position('LOSE', { allocationPct: 50, priceInfo: { sector: 'Energy', history: { closes: [100, 90] }, technical_detail: { beta: 1 } } })

    const result = explainPortfolioMove([winner, loser], benchmarkHistory)

    expect(result.topContributors[0].ticker).toBe('WIN')
    expect(result.topDetractors[0].ticker).toBe('LOSE')
  })

  it('groups the idiosyncratic component by sector without claiming a market sector benchmark', () => {
    const tech = position('T1', { allocationPct: 50, priceInfo: { sector: 'Technology', history: { closes: [100, 105] }, technical_detail: { beta: 1 } } })
    const energy = position('E1', { allocationPct: 50, priceInfo: { sector: 'Energy', history: { closes: [100, 95] }, technical_detail: { beta: 1 } } })

    const result = explainPortfolioMove([tech, energy], benchmarkHistory)

    const sectors = result.sectorBreakdown.map((entry) => entry.sector)
    expect(sectors).toContain('Technology')
    expect(sectors).toContain('Energy')
  })

  it('does not claim catalyst attribution that has not been built yet', () => {
    const result = explainPortfolioMove([position('AAPL')], benchmarkHistory)
    expect(result.catalysts).toEqual([])
    expect(result.catalystStatus).toBe('not_available_this_phase')
  })

  it('excludes a holding with no price history from the totals but still lists it as unpriced', () => {
    const noHistory = position('HALTED', { priceInfo: { sector: 'Technology', history: { closes: [] }, technical_detail: { beta: 1 } } })
    const result = explainPortfolioMove([noHistory], benchmarkHistory)

    expect(result.totalReturnPct).toBe(0)
    expect(result.unpriced).toEqual(['HALTED'])
  })

  it('ignores positions with no allocation (fully exited or zero-value)', () => {
    const zeroWeight = position('GONE', { allocationPct: 0 })
    const result = explainPortfolioMove([zeroWeight], benchmarkHistory)
    expect(result.holdings).toEqual([])
  })

  it('prefers a live quote over the stale pipeline snapshot for a holdings daily return', () => {
    // history.closes says +2% (the pipeline's last refresh); the live quote says +5% today.
    const live = position('AAPL', {
      priceInfo: {
        sector: 'Technology', history: { closes: [100, 102] }, technical_detail: { beta: 1.2 },
        portfolioQuote: true, price: 105, previousClose: 100,
      },
    })
    const result = explainPortfolioMove([live], benchmarkHistory)
    expect(result.holdings[0].dailyReturnPct).toBeCloseTo(5, 6)
  })

  it('falls back to history.closes when no live quote has been fetched for that symbol', () => {
    const result = explainPortfolioMove([position('AAPL')], benchmarkHistory)
    expect(result.holdings[0].dailyReturnPct).toBeCloseTo(2, 6)
  })

  it('ignores a stale previousClose left over on a row that is not actually a live quote', () => {
    // portfolioQuote is unset -- previousClose here must never be treated as live.
    const notLive = position('AAPL', {
      priceInfo: {
        sector: 'Technology', history: { closes: [100, 102] }, technical_detail: { beta: 1.2 },
        price: 105, previousClose: 100,
      },
    })
    const result = explainPortfolioMove([notLive], benchmarkHistory)
    expect(result.holdings[0].dailyReturnPct).toBeCloseTo(2, 6)
  })

  it('prefers a live benchmark quote over the stale benchmark history', () => {
    const result = explainPortfolioMove([position('AAPL')], benchmarkHistory, {
      benchmarkQuote: { portfolioQuote: true, price: 510, previousClose: 500 },
    })
    // benchmarkHistory alone would give +1%; the live SPY quote says +2%.
    expect(result.benchmarkReturnPct).toBeCloseTo(2, 6)
  })

  it('still reconciles exactly when both holdings and the benchmark use live quotes', () => {
    const live = position('AAPL', {
      priceInfo: {
        sector: 'Technology', history: { closes: [100, 102] }, technical_detail: { beta: 1.2 },
        portfolioQuote: true, price: 108, previousClose: 100,
      },
    })
    const result = explainPortfolioMove([live], benchmarkHistory, {
      benchmarkQuote: { portfolioQuote: true, price: 515, previousClose: 500 },
    })
    expect(result.reconciles).toBe(true)
  })
})

const DAY_MS = 24 * 60 * 60 * 1000
const END_DATE = '2026-08-14'

/** Daily dated closes ending on END_DATE; `priceAt` receives 0 for the oldest observation. */
const datedSeries = (count, priceAt) => {
  const end = Date.parse(`${END_DATE}T00:00:00Z`)
  const dates = []
  const closes = []
  for (let offset = count - 1; offset >= 0; offset -= 1) {
    dates.push(new Date(end - offset * DAY_MS).toISOString().slice(0, 10))
    closes.push(priceAt(count - 1 - offset))
  }
  return { dates, closes }
}

// Flat until the final observation, so a window's return is whatever that last close says.
const flatThenMove = (count, endPrice, basePrice = 100) =>
  datedSeries(count, (index) => (index === count - 1 ? endPrice : basePrice))

const datedBenchmark = flatThenMove(400, 101) // +1% across any window that ends today

const datedPosition = (ticker, overrides = {}) => ({
  ticker,
  name: `${ticker} Inc`,
  shares: 10,
  allocationPct: 100,
  priceInfo: {
    sector: 'Technology',
    history: flatThenMove(400, 110),
    technical_detail: { beta: 1.2 },
  },
  ...overrides,
})

describe('portfolio move attribution over a longer window', () => {
  it('offers today, week, month, three months and a year', () => {
    expect(ATTRIBUTION_PERIODS.map((entry) => entry.key)).toEqual(['1D', '1W', '1M', '3M', '1Y'])
  })

  it.each(['1W', '1M', '3M', '1Y'])('resolves the published window it actually measured for %s', (period) => {
    const days = ATTRIBUTION_PERIODS.find((entry) => entry.key === period).days
    const result = explainPortfolioMove([datedPosition('AAPL')], datedBenchmark, { period })

    expect(result.available).toBe(true)
    expect(result.endDate).toBe(END_DATE)
    expect(result.period).toBe(period)
    // Never shorter than requested: the start snaps to the last close at or before the target.
    expect(result.spanDays).toBeGreaterThanOrEqual(days)
    expect(result.windowTruncated).toBe(false)
  })

  it('measures each holding from the resolved start close rather than yesterday', () => {
    const result = explainPortfolioMove([datedPosition('AAPL')], datedBenchmark, { period: '1M' })
    const [holding] = result.holdings

    expect(holding.returnPct).toBeCloseTo(10, 6) // 100 -> 110 across the window
    expect(result.benchmarkReturnPct).toBeCloseTo(1, 6)
    // weight 1, beta 1.2, benchmark +1% -> market 1.2, idiosyncratic 10 - 1.2 = 8.8
    expect(holding.marketComponentPct).toBeCloseTo(1.2, 6)
    expect(holding.idiosyncraticComponentPct).toBeCloseTo(8.8, 6)
  })

  it.each(['1W', '1M', '3M', '1Y'])('market plus idiosyncratic still reconciles exactly for %s', (period) => {
    const positions = [
      datedPosition('AAPL', { allocationPct: 60 }),
      datedPosition('MSFT', {
        allocationPct: 40, shares: 5,
        priceInfo: { sector: 'Energy', history: flatThenMove(400, 92, 100), technical_detail: { beta: 0.8 } },
      }),
    ]
    const result = explainPortfolioMove(positions, datedBenchmark, { period })

    expect(result.reconciles).toBe(true)
    expect(result.marketPct + result.idiosyncraticPct).toBeCloseTo(result.totalReturnPct, 9)
  })

  it('weights by start-of-window value, so a winner is not credited twice', () => {
    // Both opened the window worth $1,000. One doubled, the other was flat: the basket went
    // 2,000 -> 3,000, i.e. +50%. Today's allocations (66.7/33.3) would report +66.7%.
    const doubled = datedPosition('WIN', {
      allocationPct: 66.67, shares: 10,
      priceInfo: { sector: 'Technology', history: flatThenMove(400, 200, 100), technical_detail: { beta: 1 } },
    })
    const flat = datedPosition('FLAT', {
      allocationPct: 33.33, shares: 10,
      priceInfo: { sector: 'Energy', history: flatThenMove(400, 100, 100), technical_detail: { beta: 1 } },
    })
    const result = explainPortfolioMove([doubled, flat], datedBenchmark, { period: '3M' })

    expect(result.weightBasis).toBe('start_of_period')
    expect(result.holdings[0].weight).toBeCloseTo(0.5, 6)
    expect(result.totalReturnPct).toBeCloseTo(50, 6)
  })

  it('falls back to current allocation and says so when share counts are missing', () => {
    const noShares = datedPosition('AAPL', { shares: null, allocationPct: 40 })
    const result = explainPortfolioMove([noShares], datedBenchmark, { period: '1M' })

    expect(result.weightBasis).toBe('current_allocation')
    expect(result.holdings[0].weight).toBeCloseTo(0.4, 6)
  })

  it('flags a window truncated by the published history instead of relabelling it', () => {
    const shortBenchmark = flatThenMove(30, 101)
    const shortPosition = datedPosition('AAPL', {
      priceInfo: { sector: 'Technology', history: flatThenMove(30, 110), technical_detail: { beta: 1.2 } },
    })
    const result = explainPortfolioMove([shortPosition], shortBenchmark, { period: '1Y' })

    expect(result.available).toBe(true)
    expect(result.windowTruncated).toBe(true)
    expect(result.spanDays).toBe(29)
  })

  it('flags a holding bought after the window opened rather than dropping it', () => {
    const recent = datedPosition('NEW', { purchaseDate: END_DATE })
    const result = explainPortfolioMove([recent], datedBenchmark, { period: '3M' })

    expect(result.partialHoldings).toEqual(['NEW'])
    expect(result.holdings[0].available).toBe(true)
  })

  it('does not flag a holding bought before the window opened', () => {
    const old = datedPosition('OLD', { purchaseDate: '2020-01-01' })
    const result = explainPortfolioMove([old], datedBenchmark, { period: '3M' })
    expect(result.partialHoldings).toEqual([])
  })

  it('closes the window on a live quote when one has been fetched', () => {
    const live = datedPosition('AAPL', {
      priceInfo: {
        sector: 'Technology', history: flatThenMove(400, 110), technical_detail: { beta: 1.2 },
        portfolioQuote: true, price: 120, previousClose: 110,
      },
    })
    const result = explainPortfolioMove([live], datedBenchmark, {
      period: '1M',
      benchmarkQuote: { portfolioQuote: true, price: 102, previousClose: 101 },
    })

    expect(result.holdings[0].returnPct).toBeCloseTo(20, 6) // 100 -> live 120, not the 110 close
    expect(result.benchmarkReturnPct).toBeCloseTo(2, 6)
  })

  it('excludes a holding whose history does not reach the window start and reports coverage', () => {
    const covered = datedPosition('AAPL', { allocationPct: 70 })
    const tooNew = datedPosition('IPO', {
      allocationPct: 30,
      priceInfo: { sector: 'Technology', history: flatThenMove(3, 110), technical_detail: { beta: 1 } },
    })
    const result = explainPortfolioMove([covered, tooNew], datedBenchmark, { period: '3M' })

    expect(result.unpriced).toEqual(['IPO'])
    expect(result.pricedCount).toBe(1)
    expect(result.holdingCount).toBe(2)
    expect(result.coveragePct).toBeCloseTo(70, 6)
  })

  it('is unavailable, with the window named, when no benchmark history covers it', () => {
    const result = explainPortfolioMove([datedPosition('AAPL')], null, { period: '1Y' })
    expect(result.available).toBe(false)
    expect(result.reason).toMatch(/year/i)
    expect(result.period).toBe('1Y')
  })

  it('treats an unknown period as today rather than failing', () => {
    const result = explainPortfolioMove([position('AAPL')], benchmarkHistory, { period: '7Y' })
    expect(result.period).toBe('1D')
    expect(result.available).toBe(true)
  })
})
