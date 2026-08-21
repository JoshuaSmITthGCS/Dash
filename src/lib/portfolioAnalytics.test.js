import { describe, expect, it } from 'vitest'
import {
  alignSeries, annualizeReturnPct, compareBenchmarkSeries, concentrationLiquidityScore, correlationDiversification, costWeights, currentHoldingsSeries, diversificationScore, enrichPortfolio,
  contributionAdjustedPerformance, intradayPortfolioHigh, latestMarketDayReturn, modifiedDietzReturn, moneyWeightedAccountReturn, netInvestedCapital, opportunityCost, performanceMetrics,
  portfolioAnnualizedReturn, portfolioReconciliationBridge, portfolioReturnSummary, portfolioRiskDecomposition, portfolioScore, resilienceIndex, sectorLookThrough, selectPeriod, shrinkCovarianceMatrix, sliceSeriesFrom, trackedAllTimeEarnings, trailingCashFlowPace, underwaterProfile,
} from './portfolioAnalytics.js'

describe('portfolio report analytics', () => {
  it('separates entered cost basis from current value and allocation', () => {
    const result = enrichPortfolio([{ ticker: 'AAA', shares: 2, costBasis: 50 }, { ticker: 'BBB', shares: 1, costBasis: 80 }], { AAA: { price: 75 }, BBB: { price: 50 } })
    expect(result.totalCost).toBe(180)
    expect(result.totalValue).toBe(200)
    expect(result.gain).toBe(20)
    expect(result.positions[0].allocationPct).toBe(75)
  })

  describe('portfolioReconciliationBridge (B2)', () => {
    const snapshots = [
      { value: 10000, unrealizedGain: 1000, marketDate: '2026-01-01', recordedAt: '2026-01-01T20:00:00Z' },
      { value: 10540, unrealizedGain: 1200, marketDate: '2026-01-02', recordedAt: '2026-01-02T20:00:00Z' },
    ]
    const activities = [
      { type: 'deposit', amount: 200, effectiveDate: '2026-01-02' },
      { type: 'dividend', amount: 50, effectiveDate: '2026-01-02' },
      { type: 'fee', amount: 10, effectiveDate: '2026-01-02' },
      { type: 'realized_gain', amount: 100, effectiveDate: '2026-01-02' },
    ]

    it('is unavailable with fewer than two unrealized-gain-tagged snapshots', () => {
      expect(portfolioReconciliationBridge([], [])).toMatchObject({ available: false })
      expect(portfolioReconciliationBridge([snapshots[0]], [])).toMatchObject({ available: false })
      expect(portfolioReconciliationBridge([
        { value: 10000, marketDate: '2026-01-01', recordedAt: '2026-01-01T20:00:00Z' },
        { value: 10540, marketDate: '2026-01-02', recordedAt: '2026-01-02T20:00:00Z' },
      ], [])).toMatchObject({ available: false })
    })

    it('reconciles every independently-sourced line to the recorded ending NAV within a penny', () => {
      const bridge = portfolioReconciliationBridge(snapshots, activities)
      expect(bridge.available).toBe(true)
      expect(bridge.deposits).toBe(200)
      expect(bridge.dividends).toBe(50)
      expect(bridge.fees).toBe(10)
      expect(bridge.realizedGains).toBe(100)
      expect(bridge.unrealizedGainChange).toBe(200)
      expect(bridge.reconstructedEndingNav).toBeCloseTo(10540, 6)
      expect(bridge.residual).toBeCloseTo(0, 6)
      expect(bridge.status).toBe('RECONCILED')
      expect(bridge.fx.tracked).toBe(false)
      expect(bridge.taxes.tracked).toBe(false)
      expect(bridge.tradingCosts.tracked).toBe(false)
    })

    it('flags RECONCILIATION_FAILED when the recorded ending NAV does not match the reconstruction', () => {
      const mismatched = [snapshots[0], { ...snapshots[1], value: 10600 }]
      const bridge = portfolioReconciliationBridge(mismatched, activities)
      expect(bridge.status).toBe('RECONCILIATION_FAILED')
      expect(bridge.reconciled).toBe(false)
      expect(bridge.residual).toBeCloseTo(60, 6)
      expect(bridge.reason).toContain('unrecorded cash flow')
    })

    it('only counts activity dated within the bridged period, not before or after it', () => {
      const stray = [...activities, { type: 'deposit', amount: 9999, effectiveDate: '2025-01-01' }, { type: 'fee', amount: 9999, effectiveDate: '2026-06-01' }]
      const bridge = portfolioReconciliationBridge(snapshots, stray)
      expect(bridge.deposits).toBe(200)
      expect(bridge.fees).toBe(10)
      expect(bridge.status).toBe('RECONCILED')
    })
  })

  it('computes cost-basis dollar weights normalized to sum to 1, for the turnover rebalance ledger', () => {
    const weights = costWeights([
      { ticker: 'aaa', shares: 10, costBasis: 20 },
      { ticker: 'bbb', shares: 5, costBasis: 40 },
    ])
    expect(weights).toMatchObject({ AAA: 0.5, BBB: 0.5 })
    expect(costWeights([])).toEqual({})
    expect(costWeights([{ ticker: 'AAA', shares: 0, costBasis: 20 }])).toEqual({})
  })

  it('builds an explicitly current-holdings daily-close backtest and changes data by period', () => {
    const series = currentHoldingsSeries([{ ticker: 'AAA', shares: 2 }], { AAA: { history: { dates: ['2026-06-01', '2026-06-25', '2026-06-30'], closes: [10, 12, 15] } } })
    expect(series.values).toEqual([20, 24, 30])
    expect(series.methodology).toContain('Current quantities')
    expect(selectPeriod(series, '1W').dates).toEqual(['2026-06-25', '2026-06-30'])
    expect(selectPeriod(series, 'All').values).toHaveLength(3)
    expect(selectPeriod({ dates: ['2025-12-31', '2026-01-02', '2026-06-30'], values: [18, 19, 30] }, 'YTD').dates).toEqual(['2026-01-02', '2026-06-30'])
  })

  it('keeps a session one holding is missing by valuing it at that holding’s previous close', () => {
    // The provider dropped BBB's 06-02 bar. Discarding the whole session (the old behaviour)
    // spliced 06-01→06-03 into a single observation for every holding at once.
    const series = currentHoldingsSeries(
      [{ ticker: 'AAA', shares: 2 }, { ticker: 'BBB', shares: 1 }],
      {
        AAA: { history: { dates: ['2026-06-01', '2026-06-02', '2026-06-03'], closes: [10, 11, 12] } },
        BBB: { history: { dates: ['2026-06-01', '2026-06-03'], closes: [100, 130] } },
      },
      ['2026-06-01', '2026-06-02', '2026-06-03'],
    )

    expect(series.dates).toEqual(['2026-06-01', '2026-06-02', '2026-06-03'])
    expect(series.values).toEqual([120, 122, 154])
    expect(series.carried).toEqual([0, 1, 0])
    expect(series.carriedObservations).toBe(1)
    expect(series.methodology).toContain('previous close')
  })

  it('stays native daily when a holding has no published price history at all', () => {
    // Two unpriceable holdings out of 88 used to mark the whole series "irregular", which
    // made every standard measure report the series as a compact chart grid and refuse.
    const series = currentHoldingsSeries(
      [{ ticker: 'AAA', shares: 2 }, { ticker: 'DECJ', shares: 1 }],
      {
        AAA: { analytics_history: { dates: ['2026-06-01', '2026-06-02'], closes: [10, 11], frequency: 'daily' } },
        DECJ: {},
      },
      ['2026-06-01', '2026-06-02'],
    )

    expect(series.frequency).toBe('daily')
    expect(series.untracked).toEqual(['DECJ'])
    expect(series.trackedPositions).toBe(1)
    expect(series.totalPositions).toBe(2)
    expect(series.methodology).toContain('DECJ')
    expect(series.coverage).toEqual([50, 50])
  })

  it('does not carry a close backwards to before a holding existed', () => {
    const series = currentHoldingsSeries(
      [{ ticker: 'AAA', shares: 2 }, { ticker: 'NEW', shares: 1 }],
      {
        AAA: { history: { dates: ['2026-06-01', '2026-06-02', '2026-06-03'], closes: [10, 11, 12] } },
        NEW: { history: { dates: ['2026-06-02', '2026-06-03'], closes: [50, 60] } },
      },
      ['2026-06-01', '2026-06-02', '2026-06-03'],
    )

    expect(series.dates).toEqual(['2026-06-02', '2026-06-03'])
    expect(series.carriedObservations).toBe(0)
  })

  it('stops pricing a holding whose closes have gone stale beyond the carry window', () => {
    const series = currentHoldingsSeries(
      [{ ticker: 'AAA', shares: 2 }, { ticker: 'DEAD', shares: 1 }],
      {
        AAA: { history: { dates: ['2026-06-01', '2026-06-02', '2026-06-30'], closes: [10, 11, 12] } },
        DEAD: { history: { dates: ['2026-06-01', '2026-06-02'], closes: [100, 100] } },
      },
      ['2026-06-01', '2026-06-02', '2026-06-30'],
    )

    // 06-30 is far past DEAD's last print, so the date is dropped rather than valued off a
    // close that stopped updating four weeks earlier.
    expect(series.dates).toEqual(['2026-06-01', '2026-06-02'])
  })

  it('uses the last two closes for latest market-day return', () => {
    expect(latestMarketDayReturn({ dates: ['a', 'b', 'c'], values: [100, 105, 103] })).toMatchObject({ date: 'c', dollarReturn: -2 })
  })

  it('does not call cost basis invested capital without a cash-flow ledger', () => {
    expect(netInvestedCapital(null).available).toBe(false)
    expect(netInvestedCapital([{ type: 'deposit', amount: 1000, date: '2026-01-01' }, { type: 'withdrawal', amount: 100, date: '2026-02-01' }]).value).toBe(900)
    expect(netInvestedCapital([{ type: 'deposit', amount: 1000, effectiveDate: '2026-01-01' }])).toMatchObject({ deposits: 1000, withdrawals: 0 })
    expect(netInvestedCapital([
      { type: 'deposit', amount: 1000, effectiveDate: '2026-01-01' },
      { type: 'sale_proceeds', amount: 250, effectiveDate: '2026-01-02' },
      { type: 'stock_purchase', amount: 200, effectiveDate: '2026-01-03' },
    ]).value).toBe(1000)
  })

  it('calculates actual account growth from complete external cash flows', () => {
    const rows = [{ type: 'deposit', amount: 2880, effectiveDate: '2026-01-01' }, { type: 'withdrawal', amount: 200, effectiveDate: '2026-02-01' }]
    expect(contributionAdjustedPerformance(2827.96, rows, false).available).toBe(false)
    const result = contributionAdjustedPerformance(2827.96, rows, true)
    expect(result.netContributions).toBe(2680)
    expect(result.value).toBeCloseTo(147.96, 2)
    expect(result.returnPct).toBeCloseTo(5.52, 2)
  })

  it('calculates Modified Dietz for a worked mid-period deposit example', () => {
    const result = modifiedDietzReturn(100, 165, [
      { type: 'deposit', amount: 50, effectiveDate: '2026-01-06' },
    ], '2026-01-01', '2026-01-11', true)
    expect(result.returnPct).toBeCloseTo(12, 8)
    expect(result.weightedCapital).toBe(125)
  })

  it('treats a new position funded by new money as a contribution, not strategy gain', () => {
    const rows = [{ type: 'external_contribution', amount: 1000, effectiveDate: '2026-06-01' }]
    expect(netInvestedCapital(rows)).toMatchObject({ value: 1000, deposits: 1000, withdrawals: 0 })
    const dietz = modifiedDietzReturn(1000, 2200, rows, '2026-01-01', '2026-07-01', true)
    // The $1000 contribution explains $1000 of the $1200 jump; only the remaining $200 is
    // attributed to the strategy, instead of the whole jump looking like investment gain.
    expect(dietz.netExternalFlows).toBe(1000)
    expect(dietz.gain).toBe(200)
  })

  it('chains a true time-weighted strategy return without counting deposits', () => {
    const result = portfolioReturnSummary([
      { value: 100, marketDate: '2026-01-01', recordedAt: '2026-01-01T20:00:00Z' },
      { value: 165, marketDate: '2026-01-02', recordedAt: '2026-01-02T20:00:00Z' },
      { value: 181.5, marketDate: '2026-01-03', recordedAt: '2026-01-03T20:00:00Z' },
    ], [
      { type: 'deposit', amount: 50, effectiveDate: '2026-01-02' },
    ], true)

    // Day 1 earns 15% after the $50 deposit is removed; day 2 earns 10%.
    expect(result.strategy.returnPct).toBeCloseTo(26.5, 8)
    expect(result.strategy.gain).toBeCloseTo(26.5, 8)
    expect(result.strategy.methodology).toContain('removing settled external deposits')
  })

  // Master Remediation Prompt v3, B2: TWR must never be contaminated by deposits or
  // withdrawals. These four cases are the isolation guarantee's own regression suite --
  // confirmed passing against the current implementation, not just documentation of intent.
  describe('TWR flow isolation (B2)', () => {
    it('a pure deposit with no market move reports ~0% strategy return, not a gain', () => {
      const result = portfolioReturnSummary([
        { value: 1000, marketDate: '2026-01-01', recordedAt: '2026-01-01T20:00:00Z' },
        { value: 1100, marketDate: '2026-01-02', recordedAt: '2026-01-02T20:00:00Z' },
      ], [{ type: 'deposit', amount: 100, effectiveDate: '2026-01-02' }], true)
      expect(result.strategy.returnPct).toBeCloseTo(0, 6)
    })

    it('a pure withdrawal with no market move reports ~0% strategy return, not a loss', () => {
      const result = portfolioReturnSummary([
        { value: 1000, marketDate: '2026-01-01', recordedAt: '2026-01-01T20:00:00Z' },
        { value: 900, marketDate: '2026-01-02', recordedAt: '2026-01-02T20:00:00Z' },
      ], [{ type: 'withdrawal', amount: 100, effectiveDate: '2026-01-02' }], true)
      expect(result.strategy.returnPct).toBeCloseTo(0, 6)
    })

    it('a deposit immediately before a gain does not inflate the reported return', () => {
      const result = portfolioReturnSummary([
        { value: 1000, marketDate: '2026-01-01', recordedAt: '2026-01-01T20:00:00Z' },
        { value: 1500, marketDate: '2026-01-02', recordedAt: '2026-01-02T20:00:00Z' },
        { value: 1650, marketDate: '2026-01-03', recordedAt: '2026-01-03T20:00:00Z' },
      ], [{ type: 'deposit', amount: 500, effectiveDate: '2026-01-02' }], true)
      // Only day 2's genuine 10% market gain (1500 -> 1650) should show; the deposit itself
      // (day 1 -> day 2) contributes 0%, not the 50% the raw dollar jump would imply.
      expect(result.strategy.returnPct).toBeCloseTo(10, 6)
    })

    it('a withdrawal immediately before a loss does not distort the reported return', () => {
      const result = portfolioReturnSummary([
        { value: 1000, marketDate: '2026-01-01', recordedAt: '2026-01-01T20:00:00Z' },
        { value: 700, marketDate: '2026-01-02', recordedAt: '2026-01-02T20:00:00Z' },
        { value: 630, marketDate: '2026-01-03', recordedAt: '2026-01-03T20:00:00Z' },
      ], [{ type: 'withdrawal', amount: 300, effectiveDate: '2026-01-02' }], true)
      // Only day 2's genuine 10% market loss (700 -> 630) should show; the withdrawal itself
      // (day 1 -> day 2) contributes 0%, not the 30% the raw dollar drop would imply.
      expect(result.strategy.returnPct).toBeCloseTo(-10, 6)
    })
  })

  it('computes a money-weighted (XIRR) return alongside the time-weighted one', () => {
    const result = portfolioReturnSummary([
      { value: 1000, marketDate: '2026-01-01', recordedAt: '2026-01-01T20:00:00Z' },
      { value: 1650, marketDate: '2026-02-01', recordedAt: '2026-02-01T20:00:00Z' },
    ], [{ type: 'deposit', amount: 500, effectiveDate: '2026-01-15' }], true)
    expect(result.moneyWeighted.available).toBe(true)
    // MWR reflects the size and timing of the deposit, unlike the TWR above -- a $500
    // deposit landing mid-period means the account grew from less invested capital than
    // ending value alone would suggest, so MWR > the simple (ending/beginning - 1) return.
    expect(result.moneyWeighted.rate).toBeGreaterThan(0)
    expect(moneyWeightedAccountReturn([], [], true)).toMatchObject({ available: false })
  })

  it('annualizes a realized return over an arbitrary span', () => {
    expect(annualizeReturnPct(12, '2026-01-01', '2026-07-02')).toBeCloseTo(25.5, 1)
    expect(annualizeReturnPct(null, '2026-01-01', '2026-07-01')).toBeNull()
    expect(annualizeReturnPct(5, '2026-01-01', '2026-01-01')).toBeNull()
  })

  it('refuses to annualize a span shorter than the given minimum', () => {
    // 18 days of live tracking stretched to a year would wildly overstate the rate.
    expect(annualizeReturnPct(10.1, '2026-07-20', '2026-08-07', 30)).toBeNull()
    expect(annualizeReturnPct(10.1, '2026-07-20', '2026-08-07')).not.toBeNull()
    expect(annualizeReturnPct(10.1, '2026-01-01', '2026-08-07', 30)).not.toBeNull()
  })

  it('slices a series to only dates on or after a cutoff', () => {
    const series = { dates: ['2026-06-01', '2026-07-19', '2026-07-20', '2026-08-01'], values: [10, 11, 12, 13] }
    expect(sliceSeriesFrom(series, '2026-07-20')).toMatchObject({ dates: ['2026-07-20', '2026-08-01'], values: [12, 13] })
    expect(sliceSeriesFrom(series, '2027-01-01')).toBeNull()
    expect(sliceSeriesFrom(null, '2026-07-20')).toBeNull()
  })

  it('excludes processing transfers from actual gains and the observed contribution pace', () => {
    const rows = [
      { type: 'deposit', amount: 60, effectiveDate: '2025-08-04' },
      { type: 'deposit', amount: 200, effectiveDate: '2026-02-13' },
      { type: 'withdrawal', amount: 200, effectiveDate: '2026-03-30' },
      { type: 'deposit', amount: 2500, effectiveDate: '2026-08-03' },
      { type: 'deposit', amount: 100, effectiveDate: '2026-08-04', status: 'processing' },
    ]
    const performance = contributionAdjustedPerformance(2818.41, rows, true)
    expect(performance.netContributions).toBe(2560)
    expect(performance.value).toBeCloseTo(258.41, 2)
    expect(trailingCashFlowPace(rows, '2026-08-04', true)).toMatchObject({ deposits: 2760, withdrawals: 200, netContributions: 2560, count: 4 })
  })

  it('aligns exact dates before benchmark and opportunity-cost comparisons', () => {
    const aligned = alignSeries({ period: '1M', dates: ['a', 'b', 'c'], values: [100, 105, 110] }, { dates: ['b', 'c', 'd'], values: [200, 204, 210] })
    expect(aligned.dates).toEqual(['b', 'c'])
    const longLeft = { values: Array.from({ length: 25 }, (_, index) => 100 + index), period: '1M' }
    const longRight = { values: Array.from({ length: 25 }, (_, index) => 100 + index * 0.8), period: '1M' }
    const performance = performanceMetrics(longLeft, longRight)
    expect(performance.available).toBe(true)
    expect(performance.score).toBeNull()
    expect(performance.rating).toBeUndefined()
    const cost = opportunityCost(aligned.left, aligned.right)
    expect(cost.startDate).toBe('b')
  })

  it('uses one exact-date, equal-start calculation for multi-benchmark charts and potential earnings', () => {
    const comparison = compareBenchmarkSeries(
      { period: '1M', dates: ['a', 'b', 'c'], values: [100, 110, 120], methodology: 'test' },
      [
        { symbol: 'SPY', dates: ['a', 'b', 'c'], closes: [200, 210, 220] },
        { symbol: 'QQQ', dates: ['a', 'b', 'c'], closes: [50, 60, 70] },
      ],
    )
    expect(comparison.dates).toEqual(['a', 'b', 'c'])
    expect(comparison.portfolio.endValue).toBe(120)
    expect(comparison.benchmarks[0]).toMatchObject({ symbol: 'SPY', endValue: 110, potentialEarnings: 10, differenceVsPortfolio: 10 })
    expect(comparison.benchmarks[1]).toMatchObject({ symbol: 'QQQ', endValue: 140, potentialEarnings: 40, differenceVsPortfolio: -20 })
  })

  it('marks sparse resilience and concentrated diversification transparently', () => {
    const sparse = resilienceIndex([100, 101])
    expect(sparse.available).toBe(false)
    const concentrated = diversificationScore([{ ticker: 'AAA', currentValue: 90, priceInfo: { sector: 'Tech', industry: 'Software' } }, { ticker: 'BBB', currentValue: 10, priceInfo: { sector: 'Health', industry: 'Care' } }])
    expect(concentrated.score).toBeLessThan(60)
    expect(concentrated.warnings[0]).toContain('Largest holding')
  })

  it('computes HHI and effective holdings for a hand-calculated four-position case', () => {
    const positions = [40, 30, 20, 10].map((currentValue, index) => ({
      ticker: `P${index}`,
      currentValue,
      priceInfo: { sector: `S${index}`, industry: `I${index}` },
    }))
    const result = diversificationScore(positions)
    expect(result.hhi).toBeCloseTo(0.3, 10)
    expect(result.effectiveHoldings).toBeCloseTo(10 / 3, 10)
    expect(result.rawHoldingCount).toBe(4)
  })

  it('collapses perfectly correlated holdings to one effective bet', () => {
    const dates = Array.from({ length: 70 }, (_, index) => `2026-01-${String(index + 1).padStart(2, '0')}`)
    const closes = dates.map((_, index) => 100 * (1.01 ** index))
    const positions = ['AAA', 'BBB'].map((ticker) => ({
      ticker,
      currentValue: 50,
      priceInfo: { history: { dates, closes } },
    }))
    const result = correlationDiversification(positions)
    expect(result.available).toBe(true)
    expect(result.effectiveBets).toBeCloseTo(1, 6)
    expect(result.diversificationRatio).toBeCloseTo(1, 6)
  })

  it('looks through an ETF before aggregating direct sector exposure', () => {
    const positions = [
      { ticker: 'VOO', currentValue: 50, priceInfo: { sector: 'ETF' } },
      { ticker: 'MSFT', currentValue: 50, priceInfo: { sector: 'Technology' } },
    ]
    const result = sectorLookThrough(positions, [{
      ticker: 'VOO',
      sector_weights: { technology: 0.6, healthcare: 0.4 },
    }])
    expect(result.exposures).toEqual([
      { label: 'Technology', pct: 80 },
      { label: 'Healthcare', pct: 20 },
    ])
    expect(result.unavailableEtfs).toEqual([])
  })

  it('combines an ETF constituent with the same direct position', () => {
    const result = sectorLookThrough([
      { ticker: 'VOO', currentValue: 50, priceInfo: { sector: 'ETF' } },
      { ticker: 'NVDA', currentValue: 50, priceInfo: { sector: 'Technology' } },
    ], [{
      ticker: 'VOO',
      sector_weights: { technology: 1 },
      top_holdings: [{ ticker: 'NVDA', weight: 0.1 }, { ticker: 'MSFT', weight: 0.2 }],
    }])
    expect(result.positionExposures.find((row) => row.ticker === 'NVDA').pct).toBeCloseTo(55, 10)
    expect(result.positionExposures.find((row) => row.ticker === 'MSFT').pct).toBeCloseTo(10, 10)
    expect(result.positionExposures.find((row) => row.ticker === 'Other VOO holdings').pct).toBeCloseTo(35, 10)
  })

  it('flags an ETF when sector look-through is unavailable', () => {
    const result = sectorLookThrough([
      { ticker: 'VOO', currentValue: 100, priceInfo: { sector: 'ETF' } },
    ], [{ ticker: 'VOO', sector_weights: null }])
    expect(result.unavailableEtfs).toEqual(['VOO'])
    expect(result.exposures[0].label).toBe('ETF look-through unavailable')
    expect(result.unresolvedDollars).toBe(100)
  })

  it('reconciles percent contribution to total risk to 100%', () => {
    const dates = Array.from({ length: 90 }, (_, index) => `d-${index}`)
    const makeCloses = (phase) => dates.map((_, index) => 100 * (1 + index * 0.001 + Math.sin(index + phase) * 0.01))
    const positions = [
      { ticker: 'AAA', currentValue: 60, priceInfo: { history: { dates, closes: makeCloses(0) } } },
      { ticker: 'BBB', currentValue: 40, priceInfo: { history: { dates, closes: makeCloses(1) } } },
    ]
    const result = portfolioRiskDecomposition(positions)
    expect(result.available).toBe(true)
    expect(result.contributions.reduce((sum, row) => sum + row.percentContributionToRisk, 0)).toBeCloseTo(100, 8)
    expect(result.expectedShortfall95Pct).toBeLessThan(0)
  })

  it('publishes active share only when benchmark constituent weights are available', () => {
    const dates = Array.from({ length: 90 }, (_, index) => `d-${index}`)
    const positions = [
      { ticker: 'AAA', currentValue: 60, priceInfo: { history: { dates, closes: dates.map((_, index) => 100 + index + Math.sin(index)) } } },
      { ticker: 'BBB', currentValue: 40, priceInfo: { history: { dates, closes: dates.map((_, index) => 100 + index + Math.cos(index)) } } },
    ]
    expect(portfolioRiskDecomposition(positions).activeSharePct).toBeNull()
    expect(portfolioRiskDecomposition(positions, { benchmarkWeights: { AAA: 0.5, BBB: 0.5 } }).activeSharePct).toBeCloseTo(10, 10)
  })

  it('issues a clearly provisional score without turning missing components into zero', () => {
    const liquidity = concentrationLiquidityScore([{ currentValue: 1000, allocationPct: 100, priceInfo: { average_dollar_volume: 1_000_000 } }])
    expect(liquidity.available).toBe(true)
    const score = portfolioScore({ diversification: { score: 50 }, resilience: { score: null }, performance: { score: 50 }, benchmarkEfficiency: 50, concentrationLiquidity: liquidity, dataCompleteness: 100 })
    expect(score.available).toBe(true)
    expect(score.provisional).toBe(true)
    expect(score.components.resilience).toBeNull()
  })

  it('derives a money-weighted annualized return from current holdings', () => {
    const positions = [{ purchaseDate: '2025-01-01', totalCost: 1000, currentValue: 1100 }]
    const annualized = portfolioAnnualizedReturn(positions, '2026-01-01')
    expect(annualized.available).toBe(true)
    expect(annualized.rate).toBeCloseTo(10, 1)
  })

  it('stores observed intraday highs and only calculates all-time earnings after ledger confirmation', () => {
    expect(intradayPortfolioHigh([{ recordedAt: '2026-08-04T14:00:00Z', value: 100 }, { recordedAt: '2026-08-04T15:00:00Z', value: 110 }])).toMatchObject({ value: 110, observations: 2 })
    const incomplete = trackedAllTimeEarnings({ gain: 20 }, [{ type: 'dividend', amount: 5 }], { trackingStartedAt: '2026-01-01' })
    expect(incomplete.available).toBe(false)
    const complete = trackedAllTimeEarnings({ gain: 20 }, [{ type: 'realized_gain', amount: -4 }, { type: 'dividend', amount: 5 }, { type: 'fee', amount: 1 }], { trackingStartedAt: '2026-01-01', ledgerComplete: true })
    expect(complete.value).toBe(20)
  })
})

