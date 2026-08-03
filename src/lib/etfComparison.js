export const SUPPORTED_ETF_SCHEMA_MAJOR = 4

const finite = (value) => typeof value === 'number' && Number.isFinite(value)
const numeric = (value) => value == null || value === '' ? Number.NaN : Number(value)

export function parseEtfComparison(payload) {
  if (!payload || typeof payload !== 'object') throw new Error('ETF comparison response is invalid')
  const major = Number(String(payload.schema_version || '0').split('.')[0])
  if (major !== SUPPORTED_ETF_SCHEMA_MAJOR) {
    throw new Error(`Unsupported ETF comparison schema: ${payload.schema_version || 'missing'}`)
  }
  const chartRanges = Object.fromEntries(Object.entries(payload.chart_ranges || {}).map(([key, range]) => {
    const series = (range?.series || []).map((row) => ({
      date: String(row.date || '').slice(0, 10),
      fund_index: numeric(row.fund_index),
      benchmark_index: numeric(row.benchmark_index),
      relative_index: numeric(row.relative_index),
      fund_drawdown: numeric(row.fund_drawdown),
      benchmark_drawdown: numeric(row.benchmark_drawdown),
    })).filter((row) => row.date && finite(row.fund_index) && finite(row.benchmark_index))
    return [key, { ...range, series }]
  }))
  return { ...payload, chart_ranges: chartRanges }
}

export function comparisonLines(range, view, ticker, benchmarkLabel) {
  if (view === 'relative') return [{ label: `${ticker} relative strength`, key: 'relative_index', color: 'var(--series-stock)' }]
  if (view === 'drawdown') return [
    { label: `${ticker} drawdown`, key: 'fund_drawdown', color: 'var(--series-stock)' },
    { label: `${benchmarkLabel} drawdown`, key: 'benchmark_drawdown', color: 'var(--series-benchmark)', dashed: true },
  ]
  return [
    { label: ticker, key: 'fund_index', color: 'var(--series-stock)' },
    { label: benchmarkLabel, key: 'benchmark_index', color: 'var(--series-benchmark)', dashed: true },
  ]
}
