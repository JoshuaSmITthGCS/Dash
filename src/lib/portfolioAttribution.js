/**
 * Explains a portfolio's move over a chosen window - today, the past week, month, three
 * months or year: how much came from the market, how much was stock-specific, and which
 * holdings drove it.
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
 *
 * daily_return_pct prefers a live quote (price vs. previousClose, fetched via
 * usePortfolioQuotes) over the pipeline snapshot's history.closes whenever one has been
 * fetched for that symbol -- otherwise this widget would show a stale close-to-close move
 * for a holding priced live everywhere else on the page. Same preference applies to the
 * benchmark leg via the optional `benchmarkQuote` option.
 *
 * ## Windows longer than one day
 *
 * Two things change, both because weight drift stops being negligible past a single session:
 *
 * 1. Weights are taken at the *start* of the window (today's share count valued at the
 *    window's opening close), not at today's prices. Sum(w0 * r) is then exactly the
 *    buy-and-hold return of the current basket across the window; using today's weights
 *    would double-count the winners, since a name is heavy today partly *because* it rose.
 *    Whether that basis was usable is reported as `weightBasis`, never assumed.
 * 2. The window's start date is resolved from published closes, not from a fixed number of
 *    points: `benchmark_history` is daily only for the recent stretch and roughly
 *    fortnightly further back, so the Nth point from the end is not a fixed span of time.
 *    The resolved `startDate`/`endDate`/`spanDays` are published so the label can state the
 *    window actually measured rather than the one requested.
 *
 * Beta is still a single published number applied across the whole window, and holdings
 * bought mid-window are measured as though held throughout (their count is reported as
 * `partialHoldings`) - both are disclosed in the UI rather than silently smoothed over.
 */

import { closeOnDates } from './portfolioPerformance.js'

const DAY_MS = 24 * 60 * 60 * 1000

/**
 * Calendar-day lookbacks rather than point counts, matching the convention used by
 * PERFORMANCE_PERIOD_MS in portfolioPerformance.js and ZOOM_RANGES in GrowthChart.
 */
export const ATTRIBUTION_PERIODS = [
  { key: '1D', label: '1D', name: 'Today', phrase: 'today', days: null },
  { key: '1W', label: '1W', name: 'Week', phrase: 'this past week', days: 7 },
  { key: '1M', label: '1M', name: 'Month', phrase: 'this past month', days: 31 },
  { key: '3M', label: '3M', name: '3 months', phrase: 'these past 3 months', days: 93 },
  { key: '1Y', label: '1Y', name: 'Year', phrase: 'this past year', days: 366 },
]

const PERIOD_BY_KEY = new Map(ATTRIBUTION_PERIODS.map((entry) => [entry.key, entry]))

const finite = (value) => typeof value === 'number' && Number.isFinite(value)

function latestDailyReturnPct(history) {
  const closes = history?.closes || []
  if (closes.length < 2 || !finite(closes.at(-2)) || !closes.at(-2)) return null
  return (closes.at(-1) / closes.at(-2) - 1) * 100
}

function benchmarkDailyReturnPct(benchmarkHistory) {
  return latestDailyReturnPct(benchmarkHistory)
}

// A live quote (fetched on demand via usePortfolioQuotes / the portfolio-prices Netlify
// function) is today's actual price versus its own previousClose - a true intraday return.
// The pipeline snapshot's history.closes only advances when the research pipeline itself
// refreshes (a few times a day at most), so without this a holding priced live everywhere
// else on the page would still show yesterday's close-to-close move here. Falls back to
// history.closes whenever no live quote has been fetched for that symbol yet.
function liveQuoteDailyReturnPct(quote) {
  if (!quote?.portfolioQuote) return null
  const { price, previousClose } = quote
  if (!finite(price) || !finite(previousClose) || previousClose === 0) return null
  return (price / previousClose - 1) * 100
}

/** The live price itself, used as the closing end of a multi-day window. */
function liveQuotePrice(quote) {
  if (!quote?.portfolioQuote || !finite(quote.price)) return null
  return quote.price
}

const lastFiniteClose = (closes = []) => {
  for (let index = closes.length - 1; index >= 0; index -= 1) {
    if (finite(closes[index])) return closes[index]
  }
  return null
}

const betaOf = (position, defaultBeta) => {
  const published = position.priceInfo?.technical_detail?.beta
  return finite(published)
    ? { beta: published, betaIsAssumed: false }
    : { beta: defaultBeta, betaIsAssumed: true }
}

const identity = (position) => ({
  ticker: position.ticker,
  name: position.name || position.priceInfo?.name || position.ticker,
  sector: position.priceInfo?.sector || 'Unclassified',
})