describe('covariance shrinkage', () => {
  const sample = [[0.04, 0.02, 0.01], [0.02, 0.09, 0.015], [0.01, 0.015, 0.0625]]

  it('leaves variances (the diagonal) untouched', () => {
    const shrunk = shrinkCovarianceMatrix(sample, 0.5)
    expect(shrunk[0][0]).toBe(0.04)
    expect(shrunk[1][1]).toBe(0.09)
    expect(shrunk[2][2]).toBe(0.0625)
  })

  it('pulls off-diagonal covariances toward zero proportionally to intensity', () => {
    const shrunk = shrinkCovarianceMatrix(sample, 0.5)
    expect(shrunk[0][1]).toBeCloseTo(0.01, 6)
    expect(shrunk[1][0]).toBeCloseTo(0.01, 6)
  })

  it('zero intensity returns the sample matrix unchanged', () => {
    expect(shrinkCovarianceMatrix(sample, 0)).toEqual(sample)
  })

  it('full intensity zeroes every off-diagonal entry', () => {
    const shrunk = shrinkCovarianceMatrix(sample, 1)
    expect(shrunk[0][1]).toBe(0)
    expect(shrunk[1][2]).toBe(0)
    expect(shrunk[0][0]).toBe(0.04)
  })

  it('clamps an out-of-range intensity instead of producing a negative covariance', () => {
    const shrunk = shrinkCovarianceMatrix(sample, 5)
    expect(shrunk[0][1]).toBe(0)
  })

  it('handles an empty or missing matrix without throwing', () => {
    expect(shrinkCovarianceMatrix([])).toEqual([])
    expect(shrinkCovarianceMatrix(null)).toBeNull()
  })
})

