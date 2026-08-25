import { resolvedMetricSections } from '../components/MetricSections.jsx'

// One-button plain-text export of everything the stock detail sheet actually shows for a
// company: identity, score, every resolved metric section (same filtering
// resolvedMetricSections applies to the live panel, so this can never show a number the
// screen itself withheld), insider Form 4 activity, and disclosed Congressional/institutional
// positioning when either is published for this ticker. Meant to be pasted somewhere else
// entirely - a note, a spreadsheet, another tool - so it reads as plain lines, not markup.

const signed = (value, digits = 1) => `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`

function headerLines(stock) {
  const lines = [`${stock.ticker} — ${stock.name || 'Name unavailable'}`]
  const place = [stock.industry || stock.sector, stock.sector && stock.industry ? stock.sector : null]
    .filter(Boolean).join(' · ')
  if (place) lines.push(place)
  const score = stock.score
  lines.push(score == null
    ? 'Research score: not published'
    : `Research score: ${Math.round(score)}${stock.stance ? ` (${stock.stance})` : ''}`)
  if (typeof stock.data_coverage === 'number' && Number.isFinite(stock.data_coverage)) {
    lines.push(`Data coverage: ${Math.round(stock.data_coverage * 100)}%`)
  }
  return lines
}

function metricSectionLines(stock) {
  const rendered = resolvedMetricSections(stock)
  if (!rendered.length) return []
  const lines = ['', 'METRICS']
  rendered.forEach((section) => {
    lines.push('', section.title.toUpperCase())
    section.resolved.forEach((metric) => {
      lines.push(`  ${metric.label}: ${metric.format(metric.value)}`)
    })
  })
  return lines
}

function insiderActivityLines(insider) {
  const buys = insider?.recent_acquisitions || 0
  const sells = insider?.recent_disposals || 0
  if (!insider?.records_reviewed || (!buys && !sells)) return []
  return [
    '', 'INSIDER ACTIVITY (Form 4)',
    `  ${buys} buy${buys === 1 ? '' : 's'} · ${sells} sell${sells === 1 ? '' : 's'} ` +
      `(${insider.records_reviewed} filing${insider.records_reviewed === 1 ? '' : 's'} reviewed)`,
  ]
}

const CONGRESS_FLAG_LABELS = {
  EXTRAORDINARY_BUY: 'First trade in a small, unfamiliar company',
  CLUSTER_TRADE: '3+ representatives, 14-day span',
  BUY_SELL_FLIP: 'Round trip within 60 days',
}

function disclosedPositioningLines(info) {
  if (!info) return []
  const lines = ['', 'DISCLOSED POSITIONING (Congress / institutional)']
  if (info.institutional_flag) {
    lines.push(`  ${info.institutional_flag === 'CLUSTER_ACCUMULATION'
      ? 'Curated managers accumulating' : 'Curated managers distributing'}`)
  }
  ;(info.congress_flags || []).forEach((flag) => {
    lines.push(`  ${CONGRESS_FLAG_LABELS[flag] || flag}`)
  })
  if (typeof info.score === 'number') lines.push(`  Combined score: ${info.score.toFixed(2)}`)
  return lines
}

function strengthsAndRisksLines(stock) {
  const lines = []
  if (stock.strengths?.length) {
    lines.push('', 'EVIDENCE FOR', ...stock.strengths.map((item) => `  + ${item}`))
  }
  if (stock.risks?.length) {
    lines.push('', 'RISKS / GAPS', ...stock.risks.map((item) => `  - ${item}`))
  }
  return lines
}

/**
 * @param {object} stock - a research row (research/portfolio_coverage/screen_universe shape)
 * @param {object} [insideInfo] - screens/inside-information.json's by_ticker[stock.ticker] entry
 * @returns {string} plain text, ready for the clipboard
 */
export function buildStockCopyText(stock, insideInfo) {
  if (!stock?.ticker) return ''
  const priceLine = stock.price ? [`Price: $${Number(stock.price).toFixed(2)}`] : []
  const moveLine = typeof stock.technical_detail?.return_20d === 'number'
    ? [`20-day move: ${signed(stock.technical_detail.return_20d)}`]
    : []
  return [
    ...headerLines(stock),
    ...priceLine,
    ...moveLine,
    ...metricSectionLines(stock),
    ...insiderActivityLines(stock.insider_activity),
    ...disclosedPositioningLines(insideInfo),
    ...strengthsAndRisksLines(stock),
  ].join('\n')
}
