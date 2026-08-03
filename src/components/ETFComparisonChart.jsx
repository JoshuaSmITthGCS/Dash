import { useMemo, useState } from 'react'
import GrowthChart from './GrowthChart'
import { comparisonLines } from '../lib/etfComparison'

const RANGE_ORDER = ['1M', '3M', '6M', 'YTD', '1Y', '3Y', '5Y', 'MAX']
const VIEWS = [['growth', 'Fund vs benchmark'], ['relative', 'Relative strength'], ['drawdown', 'Drawdowns']]
const pct = (value) => value == null ? '—' : `${value > 0 ? '+' : ''}${Number(value).toFixed(2)}%`
const decimal = (value) => value == null ? '—' : Number(value).toFixed(2)

export function ETFComparisonChart({ data, initialRange = '1Y' }) {
  const available = RANGE_ORDER.filter((key) => data.chart_ranges?.[key])
  const [rangeKey, setRangeKey] = useState(available.includes(initialRange) ? initialRange : available[0])
  const [view, setView] = useState('growth')
  const range = data.chart_ranges?.[rangeKey]
  const benchmark = data.benchmark || {}
  const benchmarkLabel = benchmark.display_name || benchmark.ticker || 'Benchmark'
  const lines = useMemo(() => comparisonLines(range, view, data.ticker, benchmarkLabel).map((line) => ({
    ...line, values: (range?.series || []).map((row) => row[line.key]),
  })), [range, view, data.ticker, benchmarkLabel])

  if (!range || range.status !== 'success' || range.series.length < 2) {
    return <div className="card etf-state" role="status">
      <strong>Benchmark history unavailable for this range</strong>
      <span>Reason: {range?.reason_code || data.reason_code || 'NO_VALID_COMPARISON_SERIES'}</span>
    </div>
  }
  const metrics = range.metrics || {}
  const trackingAllowed = ['actual_index', 'investable_proxy'].includes(benchmark.type)
  const cards = [
    ['Fund return', pct(metrics.fund_return)], ['Benchmark return', pct(metrics.benchmark_return)],
    ['Excess return', pct(metrics.excess_return)], ['Beta', decimal(metrics.beta)],
    ['Correlation', decimal(metrics.correlation)], ['Maximum drawdown', pct(metrics.fund_max_drawdown)],
    ...(trackingAllowed ? [['Tracking difference', pct(metrics.tracking_difference)], ['Tracking error', pct(metrics.tracking_error)]] : []),
    ['Sharpe', decimal(metrics.sharpe)], ['Sortino', decimal(metrics.sortino)],
  ]
  return <section className="etf-comparison" aria-label={`${data.ticker} benchmark comparison`}>
    <div className="etf-benchmark-heading">
      <div><span className="sec-label">Benchmark</span><h3>{benchmarkLabel}</h3></div>
      <span className="chip">{benchmark.quality_label} · {Math.round((benchmark.confidence || 0) * 100)}% source confidence</span>
    </div>
    <div className="etf-controls">
      <div className="chart-zoom" aria-label="ETF chart range">{available.map((key) => <button key={key}
        className={key === rangeKey ? 'active' : ''} aria-pressed={key === rangeKey} onClick={() => setRangeKey(key)}>{key}</button>)}</div>
      <div className="chart-zoom" aria-label="ETF chart view">{VIEWS.map(([key, label]) => <button key={key}
        className={key === view ? 'active' : ''} aria-pressed={key === view} onClick={() => setView(key)}>{label}</button>)}</div>
    </div>
    <GrowthChart dates={range.series.map((row) => row.date)} series={lines}
      title={view === 'growth' ? `Normalized growth of 100 — ${data.ticker} vs ${benchmarkLabel}` : view === 'relative' ? `${data.ticker} relative to ${benchmarkLabel}` : 'Drawdown comparison'}
      valueFormatter={view === 'drawdown' ? pct : (value) => Number(value).toFixed(1)} />
    <div className="etf-metric-grid">{cards.map(([label, value]) => <div className="card kpi" key={label}>
      <div className="kpi-label">{label}</div><div className="kpi-value">{value}</div></div>)}</div>
    <p className="etf-quality-note">{range.observation_count} overlapping sessions · {range.actual_start} to {range.end}
      {range.quality_flags?.length ? ` · ${range.quality_flags.join(', ')}` : ''}</p>
  </section>
}
