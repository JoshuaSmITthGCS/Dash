/**
 * Reconstructs the annualized mean/volatility parameters that drive the planner's Monte
 * Carlo simulation algebraically from the same Sharpe, Sortino, Lo-adjusted Sortino, and
 * Calmar ratios shown on the portfolio Overview panel, rather than resampling the observed
 * daily series directly. `performanceMetrics` and `performanceStatistics` are the exact
 * functions (and the exact portfolio period) that produce those displayed numbers, so the
 * ratio on screen and the ratio driving the simulation never diverge.
 */
import { performanceMetrics, riskFreeAnnualRate, selectPeriod } from './portfolioAnalytics.js'
import { performanceStatistics } from './portfolioStatistics.js'

const finite = (value) => value !== null && value !== '' && Number.isFinite(Number(value))

export function derivePortfolioRiskProfile(portfolioSeries, data) {
  const portfolioPeriod = selectPeriod(portfolioSeries, 'All')
  if (!portfolioPeriod) return { available: false, reason: 'Portfolio return history is required.' }

  const riskFree = riskFreeAnnualRate(data)
  const performance = performanceMetrics(portfolioPeriod, null, riskFree.annualPct)
  if (!performance.available) return { available: false, reason: performance.reason }

  const statistics = performanceStatistics(portfolioPeriod, riskFree.annualPct)
  const annualReturn = performance.annualizedReturn / 100
  const riskFreeRate = riskFree.annualPct / 100
  const excessReturn = annualReturn - riskFreeRate

  // Sharpe = excess return / total volatility, so total volatility = excess return / Sharpe.
  const sharpeVolAnnual = finite(performance.sharpe) && performance.sharpe !== 0
    ? Math.abs(excessReturn / performance.sharpe)
    : null
  // Sortino = excess return / downside deviation, so downside deviation = excess return / Sortino.
  const naiveSortinoDownsideVolAnnual = finite(performance.sortino) && performance.sortino !== 0
    ? Math.abs(excessReturn / performance.sortino)
    : sharpeVolAnnual
  const loAdjustedSortino = statistics?.available ? statistics.loAdjustedSortino : null
  const loSortinoDownsideVolAnnual = finite(loAdjustedSortino) && loAdjustedSortino !== 0
    ? Math.abs(excessReturn / loAdjustedSortino)
    : null
  // Lo's autocorrelation-aware annualization only widens the honest estimate of downside risk
  // when return smoothing makes the naive figure understate it - it is never used to narrow it.
  const downsideVolAnnual = loSortinoDownsideVolAnnual != null
    ? Math.max(loSortinoDownsideVolAnnual, naiveSortinoDownsideVolAnnual)
    : naiveSortinoDownsideVolAnnual

  // Calmar = annualized return / |max drawdown|, so max drawdown = annualized return / Calmar.
  const impliedMaxDrawdown = finite(performance.calmar) && performance.calmar !== 0
    ? Math.abs(annualReturn / performance.calmar)
    : finite(performance.maxDrawdown) ? Math.abs(performance.maxDrawdown) / 100 : null

  // Split-normal (two-piece) calibration: the downside standard deviation comes from Sortino,
  // and the upside standard deviation is solved so the blended variance matches the
  // Sharpe-implied total volatility - (down^2 + up^2) / 2 ~= total^2 for a centered split
  // normal - which keeps the asymmetry of the observed track record instead of assuming
  // symmetric returns.
  const totalVolAnnual = sharpeVolAnnual != null
    ? Math.max(sharpeVolAnnual, (downsideVolAnnual || 0) * 0.5)
    : downsideVolAnnual
  const upsideVolAnnual = totalVolAnnual != null && downsideVolAnnual != null
    ? Math.sqrt(Math.max(0, 2 * totalVolAnnual ** 2 - downsideVolAnnual ** 2))
    : totalVolAnnual

  return {
    available: true,
    observations: performance.observations,
    startDate: portfolioPeriod.startDate,
    endDate: portfolioPeriod.endDate,
    annualReturn,
    riskFreeRate,
    sharpe: performance.sharpe,
    sortino: performance.sortino,
    loAdjustedSortino,
    loAdjusted: loSortinoDownsideVolAnnual != null,
    calmar: performance.calmar,
    downsideVolAnnual,
    upsideVolAnnual,
    impliedMaxDrawdown,
    confidence: performance.observations >= 253 ? 'full' : performance.observations >= 60 ? 'moderate' : 'limited',
  }
}
