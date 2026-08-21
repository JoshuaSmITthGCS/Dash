// View 02 — Performance. Time-weighted return against the selected benchmark, the
// opportunity-cost comparison from the recorded purchase dates, and (once enough recorded
// account values and settled cash flows exist) the money-weighted return and cash-flow ledger.
//
// This view always reads full holdings history; the Data overview's scope switch narrows
// the statistics, not this chart.
//
// Two independent return computations live on this page, deliberately kept apart:
//  - "Time-weighted return" above reprices today's exact share count against historical
//    closes, so it is immune to cash-flow timing by construction and needs no manual
//    input -- it accumulates purely from published price history.
//  - "Money-weighted return (XIRR)" below is computed from recorded account-value snapshots
//    and a settled deposit/withdrawal ledger (portfolioReturnSummary, src/lib/portfolioAnalytics.js).
//    It reflects the actual size and timing of your cash flows, which the reprice-based figure
//    above deliberately does not. It needs real recorded history to mean anything, so it starts
//    in an honest "accumulating" state -- the same pattern this app already uses for score
//    history and other young live series -- rather than being backfilled or approximated.

import { useEffect, useState } from 'react'
import GrowthChart from '../../components/GrowthChart'
import Icon from '../../components/Icons'
import { compareBenchmarkSeries, netInvestedCapital, portfolioReconciliationBridge, portfolioReturnSummary, selectPeriod } from '../../lib/portfolioAnalytics.js'
import { marketDate } from '../../lib/usePortfolioTracking.js'
import { money, moveColor, PERFORMANCE_PERIODS, PERIOD_NAMES, signedPct } from './format.js'

const CASH_FLOW_TYPES = [
  { value: 'deposit', label: 'Deposit' },
  { value: 'withdrawal', label: 'Withdrawal' },
  { value: 'dividend', label: 'Dividend received' },
  { value: 'fee', label: 'Fee charged' },
]

