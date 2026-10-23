// Total returns: the portfolio's time-weighted return beside a fixed set of market indexes, all
// measured to the same close. index-history.json is rebuilt after every US close (see
// .github/workflows/refresh-index-returns.yml), so "as of" is always the session that just ended.
//
// `compact` is the Summary-page card: four columns, a handful of rows, a link to the full table.

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useData } from '../../lib/useData'
import { buildReturnsTable } from '../../lib/indexReturns.js'
import { signedPct } from './format.js'

const COMPACT_COLUMNS = ['1D', 'MTD', 'YTD', '1Y']
const COMPACT_ROWS = ['SPY', 'VTI', 'QQQ', 'AGG']
const BENCHMARK_ROW = 'SPY'

const longDate = (iso) => {
  if (!iso) return ''
  const [year, month, day] = iso.split('-')
  const name = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(month) - 1]
  return `${name}-${day}-${year}`
}

function Cell({ cell }) {
  if (!cell) return <td className="returns-cell returns-cell--empty">--</td>
  return (
    <td className={`returns-cell ${cell.pct >= 0 ? 'positive' : 'negative'}`}>
      {signedPct(cell.pct, 2)}
      {cell.since && <small> {longDate(cell.since)}</small>}
    </td>
  )
}

function ReturnsTable({ title, columns, rows, hint }) {
  return (
    <div className="returns-table-wrap">
      <table className="returns-table">
        <thead><tr><th scope="col" title={hint}>{title}</th>{columns.map((column) => <th key={column.key} scope="col">{column.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <th scope="row">{row.label}</th>
              {columns.map((column) => <Cell key={column.key} cell={row.values[column.key]} />)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function exportCsv(table) {
  const header = ['Name', ...table.columns.map((column) => column.label)]
  const rows = [table.portfolio, ...table.rows].filter(Boolean).map((row) => [
    row.label, ...table.columns.map((column) => {
      const cell = row.values[column.key]
      return cell ? cell.pct.toFixed(2) : ''
    }),
  ])
  const csv = [header, ...rows].map((line) => line.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(',')).join('\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `total-returns-${table.asOf}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

export default function IndexReturnsTable({ portfolioSeries, moneyWeighted = null, compact = false }) {
  const { data: history, loading, error } = useData('index-history.json')
  const [frequency, setFrequency] = useState('daily')
  const [growth, setGrowth] = useState('annualized')
  const [custom, setCustom] = useState({ start: '', end: '' })

  if (loading) return <div className="card returns-card" aria-busy="true"><p className="returns-note">Loading market index returns…</p></div>
  if (error || !history) {
    return <div className="card returns-card"><p className="returns-note">Market index returns are unavailable right now. They are rebuilt after each US close.</p></div>
  }

  const table = buildReturnsTable({ history, portfolio: portfolioSeries, frequency: compact ? 'daily' : frequency, growth, custom })
  if (!table) return null

  const benchmark = table.rows.find((row) => row.id === BENCHMARK_ROW)
  const withExcess = table.portfolio && benchmark ? {
    id: 'excess',
    label: `Difference vs ${benchmark.label}`,
    values: Object.fromEntries(table.columns.map((column) => {
      const mine = table.portfolio.values[column.key]
      const theirs = benchmark.values[column.key]
      return [column.key, mine && theirs ? { pct: mine.pct - theirs.pct } : null]
    })),
  } : null

  if (compact) {
    const columns = table.columns.filter((column) => COMPACT_COLUMNS.includes(column.key))
    const rows = [table.portfolio, ...COMPACT_ROWS.map((id) => table.rows.find((row) => row.id === id))].filter(Boolean)
    return (
      <div className="card returns-card returns-card--compact">
        <div className="portfolio-section-heading">
          <div><span className="eyebrow">Versus the market</span><h3>Total returns</h3></div>
          <Link className="chip button-chip" to="/portfolio/performance">Full table</Link>
        </div>
        <p className="returns-note">Prior-close performance as of {longDate(table.asOf)}. Refreshed after every US market close.</p>
        <ReturnsTable title="Total return" columns={columns} rows={withExcess ? [...rows, withExcess] : rows} />
      </div>
    )
  }

  const portfolioRows = [table.portfolio, withExcess].filter(Boolean)
  const moneyRow = moneyWeighted && table.columns.some((column) => column.key === 'LIFE')
    ? [{ id: 'xirr', label: 'Your portfolio (XIRR)', values: Object.fromEntries(table.columns.map((column) => [column.key, column.key === 'LIFE' ? { pct: moneyWeighted.rate } : null])) }]
    : null
  const asOfLabel = frequency === 'monthly' ? 'Prior month end performance' : frequency === 'custom' ? 'Custom range performance' : 'Prior day performance'

  return (
    <section className="card returns-card" aria-labelledby="total-returns-title">
      <div className="portfolio-section-heading">
        <div><span className="eyebrow">Versus the market</span><h3 id="total-returns-title">Total returns</h3></div>
        <button type="button" className="secondary-button" onClick={() => exportCsv(table)} disabled={!table.rows.length}>Export data to spreadsheet</button>
      </div>
      <p className="returns-note">{asOfLabel} as of {longDate(table.asOf)}. Updated after every US market close (latest close: {longDate(table.lastClose)}).</p>

      <div className="returns-controls">
        <fieldset>
          <legend>Frequency</legend>
          {[['daily', 'Daily'], ['monthly', 'Monthly'], ['custom', 'Custom']].map(([value, label]) => (
            <label key={value}><input type="radio" name="returns-frequency" checked={frequency === value} onChange={() => setFrequency(value)} />{label}</label>
          ))}
        </fieldset>
        <fieldset>
          <legend>View your investment growth</legend>
          {[['cumulative', 'Cumulative'], ['annualized', 'Annualized']].map(([value, label]) => (
            <label key={value}><input type="radio" name="returns-growth" checked={growth === value} onChange={() => setGrowth(value)} />{label}</label>
          ))}
        </fieldset>
        {frequency === 'custom' && (
          <fieldset className="returns-custom">
            <legend>Date range</legend>
            <label><span>From</span><input type="date" value={custom.start} max={table.lastClose} onChange={(event) => setCustom({ ...custom, start: event.target.value })} /></label>
            <label><span>To</span><input type="date" value={custom.end} max={table.lastClose} onChange={(event) => setCustom({ ...custom, end: event.target.value })} /></label>
          </fieldset>
        )}
      </div>

      {table.invalidCustom ? (
        <p className="returns-note">Pick a start date before the end date to see a custom range.</p>
      ) : (
        <>
          {table.portfolioStale && <p className="returns-note">Your holdings history stops before this close, so your row reads “--” until prices catch up.</p>}
          {!table.portfolio && <p className="returns-note">Your portfolio return needs at least two dated closes of holdings history.</p>}
          {portfolioRows.length > 0 && <ReturnsTable title="Time-weighted rate of return (pre-tax)" hint="Cash deposits and withdrawals do not affect this figure." columns={table.columns} rows={portfolioRows} />}
          {moneyRow && <ReturnsTable title="Money-weighted rate of return (pre-tax)" hint="Reflects the size and timing of your cash flows." columns={table.columns} rows={moneyRow} />}
          <h4 className="returns-subhead">Market indexes</h4>
          <ReturnsTable title="Name" columns={table.columns} rows={table.rows} />
          <p className="returns-note">
            Indexes are measured with investable ETF proxies on adjusted closes (dividends included), so they differ slightly from the published index.
            Index blends are monthly-rebalanced mixes of a U.S. total-market and a bond proxy. Periods longer than your holdings history read “--”.
            Past performance does not predict future results.
          </p>
        </>
      )}
    </section>
  )
}
