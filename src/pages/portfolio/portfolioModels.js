// Pure derivations behind the portfolio pages: prices, enriched holdings, and the
// benchmark series the analytics and performance views compare against. No React here —
// `Portfolio.jsx` calls these in order (prices → holdings → benchmarks) and hands the
// results to the view components.

import { getRecommendation } from '../../lib/recommendation'
import { stopLossLevels, withStopLoss } from '../../lib/positionRisk'
import { assessPortfolioExposure } from '../../lib/portfolioExposure'
import {
  benchmarkAlternative,
  portfolioFixedBasisVsBenchmark,
  portfolioGrowthSeries,
  portfolioVsBenchmark,
} from '../../lib/portfolioPerformance'
import { buildPortfolioPriceData, mergePortfolioQuotes, mergePositionSnapshots } from '../../lib/portfolioPosition'
import { buildRatingContext, researchRating } from '../../lib/researchRating.js'
import {
  BENCHMARKS,
  benchmarkHistoryFromSnapshot,
  sectorLookThrough,
  weightedExpenseRatio,
} from '../../lib/portfolioAnalytics.js'
import { dailyMoveForPosition } from '../../lib/marketPresentation.js'
import { buildPeerIndex } from '../../lib/rankingModels.js'
import { styleOf } from '../../lib/portfolioStyleTilt.js'
import { recentReturn } from './format.js'

export function asValueSeries(history, limit = null) {
  if (!history?.dates?.length) return null
  const start = limit ? Math.max(0, history.dates.length - limit) : 0
  return {
    dates: history.dates.slice(start),
    values: (history.values || history.closes || []).slice(start),
    frequency: history.frequency || 'daily',
    source: history.source || history.symbol || null,
    symbol: history.symbol || null,
    label: history.label || null,
    methodology: history.methodology,
  }
}

/**
 * Unions two value series for the same instrument, newest source winning on shared dates.
 *
 * `etf/<SYMBOL>.json` and the advisor snapshot's own benchmark tape are written by different
 * pipeline steps and do not land on the same session: the ETF file has been observed ending
 * two sessions behind the advisor's tape despite being generated later in the same run.
 * Whichever is used alone silently caps every window measured against it - which is what held
 * the tear sheet at 19 daily returns while the dashboard had 20. Both carry the same adjusted
 * closes on every overlapping date, so a union is a gap fill, not a splice of two price bases.
 * Callers must only pass series for the same symbol.
 */
export function unionValueSeries(primary, secondary) {
  if (!primary?.dates?.length) return secondary || null
  if (!secondary?.dates?.length) return primary
  const merged = new Map()
  secondary.dates.forEach((date, index) => { merged.set(date, secondary.values[index]) })
  primary.dates.forEach((date, index) => { merged.set(date, primary.values[index]) })
  const dates = [...merged.keys()].sort()
  return { ...primary, dates, values: dates.map((date) => merged.get(date)) }
}

export function sliceSeriesBefore(series, cutoffDate) {
  if (!series?.dates?.length) return null
  const end = series.dates.findIndex((date) => date >= cutoffDate)
  if (end < 2) return null
  return { ...series, dates: series.dates.slice(0, end), values: series.values.slice(0, end), coverage: series.coverage?.slice(0, end) }
}

/**
 * Resolves the price each holding is marked at, preferring a live quote refresh over the
 * published research snapshot when it is genuinely newer.
 */