function CashFlowLedger({ tracking }) {
  const [form, setForm] = useState({ type: 'deposit', amount: '', effectiveDate: new Date().toISOString().slice(0, 10) })
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  const submit = async (event) => {
    event.preventDefault()
    const amount = parseFloat(form.amount)
    if (!Number.isFinite(amount) || amount <= 0 || !form.effectiveDate) {
      setMessage('Enter a positive amount and a date.')
      return
    }
    setSaving(true)
    const result = await tracking.recordActivity({ type: form.type, amount, effectiveDate: form.effectiveDate })
    setSaving(false)
    if (result?.success === false) {
      setMessage(`Could not save: ${result.error || 'Unknown error'}`)
      return
    }
    setMessage(`${CASH_FLOW_TYPES.find((row) => row.value === form.type)?.label} of ${money(amount)} recorded for ${form.effectiveDate}.`)
    setForm({ type: form.type, amount: '', effectiveDate: new Date().toISOString().slice(0, 10) })
  }

  const flows = netInvestedCapital(tracking.activities)
  const recent = [...(tracking.activities || [])]
    .filter((row) => CASH_FLOW_TYPES.some((type) => type.value === row.type))
    .slice(0, 8)

  return (
    <div className="card cash-flow-ledger">
      <div className="portfolio-section-heading">
        <div><span className="eyebrow">Accounting</span><h3>Cash flow ledger</h3></div>
      </div>
      <p className="cash-flow-ledger-note">
        Record deposits and withdrawals here to unlock a money-weighted (XIRR) return below and,
        once enough dated history accumulates, a reconciliation bridge. This does not affect the
        time-weighted return above, which already excludes cash flows by construction.
      </p>
      <form className="holding-edit-form cash-flow-form" onSubmit={submit}>
        <label><span>Type</span>
          <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
            {CASH_FLOW_TYPES.map((row) => <option key={row.value} value={row.value}>{row.label}</option>)}
          </select>
        </label>
        <label><span>Amount</span>
          <input className="inline-edit-input" type="number" step="0.01" min="0" value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        </label>
        <label><span>Date</span>
          <input className="inline-edit-input" type="date" value={form.effectiveDate}
            onChange={(e) => setForm({ ...form, effectiveDate: e.target.value })} />
        </label>
        <button type="submit" className="secondary-button" disabled={saving}>{saving ? 'Saving…' : 'Record'}</button>
      </form>
      {message && <p className="cash-flow-ledger-message">{message}</p>}

      <label className="cash-flow-ledger-complete">
        <input type="checkbox" checked={Boolean(tracking.trackingState?.ledgerComplete)}
          onChange={(e) => tracking.setLedgerComplete(e.target.checked)} />
        <span>This ledger has every deposit and withdrawal since tracking started — enable the money-weighted return once checked.</span>
      </label>

      {flows.available && <p className="cash-flow-ledger-summary">Net external flows recorded: {money(flows.deposits)} in, {money(flows.withdrawals)} out ({flows.count} entries).</p>}

      {recent.length > 0 && (
        <ul className="cash-flow-ledger-list">
          {recent.map((row) => (
            <li key={row.id}>
              <span>{CASH_FLOW_TYPES.find((type) => type.value === row.type)?.label || row.type}</span>
              <span>{money(row.amount)}</span>
              <span>{row.effectiveDate}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ReconciliationBridge({ bridge }) {
  if (!bridge) return null
  if (!bridge.available) {
    return <p className="cash-flow-ledger-note">Reconciliation bridge is accumulating: {bridge.reason}</p>
  }
  const lines = [
    ['Beginning NAV', bridge.beginningNav],
    ['+ Deposits', bridge.deposits],
    ['− Withdrawals', -bridge.withdrawals],
    ['+ Dividends', bridge.dividends],
    ['− Fees', -bridge.fees],
    ['+ Realized gains', bridge.realizedGains],
    ['+ Unrealized gain change', bridge.unrealizedGainChange],
    ['+ FX (not tracked)', bridge.fx.value],
    ['− Taxes (not tracked)', -bridge.taxes.value],
    ['− Trading costs (not tracked)', -bridge.tradingCosts.value],
  ]
  return (
    <div className={`card cash-flow-ledger reconciliation-bridge reconciliation-bridge--${bridge.status.toLowerCase()}`}>
      <div className="portfolio-section-heading">
        <div><span className="eyebrow">Accounting</span><h3>Reconciliation bridge</h3></div>
        <span className={`reconciliation-status reconciliation-status--${bridge.status.toLowerCase()}`}>{bridge.status === 'RECONCILED' ? 'Reconciled' : 'Reconciliation failed'}</span>
      </div>
      <p className="cash-flow-ledger-note">{bridge.startDate} to {bridge.endDate}, the most recent recorded period.</p>
      <ul className="cash-flow-ledger-list reconciliation-bridge-list">
        {lines.map(([label, value]) => (
          <li key={label}><span>{label}</span><span>{money(value, 2)}</span></li>
        ))}
        <li className="reconciliation-bridge-total"><span>= Reconstructed ending NAV</span><span>{money(bridge.reconstructedEndingNav, 2)}</span></li>
        <li><span>Recorded ending NAV</span><span>{money(bridge.endingNav, 2)}</span></li>
        <li className={bridge.reconciled ? 'positive' : 'negative'}><span>Residual</span><span>{money(bridge.residual, 2)}</span></li>
      </ul>
      <p className="cash-flow-ledger-note">{bridge.reason}</p>
    </div>
  )
}

export default function Performance({
  holdings,
  holdingsSeriesFull,
  benchmarks,
  performancePeriod,
  onPerformancePeriodChange,
  tracking,
}) {
  const { growth, versusIndex } = holdings
  const { analyticsBenchmarkSeries, selectedBenchmarkSymbol, selectedBenchmarkLabel } = benchmarks

  // Auto-record today's portfolio value once per NY market day so the recorded account-value
  // series (which the money-weighted return below needs) starts accumulating from real,
  // observed values -- never backfilled, same discipline the pipeline's own PIT store uses.
  useEffect(() => {
    if (!tracking?.recordSnapshot || !Number.isFinite(holdings.totalValue) || holdings.totalValue <= 0) return
    const today = marketDate()
    const alreadyRecorded = (tracking.snapshots || []).some((row) => (row.marketDate || String(row.recordedAt).slice(0, 10)) === today)
    if (alreadyRecorded) return
    const pricedCount = (holdings.positions || []).filter((row) => row.currentValue != null).length
    const coveragePct = holdings.positions?.length ? Math.round(pricedCount / holdings.positions.length * 100) : 0
    tracking.recordSnapshot({ value: holdings.totalValue, coveragePct, source: 'performance_view', unrealizedGain: holdings.totalGain })
  }, [holdings.totalValue, holdings.totalGain, tracking?.snapshots])

  const returnSummary = tracking
    ? portfolioReturnSummary(tracking.snapshots, tracking.activities, Boolean(tracking.trackingState?.ledgerComplete))
    : null
  const bridge = tracking ? portfolioReconciliationBridge(tracking.snapshots, tracking.activities) : null

  const comparison = compareBenchmarkSeries(
    selectPeriod(holdingsSeriesFull, performancePeriod),
    analyticsBenchmarkSeries ? [{
      symbol: selectedBenchmarkSymbol,
      label: selectedBenchmarkLabel,
      dates: analyticsBenchmarkSeries.dates,
      values: analyticsBenchmarkSeries.values,
    }] : [],
  )
  const performanceIndex = comparison ? {
    dates: comparison.dates,
    portfolio: comparison.portfolio.values.map((value) => 100 * value / comparison.portfolio.values[0]),
    benchmark: comparison.benchmarks[0].values.map((value) => 100 * value / comparison.benchmarks[0].values[0]),
  } : null

  return (
    <section className="portfolio-dashboard-section portfolio-performance-section" aria-labelledby="portfolio-performance-title">
      <header className="portfolio-section-heading">
        <div><span className="portfolio-section-number">02</span><div><span className="eyebrow">Benchmark</span><h2 id="portfolio-performance-title">Performance</h2></div></div>
        <label><span>Compare over</span><select value={performancePeriod} onChange={(event) => onPerformancePeriodChange(event.target.value)}>{PERFORMANCE_PERIODS.map((period) => <option key={period} value={period}>{PERIOD_NAMES[period]}</option>)}</select></label>
      </header>
      {performanceIndex ? <div className="portfolio-benchmark-chart">
        <div className="portfolio-benchmark-kpis">
          <span><small>Time-weighted return</small><strong className={comparison.portfolio.returnPct >= 0 ? 'positive' : 'negative'}>{signedPct(comparison.portfolio.returnPct, 2)}</strong></span>
          <span><small>{selectedBenchmarkLabel}</small><strong className={comparison.benchmarks[0].returnPct >= 0 ? 'positive' : 'negative'}>{signedPct(comparison.benchmarks[0].returnPct, 2)}</strong></span>
          <span><small>Difference</small><strong className={comparison.portfolio.returnPct - comparison.benchmarks[0].returnPct >= 0 ? 'positive' : 'negative'}>{signedPct(comparison.portfolio.returnPct - comparison.benchmarks[0].returnPct, 2)}</strong></span>
        </div>
        <GrowthChart
          height={330}
          width={1080}
          dates={performanceIndex.dates}
          series={[
            { label: 'Portfolio TWR', values: performanceIndex.portfolio, color: 'var(--series-stock)', emphasis: true },
            { label: selectedBenchmarkLabel, values: performanceIndex.benchmark, color: 'var(--series-benchmark)', dashPattern: '7 5' },
          ]}
          valueFormatter={(value) => signedPct(value - 100, 1)}
          caption={`Both lines start at 0% on the same market date. Your line reprices today's exact shares at matched historical closes, so cash transfers cannot affect it; ${selectedBenchmarkLabel} uses the same dates.`}
          lineStyle="line"
        />
      </div> : <div className="unavailable-panel"><strong>Comparison history is still building</strong><p>Two shared market dates are needed to compare your current holdings with {selectedBenchmarkLabel}.</p></div>}

      {returnSummary?.moneyWeighted?.available ? (
        <div className="portfolio-benchmark-kpis money-weighted-kpi">
          <span><small>Money-weighted return (XIRR)</small><strong className={returnSummary.moneyWeighted.rate >= 0 ? 'positive' : 'negative'}>{signedPct(returnSummary.moneyWeighted.rate, 2)}</strong></span>
        </div>
      ) : returnSummary?.moneyWeighted?.reason && (
        <p className="cash-flow-ledger-note">Money-weighted return (XIRR) is accumulating: {returnSummary.moneyWeighted.reason}</p>
      )}

      {tracking && <CashFlowLedger tracking={tracking} />}
      {tracking && <ReconciliationBridge bridge={bridge} />}

      {growth && (
        <details className="card portfolio-comparison">
          <summary>
            <div>
              <span className="eyebrow">Opportunity cost</span>
              <strong>What if I chose the S&amp;P 500–or did not invest?</strong>
              <small>Same cost-basis dollars on your recorded purchase dates</small>
            </div>
            <div className="comparison-summary-side">
              {versusIndex && <span className="comparison-edge" style={{ color: moveColor(versusIndex.excessReturnPct) }}>{signedPct(versusIndex.excessReturnPct)} vs S&amp;P</span>}
              <span className="comparison-toggle" aria-hidden="true"><Icon name="chevron" size={18} /></span>
            </div>
          </summary>
          <div className="portfolio-comparison-chart">
            <GrowthChart
              dates={growth.dates}
              series={[
                { label: 'My holdings', values: growth.holdings, color: 'var(--series-stock)', emphasis: true },
                { label: 'S&P 500, same cost basis', values: growth.benchmark, color: 'var(--series-benchmark)', dashPattern: '7 5' },
                { label: 'Cost basis held flat', values: growth.cash, color: 'var(--series-cash)', dashPattern: '2 5' },
              ]}
              title="One-to-one performance from your investment dates"
              caption={`Each holding starts with its exact cost-basis dollars on its recorded purchase date, then follows that stock’s price return. The S&P receives the identical starting dollars on the identical date; the flat line leaves that cost basis unchanged. Covers ${growth.trackedTickers.length} dated position${growth.trackedTickers.length === 1 ? '' : 's'} from ${growth.firstInvestmentDate}${growth.untrackedCount ? `. ${growth.untrackedCount} missing a usable date or published history` : ''}.`}
              zoomable
            />
          </div>
        </details>
      )}
    </section>
  )
}
