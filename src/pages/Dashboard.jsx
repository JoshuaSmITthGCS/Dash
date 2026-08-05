import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useData } from '../lib/useData.js'
import { useAuth } from '../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'
import { buildPortfolioPriceData } from '../lib/portfolioPosition.js'
import { usePreferences, formatPreferenceMoney } from '../lib/PreferencesContext.jsx'
import { signedPct } from '../lib/formatters.js'
import {
  BENCHMARKS, compareBenchmarkSeries, concentrationLiquidityScore, contributionAdjustedPerformance, currentHoldingsSeries, diversificationScore,
  enrichPortfolio, intradayPortfolioHigh, latestMarketDayReturn, performanceRating, planningReturnRates, portfolioScore,
  resilienceIndex, scenarioProjection, selectPeriod, trackedAllTimeEarnings,
} from '../lib/portfolioAnalytics.js'
import { beatMarketStreak, portfolioMood, valueStreak } from '../lib/traderInsights.js'
import { Loading, Empty, Tier } from '../components/Bits.jsx'
import GrowthChart from '../components/GrowthChart.jsx'
import CompanyLogo from '../components/CompanyLogo.jsx'
import Icon from '../components/Icons.jsx'
import { getRecommendation } from '../lib/recommendation.js'
import { usePortfolioTracking } from '../lib/usePortfolioTracking.js'
import { usePortfolioQuotes } from '../lib/usePortfolioQuotes.js'
import { afterHoursPortfolioReturn } from '../lib/afterHoursQuotes.js'

const WATCH_KEY = 'valuesignal.watchlist'
const PERIODS = ['1D', '1W', '1M', '3M', '6M', '1Y', 'All']
const BENCHMARK_STYLES = [
  { color: 'var(--series-benchmark)', dashPattern: '7 5' },
  { color: 'var(--series-benchmark-2)', dashPattern: '3 4' },
  { color: 'var(--series-benchmark-3)', dashPattern: '10 4 2 4' },
]

function Metric({ label, value, note, tone = '' }) {
  return <article className="report-metric"><span>{label}</span><strong className={tone}>{value}</strong><small>{note}</small></article>
}

function ScoreCard({ label, result, note }) {
  return <article className="report-score-card"><div className="score-orbit" style={{ '--score': result?.score || 0 }}><strong>{result?.available ? result.score : '—'}</strong><span>/100</span></div><div><h3>{label}</h3><p>{result?.available ? note : result?.reason || 'Not enough portfolio data yet.'}</p>{result?.provisional && <span className="provisional-badge">Provisional</span>}</div></article>
}

function Customizer({ widgets, onChange, onDone }) {
  const move = (index, direction) => {
    const target = index + direction
    if (target < 0 || target >= widgets.length) return
    const next = [...widgets]; [next[index], next[target]] = [next[target], next[index]]
    onChange(next.map((widget, order) => ({ ...widget, order })))
  }
  return <aside className="customizer-panel"><div className="customizer-head"><div><span className="eyebrow">Settings</span><h2>Customize report</h2></div><button className="icon-button" onClick={onDone} aria-label="Close customization"><Icon name="close" /></button></div><p>Choose supporting modules and their reading order. Core financial-report metrics always remain visible.</p><div className="customizer-list">{widgets.map((widget, index) => <div className="customizer-row" key={widget.id}><Icon name="grip" /><div><strong>{widget.label}</strong><small>{widget.locked ? 'Required' : `Position ${index + 1}`}</small></div><label className="switch compact-switch"><span className="sr-only">Show {widget.label}</span><input type="checkbox" checked={widget.visible} disabled={widget.locked} onChange={(event) => onChange(widgets.map((item) => item.id === widget.id ? { ...item, visible: event.target.checked } : item))} /><span /></label><div className="reorder-buttons"><button onClick={() => move(index, -1)} disabled={!index}><Icon name="up" /></button><button onClick={() => move(index, 1)} disabled={index === widgets.length - 1}><Icon name="down" /></button></div></div>)}</div><button className="primary-button" onClick={onDone}>Save report</button></aside>
}

