/**
 * Pure boundary math for "refresh once a day, at or after 9pm local time."
 *
 * 9pm is after Nasdaq/NYSE after-hours trading has wound down (it runs 4-8pm ET), so a
 * refresh then captures the session's after-hours move rather than a partial one. This is
 * a static site with no server-side cron, so "at 9pm" means: while the app happens to be
 * open, refresh at the first 9pm boundary it sees, and if it's opened after 9pm without a
 * same-day refresh yet, catch up immediately instead of waiting for tomorrow.
 */

const REFRESH_HOUR = 21

function boundaryOnOrBefore(now) {
  const boundary = new Date(now)
  boundary.setHours(REFRESH_HOUR, 0, 0, 0)
  if (boundary.getTime() > now.getTime()) boundary.setDate(boundary.getDate() - 1)
  return boundary.getTime()
}

export function isRefreshDue(fetchedAt, now = new Date()) {
  const fetchedAtMs = fetchedAt ? new Date(fetchedAt).getTime() : NaN
  if (!Number.isFinite(fetchedAtMs)) return true
  return fetchedAtMs < boundaryOnOrBefore(now)
}

export function msUntilNextBoundary(now = new Date()) {
  const boundary = new Date(now)
  boundary.setHours(REFRESH_HOUR, 0, 0, 0)
  if (boundary.getTime() <= now.getTime()) boundary.setDate(boundary.getDate() + 1)
  return boundary.getTime() - now.getTime()
}
