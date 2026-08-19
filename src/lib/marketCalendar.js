import modelSettings from '../../pipeline/config/settings.json' with { type: 'json' }

const refreshConfig = modelSettings.projection.parametric_calibration

// Converts a wall-clock time in the given IANA zone to a UTC epoch, correct across DST, by
// iterating the zone-offset guess to a fixed point (three passes always converges since
// offsets only ever move in whole-minute steps).
function zonedWallClockToUtcMs(year, month, day, hour, minute, timeZone) {
  const target = Date.UTC(year, month - 1, day, hour, minute)
  let guess = target
  for (let iteration = 0; iteration < 3; iteration += 1) {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
    }).formatToParts(new Date(guess))
    const map = Object.fromEntries(parts.map((part) => [part.type, part.value]))
    const observedHour = Number(map.hour) === 24 ? 0 : Number(map.hour)
    const observed = Date.UTC(Number(map.year), Number(map.month) - 1, Number(map.day), observedHour, Number(map.minute))
    guess += target - observed
  }
  return guess
}

/**
 * Most recent weekly refresh boundary (configured weekday/hour/zone - Friday 4pm
 * America/New_York, US market close, by default) at or before `nowMs`. Looks back up to a
 * week of calendar days in the configured zone to find it.
 */
export function mostRecentWeeklyRefreshMs(nowMs = Date.now()) {
  const { refresh_timezone: timeZone, refresh_weekday: weekday, refresh_hour: hour } = refreshConfig
  const parts = new Intl.DateTimeFormat('en-US', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(nowMs))
  const map = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  const todayUtcMidnight = Date.UTC(Number(map.year), Number(map.month) - 1, Number(map.day))
  for (let back = 0; back < 8; back += 1) {
    const day = new Date(todayUtcMidnight - back * 86400000)
    if (day.getUTCDay() !== weekday) continue
    const closeMs = zonedWallClockToUtcMs(day.getUTCFullYear(), day.getUTCMonth() + 1, day.getUTCDate(), hour, 0, timeZone)
    if (closeMs <= nowMs) return closeMs
  }
  return null
}

export function weekdayLabel(weekday) {
  // 2023-01-01 was a Sunday (weekday 0); offsetting from it gets the day name without
  // depending on the refresh timezone, since a calendar weekday name is zone-independent.
  return new Intl.DateTimeFormat('en-US', { weekday: 'long' }).format(new Date(Date.UTC(2023, 0, 1 + weekday)))
}

export function hourLabel(hour) {
  const period = hour >= 12 ? 'pm' : 'am'
  const twelveHour = hour % 12 === 0 ? 12 : hour % 12
  return `${twelveHour}${period}`
}

export function refreshBoundaryLabel() {
  return `${weekdayLabel(refreshConfig.refresh_weekday)} ${hourLabel(refreshConfig.refresh_hour)} market close`
}
