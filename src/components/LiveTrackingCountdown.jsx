import { useEffect, useState } from 'react'
import {
  formatCountdownDate,
  standardMeasuresCountdown,
} from '../lib/liveTrackingAvailability.js'

function countdownHeadline(status) {
  if (status.available) return 'Live'
  if (status.calendarDaysToTarget > 0) return `${status.calendarDaysToTarget}d`
  if (status.calendarDaysToTarget === 0) return 'Today'
  return `${status.remainingReturns} left`
}

function countdownDetail(status) {
  if (status.available) return 'Sharpe, Sortino, Calmar and drawdown measures are available.'
  if (status.calendarDaysToTarget < 0) {
    return `Waiting for ${status.remainingReturns} more daily return${status.remainingReturns === 1 ? '' : 's'} from the next data refresh.`
  }
  return `Estimated ${formatCountdownDate(status.targetDate)}, after the market data refresh.`
}

export default function LiveTrackingCountdown({ dates, now: suppliedNow }) {
  const [clock, setClock] = useState(() => suppliedNow ?? Date.now())

  useEffect(() => {
    if (suppliedNow != null) return undefined
    const timer = window.setInterval(() => setClock(Date.now()), 60000)
    return () => window.clearInterval(timer)
  }, [suppliedNow])

  const status = standardMeasuresCountdown({ dates, now: suppliedNow ?? clock })
  const ariaLabel = status.available
    ? `Live-only standard measures are live with ${status.observations} daily returns.`
    : `Live-only standard measures: ${status.observations} of ${status.minimumReturns} daily returns recorded. Estimated live ${formatCountdownDate(status.targetDate)}.`

  return (
    <div className={`live-tracking-countdown${status.available ? ' available' : ''}`} role="status" aria-live="polite" aria-label={ariaLabel}>
      <div className="live-countdown-number">
        <span>{status.available ? 'Standard measures' : 'Unlock in'}</span>
        <strong>{countdownHeadline(status)}</strong>
      </div>
      <div className="live-countdown-progress">
        <span>Live-only standard measures</span>
        <strong>{status.observations} of {status.minimumReturns} daily returns</strong>
        <small>{countdownDetail(status)}</small>
        <i
          role="progressbar"
          aria-label="Daily return history collected"
          aria-valuemin="0"
          aria-valuemax={status.minimumReturns}
          aria-valuenow={Math.min(status.observations, status.minimumReturns)}
        >
          <span style={{ width: `${status.progressPct}%` }} />
        </i>
      </div>
    </div>
  )
}
