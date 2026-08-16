// View 01 — Summary. Account KPIs and value chart, the holdings section, the sell-signal
// queue, concentration warnings, and the allocation split.

import GrowthChart from '../../components/GrowthChart'
import Icon from '../../components/Icons'
import AnimatedNumber from '../../components/AnimatedNumber.jsx'
import AllocationDonut from '../../components/AllocationDonut.jsx'
import { ActionPill } from '../../components/ActionGuidance'
import { currentHoldingsPerformanceSeriesForPeriod } from '../../lib/portfolioPerformance'
import { latestMarketDayReturn, selectPeriod } from '../../lib/portfolioAnalytics.js'
import { liveTodayPortfolioReturn } from '../../lib/afterHoursQuotes.js'
import { money, PERIOD_NAMES, signedPct, SUMMARY_PERIODS } from './format.js'
import Holdings from './Holdings.jsx'

/** The account value line for the selected range, preferring recorded five-minute snapshots. */
function summaryChartFor({ trackingSnapshots, positions, priceData, period, holdingsSeriesFull }) {
  const recorded = currentHoldingsPerformanceSeriesForPeriod(trackingSnapshots, positions, priceData, period)
  const chart = recorded || (period === '1H' ? null : selectPeriod(holdingsSeriesFull, period))
  if (!chart) return { chart: null, profit: null, returnPct: null }
  return {
    chart,
    profit: chart.dollarReturn
      ?? (chart.values?.length > 1 ? chart.values.at(-1) - chart.values[0] : null),
    returnPct: chart.returnPct
      ?? (chart.values?.length > 1 && chart.values[0]
        ? (chart.values.at(-1) / chart.values[0] - 1) * 100
        : null),
  }
}

function SuggestedActions({ actionable, open, onToggle, onSelectStock }) {
  return (
    <details id="sell-signals" className="card card-pad suggested-actions" open={open} onToggle={(event) => onToggle(event.currentTarget.open)}>
      <summary><span><span className="sec-label">Suggested actions</span><strong>{actionable.length} holding{actionable.length === 1 ? '' : 's'} to review</strong></span><Icon name="chevron" /></summary>
      <div className="portfolio-suggested-list">
        {actionable.length ? actionable.map((pos) => (
          <div className="portfolio-suggested-row" key={pos.id || pos.ticker}>
            <ActionPill recommendation={pos.recommendation} />
            <b className="mono">{pos.ticker}</b>
            <span>{pos.recommendation.summary}</span>
            {pos.recommendation.suggestedTrimPct > 0 && (
              <small className="mono">
                {((pos.shares * pos.recommendation.suggestedTrimPct) / 100).toFixed(2)} of {pos.shares} shares
                {' '}≈ {money((pos.currentValue * pos.recommendation.suggestedTrimPct) / 100)}
              </small>
            )}
            <button className="chip button-chip" onClick={() => onSelectStock(pos)}>Why</button>
          </div>
        )) : <p className="portfolio-suggested-empty">No sell actions need review. Your current hold guidance remains visible on each position.</p>}
      </div>
    </details>
  )
}

function ConcentrationCard({ exposure }) {
  if (!exposure.warnings.length) return null
  return (
    <div className="card card-pad portfolio-concentration-card">
      <div className="sec-label">Concentration risk</div>
      <div className="portfolio-concentration-list">
        {exposure.warnings.map((warning) => (
          <div key={`${warning.type}-${warning.label}`}>
            <span className="mono">{warning.pct.toFixed(1)}%</span>
            <span>{warning.message}</span>
          </div>
        ))}
      </div>
      <p>
        Illustrative guidelines only ({exposure.maxPositionPct}% per position, {exposure.maxSectorPct}% per
        sector) – not a rule to force a sale, but a prompt to size new buys and rebalancing with the
        concentration you already carry in mind.
      </p>
    </div>
  )
}

