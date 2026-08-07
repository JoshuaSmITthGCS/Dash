const finite = (value) => value !== null && value !== '' && typeof value !== 'boolean' && Number.isFinite(Number(value))

function closesByDate(history) {
  return new Map((history?.dates || []).map((date, index) => [date, history.closes?.[index]]).filter(([, value]) => finite(value)))
}

function closeOnOrAfter(history, date) {
  const dates = history?.dates || []
  const closes = history?.closes || []
  for (let index = 0; index < dates.length; index += 1) {
    if (dates[index] >= date && finite(closes[index])) return { date: dates[index], close: Number(closes[index]) }
  }
  return null
}

function dailyValues(snapshots = []) {
  const byDay = new Map()
  snapshots.filter((row) => row.marketDate && finite(row.value)).forEach((row) => byDay.set(row.marketDate, Number(row.value)))
  return [...byDay.entries()].sort((a, b) => a[0].localeCompare(b[0]))
}

export function snapshotDailySeries(snapshots = []) {
  const days = dailyValues(snapshots)
  return { dates: days.map(([date]) => date), values: days.map(([, value]) => value) }
}

// Puts two independently-dated {dates, values} series onto one shared, sorted date axis so
// a chart can plot them as parallel lines, null-filling whichever series has no observation
// on a given date.
export function alignForChart(primary, secondary) {
  const dates = [...new Set([...(primary?.dates || []), ...(secondary?.dates || [])])].sort()
  const toMap = (series) => new Map((series?.dates || []).map((date, index) => [date, series.values[index]]))
  const primaryMap = toMap(primary)
  const secondaryMap = toMap(secondary)
  return {
    dates,
    primaryValues: dates.map((date) => primaryMap.has(date) ? primaryMap.get(date) : null),
    secondaryValues: dates.map((date) => secondaryMap.has(date) ? secondaryMap.get(date) : null),
  }
}

// Replays the cash-flow ledger as if every deposit bought, and every withdrawal sold,
// benchmark units at that day's close instead of touching the real portfolio. Gives an
// apples-to-apples "same dollars, in the index instead" account value series.
export function benchmarkShadowPortfolio(cashFlows = [], benchmarkHistory) {
  const dates = benchmarkHistory?.dates || []
  const closes = benchmarkHistory?.closes || []
  const flows = cashFlows
    .filter((row) => ['deposit', 'external_contribution', 'withdrawal'].includes(row.type) && finite(row.amount) && row.effectiveDate && !['pending', 'processing'].includes(row.status))
    .map((row) => ({ type: row.type, amount: Number(row.amount), effectiveDate: row.effectiveDate }))
    .sort((a, b) => a.effectiveDate.localeCompare(b.effectiveDate))
  if (!flows.length || dates.length < 2) return { available: false, reason: 'Not enough cash-flow or benchmark history to build a comparison.' }
  const startIndex = dates.findIndex((date) => date >= flows[0].effectiveDate)
  if (startIndex < 0) return { available: false, reason: 'No benchmark history overlaps the cash-flow history.' }

  let units = 0
  let netContributions = 0
  const pending = [...flows]
  const outDates = []
  const outValues = []
  for (let index = startIndex; index < dates.length; index += 1) {
    const date = dates[index]
    const close = Number(closes[index])
    if (!finite(close)) continue
    while (pending.length && pending[0].effectiveDate <= date) {
      const flow = pending.shift()
      if (flow.type === 'deposit' || flow.type === 'external_contribution') { units += flow.amount / close; netContributions += flow.amount }
      else { units = Math.max(0, units - flow.amount / close); netContributions -= flow.amount }
    }
    outDates.push(date)
    outValues.push(units * close)
  }
  if (outValues.length < 2) return { available: false, reason: 'Not enough overlapping trading days to build a comparison.' }
  return {
    available: true,
    dates: outDates,
    values: outValues,
    netContributions,
    finalValue: outValues.at(-1),
    symbol: benchmarkHistory.symbol || benchmarkHistory.label,
    methodology: 'Each settled deposit buys, and each withdrawal sells, benchmark units at that date’s close – the same dollars, invested in the benchmark instead. Pending transfers are excluded.',
  }
}

