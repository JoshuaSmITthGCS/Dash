import { describe, expect, it } from 'vitest'
import { aggregateThemeExposure, factorRegression } from './factorAnalytics.js'

function factorFixture(count = 30) {
  const observations = Array.from({ length: count }, (_, index) => {
    const year = 2022 + Math.floor(index / 12)
    const month = String(index % 12 + 1).padStart(2, '0')
    return {
      month: `${year}-${month}`,
      market_excess: Math.sin(index * 1.1) * 0.02,
      size: Math.cos(index * 0.7) * 0.015,
      value: Math.sin(index * 0.5 + 1) * 0.012,
      profitability: Math.cos(index * 1.3 + 0.2) * 0.01,
      investment: Math.sin(index * 1.7 + 0.5) * 0.009,
      momentum: Math.cos(index * 1.9 + 0.8) * 0.014,
      risk_free: 0.002,
    }
  })
  const values = [100]
  observations.forEach((row) => {
    const excess = 0.001 + 1.1 * row.market_excess - 0.3 * row.size - 0.4 * row.value
      + 0.5 * row.profitability + 0.1 * row.investment + 0.2 * row.momentum
    values.push(values.at(-1) * (1 + row.risk_free + excess))
  })
  const prior = { month: '2021-12' }
  return {
    payload: { observations },
    series: { dates: [prior, ...observations].map((row) => `${row.month}-28`), values },
  }
}

describe('factor analytics', () => {
  it('gates regression until 24 monthly observations exist', () => {
    const fixture = factorFixture(12)
    expect(factorRegression(fixture.series, fixture.payload)).toMatchObject({ available: false, observations: 12, requiredObservations: 24 })
  })

  it('recovers six-factor loadings and regression diagnostics', () => {
    const fixture = factorFixture()
    const result = factorRegression(fixture.series, fixture.payload)
    expect(result.available).toBe(true)
    expect(result.loadings.market_excess).toBeCloseTo(1.1, 6)
    expect(result.loadings.value).toBeCloseTo(-0.4, 6)
    expect(result.rSquared).toBeCloseTo(1, 8)
    expect(result.alphaAnnualPct).toBeCloseTo(1.2, 6)
  })

  it('matches an independently calculated Newey-West HAC reference', () => {
    const observations = Array.from({ length: 60 }, (_, index) => ({
      month: `${2020 + Math.floor(index / 12)}-${String(index % 12 + 1).padStart(2, '0')}`,
      market_excess: Math.sin(index * 1.1) * 0.02,
      size: Math.cos(index * 0.7) * 0.015,
      value: Math.sin(index * 0.5 + 1) * 0.012,
      profitability: Math.cos(index * 1.3 + 0.2) * 0.01,
      investment: Math.sin(index * 1.7 + 0.5) * 0.009,
      momentum: Math.cos(index * 1.9 + 0.8) * 0.014,
      risk_free: 0.002,
    }))
    const values = [100]
    let residual = 0
    observations.forEach((row, index) => {
      residual = 0.55 * residual + Math.sin(index * 0.37) * 0.0015
      const excess = 0.001 + 1.1 * row.market_excess - 0.3 * row.size - 0.4 * row.value
        + 0.5 * row.profitability + 0.1 * row.investment + 0.2 * row.momentum + residual
      values.push(values.at(-1) * (1 + row.risk_free + excess))
    })
    const result = factorRegression({
      dates: ['2019-12-28', ...observations.map((row) => `${row.month}-28`)],
      values,
    }, { observations })
    const carhart = result.models.find((model) => model.id === 'carhart4')
    // Reference: independent NumPy sandwich covariance with Bartlett weights, lag 3,
    // and n/(n-k) finite-sample correction (same settings as statsmodels HAC use_correction).
    expect(carhart.alphaAnnualPct).toBeCloseTo(1.6355911975, 8)
    expect(carhart.alphaTStatistic).toBeCloseTo(2.4894066167, 8)
    expect(carhart.standardErrors.market_excess).toBeCloseTo(0.0532338031, 8)
    expect(carhart.rSquared).toBeCloseTo(0.9391127861, 8)
    expect(carhart.hacLag).toBe(3)
  })

  it('aggregates theme scores independently by portfolio weight', () => {
    const result = aggregateThemeExposure([
      { ticker: 'AAA', currentValue: 75 },
      { ticker: 'BBB', currentValue: 25 },
    ], {
      AAA: [{ theme: 'AI', score: 80 }],
      BBB: [{ theme: 'AI', score: 40 }],
    })
    expect(result[0]).toMatchObject({ theme: 'AI', exposureScore: 70, portfolioCoveragePct: 100 })
  })

  it('reads the theme keys the pipeline actually publishes', () => {
    // theme_screen.by_ticker entries are {theme_id, display_name, theme_exposure_score, ...}.
    // Matching only on `theme`/`score` resolved nothing, so a fully populated payload
    // rendered the portfolio lens's "unavailable" branch.
    const result = aggregateThemeExposure([
      { ticker: 'AAA', currentValue: 60 },
      { ticker: 'BBB', currentValue: 40 },
    ], {
      AAA: [{ theme_id: 'ai_infrastructure', display_name: 'AI Infrastructure Buildout', theme_exposure_score: 90 }],
      BBB: [{ theme_id: 'ai_infrastructure', display_name: 'AI Infrastructure Buildout', theme_exposure_score: 40 }],
    })
    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({
      theme: 'AI Infrastructure Buildout', exposureScore: 70, portfolioCoveragePct: 100,
    })
  })

  it('covers only the weight of positions that actually carry the theme', () => {
    const result = aggregateThemeExposure([
      { ticker: 'AAA', currentValue: 25 },
      { ticker: 'BBB', currentValue: 75 },
    ], {
      AAA: [{ theme_id: 'grid', display_name: 'Grid', theme_exposure_score: 80 }],
    })
    expect(result[0]).toMatchObject({ theme: 'Grid', exposureScore: 80, portfolioCoveragePct: 25 })
  })
})
