// Splits the account into the holdings the model currently ranks and everything else, so the
// live record can say how much of it measures ValueSignal and how much measures the owner's
// own picks. "On-model" means the ticker is in advisor.json's published `research` list (the
// ranked leaderboard); a trailing-stop SELL flag on a position does not move it out of that
// group, because the stop is position risk, not the model's view of the company.

import { annualizedVolatility, currentHoldingsSeries, maximumDrawdown } from './portfolioAnalytics.js'

const finite = (value) => value != null && Number.isFinite(Number(value))
const upper = (value) => String(value || '').trim().toUpperCase()

/** ticker -> 1-based rank in the published research list. */
export function modelRanks(research = []) {
  const ranks = new Map()
  research.forEach((row, index) => {
    const ticker = upper(row?.ticker)
    if (ticker && !ranks.has(ticker)) ranks.set(ticker, index + 1)
  })
  return ranks
}

function closeOnOrBefore(history, date) {
  let found = null
  ;(history?.dates || []).forEach((day, index) => {
    const close = history.closes?.[index]
    if (day <= date && finite(close)) found = Number(close)
  })
  return found
}

function closeOnOrAfter(history, date) {
  const dates = history?.dates || []
  for (let index = 0; index < dates.length; index += 1) {
    const close = history.closes?.[index]
    if (dates[index] >= date && finite(close)) return Number(close)
  }
  return null
}

function groupSummary(id, label, rows, totalValue, priceData, benchmarkHistory) {
  const value = rows.reduce((sum, row) => sum + (finite(row.currentValue) ? Number(row.currentValue) : 0), 0)
  const cost = rows.reduce((sum, row) => sum + (finite(row.totalCost) ? Number(row.totalCost) : 0), 0)
  const gain = value - cost
  const series = rows.length ? currentHoldingsSeries(rows, priceData, benchmarkHistory?.dates || []) : null
  const daily = series?.frequency === 'daily'
  let replay = null
  if (series?.values?.length > 1) {
    const start = series.dates[0]
    const end = series.dates.at(-1)
    const returnPct = (series.values.at(-1) / series.values[0] - 1) * 100
    const benchStart = closeOnOrAfter(benchmarkHistory, start)
    const benchEnd = closeOnOrBefore(benchmarkHistory, end)
    const benchmarkPct = benchStart && benchEnd ? (benchEnd / benchStart - 1) * 100 : null
    replay = {
      start,
      end,
      observations: series.values.length,
      returnPct,
      benchmarkPct,
      excessPct: benchmarkPct == null ? null : returnPct - benchmarkPct,
      volatilityPct: daily ? annualizedVolatility(series.values) : null,
      maxDrawdownPct: maximumDrawdown(series.values),
      untracked: series.untracked || [],
    }
  }
  return {
    id,
    label,
    count: rows.length,
    tickers: rows.map((row) => ({ ticker: row.ticker, rank: row.modelRank ?? null })),
    value,
    cost,
    gain,
    gainPct: cost > 0 ? gain / cost * 100 : null,
    weightPct: totalValue > 0 ? value / totalValue * 100 : null,
    replay,
  }
}

/**
 * On-model vs. discretionary breakdown of the current holdings.
 *
 * `replay` applies today's quantities to each group's price history (the same method as the
 * Summary chart), so the two groups are compared over one shared window rather than each
 * position's own purchase date. It is a like-for-like comparison of what each group has been
 * doing, not a reconstruction of account history.
 */
export function splitHoldingsByModel({ positions = [], research = [], priceData = {}, benchmarkHistory = null } = {}) {
  const ranks = modelRanks(research)
  if (!ranks.size) return { available: false, reason: 'The model has no published ranked list in this refresh.' }
  const held = positions
    .map((position) => ({ ...position, ticker: upper(position.ticker) }))
    .filter((position) => position.ticker && finite(position.shares) && Number(position.shares) > 0)
  if (!held.length) return { available: false, reason: 'No holdings to compare.' }

  const withRank = held.map((position) => ({ ...position, modelRank: ranks.get(position.ticker) ?? null }))
  const onModel = withRank.filter((position) => position.modelRank != null).sort((a, b) => a.modelRank - b.modelRank)
  const offModel = withRank.filter((position) => position.modelRank == null)
    .sort((a, b) => (Number(b.currentValue) || 0) - (Number(a.currentValue) || 0))
  const totalValue = withRank.reduce((sum, row) => sum + (finite(row.currentValue) ? Number(row.currentValue) : 0), 0)

  return {
    available: true,
    modelListSize: ranks.size,
    totalValue,
    groups: [
      groupSummary('model', `In the model's top ${ranks.size}`, onModel, totalValue, priceData, benchmarkHistory),
      groupSummary('discretionary', 'Your own picks', offModel, totalValue, priceData, benchmarkHistory),
    ],
    methodology: 'On-model means the ticker is in the published ranked list today. Replay figures apply current '
      + 'quantities to each group’s price history over a shared window, so they compare the two groups '
      + 'like for like; they are not the account’s recorded history.',
  }
}
