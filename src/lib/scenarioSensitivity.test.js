import { describe, expect, it } from 'vitest'
import { availableScenarios, portfolioProjectedImpact, rankHoldingsByScenario } from './scenarioSensitivity'

function signalMetrics(overrides = {}) {
  return {
    metrics: [
      {
        id: 'scenario_gfc_2008', label: '2008 Global Financial Crisis', status: 'ready',
        detail: { description: 'S&P 500 all-time high to the post-crisis trough.', spy_return_pct: -55.19 },
      },
      {
        id: 'scenario_hypothetical_spy', label: 'Hypothetical: SPY -30%', status: 'ready',
        detail: { shock_pct: -30, beta_spy: 0.65, projected_return_pct: -19.5 },
      },
      {
        id: 'scenario_hypothetical_rates', label: 'Hypothetical: rates +200bp', status: 'ready',
        detail: { shock_bps: 200, rate_beta: 0.04, projected_return_pct: -1.36 },
      },
      { id: 'scenario_covid_2020', label: 'March 2020 COVID crash', status: 'awaiting_input', detail: null },
      ...(overrides.metrics || []),
    ],
  }
}

describe('availableScenarios', () => {
  it('only includes scenarios that are ready with a usable market return', () => {
    const scenarios = availableScenarios(signalMetrics())
    expect(scenarios.map((row) => row.id)).toEqual([
      'scenario_gfc_2008', 'scenario_hypothetical_spy',
    ])
  })

  it('excludes the hypothetical rate shock: no per-holding rate beta exists to project through', () => {
    // Only the whole book's beta to TLT is published (rate_beta), not one per holding, so
    // this ranking -- which projects through each holding's own *equity* beta -- must not
    // pretend a rate shock and a market shock use the same beta.
    const scenarios = availableScenarios(signalMetrics())
    expect(scenarios.some((row) => row.id === 'scenario_hypothetical_rates')).toBe(false)
  })

  it('reads spy_return_pct for named scenarios and shock_pct for the hypothetical SPY scenario', () => {
    const scenarios = availableScenarios(signalMetrics())
    expect(scenarios.find((row) => row.id === 'scenario_gfc_2008').marketReturnPct).toBe(-55.19)
    expect(scenarios.find((row) => row.id === 'scenario_hypothetical_spy').marketReturnPct).toBe(-30)
  })

  it('is empty when signalMetrics has not published yet', () => {
    expect(availableScenarios(null)).toEqual([])
    expect(availableScenarios({ metrics: [] })).toEqual([])
  })
})

function position(ticker, beta, { currentValue = 1000, sector = 'technology', allocationPct = 10 } = {}) {
  return { ticker, currentValue, allocationPct, priceInfo: { name: ticker, sector, technical_detail: { beta } } }
}

describe('rankHoldingsByScenario', () => {
  it('projects each holding through its own beta and sorts most-negative first', () => {
    const positions = [position('LOWBETA', 0.3), position('HIGHBETA', 1.8), position('NEGBETA', -0.5)]
    const ranked = rankHoldingsByScenario(positions, -50)
    expect(ranked.map((row) => row.ticker)).toEqual(['HIGHBETA', 'LOWBETA', 'NEGBETA'])
    expect(ranked[0].projectedReturnPct).toBeCloseTo(-90, 5)
    expect(ranked[2].projectedReturnPct).toBeCloseTo(25, 5) // negative beta benefits from a downturn
  })

  it('computes a dollar impact from current value and the projected return', () => {
    const ranked = rankHoldingsByScenario([position('AAPL', 1.0, { currentValue: 2000 })], -10)
    expect(ranked[0].projectedDollarImpact).toBeCloseTo(-200, 5)
  })

  it('drops a holding with no measured beta rather than guessing one', () => {
    const positions = [position('AAPL', 1.0), { ticker: 'NEWCO', currentValue: 500, priceInfo: {} }]
    const ranked = rankHoldingsByScenario(positions, -20)
    expect(ranked.map((row) => row.ticker)).toEqual(['AAPL'])
  })

  it('is empty without a finite market return', () => {
    expect(rankHoldingsByScenario([position('AAPL', 1.0)], null)).toEqual([])
    expect(rankHoldingsByScenario([position('AAPL', 1.0)], undefined)).toEqual([])
  })
})

describe('portfolioProjectedImpact', () => {
  it('value-weights the per-holding projections into one portfolio-level read', () => {
    const ranked = rankHoldingsByScenario(
      [position('A', 1.0, { currentValue: 1000 }), position('B', 0.0, { currentValue: 1000 })], -10)
    const impact = portfolioProjectedImpact(ranked)
    // A loses 10% of 1000 = -100; B is flat. Weighted return over 2000 total = -5%.
    expect(impact.weightedReturnPct).toBeCloseTo(-5, 5)
    expect(impact.totalDollarImpact).toBeCloseTo(-100, 5)
    expect(impact.positionsIncluded).toBe(2)
  })

  it('excludes unpriced holdings from the weighting rather than treating them as zero value', () => {
    const ranked = [
      { ticker: 'A', currentValue: 1000, projectedReturnPct: -10, projectedDollarImpact: -100 },
      { ticker: 'B', currentValue: null, projectedReturnPct: -50, projectedDollarImpact: null },
    ]
    const impact = portfolioProjectedImpact(ranked)
    expect(impact.positionsIncluded).toBe(1)
    expect(impact.weightedReturnPct).toBeCloseTo(-10, 5)
  })

  it('is null when nothing is priced', () => {
    expect(portfolioProjectedImpact([])).toBeNull()
  })
})
