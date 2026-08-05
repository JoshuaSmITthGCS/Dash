import modelSettings from '../../pipeline/config/settings.json'

export const alertConfig = modelSettings.alerts

export const ALERT_TYPES = [
  { value: 'price_cross', label: 'Price crosses a level' },
  { value: 'percent_move', label: 'Percent move over 1 or 5 days' },
  { value: 'stop_trigger', label: 'Trim or exit stop triggers' },
  { value: 'score_band', label: 'Research score changes band' },
  { value: 'guidance_change', label: 'Guidance changes to Trim or Sell' },
  { value: 'earnings_upcoming', label: 'Upcoming earnings date' },
  { value: 'pipeline_stale', label: 'Research data becomes stale' },
]

export const SCORE_BANDS = ['ATTRACTIVE', 'NEUTRAL', 'CAUTIOUS', 'UNATTRACTIVE']

export function normalizeAlertRule(input = {}) {
  const type = ALERT_TYPES.some((item) => item.value === input.type) ? input.type : 'price_cross'
  const ticker = String(input.ticker || '').trim().toUpperCase()
  return {
    type,
    ticker: type === 'pipeline_stale' ? '' : ticker,
    direction: input.direction === 'below' ? 'below' : 'above',
    threshold: input.threshold === '' || input.threshold == null ? Number.NaN : Number(input.threshold),
    periodDays: Number(input.periodDays) === 5 ? 5 : 1,
    stopKind: input.stopKind === 'exit' ? 'exit' : 'trim',
    band: SCORE_BANDS.includes(input.band) ? input.band : 'ATTRACTIVE',
    guidanceActions: Array.isArray(input.guidanceActions) && input.guidanceActions.length
      ? input.guidanceActions.filter((value) => ['TRIM', 'SELL'].includes(value))
      : ['TRIM', 'SELL'],
    daysAhead: Number.isFinite(Number(input.daysAhead)) ? Number(input.daysAhead) : alertConfig.default_earnings_notice_days,
    staleHours: Number.isFinite(Number(input.staleHours)) ? Number(input.staleHours) : alertConfig.default_pipeline_stale_hours,
    enabled: input.enabled !== false,
  }
}

export function validateAlertRule(input) {
  const rule = normalizeAlertRule(input)
  if (rule.type !== 'pipeline_stale' && !/^[A-Z][A-Z0-9.-]{0,9}$/.test(rule.ticker)) return { valid: false, error: 'Enter a valid ticker.' }
  if (['price_cross', 'percent_move', 'stop_trigger'].includes(rule.type) && (!Number.isFinite(rule.threshold) || rule.threshold <= 0)) return { valid: false, error: 'Enter a threshold greater than zero.' }
  if (rule.type === 'earnings_upcoming' && (!Number.isFinite(rule.daysAhead) || rule.daysAhead < 1 || rule.daysAhead > 90)) return { valid: false, error: 'Choose an earnings window from 1 to 90 days.' }
  if (rule.type === 'pipeline_stale' && (!Number.isFinite(rule.staleHours) || rule.staleHours < 1 || rule.staleHours > 168)) return { valid: false, error: 'Choose a stale-data window from 1 to 168 hours.' }
  return { valid: true, rule }
}

export function alertRuleLabel(rule) {
  const symbol = rule.ticker ? `${rule.ticker} ` : ''
  if (rule.type === 'price_cross') return `${symbol}price ${rule.direction} $${rule.threshold}`
  if (rule.type === 'percent_move') return `${symbol}${rule.periodDays}-day move ${rule.direction} ${rule.threshold}%`
  if (rule.type === 'stop_trigger') return `${symbol}${rule.stopKind} stop at $${rule.threshold}`
  if (rule.type === 'score_band') return `${symbol}score moves ${rule.direction} ${rule.band}`
  if (rule.type === 'guidance_change') return `${symbol}guidance changes to ${rule.guidanceActions.join(' or ')}`
  if (rule.type === 'earnings_upcoming') return `${symbol}earnings within ${rule.daysAhead} days`
  return `Research data older than ${rule.staleHours} hours`
}
