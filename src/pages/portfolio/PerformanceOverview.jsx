// Performance overview: range pills, Balance and Return, a monthly-return bars + value line
// chart, and a row of cards (Total returns, Investment income, Asset allocation) that all follow
// the selected range.
//
// Everything is built from the repriced-holdings series, so the bars are time-weighted monthly
// returns: money you add or withdraw never shows as a gain or a loss.

import { useState } from 'react'
import AllocationDonut from '../../components/AllocationDonut.jsx'
import { useData } from '../../lib/useData'
import { selectPeriod } from '../../lib/portfolioAnalytics.js'
import { buildReturnsTable } from '../../lib/indexReturns.js'
import { flowsBetween, monthlyBars, monthlyIncome } from '../../lib/performanceOverview.js'
import { money, PERFORMANCE_PERIODS, signedPct } from './format.js'

const PILL_LABELS = { All: 'ALL' }
const CARD_INDEXES = ['SPY', 'VTI', 'ACWX', 'AGG', 'MUB']

const longDate = (iso) => {
  if (!iso) return ''
  const [year, month, day] = iso.split('-')
  return `${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(month) - 1]}-${day}-${year}`
}
const tone = (value) => (value >= 0 ? 'positive' : 'negative')
const signedMoney = (value) => `${value >= 0 ? '+' : '−'}${money(Math.abs(value), 2)}`

/** Axis ceiling rounded up to a 2.5-style step so the gridlines read as round numbers. */
function niceMax(value, steps = [1, 2, 2.5, 5, 10]) {
  if (!(value > 0)) return 5
  const magnitude = 10 ** Math.floor(Math.log10(value))
  for (const step of steps) if (value <= step * magnitude) return step * magnitude
  return 10 * magnitude
}

const W = 1000
const H = 340
const PAD = { left: 56, right: 64, top: 16, bottom: 44 }

function ReturnChart({ bars }) {
  const [active, setActive] = useState(null)
  if (!bars.length) {
    return <div className="unavailable-panel"><strong>Monthly history is still building</strong><p>Two months of dated closes are needed to draw the bars.</p></div>
  }
  const plotW = W - PAD.left - PAD.right
  const plotH = H - PAD.top - PAD.bottom
  const maxAbs = niceMax(Math.max(...bars.map((bar) => Math.abs(bar.returnPct))), [1, 2.5, 5, 10])
  const balances = bars.map((bar) => bar.end)
  const lo = Math.min(...balances)
  const hi = Math.max(...balances)
  const pad = (hi - lo) * 0.15 || hi * 0.05 || 1
  const balMin = lo - pad
  const balMax = hi + pad
  const y = (pct) => PAD.top + plotH / 2 - (pct / maxAbs) * (plotH / 2)
  const yBal = (value) => PAD.top + plotH - ((value - balMin) / (balMax - balMin)) * plotH
  const slot = plotW / bars.length
  const barW = Math.min(slot * 0.5, 160)
  const cx = (index) => PAD.left + slot * index + slot / 2
  const line = bars.map((bar, index) => `${index ? 'L' : 'M'}${cx(index).toFixed(1)},${yBal(bar.end).toFixed(1)}`).join(' ')
  const ticks = [-maxAbs, -maxAbs / 2, 0, maxAbs / 2, maxAbs]
  const shown = active != null ? bars[active] : null

  return (
    <div className="overview-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Monthly return bars with a holdings value line">
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(tick)} y2={y(tick)} className={tick === 0 || Math.abs(tick) === maxAbs ? 'overview-axis' : 'overview-grid'} />
            <text x={PAD.left - 8} y={y(tick) + 4} textAnchor="end" className="overview-tick">{`${tick}%`}</text>
          </g>
        ))}
        {[0, 1, 2, 3, 4].map((step) => {
          const value = balMin + ((balMax - balMin) * step) / 4
          return <text key={step} x={W - PAD.right + 8} y={yBal(value) + 4} className="overview-tick">{money(value, 0)}</text>
        })}
        {bars.map((bar, index) => {
          const top = Math.min(y(bar.returnPct), y(0))
          return (
            <g key={bar.month} onMouseEnter={() => setActive(index)} onMouseLeave={() => setActive(null)} onFocus={() => setActive(index)} onBlur={() => setActive(null)} tabIndex={0} role="img" aria-label={`${bar.label}: ${signedPct(bar.returnPct, 2)}`}>
              <rect x={PAD.left + slot * index} y={PAD.top} width={slot} height={plotH} fill="transparent" />
              <rect x={cx(index) - barW / 2} y={top} width={barW} height={Math.max(Math.abs(y(bar.returnPct) - y(0)), 1)} rx="4"
                className={bar.returnPct >= 0 ? 'overview-bar overview-bar--gain' : 'overview-bar overview-bar--loss'} />
              <text x={cx(index)} y={H - PAD.bottom + 28} textAnchor="end" transform={`rotate(-40 ${cx(index)} ${H - PAD.bottom + 28})`} className="overview-tick">{bar.label}</text>
            </g>
          )
        })}
        <path d={line} fill="none" className="overview-line" />
        {bars.length === 1 && <circle cx={cx(0)} cy={yBal(bars[0].end)} r="4" className="overview-dot" />}
      </svg>
      {shown && (
        <div className="overview-tooltip" style={{ left: `${Math.min(Math.max(cx(active) / W * 100, 14), 86)}%` }} role="status">
          <strong>{longDate(shown.startDate)} to {longDate(shown.endDate)}</strong>
          <dl>
            <dt>Value</dt><dd>{money(shown.end, 2)}</dd>
            <dt>Return</dt><dd className={tone(shown.returnPct)}>{signedPct(shown.returnPct, 2)} ({signedMoney(shown.change)})</dd>
          </dl>
        </div>
      )}
      <div className="overview-legend">
        <span><i className="overview-legend-line" />Holdings value (today’s shares)</span>
        <span>Rate of return (<i className="overview-legend-dot overview-legend-dot--gain" />gain <i className="overview-legend-dot overview-legend-dot--loss" />loss)</span>
      </div>
    </div>
  )
}

