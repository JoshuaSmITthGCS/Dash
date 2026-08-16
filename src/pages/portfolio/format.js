// Formatting and small numeric helpers shared by every portfolio view.
// Nothing here reads React state or the DOM, so the view files can stay declarative.

export const SUMMARY_PERIODS = ['1H', '1D', '1W', '1M', '3M', '1Y']
export const PERFORMANCE_PERIODS = ['1W', '1M', '3M', '1Y', 'All']
export const PERIOD_NAMES = { '1H': 'Last hour', '1D': 'Today', '1W': 'Week', '1M': 'Month', '3M': '3 months', '1Y': 'Year', All: 'All time' }

// The backtested-basket series that risk/performance stats are computed from applies today's
// holdings to every historical date it has prices for -- including dates before live tracking
// in this account actually began. The switch below lets those stats be evaluated only since
// that date instead, so ratios reflect the strategy actually being run, not a hypothetical
// basket replayed further back than the account existed.
export const ANALYTICS_SCOPES = [
  { id: 'all_history', label: 'All portfolio history' },
  { id: 'since_algorithm', label: 'Since algorithm activation' },
  { id: 'live_algorithm', label: 'Live algorithm only' },
  { id: 'backtest', label: 'Backtest period' },
]

export const money = (value, digits = 0) =>
  value == null ? '–' : `$${value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`

export const signedPct = (value, digits = 1) =>
  value == null ? '–' : `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`

export const moveColor = (value) => (value == null ? undefined : value >= 0 ? 'var(--pos)' : 'var(--neg)')

export function recentReturn(values, points = 5) {
  const clean = (values || []).filter(Number.isFinite).slice(-points)
  if (clean.length < 2 || !clean[0]) return null
  return (clean.at(-1) / clean[0] - 1) * 100
}

// Cost basis is stored per share everywhere downstream (totalCost = shares * costBasis), but
// that's easy to enter wrong: a $200 total investment typed into a bare "Cost Basis" field
// reads as $200/share, inflating cost basis by the share count. Letting the form accept
// either unit and normalizing here keeps the stored value's meaning consistent.
export function perShareCost(rawValue, shares, mode) {
  const amount = parseFloat(rawValue)
  if (!Number.isFinite(amount) || !Number.isFinite(shares) || shares <= 0) return NaN
  return mode === 'total' ? amount / shares : amount
}

export function sessionSetting(key, fallback) {
  try { return globalThis.sessionStorage?.getItem(key) || fallback } catch { return fallback }
}