describe('underwaterProfile', () => {
  // A fall, a long crawl back, a new high, then a second shallower fall it is still in.
  const dates = []
  const values = []
  const add = (day, value) => { dates.push(new Date(Date.parse('2025-01-01T00:00:00Z') + day * 86400000).toISOString().slice(0, 10)); values.push(value) }
  add(0, 100); add(30, 120); add(60, 90); add(200, 110); add(300, 121); add(330, 112); add(360, 115)
  const series = { dates, values }

  it('reports how long the portfolio sat below its high, not just how deep it went', () => {
    const reading = underwaterProfile(series)
    expect(reading.available).toBe(true)
    // Peak on day 30, back above it on day 300: 270 days underwater. Counting the four
    // observations in between would have called it a four-day dip.
    expect(reading.longestUnderwaterDays).toBe(270)
    expect(reading.deepestDrawdownPct).toBeCloseTo(-25, 5)
    expect(reading.recoveryDaysForDeepest).toBe(270)
  })

  it('measures the current spell from the high-water mark, not the last observation', () => {
    const reading = underwaterProfile(series)
    expect(reading.stillUnderwater).toBe(true)
    expect(reading.highWaterDate).toBe(dates[4])
    expect(reading.currentUnderwaterDays).toBe(60)
    expect(reading.currentDrawdownPct).toBeCloseTo((115 / 121 - 1) * 100, 5)
  })

  it('leaves recovery null while the deepest fall has not been recovered', () => {
    // Null is the answer here. A zero would read as "recovered immediately".
    const sinking = { dates: dates.slice(0, 3), values: [100, 120, 90] }
    const reading = underwaterProfile(sinking)
    expect(reading.recoveryDaysForDeepest).toBeNull()
    expect(reading.stillUnderwater).toBe(true)
    expect(reading.longestUnderwaterDays).toBe(30)
  })

  it('reports zero days underwater for a portfolio at its high', () => {
    const climbing = { dates: dates.slice(0, 3), values: [100, 110, 130] }
    const reading = underwaterProfile(climbing)
    expect(reading.stillUnderwater).toBe(false)
    expect(reading.currentUnderwaterDays).toBe(0)
    expect(reading.currentDrawdownPct).toBe(0)
  })

  it('needs two dated values before it will answer', () => {
    expect(underwaterProfile(null).available).toBe(false)
    expect(underwaterProfile({ dates: ['2025-01-01'], values: [100] }).available).toBe(false)
  })
})
