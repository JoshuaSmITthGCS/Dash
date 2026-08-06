import { signedPct } from '../lib/formatters.js'

const PERIOD_COPY = {
  '1D': 'today',
  '1W': 'past week',
  '1M': 'past month',
  '3M': 'past 3 months',
  YTD: 'year to date',
  '1Y': 'past year',
  All: 'all recorded dates',
}

export function portfolioPeriodCopy(period) {
  return PERIOD_COPY[period] || period
}

export default function PortfolioChartOverlay({ summary, period, money, seriesLabel, holdings, coveragePct }) {
  if (!summary) return null
  const positive = summary.dollarReturn >= 0
  const direction = positive ? 'move-positive' : 'move-negative'
  const sign = positive ? '+' : '−'

  return <div className={`mobile-chart-overlay ${direction}`} aria-live="polite">
    <span className="mobile-chart-balance-label">Current portfolio value</span>
    <strong className="mobile-chart-balance">{money(summary.endValue)}</strong>
    <div className="mobile-chart-period-move">
      <span className="mobile-chart-direction" aria-hidden="true">{positive ? '▲' : '▼'}</span>
      <b>{sign}{money(Math.abs(summary.dollarReturn))}</b>
      <span>{signedPct(summary.returnPct, 2)} {portfolioPeriodCopy(period)}</span>
    </div>
    <small>{seriesLabel} · {holdings} holdings · {Math.round(coveragePct)}% price coverage</small>
  </div>
}