// Win rate and best/worst trades from the realized-gain ledger. Amount sign carries the
// win/loss; note is whatever free-text label the entry was saved with.
export function tradeStats(activities = []) {
  const trades = activities.filter((row) => row.type === 'realized_gain' && finite(row.amount))
  if (!trades.length) return { available: false, count: 0, reason: 'No realized gains or losses logged yet.' }
  const wins = trades.filter((row) => Number(row.amount) > 0)
  const losses = trades.filter((row) => Number(row.amount) < 0)
  const sum = (rows) => rows.reduce((total, row) => total + Number(row.amount), 0)
  return {
    available: true,
    count: trades.length,
    winCount: wins.length,
    lossCount: losses.length,
    winRate: wins.length / trades.length * 100,
    avgWin: wins.length ? sum(wins) / wins.length : null,
    avgLoss: losses.length ? sum(losses) / losses.length : null,
    totalRealized: sum(trades),
    best: trades.reduce((top, row) => Number(row.amount) > Number(top.amount) ? row : top),
    worst: trades.reduce((bottom, row) => Number(row.amount) < Number(bottom.amount) ? row : bottom),
  }
}

// Compares the purchase-day close against the trailing average leading into it, on the
// holding's own price history, to flag whether a buy landed on a dip or near a local high.
export function purchaseTimingSignal(position, history, windowDays = 30) {
  const purchaseDate = position?.purchaseDate
  const dates = history?.dates || []
  const closes = history?.closes || []
  if (!purchaseDate || dates.length < 2) return { available: false, reason: 'No purchase date or price history for this holding.' }
  const purchaseIndex = dates.findIndex((date, index) => date >= purchaseDate && finite(closes[index]))
  if (purchaseIndex < 1) return { available: false, reason: 'Not enough price history around the purchase date.' }
  const window = closes.slice(Math.max(0, purchaseIndex - windowDays), purchaseIndex).map(Number).filter(finite)
  if (window.length < 5) return { available: false, reason: 'Not enough trading days before the purchase to compare against.' }
  const trailingAvg = window.reduce((total, value) => total + value, 0) / window.length
  const purchasePrice = Number(closes[purchaseIndex])
  const deltaPct = trailingAvg ? (purchasePrice - trailingAvg) / trailingAvg * 100 : null
  const label = deltaPct == null ? null : deltaPct <= -3 ? 'Bought the dip' : deltaPct >= 3 ? 'Bought near a high' : 'Bought near average levels'
  return { available: deltaPct != null, deltaPct, label, trailingAvg, purchasePrice, purchaseDate: dates[purchaseIndex], windowDays: window.length }
}

// Ranks holdings by how much they have beaten (or lagged) the benchmark since each one's
// own purchase date – not a single shared start date, since positions were bought at
// different times.
export function holdingsVsBenchmark(positions = [], benchmarkHistory) {
  if (!benchmarkHistory?.dates?.length) return []
  const benchClose = closesByDate(benchmarkHistory)
  const latestBenchDate = benchmarkHistory.dates.at(-1)
  const latestBenchClose = benchClose.get(latestBenchDate)
  if (!finite(latestBenchClose)) return []
  return positions.map((position) => {
    const history = position.priceInfo?.history
    if (!position.purchaseDate || !history?.dates?.length || !finite(position.currentPrice)) return null
    const stockStart = closeOnOrAfter(history, position.purchaseDate)
    const benchStart = closeOnOrAfter(benchmarkHistory, position.purchaseDate)
    if (!stockStart || !benchStart) return null
    const stockReturnPct = (Number(position.currentPrice) - stockStart.close) / stockStart.close * 100
    const benchmarkReturnPct = (Number(latestBenchClose) - benchStart.close) / benchStart.close * 100
    return { ticker: position.ticker, purchaseDate: position.purchaseDate, stockReturnPct, benchmarkReturnPct, deltaPct: stockReturnPct - benchmarkReturnPct }
  }).filter(Boolean).sort((a, b) => b.deltaPct - a.deltaPct)
}

