/**
 * Explains a portfolio's move on its most recent trading day: how much came from the
 * market, how much was stock-specific, and which holdings drove it.
 *
 * Every published research row already carries a beta (advisor_engine.technical_factors,
 * pipeline/technical_indicators.py), so this reuses that rather than estimating a new one.
 * The decomposition is a single-factor (CAPM-style) split, not a full sector/style
 * attribution: for each holding,
 *
 *   contribution        = weight * holding_return
 *   market_component     = weight * beta * benchmark_return
 *   idiosyncratic_component = contribution - market_component
 *
 * so market_component + idiosyncratic_component always reconciles exactly to
 * total contribution (and the sum of every holding's contribution reconciles to the
 * portfolio's total return) -- this is arithmetic identity, not a fitted model. A true
 * sector-factor decomposition would need daily sector-index returns, which this codebase
 * does not fetch anywhere; the sector breakdown below is a within-portfolio grouping of the
 * idiosyncratic component, not a market sector benchmark, and is labeled as such.
 *
 * News-driven catalyst attribution (linking a move to a specific headline) needs the event
 * classification work planned for a later phase (docs/CHANGELOG-QUANT-UPGRADE.md) and is not
 * available yet -- catalysts is always [] with an explicit status, never guessed.
 */

const finite = (value) => typeof value === 'number' && Number.isFinite(value)

function latestDailyReturnPct(history) {
  const closes = history?.closes || []
  if (closes.length < 2 || !finite(closes.at(-2)) || !closes.at(-2)) return null
  return (closes.at(-1) / closes.at(-2) - 1) * 100
}

function benchmarkDailyReturnPct(benchmarkHistory) {
  return latestDailyReturnPct(benchmarkHistory)
}

export function explainPortfolioMove(positions = [], benchmarkHistory = null, { defaultBeta = 1 } = {}) {
  const benchmarkReturnPct = benchmarkDailyReturnPct(benchmarkHistory)
  if (benchmarkReturnPct == null) {
    return {
      available: false,
      reason: 'No benchmark price history available for today - market/idiosyncratic split cannot be computed without it.',
      holdings: [], totalReturnPct: null, marketPct: null, idiosyncraticPct: null,
      topContributors: [], topDetractors: [], sectorBreakdown: [],
      catalysts: [], catalystStatus: 'not_available_this_phase',
    }
  }

  const holdings = positions
    .filter((position) => finite(position.allocationPct) && position.allocationPct > 0)
    .map((position) => {
      const dailyReturnPct = latestDailyReturnPct(position.priceInfo?.history)
      const weight = position.allocationPct / 100
      const beta = finite(position.priceInfo?.technical_detail?.beta)
        ? position.priceInfo.technical_detail.beta
        : defaultBeta
      const betaIsAssumed = !finite(position.priceInfo?.technical_detail?.beta)
      if (dailyReturnPct == null) {
        return {
          ticker: position.ticker, name: position.name || position.priceInfo?.name || position.ticker,
          sector: position.priceInfo?.sector || 'Unclassified', weight, dailyReturnPct: null,
          contributionPct: null, marketComponentPct: null, idiosyncraticComponentPct: null,
          beta, betaIsAssumed, available: false,
        }
      }
      const contributionPct = weight * dailyReturnPct
      const marketComponentPct = weight * beta * benchmarkReturnPct
      const idiosyncraticComponentPct = contributionPct - marketComponentPct
      return {
        ticker: position.ticker, name: position.name || position.priceInfo?.name || position.ticker,
        sector: position.priceInfo?.sector || 'Unclassified', weight, dailyReturnPct,
        contributionPct, marketComponentPct, idiosyncraticComponentPct, beta, betaIsAssumed, available: true,
      }
    })

  const priced = holdings.filter((holding) => holding.available)
  const totalReturnPct = priced.reduce((sum, holding) => sum + holding.contributionPct, 0)
  const marketPct = priced.reduce((sum, holding) => sum + holding.marketComponentPct, 0)
  const idiosyncraticPct = priced.reduce((sum, holding) => sum + holding.idiosyncraticComponentPct, 0)

  const bySector = new Map()
  for (const holding of priced) {
    const current = bySector.get(holding.sector) || { sector: holding.sector, idiosyncraticContributionPct: 0, holdingCount: 0 }
    current.idiosyncraticContributionPct += holding.idiosyncraticComponentPct
    current.holdingCount += 1
    bySector.set(holding.sector, current)
  }
  const sectorBreakdown = [...bySector.values()].sort(
    (left, right) => Math.abs(right.idiosyncraticContributionPct) - Math.abs(left.idiosyncraticContributionPct),
  )

  const ranked = priced.slice().sort((left, right) => right.contributionPct - left.contributionPct)

  return {
    available: true,
    benchmarkReturnPct,
    holdings,
    unpriced: holdings.filter((holding) => !holding.available).map((holding) => holding.ticker),
    totalReturnPct, marketPct, idiosyncraticPct,
    // Exact by construction (sum of two exhaustive components of every holding's exact
    // contribution) - included so a consumer can assert reconciliation rather than trust it.
    reconciles: Math.abs((marketPct + idiosyncraticPct) - totalReturnPct) < 1e-9,
    topContributors: ranked.filter((holding) => holding.contributionPct > 0).slice(0, 5),
    topDetractors: ranked.filter((holding) => holding.contributionPct < 0).slice(-5).reverse(),
    sectorBreakdown,
    catalysts: [], catalystStatus: 'not_available_this_phase',
  }
}
