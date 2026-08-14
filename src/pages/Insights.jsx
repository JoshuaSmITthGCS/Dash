import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useData } from '../lib/useData.js'
import { useAuth } from '../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'
import { usePortfolioTracking } from '../lib/usePortfolioTracking.js'
import { buildPortfolioPriceData, mergePositionSnapshots } from '../lib/portfolioPosition.js'
import { usePreferences, formatPreferenceMoney } from '../lib/PreferencesContext.jsx'
import { signedPct } from '../lib/formatters.js'
import {
  benchmarkHistoryFromSnapshot, currentHoldingsSeries,
  diversificationScore, enrichPortfolio, latestMarketDayReturn, selectPeriod,
} from '../lib/portfolioAnalytics.js'
import {
  alignManyForChart, benchmarkShadowPortfolio, holdingsVsBenchmark, portfolioMood,
  purchaseTimingSignal, snapshotDailySeries, tradeStats,
} from '../lib/traderInsights.js'
import { Loading, Empty } from '../components/Bits.jsx'
import GrowthChart from '../components/GrowthChart.jsx'
import CompanyLogo from '../components/CompanyLogo.jsx'
import InfoTag from '../components/InfoTag.jsx'

const moveColor = (value) => value == null ? 'var(--text-faint)' : value >= 0 ? 'var(--up)' : 'var(--down)'
const MARKET_DESTINATIONS = [
  { symbol: 'SPY', label: 'S&P 500', color: 'var(--series-benchmark)', dashPattern: '7 4' },
  { symbol: 'QQQ', label: 'Nasdaq-100', color: 'var(--series-benchmark-2)', dashPattern: '3 3' },
  { symbol: 'DIA', label: 'Dow Jones', color: 'var(--series-benchmark-3)', dashPattern: '9 3 2 3' },
  { symbol: 'IWM', label: 'Russell 2000', color: 'var(--series-cash)', dashPattern: '2 4' },
]

function latestMove(history) {
  const values = history?.closes || []
  if (values.length < 2 || !values.at(-2)) return null
  return (values.at(-1) / values.at(-2) - 1) * 100
}