export function buildPriceModel({ data, positions, quotes }) {
  const research = data?.research || []
  const portfolioCoverage = data?.portfolio_coverage || []
  const screenUniverse = data?.screen_universe || []
  // Lightweight screen rows are a useful quote fallback for a holding that has been
  // fetched but has not reached full published coverage yet (EXPE is one such case).
  // Full coverage is listed last so it always wins when both versions exist.
  const publishedPriceData = mergePositionSnapshots(
    buildPortfolioPriceData(screenUniverse, portfolioCoverage, research),
    positions,
    data?.generated_at,
  )
  const quoteRefreshIsNewest = quotes.fetchedAt
    && new Date(quotes.fetchedAt) >= new Date(data?.generated_at || 0)
  return {
    priceData: mergePortfolioQuotes(publishedPriceData, quoteRefreshIsNewest ? quotes.quotes : {}),
    pricesUpdatedAt: quoteRefreshIsNewest ? quotes.fetchedAt : data?.generated_at,
    // Tagged the same way mergePortfolioQuotes tags a holding's live quote, since this is the
    // raw Netlify-function payload rather than something already run through that merge.
    benchmarkQuote: quoteRefreshIsNewest && quotes.quotes?.SPY
      ? { ...quotes.quotes.SPY, portfolioQuote: true }
      : null,
  }
}

/**
 * Turns stored positions plus resolved prices into everything the Summary view renders:
 * enriched rows, account totals, allocation splits, and the benchmark comparisons.
 */
export function buildHoldingsModel({ data, positions, priceData, etfData }) {
  const research = data?.research || []
  const benchmarkHistory = data?.benchmark_history

  const portfolioStats = positions.reduce((acc, pos) => {
    const ticker = String(pos.ticker || '').trim().toUpperCase()
    const current = priceData[ticker]
    const currentPrice = current?.price ?? pos.snapshotPrice ?? null
    const totalCost = pos.shares * pos.costBasis
    const currentValue = current?.positionSnapshot && pos.snapshotValue != null
      ? Number(pos.snapshotValue)
      : current?.price != null
      ? pos.shares * current.price
      : pos.snapshotValue ?? (currentPrice == null ? null : pos.shares * currentPrice)
    const gain = currentValue == null ? null : currentValue - totalCost
    const trendValues = current?.history?.closes?.filter(Number.isFinite).slice(-22) || []
    const gainPct = gain == null || !totalCost ? null : (gain / totalCost) * 100
    const riskPosition = { gainPct, currentPrice, costBasis: pos.costBasis, purchaseDate: pos.purchaseDate, priceInfo: current }
    const recommendation = current
      ? withStopLoss(getRecommendation(current), riskPosition)
      : null
    const enriched = {
      ...pos,
      ticker,
      currentPrice,
      totalCost,
      currentValue,
      gain,
      gainPct,
      trendValues,
      trendPct: recentReturn(trendValues),
      quoteSource: current?.portfolioQuote
        ? 'Portfolio price refresh'
        : current?.price ? 'Research refresh' : pos.snapshotPrice ? pos.snapshotSource : null,
      priceInfo: current,
      recommendation,
      stopLoss: current ? stopLossLevels(riskPosition) : null,
      versusBenchmark: benchmarkAlternative({ ...pos, currentValue }, benchmarkHistory),
    }
    return {
      totalCost: acc.totalCost + totalCost,
      totalValue: acc.totalValue + (currentValue || 0),
      totalGain: acc.totalGain + (gain || 0),
      positions: [...acc.positions, enriched],
    }
  }, { totalCost: 0, totalValue: 0, totalGain: 0, positions: [] })

  // Same percentile-based -5..+5 read used on the Research page (src/lib/researchRating.js),
  // built from the published research pool so a holding rates against the same peers there.
  const ratingContext = buildRatingContext(research)
  const portfolioPositions = portfolioStats.positions.map((position) => ({
    ...position,
    allocationPct: portfolioStats.totalValue > 0 && position.currentValue != null ? position.currentValue / portfolioStats.totalValue * 100 : null,
    rating: researchRating(position.priceInfo, ratingContext),
    dayMove: dailyMoveForPosition(position),
  }))
  const pricedAccountValue = portfolioStats.totalValue
  const etfTickers = new Set((etfData?.etfs || []).map((row) => String(row.ticker || '').toUpperCase()))
  const stylePeerIndex = buildPeerIndex(research.filter((row) => !row.is_etf))
  const assetTotals = portfolioPositions.reduce((totals, position) => {
    if (!(position.currentValue > 0)) return totals
    const bucket = etfTickers.has(position.ticker)
      ? 'ETFs'
      : styleOf(stylePeerIndex, position.priceInfo) === 'short_term'
        ? 'Short-term stocks'
        : 'Long-term stocks'
    totals[bucket] = (totals[bucket] || 0) + position.currentValue
    return totals
  }, {})
  const assetAllocation = ['Long-term stocks', 'Short-term stocks', 'ETFs']
    .filter((label) => assetTotals[label] > 0)
    .map((label) => ({
      label,
      value: assetTotals[label],
      pct: pricedAccountValue > 0 ? assetTotals[label] / pricedAccountValue * 100 : 0,
    }))
  const sectorAllocation = sectorLookThrough(portfolioPositions, etfData?.etfs || []).exposures
    .map((row) => ({ sector: row.label, pct: row.pct }))
  const fundCost = weightedExpenseRatio(portfolioPositions, etfData?.etfs || [])

  const basis = data?.hypothetical_basis || 500
  return {
    portfolioStats,
    portfolioPositions,
    assetAllocation,
    sectorAllocation,
    fundCost,
    basis,
    benchmarkHistory,
    versusIndex: portfolioVsBenchmark(portfolioPositions, benchmarkHistory),
    fixedBasisTotal: portfolioFixedBasisVsBenchmark(portfolioStats.positions, priceData, benchmarkHistory, basis),
    growth: portfolioGrowthSeries(portfolioStats.positions, priceData, benchmarkHistory),
    actionable: portfolioPositions.filter((pos) => pos.recommendation?.action === 'SELL'),
    exposure: assessPortfolioExposure(portfolioPositions),
  }
}

