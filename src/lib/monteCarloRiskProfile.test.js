import { describe, expect, it } from 'vitest'
import { derivePortfolioRiskProfile } from './monteCarloRiskProfile.js'

function dailySeries(days, drift = 0.003, wobble = 0.01) {
  const dates = []
  const values = []
  let value = 100
  const start = Date.UTC(2026, 0, 1)
  for (let index = 0; index < days; index += 1) {
    const day = new Date(start + index * 86400000)
    if (day.getUTCDay() === 0 || day.getUTCDay() === 6) continue
    dates.push(day.toISOString().slice(0, 10))
    values.push(value)
    const wave = Math.sin(index * 0.9) * wobble
    value *= 1 + drift + wave
  }
  return { dates, values }
}

describe('derivePortfolioRiskProfile', () => {
  it('reports unavailable below the 20-observation gate', () => {
    const profile = derivePortfolioRiskProfile(dailySeries(10), null)
    expect(profile.available).toBe(false)
    expect(profile.reason).toBeTruthy()
  })

  it('derives finite Sharpe/Sortino/Calmar-consistent parameters once enough daily history exists', () => {
    const series = dailySeries(40)
    const profile = derivePortfolioRiskProfile(series, null)
    expect(profile.available).toBe(true)
    expect(profile.observations).toBeGreaterThanOrEqual(20)
    expect(Number.isFinite(profile.sharpe)).toBe(true)
    expect(Number.isFinite(profile.sortino)).toBe(true)
    expect(Number.isFinite(profile.calmar)).toBe(true)
    expect(Number.isFinite(profile.annualReturn)).toBe(true)
    expect(profile.downsideVolAnnual).toBeGreaterThan(0)
    expect(profile.upsideVolAnnual).toBeGreaterThan(0)
    expect(profile.impliedMaxDrawdown).toBeGreaterThanOrEqual(0)
    // Calmar = annualReturn / |maxDrawdown|, so the implied drawdown must invert it back out.
    expect(profile.impliedMaxDrawdown).toBeCloseTo(Math.abs(profile.annualReturn / profile.calmar), 6)
  })

  it('leaves the Lo-adjusted Sortino unavailable below 253 returns and does not shrink downside volatility because of it', () => {
    const series = dailySeries(40)
    const profile = derivePortfolioRiskProfile(series, null)
    expect(profile.loAdjusted).toBe(false)
    expect(profile.loAdjustedSortino).toBeNull()
    const naiveSortinoDownsideVol = Math.abs(profile.annualReturn / profile.sortino)
    expect(profile.downsideVolAnnual).toBeCloseTo(naiveSortinoDownsideVol, 6)
  })
})