function unavailable(spec, reason) {
  return {
    available: false,
    reason,
    period: spec.key,
    periodName: spec.name,
    periodPhrase: spec.phrase,
    holdings: [], totalReturnPct: null, marketPct: null, idiosyncraticPct: null,
    topContributors: [], topDetractors: [], sectorBreakdown: [], unpriced: [],
    catalysts: [], catalystStatus: 'not_available_this_phase',
  }
}

/**
 * The last published observation at or before `days` calendar days ago, plus the span that
 * observation actually covers. Returns `truncated` when the published history does not reach
 * back far enough, so a one-year request over eight months of data is labelled rather than
 * quietly relabelled as a year.
 */
function resolveWindow(benchmarkHistory, days) {
  const dates = benchmarkHistory?.dates || []
  const closes = benchmarkHistory?.closes || []
  if (dates.length < 2) return null
  let endIndex = -1
  for (let index = closes.length - 1; index >= 0 && endIndex < 0; index -= 1) {
    if (finite(closes[index])) endIndex = index
  }
  if (endIndex < 1) return null
  const endDate = dates[endIndex]
  const requestedStart = new Date(Date.parse(`${endDate}T00:00:00Z`) - days * DAY_MS)
    .toISOString().slice(0, 10)

  let startIndex = -1
  for (let index = 0; index < endIndex; index += 1) {
    if (dates[index] <= requestedStart && finite(closes[index])) startIndex = index
  }
  const truncated = startIndex < 0
  if (truncated) startIndex = closes.findIndex((close, index) => finite(close) && index < endIndex)
  if (startIndex < 0) return null

  return {
    startDate: dates[startIndex],
    endDate,
    requestedStart,
    requestedDays: days,
    spanDays: Math.round(
      (Date.parse(`${endDate}T00:00:00Z`) - Date.parse(`${dates[startIndex]}T00:00:00Z`)) / DAY_MS,
    ),
    truncated,
  }
}

/** Sector grouping, ranking and reconciliation - shared by every window length. */
function assemble(holdings, benchmarkReturnPct, meta) {
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
    // Share of the portfolio's current value that this split actually measures, so a
    // partially-covered window reads as partial rather than as a smaller total move.
    coveragePct: priced.reduce((sum, holding) => sum + (holding.allocationPct || 0), 0),
    pricedCount: priced.length,
    holdingCount: holdings.length,
    totalReturnPct, marketPct, idiosyncraticPct,
    // Exact by construction (sum of two exhaustive components of every holding's exact
    // contribution) - included so a consumer can assert reconciliation rather than trust it.
    reconciles: Math.abs((marketPct + idiosyncraticPct) - totalReturnPct) < 1e-9,
    topContributors: ranked.filter((holding) => holding.contributionPct > 0).slice(0, 5),
    topDetractors: ranked.filter((holding) => holding.contributionPct < 0).slice(-5).reverse(),
    sectorBreakdown,
    catalysts: [], catalystStatus: 'not_available_this_phase',
    ...meta,
  }
}

/** Today's session: weights are current allocations, returns are close-to-close or live. */
function explainDailyMove(positions, benchmarkHistory, { defaultBeta, benchmarkQuote, spec }) {
  const benchmarkReturnPct = liveQuoteDailyReturnPct(benchmarkQuote) ?? benchmarkDailyReturnPct(benchmarkHistory)
  if (benchmarkReturnPct == null) {
    return unavailable(spec, 'No benchmark price history available for today - market/idiosyncratic split cannot be computed without it.')
  }

  const holdings = positions
    .filter((position) => finite(position.allocationPct) && position.allocationPct > 0)
    .map((position) => {
      const dailyReturnPct = liveQuoteDailyReturnPct(position.priceInfo)
        ?? latestDailyReturnPct(position.priceInfo?.history)
      const weight = position.allocationPct / 100
      const { beta, betaIsAssumed } = betaOf(position, defaultBeta)
      const base = { ...identity(position), allocationPct: position.allocationPct, weight, beta, betaIsAssumed }
      if (dailyReturnPct == null) {
        return {
          ...base, dailyReturnPct: null, returnPct: null,
          contributionPct: null, marketComponentPct: null, idiosyncraticComponentPct: null,
          available: false,
        }
      }
      const contributionPct = weight * dailyReturnPct
      const marketComponentPct = weight * beta * benchmarkReturnPct
      return {
        ...base,
        dailyReturnPct, returnPct: dailyReturnPct,
        contributionPct,
        marketComponentPct,
        idiosyncraticComponentPct: contributionPct - marketComponentPct,
        available: true,
      }
    })

  return assemble(holdings, benchmarkReturnPct, {
    period: spec.key,
    periodName: spec.name,
    periodPhrase: spec.phrase,
    weightBasis: 'current_allocation',
    startDate: null,
    endDate: null,
    spanDays: 1,
    windowTruncated: false,
    partialHoldings: [],
  })
}

