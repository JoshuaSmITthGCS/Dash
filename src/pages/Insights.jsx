import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useData } from '../lib/useData.js'
import { useAuth } from '../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'
import { usePortfolioTracking } from '../lib/usePortfolioTracking.js'
import { buildPortfolioPriceData } from '../lib/portfolioPosition.js'
import { usePreferences, formatPreferenceMoney } from '../lib/PreferencesContext.jsx'
import { signedPct } from '../lib/formatters.js'
import {
  benchmarkHistoryFromSnapshot, contributionAdjustedPerformance, currentHoldingsSeries,
  diversificationScore, enrichPortfolio, latestMarketDayReturn, portfolioReturnSummary,
} from '../lib/portfolioAnalytics.js'
import {
  alignForChart, beatMarketStreak, benchmarkShadowPortfolio, detectMilestones,
  holdingsVsBenchmark, portfolioMood, purchaseTimingSignal, snapshotDailySeries, tradeStats, valueStreak,
} from '../lib/traderInsights.js'
import { Loading, Empty } from '../components/Bits.jsx'
import GrowthChart from '../components/GrowthChart.jsx'
import CompanyLogo from '../components/CompanyLogo.jsx'

const moveColor = (value) => value == null ? 'var(--text-faint)' : value >= 0 ? 'var(--up)' : 'var(--down)'

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
  const { data: etfData } = useData('etfs.json')
  const [shareStatus, setShareStatus] = useState('')

  if (loading || portfolioLoading || !currentUser) return <Loading />
  if (!positions.length) return <Empty note="Add portfolio holdings to see how you're doing versus the market and as a trader." />

  const prices = buildPortfolioPriceData(data?.screen_universe || [], data?.portfolio_coverage || [], data?.research || [])
  const portfolio = enrichPortfolio(positions, prices)
  const benchmarkHistory = benchmarkHistoryFromSnapshot(benchmarkSnapshot)
    || (data?.benchmark_history?.dates ? { dates: data.benchmark_history.dates, closes: data.benchmark_history.closes, symbol: preferences.defaultBenchmark } : null)
  const benchmarkLabel = preferences.defaultBenchmark

  const uninvestedCash = tracking.trackingState?.cashTrackingEnabled ? Number(tracking.trackingState.cashBalance || 0) : 0
  const trackedAccountValue = (portfolio.totalValue || 0) + uninvestedCash
  const contributionPerformance = contributionAdjustedPerformance(trackedAccountValue, tracking.activities, tracking.trackingState?.cashFlowHistoryComplete)
  const returnSummary = portfolioReturnSummary(tracking.snapshots, tracking.activities, tracking.trackingState?.cashFlowHistoryComplete)
  const diversification = diversificationScore(portfolio.positions, { etfs: etfData?.etfs || [] })

  const actualDaily = snapshotDailySeries(tracking.snapshots)
  const shadow = benchmarkHistory ? benchmarkShadowPortfolio(tracking.activities, benchmarkHistory) : { available: false }
  const chartAligned = shadow.available ? alignForChart(actualDaily, shadow) : null

  const beatStreak = benchmarkHistory ? beatMarketStreak(tracking.snapshots, benchmarkHistory) : { available: false }
  const greenStreak = valueStreak(tracking.snapshots)
  const holdingsRanked = benchmarkHistory ? holdingsVsBenchmark(portfolio.positions, benchmarkHistory) : []

  const trades = tradeStats(tracking.activities)
  const timingSignals = portfolio.positions
    .map((position) => ({ position, timing: purchaseTimingSignal(position, position.priceInfo?.history) }))
    .filter((row) => row.timing.available)

  const milestones = detectMilestones({ snapshots: tracking.snapshots, trackedAccountValue, contributionPerformance })
  const mood = portfolioMood({ returnPct: returnSummary.strategy.returnPct, diversificationScore: diversification.score, streak: beatStreak.available ? beatStreak : greenStreak })

  const holdingsSeries = currentHoldingsSeries(positions, prices, data?.benchmark_history?.dates || [])
  const todayMove = latestMarketDayReturn(holdingsSeries)
  const topMover = portfolio.positions
    .map((position) => ({ ...position, dailyMovePct: latestMove(position.priceInfo?.history) }))
    .filter((position) => position.dailyMovePct != null)
    .sort((a, b) => Math.abs(b.dailyMovePct) - Math.abs(a.dailyMovePct))[0]

  const money = (value) => preferences.privacyMode ? '••••••' : formatPreferenceMoney(value, preferences.numberFormat)

  const shareRecap = async () => {
    const lines = [
      `${mood.emoji} ${mood.label} — my portfolio today`,
      todayMove ? `Today: ${signedPct(todayMove.returnPct, 2)} (${money(Math.abs(todayMove.dollarReturn))})` : null,
      returnSummary.strategy.available ? `Strategy return: ${signedPct(returnSummary.strategy.returnPct, 1)}` : null,
      topMover ? `Biggest mover: ${topMover.ticker} ${signedPct(topMover.dailyMovePct, 1)}` : null,
      beatStreak.available && beatStreak.days >= 1 ? `${beatStreak.beating ? 'Beating' : 'Trailing'} ${benchmarkLabel} for ${beatStreak.days} day${beatStreak.days === 1 ? '' : 's'} running` : null,
    ].filter(Boolean)
    const text = lines.join('\n')
    try {
      if (navigator.share) { await navigator.share({ text, title: 'My portfolio today' }); return }
      await navigator.clipboard.writeText(text)
      setShareStatus('Copied to clipboard.')
      setTimeout(() => setShareStatus(''), 3000)
    } catch {
      // Share was cancelled or clipboard access was denied — nothing to recover from here.
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
        <div><span>Today</span><b style={{ color: moveColor(todayMove?.dollarReturn) }}>{todayMove ? `${signedPct(todayMove.returnPct, 2)} · ${money(Math.abs(todayMove.dollarReturn))}` : '—'}</b></div>
        <div><span>Strategy return (time-weighted)</span><b style={{ color: moveColor(returnSummary.strategy.returnPct) }}>{returnSummary.strategy.available ? signedPct(returnSummary.strategy.returnPct, 1) : 'Unavailable'}</b></div>
        <div><span>Your return (money-weighted, includes timing of deposits)</span><b style={{ color: moveColor(returnSummary.moneyWeighted.rate) }}>{returnSummary.moneyWeighted.available ? signedPct(returnSummary.moneyWeighted.rate, 1) : 'Unavailable'}</b></div>
        {topMover && <div><span>Today's biggest mover</span><b style={{ color: moveColor(topMover.dailyMovePct) }}>{topMover.ticker} {signedPct(topMover.dailyMovePct, 1)}</b></div>}
        {beatStreak.available && beatStreak.days >= 1 && <div><span>{beatStreak.beating ? `Beating ${benchmarkLabel}` : `Trailing ${benchmarkLabel}`}</span><b>{beatStreak.days} day{beatStreak.days === 1 ? '' : 's'} running</b></div>}
      </div>
      {shareStatus && <p className="sr-only" aria-live="polite">{shareStatus}</p>}
      {shareStatus && <p className="insights-share-status" aria-hidden="true">{shareStatus}</p>}
    </section>

    <section className="report-section" aria-labelledby="vs-market-title">
      <header className="section-heading"><div><span className="eyebrow">Same dollars, different destination</span><h2 id="vs-market-title">You vs. {benchmarkLabel}</h2></div></header>
      {chartAligned
        ? <GrowthChart
            dates={chartAligned.dates}
            series={[
              { label: 'Your account', values: chartAligned.primaryValues, color: 'var(--accent)', emphasis: true },
              { label: `${benchmarkLabel}, same deposits`, values: chartAligned.secondaryValues, color: 'var(--text-faint)', dashed: true },
            ]}
            caption={`If every deposit and withdrawal had gone into ${benchmarkLabel} instead, that account would be worth ${money(shadow.finalValue)} today — you're at ${money(trackedAccountValue)}.`}
            zoomable
          />
        : <div className="report-empty-state"><h2>Not enough history yet</h2><p>This chart needs dated deposits/withdrawals and a refreshed portfolio value on more than one day. Keep tracking cash flows and refreshing prices to build it out.</p></div>}
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
          <div className="insights-stat-row"><span>Average win</span><b style={{ color: 'var(--up)' }}>{trades.avgWin != null ? money(trades.avgWin) : '—'}</b></div>
          <div className="insights-stat-row"><span>Average loss</span><b style={{ color: 'var(--down)' }}>{trades.avgLoss != null ? money(Math.abs(trades.avgLoss)) : '—'}</b></div>
          <div className="insights-stat-row"><span>Best trade</span><b style={{ color: 'var(--up)' }}>{money(trades.best.amount)}</b><small>{trades.best.note || 'No note'}</small></div>
          <div className="insights-stat-row"><span>Worst trade</span><b style={{ color: 'var(--down)' }}>{money(trades.worst.amount)}</b><small>{trades.worst.note || 'No note'}</small></div>
        </> : <p>Log realized gains and losses on the Portfolio page's cash-flow ledger to see win rate and trade stats here.</p>}
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

    <section className="report-section" aria-labelledby="milestones-title">
      <header className="section-heading"><div><span className="eyebrow">Progress</span><h2 id="milestones-title">Milestones</h2></div></header>
      {milestones.length ? <div className="insights-milestones">
        {milestones.map((milestone) => <div className="insights-milestone" key={milestone.id}>
          <span aria-hidden="true">🏁</span>
          <div><strong>{milestone.label}</strong>{milestone.achievedDate && <small>{milestone.achievedDate}</small>}</div>
        </div>)}
      </div> : <p className="insights-timing">No milestones reached yet — the first is $500 in tracked account value.</p>}
      {greenStreak.available && greenStreak.days >= 2 && <p className="insights-streak-note">Account value has moved {greenStreak.direction} for {greenStreak.days} days running.</p>}
    </section>
  </div>
}
