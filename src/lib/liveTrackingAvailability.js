import modelSettings from '../../pipeline/config/settings.json'

const DAY_MS = 86400000
const MARKET_TIME_ZONE = 'America/New_York'

export const LIVE_TRACKING_START = '2026-07-20'
export const STANDARD_MEASURES_MINIMUM_RETURNS = Number(
  modelSettings.portfolio_analytics.performance_minimum_observations,
)

function utcDay(date) {
  return Date.parse(`${String(date).slice(0, 10)}T00:00:00Z`)
}

function isoDay(milliseconds) {
  return new Date(milliseconds).toISOString().slice(0, 10)
}

function dateKeyInMarketTime(now) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: MARKET_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(now))
  const part = (type) => parts.find((row) => row.type === type)?.value
  return `${part('year')}-${part('month')}-${part('day')}`
}

/** Weekdays are an estimate, rather than a claim about the full exchange holiday calendar. */
export function addEstimatedMarketDays(date, count) {
  let cursor = utcDay(date)
  let remaining = Math.max(0, Math.round(Number(count) || 0))
  while (remaining > 0) {
    cursor += DAY_MS
    const weekday = new Date(cursor).getUTCDay()
    if (weekday !== 0 && weekday !== 6) remaining -= 1
  }
  return isoDay(cursor)
}

/**
 * Builds the honest part of the countdown: observations are exact, while the calendar date
 * is an estimate based on the current daily cadence. If a refresh falls behind, the return
 * count remains the source of truth and the UI stops pretending a past estimate is a timer.
 */
export function standardMeasuresCountdown({
  dates = [],
  now = Date.now(),
  minimumReturns = STANDARD_MEASURES_MINIMUM_RETURNS,
  trackingStart = LIVE_TRACKING_START,
} = {}) {
  const cleanDates = (dates || [])
    .map((date) => String(date).slice(0, 10))
    .filter((date) => Number.isFinite(utcDay(date)) && date >= trackingStart)
    .sort()
  const observations = Math.max(0, cleanDates.length - 1)
  const remainingReturns = Math.max(0, minimumReturns - observations)
  const lastObservationDate = cleanDates.at(-1) || trackingStart
  const targetDate = addEstimatedMarketDays(lastObservationDate, remainingReturns)
  const today = dateKeyInMarketTime(now)
  const calendarDaysToTarget = Math.round((utcDay(targetDate) - utcDay(today)) / DAY_MS)

  return {
    available: remainingReturns === 0,
    observations,
    minimumReturns,
    remainingReturns,
    lastObservationDate,
    targetDate,
    calendarDaysToTarget,
    progressPct: Math.min(100, observations / minimumReturns * 100),
  }
}

export function formatCountdownDate(date) {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'UTC',
    month: 'short',
    day: 'numeric',
  }).format(new Date(`${date}T12:00:00Z`))
}