export default function Dashboard() {
  const { data, loading } = useData('report.json')
  const { currentUser } = useAuth()
  const { positions, loading: portfolioLoading } = useFirebasePortfolio()
  const tracking = usePortfolioTracking()
  // Quietly refreshes at 9pm local time (see src/lib/nightlyRefresh.js) so after-hours has
  // real Yahoo data by the time anyone looks at the report, not just when someone happens to
  // hit refresh on the Portfolio page.
  const portfolioQuotes = usePortfolioQuotes(positions.map((position) => position.ticker))
  const { preferences, setWidgets, updatePreferences } = usePreferences()
  const { data: benchmarkReport, loading: benchmarkLoading } = useData(positions.length ? 'benchmark-report.json' : null)
  const [period, setPeriod] = useState(preferences.defaultChartPeriod)
  const [draftWidgets, setDraftWidgets] = useState(preferences.widgets)
  const customize = new window.URLSearchParams(window.location.search).get('customize') === '1'

  const watchlist = useMemo(() => { try { return JSON.parse(localStorage.getItem(WATCH_KEY)) || [] } catch { return [] } }, [])
  if (loading || (currentUser && (portfolioLoading || (positions.length > 0 && benchmarkLoading)))) return <Loading />
  if (!data?.research?.length) return <Empty note="No advisor dataset is available yet." />

  const rows = data.research
  const prices = buildPortfolioPriceData(data.screen_universe || [], data.portfolio_coverage || [], rows)
  const portfolio = enrichPortfolio(positions, prices)
  const holdingsSeries = currentHoldingsSeries(positions, prices, data.benchmark_history?.dates || [])
  const selected = selectPeriod(holdingsSeries, period)
  const selectedBenchmarkSymbols = preferences.defaultBenchmarks || [preferences.defaultBenchmark]
  const selectedBenchmarkSeries = selectedBenchmarkSymbols.map((symbol) => {
    const history = benchmarkReport?.histories?.[symbol]
    const definition = BENCHMARKS.find((item) => item.symbol === symbol)
    return history ? { symbol, label: definition?.label || symbol, dates: history.dates, closes: history.closes } : null
  }).filter(Boolean)
  const comparison = compareBenchmarkSeries(selected, selectedBenchmarkSeries)
  const chartedPortfolio = comparison?.portfolio || selected
  const today = latestMarketDayReturn(holdingsSeries)
  const afterHours = afterHoursPortfolioReturn(positions, portfolioQuotes.quotes)
  const diversification = diversificationScore(portfolio.positions)
  const scorePortfolioPeriod = selectPeriod(holdingsSeries, '1Y') || selectPeriod(holdingsSeries, 'All')
  const scoreComparison = compareBenchmarkSeries(scorePortfolioPeriod, selectedBenchmarkSeries.slice(0, 1))
  const resilience = resilienceIndex(scoreComparison?.portfolio.values || scorePortfolioPeriod?.values || [], diversification)
  const performance = performanceRating(scoreComparison?.portfolio, scoreComparison?.benchmarks[0])
  const concentrationLiquidity = concentrationLiquidityScore(portfolio.positions)
  const overall = portfolioScore({ diversification, resilience, performance, benchmarkEfficiency: performance.available ? performance.score : null, concentrationLiquidity, dataCompleteness: Math.round(portfolio.coveragePct || 0) })
  const leader = rows[0]
  const watchRows = watchlist.map((ticker) => rows.find((row) => row.ticker === ticker)).filter(Boolean).slice(0, 4)
  const money = (value) => preferences.privacyMode ? '••••••' : formatPreferenceMoney(value, preferences.numberFormat)
  const tone = (value) => value == null ? '' : value >= 0 ? 'positive' : 'negative'
  const forecast = preferences.forecast
  const planningRates = planningReturnRates(portfolio.positions, holdingsSeries?.values || [], today?.date)
  const scenarioHorizons = [1, 5, 10].map((years) => ({ years, values: planningRates.available ? ['conservative', 'base', 'optimistic'].map((label) => ({ label, rate: planningRates[label], value: scenarioProjection(portfolio.totalValue, planningRates[label], years, forecast.recurringAnnual) })) : [] }))
  const yearsToRetirement = Math.max(0, forecast.retirementAge - forecast.currentAge)
  const retirementValues = planningRates.available ? ['conservative', 'base', 'optimistic'].map((label) => ({ label, value: scenarioProjection(portfolio.totalValue, planningRates[label], yearsToRetirement, forecast.recurringAnnual) })) : []
  const latestTrackingDate = tracking.snapshots.at(-1)?.marketDate
  const intraday = intradayPortfolioHigh(tracking.snapshots.filter((snapshot) => snapshot.marketDate === latestTrackingDate))
  const allTimeEarnings = trackedAllTimeEarnings(portfolio, tracking.activities, tracking.trackingState)
  const actionable = portfolio.positions.map((row) => ({ ...row, recommendation: row.priceInfo ? getRecommendation(row.priceInfo) : null })).filter((row) => row.recommendation && row.recommendation.action !== 'HOLD')

  const uninvestedCash = tracking.trackingState?.cashTrackingEnabled ? Number(tracking.trackingState.cashBalance || 0) : 0
  const contributionPerformance = contributionAdjustedPerformance(portfolio.totalValue + uninvestedCash, tracking.activities, tracking.trackingState?.cashFlowHistoryComplete)
  const primaryBenchmarkHistory = benchmarkReport?.histories?.[preferences.defaultBenchmark]
    ? { dates: benchmarkReport.histories[preferences.defaultBenchmark].dates, closes: benchmarkReport.histories[preferences.defaultBenchmark].closes, symbol: preferences.defaultBenchmark }
    : null
  const beatStreak = primaryBenchmarkHistory ? beatMarketStreak(tracking.snapshots, primaryBenchmarkHistory) : { available: false }
  const greenStreak = valueStreak(tracking.snapshots)
  const mood = portfolioMood({ returnPct: contributionPerformance.returnPct, diversificationScore: diversification.score, streak: beatStreak.available ? beatStreak : greenStreak })

  const toggleBenchmark = (symbol) => {
    const next = selectedBenchmarkSymbols.includes(symbol)
      ? selectedBenchmarkSymbols.filter((item) => item !== symbol)
      : [...selectedBenchmarkSymbols, symbol].slice(0, 3)
    if (!next.length) return
    updatePreferences({ defaultBenchmarks: next, defaultBenchmark: next[0] })
  }

  const saveCustomization = () => { setWidgets(draftWidgets); window.history.replaceState({}, '', '/'); window.location.reload() }

  return <div className="financial-report-page">
    {customize && <Customizer widgets={draftWidgets} onChange={setDraftWidgets} onDone={saveCustomization} />}
    <header className="page-head report-head"><div><span className="eyebrow">Latest close · {String(data.generated_at).slice(0, 10)}</span><h1 className="page-title">Financial Report</h1><p className="page-sub">Your portfolio, explained with traceable daily-close data.</p></div><button className="icon-button desktop-only" onClick={() => updatePreferences({ privacyMode: !preferences.privacyMode })} aria-label={preferences.privacyMode ? 'Show balances' : 'Hide balances'}><Icon name={preferences.privacyMode ? 'eye-off' : 'eye'} /></button></header>

    {!currentUser || !positions.length ? <section className="report-empty-state"><span className="eyebrow">Portfolio report</span><h2>{currentUser ? 'Add holdings to unlock your report' : 'Sign in to see your financial report'}</h2><p>Research remains available now. Portfolio analytics appear only after holdings and per-share cost basis are available.</p><Link className="primary-button" to={currentUser ? '/portfolio' : '/research'}>{currentUser ? 'Add holdings' : 'Explore research'}</Link></section> : <>
      <section className="report-hero-grid">
        <article className="report-hero">
          <span>Current portfolio value</span>
          <strong>{money(portfolio.totalValue)}</strong>
          <div className="report-hero-pills">
            <span className={`value-pill ${today?.dollarReturn == null ? 'neutral' : today.dollarReturn >= 0 ? 'positive' : 'negative'}`}>
              {today ? `${today.dollarReturn >= 0 ? '▲' : '▼'} ${money(Math.abs(today.dollarReturn))} · ${signedPct(today.returnPct, 2)} today` : 'Today — unavailable'}
            </span>
            <span className={`value-pill ${!afterHours.available ? 'neutral' : afterHours.dollarReturn >= 0 ? 'positive' : 'negative'}`}
              title={afterHours.available
                ? `${afterHours.coverage} of ${positions.length} holdings had a post-market quote from Yahoo`
                : 'Refreshes automatically at 9pm local time from Yahoo, once the after-hours session has quotes for a held position.'}>
              {afterHours.available
                ? `${afterHours.dollarReturn >= 0 ? '▲' : '▼'} ${money(Math.abs(afterHours.dollarReturn))}${afterHours.returnPct != null ? ` · ${signedPct(afterHours.returnPct, 2)}` : ''} after-hours`
                : 'After-hours — refreshes at 9pm'}
            </span>
          </div>
          <small>{portfolio.positions.length} holdings · {Math.round(portfolio.coveragePct)}% price coverage</small>
        </article>
        <Metric label="Today’s return" value={today ? `${today.dollarReturn >= 0 ? '+' : '−'}${money(Math.abs(today.dollarReturn))}` : '—'} note={`${signedPct(today?.returnPct)} close-to-close through ${today?.date || 'unavailable'}`} tone={tone(today?.dollarReturn)} />
        <Metric label="Total unrealized return" value={portfolio.gain == null ? '—' : `${portfolio.gain >= 0 ? '+' : '−'}${money(Math.abs(portfolio.gain))}`} note={`${signedPct(portfolio.gainPct)} versus entered per-share cost basis`} tone={tone(portfolio.gain)} />
        <Metric label="Invested cost basis" value={money(portfolio.totalCost)} note="Shares × entered per-share cost; not net contributed capital" />
      </section>

      <section className="card insights-recap dashboard-pulse" aria-labelledby="dashboard-pulse-title">
        <div className="insights-mood">
          <span className="insights-mood-emoji" aria-hidden="true">{mood.emoji}</span>
          <div>
            <h2 id="dashboard-pulse-title">{mood.label}</h2>
            <p>{mood.blurb}{mood.note ? ` ${mood.note}` : ''}</p>
          </div>
          <Link className="secondary-button compact" to="/portfolio/insights">Trader insights →</Link>
        </div>
        <div className="insights-recap-stats">
          <div><span>Today</span><b className={tone(today?.dollarReturn)}>{today ? `${signedPct(today.returnPct, 2)} · ${money(Math.abs(today.dollarReturn))}` : '—'}</b></div>
          <div><span>Vs. contributions</span><b className={tone(contributionPerformance.returnPct)}>{contributionPerformance.available ? signedPct(contributionPerformance.returnPct, 1) : '—'}</b></div>
          {beatStreak.available && beatStreak.days >= 1 && <div><span>{beatStreak.beating ? `Beating ${preferences.defaultBenchmark}` : `Trailing ${preferences.defaultBenchmark}`}</span><b>{beatStreak.days} day{beatStreak.days === 1 ? '' : 's'} running</b></div>}
        </div>
      </section>

      <section className="report-chart-card">
        <header className="section-heading"><div><span className="eyebrow">Performance</span><h2>{period} equal-start comparison</h2></div><div className="chart-controls"><div className="period-control" aria-label="Performance period">{PERIODS.map((item) => <button key={item} className={period === item ? 'active' : ''} aria-pressed={period === item} onClick={() => { setPeriod(item); updatePreferences({ defaultChartPeriod: item }) }}>{item}</button>)}</div></div></header>
        <fieldset className="benchmark-picker" aria-label="Comparison benchmarks"><legend>Compare with up to three ETF proxies</legend><div>{BENCHMARKS.map((item) => { const checked = selectedBenchmarkSymbols.includes(item.symbol); return <label key={item.symbol} className={checked ? 'selected' : ''}><input type="checkbox" checked={checked} disabled={!checked && selectedBenchmarkSymbols.length >= 3} onChange={() => toggleBenchmark(item.symbol)} /><span>{item.symbol}</span></label> })}</div></fieldset>
        {chartedPortfolio ? <GrowthChart dates={comparison?.dates || chartedPortfolio.dates} series={[{ label: 'Current holdings', values: chartedPortfolio.values, color: 'var(--series-stock)', emphasis: true }, ...(comparison?.benchmarks || []).map((item, index) => ({ label: `${item.symbol} proxy`, values: item.values, ...BENCHMARK_STYLES[index] }))]} valueFormatter={money} caption={comparison ? `${comparison.methodology} Current holdings use current quantities applied to historical daily closes; this is not reconstructed account history.` : selected.methodology} /> : <div className="unavailable-panel"><strong>{period} history unavailable</strong><p>The current dataset does not contain two aligned daily closes for this period.</p></div>}
        {comparison?.benchmarks?.length > 0 && <div className="benchmark-result-strip" aria-label="Benchmark return comparison">{comparison.benchmarks.map((item) => <div key={item.symbol}><span>{item.symbol}<small>{item.label}</small></span><strong>{signedPct(item.returnPct)}</strong><em className={tone(item.differenceVsPortfolio)}>{item.differenceVsPortfolio >= 0 ? '+' : '−'}{money(Math.abs(item.differenceVsPortfolio))} vs portfolio</em></div>)}</div>}
        <div className="report-chart-summary"><Metric label="Charted portfolio earnings" value={chartedPortfolio ? `${chartedPortfolio.dollarReturn >= 0 ? '+' : '−'}${money(Math.abs(chartedPortfolio.dollarReturn))}` : '—'} note={chartedPortfolio ? `${signedPct(chartedPortfolio.returnPct)} · ${chartedPortfolio.startDate} to ${chartedPortfolio.endDate}` : 'Unavailable'} tone={tone(chartedPortfolio?.dollarReturn)} /><Metric label="Charted portfolio high" value={chartedPortfolio ? money(chartedPortfolio.high) : '—'} note="Highest daily-close value on the exact chart comparison dates" /><Metric label="Observed intraday high" value={intraday ? money(intraday.value) : 'Tracking'} note={intraday ? `${intraday.observations} stored observation${intraday.observations === 1 ? '' : 's'} on ${latestTrackingDate}` : 'Stored after signed-in portfolio price refreshes'} /><Metric label="All-time earnings" value={allTimeEarnings.available ? money(allTimeEarnings.value) : 'Tracking'} note={allTimeEarnings.reason} tone={tone(allTimeEarnings.value)} /></div>
      </section>

      <section className="report-section"><header className="section-heading"><div><span className="eyebrow">Portfolio scores</span><h2>Decision-quality snapshot</h2></div><Link to="/portfolio/diversification">View diversification →</Link></header><div className="report-score-grid"><ScoreCard label="Portfolio score" result={overall} note={`${overall.reason} ${overall.available ? `${overall.strongest} is strongest; ${overall.weakest} has the most room to improve.` : ''}`} /><ScoreCard label="Diversification" result={diversification} note={`${diversification.warnings.length ? diversification.warnings[0] : 'No major concentration warning in covered holdings.'}`} /><ScoreCard label="Resilience" result={resilience} note={resilience.available ? `${Math.abs(resilience.maxDrawdown).toFixed(1)}% maximum drawdown; ${resilience.volatility.toFixed(1)}% annualized volatility.` : ''} /><ScoreCard label="Performance" result={performance} note={performance.reason} /></div>{overall.available && <details className="score-method"><summary>How the portfolio score is built</summary><div>{Object.entries(overall.components).map(([label, value]) => <span key={label}><b>{label.replace(/([A-Z])/g, ' $1')}</b><em>{value == null ? 'Unavailable' : `${Math.round(value)}/100`}</em></span>)}</div><p>Weights: diversification 25%, resilience 25%, risk-adjusted performance 20%, benchmark efficiency 15%, concentration/liquidity 10%, and data completeness 5%. A provisional score reweights only available real-data components; missing components are never treated as zero.</p></details>}</section>

      <section className="report-two-column">
        <article className="planning-card"><span className="eyebrow">If all goes to plan</span><h2>1, 5, and 10-year outlook</h2>{planningRates.available ? <><div className="scenario-horizon-grid">{scenarioHorizons.map((horizon) => <section key={horizon.years}><h3>{horizon.years} year{horizon.years === 1 ? '' : 's'}</h3>{horizon.values.map((item) => <div key={item.label}><span>{item.label}<small>{item.rate.toFixed(1)}% annualized</small></span><strong>{money(item.value)}</strong></div>)}</section>)}</div><div className="retirement-outlook"><span>At retirement · age {forecast.retirementAge}</span><strong>{yearsToRetirement ? money(retirementValues.find((item) => item.label === 'base')?.value) : money(portfolio.totalValue)}</strong><small>{yearsToRetirement} years away · base annualized path</small></div><p>{planningRates.methodology} Includes {money(forecast.recurringAnnual)} at each year end. These are scenarios, not predictions.</p></> : <div className="unavailable-panel compact-unavailable"><strong>Annualized scenario unavailable</strong><p>{planningRates.reason}</p></div>}<Link to="/settings">Edit contribution and retirement age</Link></article>
        <article className="opportunity-card"><span className="eyebrow">Opportunity cost</span><h2>Potential earnings by benchmark</h2>{comparison ? <><div className="opportunity-baseline"><span>Shared starting value</span><strong>{money(comparison.startingValue)}</strong><small>{comparison.startDate} to {comparison.endDate}</small></div><div className="opportunity-list"><div className="portfolio-opportunity-row"><span>Current holdings<small>Charted potential earnings</small></span><strong>{chartedPortfolio.dollarReturn >= 0 ? '+' : '−'}{money(Math.abs(chartedPortfolio.dollarReturn))}</strong></div>{comparison.benchmarks.map((item) => <div key={item.symbol}><span>{item.symbol} proxy<small>{item.label} potential earnings</small></span><strong>{item.potentialEarnings >= 0 ? '+' : '−'}{money(Math.abs(item.potentialEarnings))}</strong><em className={tone(item.differenceVsPortfolio)}>{item.differenceVsPortfolio >= 0 ? `Portfolio ahead ${money(item.differenceVsPortfolio)}` : `Benchmark ahead ${money(Math.abs(item.differenceVsPortfolio))}`}</em></div>)}</div><small>{comparison.methodology}</small></> : <p>Comparable history is unavailable for this selection.</p>}</article>
      </section>
    </>}

    <section className="report-support-grid">
      <article className="signal-preview"><header><div><span className="eyebrow">Top signal</span><h2>Research leader</h2></div><Tier label={leader.stance} /></header><div className="signal-company"><CompanyLogo company={leader} size={48} /><div><strong>{leader.ticker}</strong><span>{leader.name}</span></div><b>{leader.score}/100</b></div><p>{leader.strengths?.[0] || 'Highest-scoring published company in the latest evidence run.'}</p><Link to="/research">Open research →</Link></article>
      <article className="watchlist-preview"><header><div><span className="eyebrow">Watchlist</span><h2>Names you follow</h2></div><Link to="/watchlist">View all</Link></header>{watchRows.length ? watchRows.map((row) => <div className="watch-preview-row" key={row.ticker}><CompanyLogo company={row} size={32} /><div><strong>{row.ticker}</strong><span>{row.name}</span></div><b>{row.score}</b></div>) : <p>No published watchlist matches yet.</p>}</article>
      {currentUser && positions.length > 0 && <article className="action-preview"><header><div><span className="eyebrow">Actions</span><h2>Holdings to review</h2></div><Link to="/portfolio">Open portfolio</Link></header><strong>{actionable.length}</strong><p>{actionable.length ? `${actionable.slice(0, 4).map((row) => row.ticker).join(', ')} have evidence-based guidance beyond Hold.` : 'No covered holding has multi-factor guidance beyond Hold.'}</p><small>Research prompts only. Review the underlying evidence before acting.</small></article>}
    </section>
    <footer className="report-methodology-note">Balances use the latest stored closes. Historical portfolio lines apply current quantities to past closes and do not reconstruct trades, deposits, withdrawals, taxes, fees, or dividends. General research only.</footer>
  </div>
}