function TotalReturnsCard({ period, holdingsSeriesFull }) {
  const { data: history } = useData('index-history.json')
  const range = selectPeriod(holdingsSeriesFull, period)
  const table = history && range
    ? buildReturnsTable({ history, portfolio: holdingsSeriesFull, frequency: 'custom', custom: { start: range.startDate, end: history.as_of || range.endDate }, growth: 'cumulative' })
    : null
  const rows = table ? [
    table.portfolio && { id: 'me', label: 'Your return', cell: table.portfolio.values.CUSTOM, strong: true },
    ...CARD_INDEXES.map((id) => table.rows.find((row) => row.id === id)).filter(Boolean).map((row) => ({ id: row.id, label: row.label, cell: row.values.CUSTOM })),
  ].filter(Boolean) : []
  return (
    <article className="card overview-card">
      <header><h3>Total returns</h3></header>
      {table ? <>
        <p className="returns-note">{longDate(range.startDate)} to {longDate(table.asOf)}</p>
        <p className="overview-card-sub"><strong>View your investment growth</strong><small>Time-weighted rate of return (pre-tax)</small></p>
        <ul className="overview-rows">
          {rows.map((row) => (
            <li key={row.id} className={row.strong ? 'overview-rows-strong' : ''}>
              <span>{row.label}</span>
              {row.cell ? <b className={tone(row.cell.pct)}>{signedPct(row.cell.pct, 2)}</b> : <b className="returns-cell--empty">--</b>}
            </li>
          ))}
        </ul>
      </> : <p className="returns-note">Index returns appear once the post-close market history loads.</p>}
    </article>
  )
}

function IncomeCard({ bars, flows, activities }) {
  const income = monthlyIncome(activities, bars)
  const max = Math.max(...income.map((row) => row.income), 0)
  return (
    <article className="card overview-card">
      <header><h3>Investment income</h3></header>
      {max > 0 ? (
        <div className="overview-income-bars" role="img" aria-label="Investment income by month">
          {income.map((row) => (
            <div key={row.month}><i style={{ height: `${Math.max(row.income / max * 100, row.income > 0 ? 4 : 0)}%` }} title={`${row.label}: ${money(row.income, 2)}`} /><small>{row.label}</small></div>
          ))}
        </div>
      ) : <p className="returns-note">No dividends or interest are recorded in this range.</p>}
      <ul className="overview-rows">
        <li><span>Investment income</span><b>{money(flows.income, 2)}</b></li>
        <li><span>Deposits</span><b>{money(flows.deposits, 2)}</b></li>
        <li><span>Withdrawals</span><b>{money(flows.withdrawals, 2)}</b></li>
      </ul>
    </article>
  )
}

