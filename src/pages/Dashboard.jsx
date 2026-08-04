import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useData } from '../lib/useData.js'
import { useAuth } from '../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'
import { buildPortfolioPriceData } from '../lib/portfolioPosition.js'
import { usePreferences, formatPreferenceMoney } from '../lib/PreferencesContext.jsx'
import { signedPct } from '../lib/formatters.js'
import {
  BENCHMARKS, benchmarkHistoryFromSnapshot, currentHoldingsSeries, diversificationScore,
  enrichPortfolio, latestMarketDayReturn, opportunityCost, performanceRating, portfolioScore,
  resilienceIndex, scenarioProjection, selectPeriod,
} from '../lib/portfolioAnalytics.js'
import { Loading, Empty, Tier } from '../components/Bits.jsx'
import GrowthChart from '../components/GrowthChart.jsx'
import CompanyLogo from '../components/CompanyLogo.jsx'
import Icon from '../components/Icons.jsx'

const WATCH_KEY = 'valuesignal.watchlist'
const PERIODS = ['1D', '1W', '1M', '3M', '6M', '1Y', 'All']

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
  const { data, loading } = useData('advisor.json')
  const { currentUser } = useAuth()
  const { positions, loading: portfolioLoading } = useFirebasePortfolio()
  const { preferences, setWidgets, updatePreferences } = usePreferences()
  const { data: benchmarkSnapshot } = useData(`etf/${preferences.defaultBenchmark}.json`)
  const [period, setPeriod] = useState(preferences.defaultChartPeriod)
  const [draftWidgets, setDraftWidgets] = useState(preferences.widgets)
  const customize = new URLSearchParams(window.location.search).get('customize') === '1'

  const watchlist = useMemo(() => { try { return JSON.parse(localStorage.getItem(WATCH_KEY)) || [] } catch { return [] } }, [])
  if (loading || (currentUser && portfolioLoading)) return <Loading />
  if (!data?.research?.length) return <Empty note="No advisor dataset is available yet." />

  const rows = data.research
  const prices = buildPortfolioPriceData(data.screen_universe || [], data.portfolio_coverage || [], rows)
  const portfolio = enrichPortfolio(positions, prices)
  const holdingsSeries = currentHoldingsSeries(positions, prices, data.benchmark_history?.dates || [])
  const selected = selectPeriod(holdingsSeries, period)
  const benchmarkRaw = benchmarkHistoryFromSnapshot(benchmarkSnapshot) || (data.benchmark_history?.dates ? { dates: data.benchmark_history.dates, values: data.benchmark_history.closes, closes: data.benchmark_history.closes } : null)
  const benchmarkSeries = benchmarkRaw ? { dates: benchmarkRaw.dates, values: benchmarkRaw.values || benchmarkRaw.closes, methodology: `${preferences.defaultBenchmark} ETF as an investable index proxy.` } : null
  const benchmarkPeriod = selectPeriod(benchmarkSeries, period)
  const today = latestMarketDayReturn(holdingsSeries)
  const diversification = diversificationScore(portfolio.positions)
  const resilience = resilienceIndex(selected?.values || [], diversification)
  const performance = performanceRating(selected, benchmarkPeriod)
  const opportunity = opportunityCost(selected, benchmarkPeriod)
  const overall = portfolioScore({ diversification, resilience, performance, benchmarkEfficiency: performance.available ? performance.score : null, dataCompleteness: Math.round(portfolio.coveragePct || 0) })
  const leader = rows[0]
  const watchRows = watchlist.map((ticker) => rows.find((row) => row.ticker === ticker)).filter(Boolean).slice(0, 4)
  const benchmark = BENCHMARKS.find((item) => item.symbol === preferences.defaultBenchmark)
  const money = (value) => preferences.privacyMode ? '••••••' : formatPreferenceMoney(value, preferences.numberFormat)
  const tone = (value) => value == null ? '' : value >= 0 ? 'positive' : 'negative'
  const normalizedBenchmark = selected && benchmarkPeriod ? benchmarkPeriod.values.map((value) => selected.startValue * value / benchmarkPeriod.startValue) : []
  const forecast = preferences.forecast
  const scenario = ['conservative', 'base', 'optimistic'].map((label) => ({ label, rate: forecast[`${label}Rate`], value: scenarioProjection(portfolio.totalValue, forecast[`${label}Rate`], forecast.horizonYears, forecast.recurringAnnual) }))

  const saveCustomization = () => { setWidgets(draftWidgets); window.history.replaceState({}, '', '/'); window.location.reload() }

  return <div className="financial-report-page">
    {customize && <Customizer widgets={draftWidgets} onChange={setDraftWidgets} onDone={saveCustomization} />}
    <header className="page-head report-head"><div><span className="eyebrow">Latest close · {String(data.generated_at).slice(0, 10)}</span><h1 className="page-title">Financial Report</h1><p className="page-sub">Your portfolio, explained with traceable daily-close data.</p></div><button className="icon-button desktop-only" onClick={() => updatePreferences({ privacyMode: !preferences.privacyMode })} aria-label={preferences.privacyMode ? 'Show balances' : 'Hide balances'}><Icon name={preferences.privacyMode ? 'eye-off' : 'eye'} /></button></header>

    {!currentUser || !positions.length ? <section className="report-empty-state"><span className="eyebrow">Portfolio report</span><h2>{currentUser ? 'Add holdings to unlock your report' : 'Sign in to see your financial report'}</h2><p>Research remains available now. Portfolio analytics appear only after holdings and per-share cost basis are available.</p><Link className="primary-button" to={currentUser ? '/portfolio' : '/research'}>{currentUser ? 'Add holdings' : 'Explore research'}</Link></section> : <>
      <section className="report-hero-grid">
        <article className="report-hero"><span>Current portfolio value</span><strong>{money(portfolio.totalValue)}</strong><div className={`report-today ${tone(today?.dollarReturn)}`}><b>{today ? `${today.dollarReturn >= 0 ? '+' : '−'}${money(Math.abs(today.dollarReturn))}` : '—'}</b><span>{signedPct(today?.returnPct)} latest market day</span></div><small>Close-to-close through {today?.date || 'unavailable'}</small></article>
        <Metric label="Total unrealized return" value={portfolio.gain == null ? '—' : `${portfolio.gain >= 0 ? '+' : '−'}${money(Math.abs(portfolio.gain))}`} note={`${signedPct(portfolio.gainPct)} versus entered per-share cost basis`} tone={tone(portfolio.gain)} />
        <Metric label="Invested cost basis" value={money(portfolio.totalCost)} note="Shares × entered per-share cost; not net contributed capital" />
      </section>

      <section className="report-chart-card">
        <header className="section-heading"><div><span className="eyebrow">Performance</span><h2>{period} portfolio view</h2></div><div className="period-control" aria-label="Performance period">{PERIODS.map((item) => <button key={item} className={period === item ? 'active' : ''} aria-pressed={period === item} onClick={() => { setPeriod(item); updatePreferences({ defaultChartPeriod: item }) }}>{item}</button>)}</div></header>
        {selected ? <GrowthChart dates={selected.dates} series={[{ label: 'Current holdings', values: selected.values, color: 'var(--series-stock)', emphasis: true }, ...(normalizedBenchmark.length ? [{ label: `${preferences.defaultBenchmark} proxy`, values: normalizedBenchmark, color: 'var(--series-market)', dashed: true }] : [])]} valueFormatter={money} caption={`${selected.methodology} Benchmark is ${benchmark?.label || preferences.defaultBenchmark} via the ${preferences.defaultBenchmark} ETF proxy. Period selection recalculates the displayed observations and returns.`} /> : <div className="unavailable-panel"><strong>{period} history unavailable</strong><p>The current dataset does not contain two aligned daily closes for this period.</p></div>}
        <div className="report-chart-summary"><Metric label="Period return" value={selected ? `${selected.dollarReturn >= 0 ? '+' : '−'}${money(Math.abs(selected.dollarReturn))}` : '—'} note={selected ? `${signedPct(selected.returnPct)} · ${selected.startDate} to ${selected.endDate}` : 'Unavailable'} tone={tone(selected?.dollarReturn)} /><Metric label="Period high" value={selected ? money(selected.high) : '—'} note="Highest daily-close value in selected period; not intraday high" /><Metric label="Intraday high" value="Unavailable" note="No time-stamped intraday portfolio series is stored" /></div>
      </section>

      <section className="report-section"><header className="section-heading"><div><span className="eyebrow">Portfolio scores</span><h2>Decision-quality snapshot</h2></div><Link to="/portfolio/diversification">View diversification →</Link></header><div className="report-score-grid"><ScoreCard label="Portfolio score" result={overall} note={`${overall.strongest || 'Coverage'} is strongest; ${overall.weakest || 'history'} has the most room to improve.`} /><ScoreCard label="Diversification" result={diversification} note={`${diversification.warnings.length ? diversification.warnings[0] : 'No major concentration warning in covered holdings.'}`} /><ScoreCard label="Resilience" result={resilience} note={resilience.available ? `${Math.abs(resilience.maxDrawdown).toFixed(1)}% maximum drawdown; ${resilience.volatility.toFixed(1)}% annualized volatility.` : ''} /><ScoreCard label="Performance" result={performance} note={performance.reason} /></div></section>

      <section className="report-two-column">
        <article className="planning-card"><span className="eyebrow">If all goes to plan</span><h2>{forecast.horizonYears}-year planning scenario</h2><div className="scenario-values">{scenario.map((item) => <div key={item.label}><span>{item.label} · {item.rate}%</span><strong>{money(item.value)}</strong></div>)}</div><p>Illustration using manual annual-return assumptions and {money(forecast.recurringAnnual)} annual contributions. Not a prediction, guarantee, or investment recommendation.</p><Link to="/settings">Edit assumptions</Link></article>
        <article className="opportunity-card"><span className="eyebrow">Opportunity cost</span><h2>{benchmark?.label || preferences.defaultBenchmark} comparison</h2>{opportunity ? <><strong className={tone(opportunity.difference)}>{opportunity.difference >= 0 ? '+' : '−'}{money(Math.abs(opportunity.difference))}</strong><p>Your current-holdings backtest {opportunity.difference >= 0 ? 'finished above' : 'finished below'} an equal-starting-value {preferences.defaultBenchmark} ETF proxy over the selected period.</p><small>{opportunity.methodology}</small></> : <p>Comparable history is unavailable for this selection.</p>}</article>
      </section>
    </>}

    <section className="report-section report-support-grid">
      <article className="signal-preview"><header><div><span className="eyebrow">Top signal</span><h2>Research leader</h2></div><Tier label={leader.stance} /></header><div className="signal-company"><CompanyLogo company={leader} size={48} /><div><strong>{leader.ticker}</strong><span>{leader.name}</span></div><b>{leader.score}/100</b></div><p>{leader.strengths?.[0] || 'Highest-scoring published company in the latest evidence run.'}</p><Link to="/research">Open research →</Link></article>
      <article className="watchlist-preview"><header><div><span className="eyebrow">Watchlist</span><h2>Names you follow</h2></div><Link to="/watchlist">View all</Link></header>{watchRows.length ? watchRows.map((row) => <div className="watch-preview-row" key={row.ticker}><CompanyLogo company={row} size={32} /><div><strong>{row.ticker}</strong><span>{row.name}</span></div><b>{row.score}</b></div>) : <p>No published watchlist matches yet.</p>}</article>
    </section>
    <footer className="report-methodology-note">Balances use the latest stored closes. Historical portfolio lines apply current quantities to past closes and do not reconstruct trades, deposits, withdrawals, taxes, fees, or dividends. General research only.</footer>
  </div>
}