/**
 * A multi-day window. Start prices come from published closes at the resolved start date;
 * the end of the window prefers a live quote so the newest session is not missing from a
 * week/month/year read that everything else on the page already reflects.
 */
function explainWindowMove(positions, benchmarkHistory, { defaultBeta, benchmarkQuote, spec }) {
  const window = resolveWindow(benchmarkHistory, spec.days)
  if (!window) {
    return unavailable(spec, `No benchmark price history covering ${spec.phrase} - market/idiosyncratic split cannot be computed without it.`)
  }
  const benchmarkStart = closeOnDates(benchmarkHistory.dates, benchmarkHistory.closes, window.startDate)
  const benchmarkEnd = liveQuotePrice(benchmarkQuote) ?? lastFiniteClose(benchmarkHistory.closes)
  if (!finite(benchmarkStart) || benchmarkStart <= 0 || !finite(benchmarkEnd)) {
    return unavailable(spec, `No benchmark price history covering ${spec.phrase} - market/idiosyncratic split cannot be computed without it.`)
  }
  const benchmarkReturnPct = (benchmarkEnd / benchmarkStart - 1) * 100

  const measured = positions
    .filter((position) => finite(position.allocationPct) && position.allocationPct > 0)
    .map((position) => {
      const history = position.priceInfo?.history
      const startPrice = closeOnDates(history?.dates || [], history?.closes || [], window.startDate)
      const endPrice = liveQuotePrice(position.priceInfo) ?? lastFiniteClose(history?.closes || [])
      const returnPct = finite(startPrice) && startPrice > 0 && finite(endPrice)
        ? (endPrice / startPrice - 1) * 100
        : null
      const shares = Number(position.shares)
      return {
        ...identity(position),
        ...betaOf(position, defaultBeta),
        allocationPct: position.allocationPct,
        startPrice: finite(startPrice) ? startPrice : null,
        endPrice: finite(endPrice) ? endPrice : null,
        returnPct,
        startValue: returnPct != null && Number.isFinite(shares) && shares > 0 ? shares * startPrice : null,
        // A position opened inside the window is still measured across the whole window;
        // flagged rather than dropped, since dropping it would understate the basket.
        partial: Boolean(position.purchaseDate) && String(position.purchaseDate).slice(0, 10) > window.startDate,
      }
    })

  // One weight basis for the whole window, never a mix: blending start-of-period weights for
  // some holdings with today's allocation for others would break the reconciliation identity.
  const priced = measured.filter((row) => row.returnPct != null)
  const startValueTotal = priced.reduce((sum, row) => sum + (row.startValue ?? 0), 0)
  const useStartWeights = priced.length > 0
    && priced.every((row) => row.startValue != null)
    && startValueTotal > 0

  const holdings = measured.map((row) => {
    const { startValue, partial, ...rest } = row
    const weight = useStartWeights ? startValue / startValueTotal : row.allocationPct / 100
    if (row.returnPct == null) {
      return {
        ...rest, partial, weight: null, dailyReturnPct: null,
        contributionPct: null, marketComponentPct: null, idiosyncraticComponentPct: null,
        available: false,
      }
    }
    const contributionPct = weight * row.returnPct
    const marketComponentPct = weight * row.beta * benchmarkReturnPct
    return {
      ...rest, partial, weight,
      // Mirrored so a consumer written against the daily shape keeps working; over a longer
      // window this is the window's return, not one session's.
      dailyReturnPct: row.returnPct,
      contributionPct,
      marketComponentPct,
      idiosyncraticComponentPct: contributionPct - marketComponentPct,
      available: true,
    }
  })

  return assemble(holdings, benchmarkReturnPct, {
    period: spec.key,
    periodName: spec.name,
    periodPhrase: spec.phrase,
    weightBasis: useStartWeights ? 'start_of_period' : 'current_allocation',
    startDate: window.startDate,
    endDate: window.endDate,
    requestedDays: window.requestedDays,
    spanDays: window.spanDays,
    windowTruncated: window.truncated,
    partialHoldings: holdings.filter((holding) => holding.available && holding.partial).map((holding) => holding.ticker),
  })
}

export function explainPortfolioMove(positions = [], benchmarkHistory = null,
                                     { defaultBeta = 1, benchmarkQuote = null, period = '1D' } = {}) {
  const spec = PERIOD_BY_KEY.get(period) || PERIOD_BY_KEY.get('1D')
  const options = { defaultBeta, benchmarkQuote, spec }
  return spec.days == null
    ? explainDailyMove(positions, benchmarkHistory, options)
    : explainWindowMove(positions, benchmarkHistory, options)
}