function AllocationCard({ assetAllocation, totalValue }) {
  const [mode, setMode] = useState('percentages')
  const items = (assetAllocation || []).filter((item) => item.pct > 0)
  return (
    <article className="card overview-card">
      <header><h3>Asset allocation</h3></header>
      <div className="returns-controls">
        <fieldset>
          {[['percentages', 'Percentages'], ['dollars', 'Dollars']].map(([value, label]) => (
            <label key={value}><input type="radio" name="allocation-mode" checked={mode === value} onChange={() => setMode(value)} />{label}</label>
          ))}
        </fieldset>
      </div>
      {items.length ? (
        <>
          <AllocationDonut sectors={items.map((item) => ({ sector: item.label, pct: item.pct }))} totalLabel={money(totalValue)} />
          {mode === 'dollars' && <ul className="overview-rows">{items.map((item) => <li key={item.label}><span>{item.label}</span><b>{money(item.value, 2)}</b></li>)}</ul>}
        </>
      ) : <p className="returns-note">Priced holdings will appear here.</p>}
    </article>
  )
}

export default function PerformanceOverview({ holdings, holdingsSeriesFull, tracking, period, onPeriodChange }) {
  const range = selectPeriod(holdingsSeriesFull, period)
  const bars = monthlyBars(range)
  const flows = range ? flowsBetween(tracking?.activities, range.startDate, range.endDate) : { deposits: 0, withdrawals: 0, net: 0, income: 0 }
  const hasFlows = (tracking?.activities || []).length > 0

  return (
    <div className="performance-overview">
      <div className="card overview-pills" role="radiogroup" aria-label="Time range">
        {PERFORMANCE_PERIODS.map((item) => (
          <button key={item} type="button" role="radio" aria-checked={period === item} className={period === item ? 'is-active' : ''} onClick={() => onPeriodChange(item)}>{PILL_LABELS[item] || item}</button>
        ))}
      </div>

      <section className="card overview-balance" aria-labelledby="overview-balance-title">
        <div className="overview-balance-head">
          <div>
            <h3 id="overview-balance-title">Balance</h3>
            <strong className="overview-balance-value">{money(holdings.totalValue, 2)}</strong>
            {range && <small className={tone(range.dollarReturn)}>{signedMoney(range.dollarReturn)} ({signedPct(range.returnPct, 2)}) over this range</small>}
          </div>
          <div>
            <h3>Return</h3>
            {range ? <strong className={`overview-balance-value ${tone(range.returnPct)}`}>{signedPct(range.returnPct, 2)}</strong> : <strong className="overview-balance-value">--</strong>}
            {range && <small>{longDate(range.startDate)} to {longDate(range.endDate)}</small>}
          </div>
        </div>
        <dl className="overview-stats">
          <div><dt>Invested</dt><dd>{money(holdings.totalValue, 2)}</dd></div>
          <div><dt>Unrealized gain</dt><dd className={tone(holdings.totalGain || 0)}>{holdings.totalGain == null ? '--' : signedMoney(holdings.totalGain)}</dd></div>
          <div><dt>Investment income</dt><dd>{hasFlows ? money(flows.income, 2) : '--'}</dd></div>
          <div><dt>Net deposits and withdrawals</dt><dd className={hasFlows ? tone(flows.net) : ''}>{hasFlows ? signedMoney(flows.net) : '--'}</dd></div>
        </dl>
        <ReturnChart bars={bars} />
      </section>

      <div className="overview-card-row">
        <TotalReturnsCard period={period} holdingsSeriesFull={holdingsSeriesFull} />
        <IncomeCard bars={bars} flows={flows} activities={tracking?.activities} />
        <AllocationCard assetAllocation={holdings.assetAllocation} totalValue={holdings.totalValue} />
      </div>
    </div>
  )
}
