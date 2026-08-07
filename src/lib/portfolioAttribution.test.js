import { describe, expect, it } from 'vitest'
import { explainPortfolioMove } from './portfolioAttribution.js'

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