export default function Insights() {
  const { data, loading } = useData('advisor.json')
  const { positions, loading: portfolioLoading } = useFirebasePortfolio()
  const tracking = usePortfolioTracking()
  const { currentUser } = useAuth()
  const { preferences } = usePreferences()
  const { data: benchmarkSnapshot } = useData(`etf/${preferences.defaultBenchmark}.json`)
  const { data: benchmarkReport, loading: benchmarkReportLoading } = useData('benchmark-report.json')
  const { data: etfData } = useData('etfs.json')
  const [shareStatus, setShareStatus] = useState('')

  if (loading || portfolioLoading || benchmarkReportLoading || !currentUser) return <Loading />
  if (!positions.length) return <Empty note="Add portfolio holdings to see how you're doing versus the market and as a trader." />

  const prices = mergePositionSnapshots(
    buildPortfolioPriceData(data?.screen_universe || [], data?.portfolio_coverage || [], data?.research || []),
    positions,
    data?.generated_at,
  )
  const portfolio = enrichPortfolio(positions, prices)
  const benchmarkHistory = benchmarkHistoryFromSnapshot(benchmarkSnapshot)
    || (data?.benchmark_history?.dates ? { dates: data.benchmark_history.dates, closes: data.benchmark_history.closes, symbol: preferences.defaultBenchmark } : null)
  const benchmarkLabel = preferences.defaultBenchmark

  const diversification = diversificationScore(portfolio.positions, { etfs: etfData?.etfs || [] })

  const marketHistories = MARKET_DESTINATIONS.map((destination) => {
    const published = benchmarkReport?.histories?.[destination.symbol]
    const history = published
      ? { ...published, symbol: destination.symbol }
      : destination.symbol === preferences.defaultBenchmark ? benchmarkHistory : null
    return history ? { ...destination, dates: history.dates, closes: history.closes } : null
  }).filter(Boolean)
  const holdingsRanked = benchmarkHistory ? holdingsVsBenchmark(portfolio.positions, benchmarkHistory) : []

  const trades = tradeStats(tracking.activities)
  const timingSignals = portfolio.positions
    .map((position) => ({ position, timing: purchaseTimingSignal(position, position.priceInfo?.history) }))
    .filter((row) => row.timing.available)

  const holdingsSeries = currentHoldingsSeries(positions, prices, data?.benchmark_history?.dates || [])
  const holdingsPeriod = selectPeriod(holdingsSeries, '1Y') || selectPeriod(holdingsSeries, 'All')
  const actualDaily = snapshotDailySeries(tracking.snapshots)
  // The first plotted date must exist in the account and every benchmark. Seeding each
  // hypothetical index with the account value on that exact date guarantees the headline's
  // "same dollars" claim is literally true before later deposits/withdrawals are replayed.
  const comparisonStartIndex = actualDaily.dates.findIndex((date) => marketHistories.every(
    (history) => history.dates.includes(date),
  ))
  const comparisonAccount = comparisonStartIndex >= 0 ? {
    dates: actualDaily.dates.slice(comparisonStartIndex),
    values: actualDaily.values.slice(comparisonStartIndex),
  } : null
  const comparisonStartDate = comparisonAccount?.dates[0]
  const comparisonStartingValue = comparisonAccount?.values[0]
  const marketShadows = comparisonStartDate ? marketHistories.map((history) => ({
    ...history,
    ...benchmarkShadowPortfolio(tracking.activities, history, {
      startDate: comparisonStartDate,
      startingValue: comparisonStartingValue,
    }),
  })).filter((shadow) => shadow.available) : []
  const chartComparison = marketShadows.length === marketHistories.length
    ? alignManyForChart(comparisonAccount, marketShadows)
    : null
  const mood = portfolioMood({ returnPct: holdingsPeriod?.returnPct, diversificationScore: diversification.score, streak: { available: false } })
  const todayMove = latestMarketDayReturn(holdingsSeries)
  const topMover = portfolio.positions
    .map((position) => ({ ...position, dailyMovePct: latestMove(position.priceInfo?.history) }))
    .filter((position) => position.dailyMovePct != null)
    .sort((a, b) => Math.abs(b.dailyMovePct) - Math.abs(a.dailyMovePct))[0]

  const money = (value) => preferences.privacyMode ? '••••••' : formatPreferenceMoney(value, preferences.numberFormat)

  const shareRecap = async () => {
    const lines = [
      `${mood.emoji} ${mood.label} – my portfolio today`,
      todayMove ? `Today: ${signedPct(todayMove.returnPct, 2)} (${money(Math.abs(todayMove.dollarReturn))})` : null,
      holdingsPeriod ? `Current-holdings return: ${signedPct(holdingsPeriod.returnPct, 1)}` : null,
      topMover ? `Biggest mover: ${topMover.ticker} ${signedPct(topMover.dailyMovePct, 1)}` : null,
    ].filter(Boolean)
    const text = lines.join('\n')
    try {
      if (navigator.share) { await navigator.share({ text, title: 'My portfolio today' }); return }
      await navigator.clipboard.writeText(text)
      setShareStatus('Copied to clipboard.')
      setTimeout(() => setShareStatus(''), 3000)
    } catch {
      // Share was cancelled or clipboard access was denied – nothing to recover from here.
    }
  }

  return <div className="insights-page">
    <header className="page-head compact-page-head">
      <div>
        <span className="eyebrow">Portfolio analytics</span>
        <h1 className="page-title">Trader <span className="accent">insights</span></h1>
        <p className="page-sub">How you're doing against the market, how you're trading, and what's changed lately.</p>
      </div>
      <Link className="secondary-button compact" to="/portfolio">Back to portfolio</Link>
    </header>

    <section className="card insights-recap insights-recap-hero" aria-labelledby="recap-title">
      <div className="insights-mood">
        <span className="insights-mood-emoji" aria-hidden="true">{mood.emoji}</span>
        <div>
          <h2 id="recap-title">{mood.label}</h2>
          <p>{mood.blurb}{mood.note ? ` ${mood.note}` : ''}</p>
        </div>
        <button type="button" className="secondary-button compact" onClick={shareRecap}>Share today</button>
      </div>
      <div className="insights-recap-stats">
        <div><span>Today</span><b style={{ color: moveColor(todayMove?.dollarReturn) }}>{todayMove ? `${signedPct(todayMove.returnPct, 2)} · ${money(Math.abs(todayMove.dollarReturn))}` : '–'}</b></div>
        <div><span>Current-holdings return</span><b style={{ color: moveColor(holdingsPeriod?.returnPct) }}>{holdingsPeriod ? signedPct(holdingsPeriod.returnPct, 1) : 'Unavailable'}</b></div>
        <div><span>Invested value</span><b>{money(portfolio.totalValue)}</b></div>
        {topMover && <div><span>Today's biggest mover</span><b style={{ color: moveColor(topMover.dailyMovePct) }}>{topMover.ticker} {signedPct(topMover.dailyMovePct, 1)}</b></div>}
      </div>
      {shareStatus && <p className="sr-only" aria-live="polite">{shareStatus}</p>}
      {shareStatus && <p className="insights-share-status" aria-hidden="true">{shareStatus}</p>}
    </section>

    <section className="report-section" aria-labelledby="vs-market-title">
      <header className="section-heading"><div><span className="eyebrow">Same dollars, different destination</span><h2 id="vs-market-title">You vs. the major indexes
        <InfoTag label="You vs. the major indexes">
          <strong>You vs. the major indexes</strong>
          <p>Starts every index with your account’s exact recorded value on the first shared date,
            then applies each later settled deposit or withdrawal using its actual amount and
            effective date. Pending transfers are excluded.</p>
        </InfoTag>
      </h2></div></header>
      {chartComparison
        ? <GrowthChart
            dates={chartComparison.dates}
            series={[
              { label: 'Your recorded account', values: chartComparison.primaryValues, color: 'var(--accent)', emphasis: true },
              ...marketShadows.map((shadow, index) => ({
                label: `${shadow.label} (${shadow.symbol})`,
                values: chartComparison.comparisonValues[index],
                color: shadow.color,
                dashPattern: shadow.dashPattern,
              })),
            ]}
            caption={`Every line starts at ${money(chartComparison.primaryValues[0])} on ${chartComparison.dates[0]}. On the latest shared recording date, your account is ${money(chartComparison.primaryValues.at(-1))}; applying the same settled deposit and withdrawal amounts on the same dates would leave ${marketShadows.map((shadow, index) => `${money(chartComparison.comparisonValues[index].at(-1))} in ${shadow.symbol}`).join(' · ')}. Pending transfers are excluded.`}
            zoomable
          />
        : <div className="report-empty-state"><h2>Not enough history yet</h2><p>This cash-flow-aware comparison needs your recorded account value on at least two market dates shared by the selected indexes.</p></div>}
    </section>

    {holdingsRanked.length > 0 && <section className="report-section" aria-labelledby="holdings-vs-title">
      <header className="section-heading"><div><span className="eyebrow">Since your purchase date</span><h2 id="holdings-vs-title">Holdings vs. {benchmarkLabel}</h2></div></header>
      <div className="insights-holdings-list">
        {holdingsRanked.map((row) => <div className="insights-holdings-row" key={row.ticker}>
          <strong>{row.ticker}</strong>
          <span className="insights-holdings-bars">
            <b style={{ color: moveColor(row.stockReturnPct) }}>{signedPct(row.stockReturnPct, 1)}</b>
            <small>vs {signedPct(row.benchmarkReturnPct, 1)} {benchmarkLabel}</small>
          </span>
          <b className="insights-delta" style={{ color: moveColor(row.deltaPct) }}>{signedPct(row.deltaPct, 1)}</b>
        </div>)}
      </div>
    </section>}

    <section className="report-two-column">
      <article className="card card-pad insights-trade-stats" aria-labelledby="trade-stats-title">
        <h2 id="trade-stats-title">As a trader</h2>
        {trades.available ? <>
          <div className="insights-stat-row"><span>Win rate</span><b>{trades.winRate.toFixed(0)}%</b><small>{trades.winCount}W / {trades.lossCount}L of {trades.count} closed</small></div>
          <div className="insights-stat-row"><span>Average win</span><b style={{ color: 'var(--up)' }}>{trades.avgWin != null ? money(trades.avgWin) : '–'}</b></div>
          <div className="insights-stat-row"><span>Average loss</span><b style={{ color: 'var(--down)' }}>{trades.avgLoss != null ? money(Math.abs(trades.avgLoss)) : '–'}</b></div>
          <div className="insights-stat-row"><span>Best trade</span><b style={{ color: 'var(--up)' }}>{money(trades.best.amount)}</b><small>{trades.best.note || 'No note'}</small></div>
          <div className="insights-stat-row"><span>Worst trade</span><b style={{ color: 'var(--down)' }}>{money(trades.worst.amount)}</b><small>{trades.worst.note || 'No note'}</small></div>
        </> : <p>Record position sales on the Portfolio page to build realized win-rate and trade statistics.</p>}
      </article>

      <article className="card card-pad insights-timing" aria-labelledby="timing-title">
        <h2 id="timing-title">Purchase timing</h2>
        {timingSignals.length ? <div className="insights-timing-list">
          {timingSignals.map(({ position, timing }) => <div key={position.id || position.ticker} className="insights-timing-row">
            <CompanyLogo company={position.priceInfo || position} size={30} />
            <div><strong>{position.ticker}</strong><small>{timing.label}</small></div>
            <b style={{ color: moveColor(-timing.deltaPct) }}>{signedPct(timing.deltaPct, 1)}</b>
          </div>)}
        </div> : <p>Not enough price history around your purchase dates yet to judge entry timing.</p>}
      </article>
    </section>

  </div>
}