/**
 * Picks the benchmark the analytics and performance views compare against, plus the
 * candidate set the best-fit statistic searches over.
 */
export function buildBenchmarkModel({ data, snapshots }) {
  const reportBenchmarkSeries = asValueSeries(data?.benchmark_analytics_history, 504)
  const candidateInputs = [
    { symbol: 'SPY', label: 'S&P 500', snapshot: snapshots.spy },
    { symbol: 'RSP', label: 'Equal-weight S&P 500', snapshot: snapshots.rsp },
    { symbol: 'IWM', label: 'Russell 2000', snapshot: snapshots.iwm },
    { symbol: 'IJR', label: 'S&P SmallCap 600', snapshot: snapshots.ijr },
  ].map(({ symbol, label, snapshot }) => {
    const series = asValueSeries(benchmarkHistoryFromSnapshot(snapshot), 504)
    if (!series) return null
    // Same gap fill as the selected benchmark below, for the same reason: the fit search
    // needs 21 overlapping dates, and an ETF file two sessions behind the portfolio left
    // every candidate one short. Only the candidate the report tape actually describes can
    // be extended - the others have no second source and stay as published.
    const extended = reportBenchmarkSeries?.symbol === symbol
      ? unionValueSeries(series, reportBenchmarkSeries)
      : series
    return { ...extended, symbol, label }
  }).filter(Boolean)
  const selectedPublished = asValueSeries(benchmarkHistoryFromSnapshot(snapshots.selected), 504)
  const selectedBenchmarkSymbol = selectedPublished?.symbol || reportBenchmarkSeries?.symbol || 'SPY'
  // Only when both tapes describe the same instrument - picking a different benchmark must
  // never quietly graft the report's SPY history onto it.
  const analyticsBenchmarkSeries = selectedPublished && reportBenchmarkSeries?.symbol === selectedPublished.symbol
    ? unionValueSeries(selectedPublished, reportBenchmarkSeries)
    : selectedPublished || reportBenchmarkSeries
  return {
    candidateInputs,
    selectedBenchmarkSymbol,
    selectedBenchmarkLabel: BENCHMARKS.find((row) => row.symbol === selectedBenchmarkSymbol)?.label
      || candidateInputs.find((row) => row.symbol === selectedBenchmarkSymbol)?.label
      || selectedBenchmarkSymbol,
    analyticsBenchmarkSeries,
  }
}