// Consecutive most-recent trading days the tracked account value moved the same direction.
export function valueStreak(snapshots = []) {
  const days = dailyValues(snapshots)
  if (days.length < 2) return { available: false, days: 0, direction: null }
  const direction = days.at(-1)[1] >= days.at(-2)[1] ? 'up' : 'down'
  let streak = 0
  for (let index = days.length - 1; index > 0; index -= 1) {
    const moveUp = days[index][1] >= days[index - 1][1]
    if ((direction === 'up') !== moveUp) break
    streak += 1
  }
  return { available: true, days: streak, direction }
}

// Consecutive most-recent trading days the tracked account's day-over-day return beat (or
// trailed) the benchmark's day-over-day return.
export function beatMarketStreak(snapshots = [], benchmarkHistory) {
  const days = dailyValues(snapshots)
  const benchClose = closesByDate(benchmarkHistory)
  const rows = days.map(([date, value], index) => {
    if (index === 0) return null
    const [prevDate, prevValue] = days[index - 1]
    const benchNow = benchClose.get(date)
    const benchPrev = benchClose.get(prevDate)
    if (!finite(benchNow) || !finite(benchPrev) || !prevValue) return null
    return { date, beat: (value - prevValue) / prevValue > (benchNow - benchPrev) / benchPrev }
  }).filter(Boolean)
  if (!rows.length) return { available: false, days: 0, beating: null }
  const beating = rows.at(-1).beat
  let streak = 0
  for (let index = rows.length - 1; index >= 0; index -= 1) {
    if (rows[index].beat !== beating) break
    streak += 1
  }
  return { available: true, days: streak, beating }
}

const MILESTONE_THRESHOLDS = [500, 1000, 2500, 5000, 10000, 25000, 50000, 100000]

// First-crossing dates for round-number account value milestones, read off the snapshot
// history the app has actually recorded (not backfilled or estimated).
export function detectMilestones({ snapshots = [], trackedAccountValue = null, contributionPerformance = null } = {}) {
  const days = dailyValues(snapshots)
  const milestones = MILESTONE_THRESHOLDS
    .filter((threshold) => finite(trackedAccountValue) && trackedAccountValue >= threshold)
    .map((threshold) => ({
      id: `value-${threshold}`,
      label: `Portfolio reached $${threshold.toLocaleString('en-US')}`,
      achievedDate: days.find(([, value]) => value >= threshold)?.[0] || null,
    }))
  if (contributionPerformance?.available && contributionPerformance.returnPct >= 10) {
    milestones.push({ id: 'double-digit-gain', label: 'First double-digit percentage gain vs. contributions', achievedDate: null })
  }
  return milestones
}

const MOODS = [
  { min: 20, emoji: '🔥', label: 'On fire', blurb: 'Big gains since you started tracking contributions.' },
  { min: 5, emoji: '📈', label: 'Cruising', blurb: 'Steady progress ahead of what you have put in.' },
  { min: -5, emoji: '😐', label: 'Holding steady', blurb: 'Close to breakeven against total contributions.' },
  { min: -15, emoji: '🌧️', label: 'Rough patch', blurb: 'Down against contributions right now – normal on a long timeline.' },
  { min: -Infinity, emoji: '⛈️', label: 'Stormy', blurb: 'A meaningfully rough stretch against what you have put in.' },
]

// A lightweight, non-financial read on how the portfolio "feels" right now, built entirely
// from figures already computed elsewhere (contribution-adjusted return, diversification,
// the beat-the-market streak).
export function portfolioMood({ returnPct = null, diversificationScore = null, streak = null } = {}) {
  if (!finite(returnPct)) return { emoji: '🌱', label: 'Just getting started', blurb: 'Add contribution history to see how the portfolio is doing.' }
  const mood = { ...MOODS.find((tier) => returnPct >= tier.min) }
  const notes = []
  if (finite(diversificationScore) && diversificationScore < 50) notes.push('Concentration is elevated.')
  if (streak?.available && streak.days >= 3) notes.push(`${streak.days}-day ${streak.beating ? 'beat-the-market' : streak.direction} streak.`)
  if (notes.length) mood.note = notes.join(' ')
  return mood
}