function AllocationSection({ assetAllocation, sectorAllocation, totalValue }) {
  return (
    <section className="portfolio-dashboard-section portfolio-allocation-section" aria-labelledby="portfolio-allocation-title">
      <header className="portfolio-subsection-heading">
        <div><span className="eyebrow">Portfolio mix</span><h3 id="portfolio-allocation-title">Allocation</h3></div>
        <span>Assets and sectors</span>
      </header>
      <div className="portfolio-allocation-grid">
        <article className="portfolio-allocation-card">
          <header><div><span className="eyebrow">By role</span><h3>Asset allocation</h3></div><small>Current market value</small></header>
          <div className="portfolio-asset-bars">{assetAllocation.map((item) => <div key={item.label}>
            <div><span>{item.label}</span><strong>{item.pct.toFixed(1)}%</strong></div>
            <i aria-hidden="true"><span style={{ width: `${item.pct}%` }} /></i>
            <small>{money(item.value, 2)}</small>
          </div>)}</div>
          <p>Stocks with an active, evidence-backed catalyst are short-term; other stocks are long-term. ETFs remain separate.</p>
        </article>
        <article className="portfolio-allocation-card portfolio-sector-card">
          <header><div><span className="eyebrow">By exposure</span><h3>Sector allocation</h3></div><small>ETF look-through where available</small></header>
          {sectorAllocation.length ? <AllocationDonut sectors={sectorAllocation} totalLabel={money(totalValue)} /> : <div className="unavailable-panel"><strong>Sector data unavailable</strong><p>Priced holdings with sector coverage will appear here.</p></div>}
        </article>
      </div>
    </section>
  )
}

export default function Summary({
  holdings,
  positions,
  priceData,
  holdingsSeriesFull,
  trackingSnapshots,
  quotesRefreshing,
  summaryPeriod,
  onSummaryPeriodChange,
  suggestedActionsOpen,
  onSuggestedActionsToggle,
  onSelectStock,
  ...holdingsProps
}) {
  const { portfolioStats, assetAllocation, sectorAllocation, actionable, exposure } = holdings
  const summary = summaryChartFor({ trackingSnapshots, positions, priceData, period: summaryPeriod, holdingsSeriesFull })
  const currentSessionMove = liveTodayPortfolioReturn(positions, priceData)
  const todayMove = currentSessionMove.available ? currentSessionMove : latestMarketDayReturn(holdingsSeriesFull)

  return (
    <section className="portfolio-page-section" aria-labelledby="portfolio-summary-title">
      <div className="portfolio-dashboard-section portfolio-summary-section">
        <header className="portfolio-section-heading">
          <div><span className="portfolio-section-number">01</span><div><span className="eyebrow">Overview</span><h2 id="portfolio-summary-title">Summary</h2></div></div>
          <label><span>Time range</span><select value={summaryPeriod} onChange={(event) => onSummaryPeriodChange(event.target.value)}>{SUMMARY_PERIODS.map((period) => <option key={period} value={period}>{PERIOD_NAMES[period]}</option>)}</select></label>
        </header>
        <div className="portfolio-summary-kpis">
          <span><small>Invested value{quotesRefreshing && <Icon name="sync" size={12} className="refresh-spin hero-value-spinner" aria-hidden="true" />}</small><strong>{portfolioStats.totalValue == null ? '–' : <AnimatedNumber value={portfolioStats.totalValue} format={(value) => money(value, 2)} />}</strong></span>
          <span><small>Today · regular session</small><strong className={todayMove?.dollarReturn >= 0 ? 'positive' : 'negative'}>{todayMove?.dollarReturn == null ? 'Unavailable' : `${todayMove.dollarReturn >= 0 ? '+' : '−'}${money(Math.abs(todayMove.dollarReturn), 2)} · ${signedPct(todayMove.returnPct, 2)}`}</strong></span>
          <span><small>Total profit · {PERIOD_NAMES[summaryPeriod]}</small><strong className={summary.profit >= 0 ? 'positive' : 'negative'}>{summary.profit == null ? 'Unavailable' : `${summary.profit >= 0 ? '+' : '−'}${money(Math.abs(summary.profit), 2)} · ${signedPct(summary.returnPct, 2)}`}</strong></span>
        </div>
        {summary.chart ? <GrowthChart
          className="portfolio-summary-chart"
          height={390}
          width={1080}
          dates={summary.chart.dates}
          series={[{ label: 'Current holdings', values: summary.chart.values, color: 'var(--series-stock)', emphasis: true }]}
          valueFormatter={(value) => money(value, 2)}
          caption={summary.chart.methodology || 'Current quantities applied to historical prices; only invested holdings are included.'}
          lineStyle="line"
        /> : <div className="unavailable-panel"><strong>{PERIOD_NAMES[summaryPeriod]} history is still building</strong><p>Two five-minute account observations are needed to draw this range.</p></div>}
      </div>

      <Holdings
        holdings={holdings}
        positionCount={positions.length}
        onSelectStock={onSelectStock}
        {...holdingsProps}
      />

      <SuggestedActions
        actionable={actionable}
        open={suggestedActionsOpen}
        onToggle={onSuggestedActionsToggle}
        onSelectStock={onSelectStock}
      />

      <ConcentrationCard exposure={exposure} />

      <AllocationSection
        assetAllocation={assetAllocation}
        sectorAllocation={sectorAllocation}
        totalValue={portfolioStats.totalValue}
      />
    </section>
  )
}
