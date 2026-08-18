import { useMemo, useState } from 'react'
import { useData } from '../lib/useData.js'
import { useAuth } from '../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'
import { useWatchlist } from '../lib/useWatchlist.js'
import { useFirebaseFinances } from '../lib/useFirebaseFinances.js'
import { buildPortfolioPriceData, mergePortfolioQuotes, mergePositionSnapshots } from '../lib/portfolioPosition.js'
import { usePreferences, formatPreferenceMoney } from '../lib/PreferencesContext.jsx'
import { signedPct } from '../lib/formatters.js'
import {
  BENCHMARKS, compareBenchmarkSeries, concentrationLiquidityScore, currentHoldingsSeries, diversificationScore,
  enrichPortfolio, latestMarketDayReturn, performanceMetrics, portfolioScore,
  resilienceIndex, riskFreeAnnualRate, selectPeriod, sliceSeriesFrom,
} from '../lib/portfolioAnalytics.js'
import { Loading, Empty } from '../components/Bits.jsx'
import CompanyLogo from '../components/CompanyLogo.jsx'
import { usePortfolioTracking } from '../lib/usePortfolioTracking.js'
import { usePortfolioQuotes } from '../lib/usePortfolioQuotes.js'
import { liveTodayPortfolioReturn } from '../lib/afterHoursQuotes.js'
import { currentHoldingsPerformanceSeriesForPeriod } from '../lib/portfolioPerformance.js'
import modelSettings from '../../pipeline/config/settings.json'
import { LIVE_TRACKING_START } from '../lib/liveTrackingAvailability.js'
import Sparkline from '../components/Sparkline.jsx'
import { dailyMoveForPosition, marketType, rankDailySectors, rankDailyStocks } from '../lib/marketPresentation.js'
import {
  CircularRadar,
  LiveClock,
  TechPanel,
  DataStrip,
  MetricGrid,
  StatusMatrix,
  SectorDonut,
} from '../lib/hudUltra.jsx'

const interfaceConfig = modelSettings.interface

export default function CommandCenter() {
  const { data, loading } = useData('report.json')
  const { data: etfData } = useData('etfs.json')
  const { currentUser } = useAuth()
  const { positions: storedPositions, loading: portfolioLoading } = useFirebasePortfolio()
  const previewPortfolio = import.meta.env.DEV
    && new window.URLSearchParams(window.location.search).get('portfolioPreview') === '1'
  const positions = previewPortfolio ? interfaceConfig.mobile_preview_positions : storedPositions
  const hasPortfolioAccess = currentUser || previewPortfolio
  const finances = useFirebaseFinances()
  const tracking = usePortfolioTracking()
  const portfolioQuotes = usePortfolioQuotes(positions.map((position) => position.ticker))
  const { preferences } = usePreferences()
  const { data: benchmarkReport, loading: benchmarkLoading } = useData(positions.length ? 'benchmark-report.json' : null)
  const [period] = useState('1D')
  const [sinceLiveTrackingOnly] = useState(true)
  const { items: watchlistItems } = useWatchlist()
  const watchlist = useMemo(() => watchlistItems.map((item) => item.ticker), [watchlistItems])

  if (loading || (hasPortfolioAccess && !previewPortfolio && (portfolioLoading || finances.loading || (positions.length > 0 && benchmarkLoading)))) return <Loading />
  if (!data?.research?.length) return <Empty note="No advisor dataset is available yet." />

  const rows = data.research
  const publishedPrices = mergePositionSnapshots(
    buildPortfolioPriceData(data.screen_universe || [], data.portfolio_coverage || [], rows),
    positions,
    data.generated_at,
  )
  const quoteRefreshIsNewest = portfolioQuotes.fetchedAt
    && new Date(portfolioQuotes.fetchedAt) >= new Date(data?.generated_at || 0)
  const prices = mergePortfolioQuotes(publishedPrices, quoteRefreshIsNewest ? portfolioQuotes.quotes : {})
  const portfolio = enrichPortfolio(positions, prices)
  const holdingsSeries = currentHoldingsSeries(positions, prices, data.benchmark_history?.dates || [])
  const selected = period === '1H' ? null : selectPeriod(holdingsSeries, period)
  const selectedBenchmarkSymbols = preferences.defaultBenchmarks || [preferences.defaultBenchmark]
  const selectedBenchmarkSeries = selectedBenchmarkSymbols.map((symbol) => {
    const history = benchmarkReport?.histories?.[symbol]
    const definition = BENCHMARKS.find((item) => item.symbol === symbol)
    return history ? { symbol, label: definition?.label || symbol, dates: history.dates, closes: history.closes } : null
  }).filter(Boolean)
  const comparison = compareBenchmarkSeries(selected, selectedBenchmarkSeries)
  const chartedPortfolio = comparison?.portfolio || selected
  const recordedZoomSeries = currentHoldingsPerformanceSeriesForPeriod(tracking.snapshots, positions, prices, period)
  const homeChart = recordedZoomSeries || chartedPortfolio
  const homePeriodProfit = homeChart?.dollarReturn
    ?? (homeChart?.values?.length > 1 ? homeChart.values.at(-1) - homeChart.values[0] : null)
  const today = latestMarketDayReturn(holdingsSeries)
  const liveToday = liveTodayPortfolioReturn(positions, prices)
  const heroToday = liveToday.available
    ? liveToday
    : today ? { dollarReturn: today.dollarReturn, returnPct: today.returnPct } : null
  const diversification = diversificationScore(portfolio.positions, { etfs: etfData?.etfs || [] })
  const liveHoldingsSeries = sliceSeriesFrom(holdingsSeries, LIVE_TRACKING_START)
  const scoreHoldingsSeries = sinceLiveTrackingOnly ? liveHoldingsSeries : holdingsSeries
  const scorePortfolioPeriod = selectPeriod(scoreHoldingsSeries, '1Y') || selectPeriod(scoreHoldingsSeries, 'All')
  const scoreComparison = compareBenchmarkSeries(scorePortfolioPeriod, selectedBenchmarkSeries.slice(0, 1))
  const resilience = resilienceIndex(scoreComparison?.portfolio.values || scorePortfolioPeriod?.values || [], diversification)
  const riskFree = riskFreeAnnualRate(data)
  const performance = performanceMetrics(scoreComparison?.portfolio, scoreComparison?.benchmarks[0], riskFree.annualPct)
  const concentrationLiquidity = concentrationLiquidityScore(portfolio.positions)
  const overall = portfolioScore({ diversification, resilience, performance, benchmarkEfficiency: null, concentrationLiquidity, dataCompleteness: Math.round(portfolio.coveragePct || 0) })
  const leader = rows[0]
  const watchRows = watchlist.map((ticker) => rows.find((row) => row.ticker === ticker)).filter(Boolean).slice(0, 4)
  const money = (value) => preferences.privacyMode ? '••••••' : formatPreferenceMoney(value, preferences.numberFormat)
  const sectorAllocation = Object.entries(portfolio.positions.reduce((totals, position) => {
    const sector = position.priceInfo?.sector || 'Unclassified'
    totals[sector] = (totals[sector] || 0) + Number(position.currentValue || 0)
    return totals
  }, {})).map(([sector, value]) => ({ sector, value, pct: portfolio.totalValue ? value / portfolio.totalValue * 100 : 0 }))
    .sort((left, right) => right.value - left.value)

  // Top stocks for radar
  const topStocks = rows.slice(0, 16).map(row => ({
    ticker: row.ticker,
    name: row.name,
    score: row.score,
    sector: row.sector,
  }))

  // Market session
  const ranked = rankDailyStocks(rows)
  const sectors = rankDailySectors(rows)
  const session = marketType(rows)
  const topMover = ranked[0]

  // Macro data
  const macro = data?.market?.macro || {}
  const regime = macro.regime

  return <div className="command-center">
    {/* Background effects */}
    <div className="particle-field" aria-hidden="true">
      {[...Array(50)].map((_, i) => (
        <div
          key={i}
          className="particle"
          style={{
            left: `${Math.random() * 100}%`,
            top: `${Math.random() * 100}%`,
            animationDelay: `${Math.random() * 5}s`,
            animationDuration: `${3 + Math.random() * 4}s`,
          }}
        />
      ))}
    </div>

    <div className="command-grid">
      {/* Header */}
      <header className="command-header">
        <div className="command-title">
          <span className="command-logo">COMMAND</span>
          <span className="command-subtitle">Tactical Research Interface · <LiveClock /></span>
        </div>
        <div className="command-status">
          <div className="command-stat">
            <span className="command-stat-label">Universe</span>
            <span className="command-stat-value">{rows.length}</span>
          </div>
          <div className="command-stat">
            <span className="command-stat-label">Portfolio</span>
            <span className="command-stat-value">{positions.length}</span>
          </div>
          <div className="command-stat">
            <span className="command-stat-label">Status</span>
            <span className="command-stat-value">LIVE</span>
          </div>
        </div>
      </header>

      {/* Left side panels */}
      <div className="side-panel side-panel-left">
        {/* System status */}
        <TechPanel title="System status" active={true}>
          <StatusMatrix items={[
            { value: 'OK', label: 'Alpha Vantage' },
            { value: 'OK', label: 'Marketaux' },
            { value: 'OK', label: 'FRED' },
            { value: 'OK', label: 'Yahoo Data' },
            { value: 'OK', label: 'Yahoo News' },
            { value: 'OK', label: 'SEC Form 4' },
          ]} />
        </TechPanel>

        {/* Market summary */}
        <TechPanel title="Market pulse" active={true}>
          <DataStrip items={[
            { label: 'Session', value: session.label },
            { label: 'Breadth', value: session.breadthPct == null ? '—' : `${session.breadthPct.toFixed(0)}%` },
            { label: 'Hot sector', value: sectors[0]?.sector || '—' },
            { label: 'Top mover', value: topMover ? `${topMover.ticker} ${signedPct(topMover.dailyMove.pct)}` : '—' },
            { label: 'Macro', value: regime?.label || '—' },
          ]} />
        </TechPanel>

        {/* Portfolio overview */}
        {hasPortfolioAccess && positions.length > 0 && (
          <TechPanel title="Portfolio overview" active={true}>
            <DataStrip items={[
              { label: 'Total value', value: money(portfolio.totalValue) },
              { label: 'Today', value: heroToday ? `${heroToday.dollarReturn >= 0 ? '+' : ''}${money(Math.abs(heroToday.dollarReturn))}` : '—' },
              { label: 'Period', value: homePeriodProfit != null ? `${homePeriodProfit >= 0 ? '+' : ''}${money(Math.abs(homePeriodProfit))}` : '—' },
              { label: 'Holdings', value: String(positions.length) },
            ]} />
          </TechPanel>
        )}

        {/* Portfolio scores */}
        {hasPortfolioAccess && positions.length > 0 && (
          <TechPanel title="Portfolio scores" active={true}>
            <MetricGrid items={[
              { label: 'Overall', value: overall.score != null ? `${Math.round(overall.score)}/100` : '—' },
              { label: 'Diversification', value: diversification.score != null ? `${Math.round(diversification.score)}/100` : '—' },
              { label: 'Resilience', value: resilience.score != null ? `${Math.round(resilience.score)}/100` : '—' },
              { label: 'Coverage', value: portfolio.coveragePct != null ? `${Math.round(portfolio.coveragePct)}%` : '—' },
            ]} />
          </TechPanel>
        )}
      </div>

      {/* Central radar */}
      <CircularRadar
        stocks={topStocks}
        onStockClick={(stock) => window.location.href = `/research?ticker=${stock.ticker}`}
      />

      {/* Right side panels */}
      <div className="side-panel side-panel-right">
        {/* Research leader */}
        <TechPanel title="Research leader" active={true}>
          <div style={{ padding: 'var(--sp-2)', display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
              <CompanyLogo company={leader} size={40} />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{leader.ticker}</div>
                <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-secondary)' }}>{leader.name}</div>
              </div>
              <div style={{ fontSize: 'var(--fs-2xl)', fontWeight: 700, color: 'var(--brand-primary)' }}>{leader.score}</div>
            </div>
            {leader.sparkline && <Sparkline values={leader.sparkline} height={40} />}
          </div>
        </TechPanel>

        {/* Top holdings */}
        {hasPortfolioAccess && positions.length > 0 && (
          <TechPanel title="Top holdings" active={true}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
              {portfolio.positions.slice(0, 5).map((position, index) => {
                const move = dailyMoveForPosition(position)
                return (
                  <div key={position.ticker} style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--sp-2)',
                    padding: 'var(--sp-2)',
                    background: 'rgba(0, 0, 0, 0.3)',
                    borderRadius: 'var(--r-xs)',
                  }}>
                    <span style={{
                      fontSize: 'var(--fs-xs)',
                      color: 'var(--brand-primary)',
                      fontWeight: 700,
                      minWidth: '20px',
                    }}>{index + 1}</span>
                    <CompanyLogo company={position.priceInfo || position} size={28} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 'var(--fs-sm)' }}>{position.ticker}</div>
                      <div style={{ fontSize: 'var(--fs-2xs)', color: 'var(--text-secondary)' }}>
                        {position.allocationPct != null ? `${position.allocationPct.toFixed(1)}%` : '—'}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{
                        fontSize: 'var(--fs-sm)',
                        fontWeight: 600,
                        color: move.pct == null ? 'var(--text-primary)' : move.pct >= 0 ? '#00ff88' : '#ff4466'
                      }}>
                        {move.pct != null ? signedPct(move.pct, 2) : '—'}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </TechPanel>
        )}

        {/* Sector allocation */}
        {hasPortfolioAccess && positions.length > 0 && sectorAllocation.length > 0 && (
          <TechPanel title="Sector allocation" active={true}>
            <div style={{ display: 'flex', justifyContent: 'center', padding: 'var(--sp-3)' }}>
              <SectorDonut sectors={sectorAllocation.slice(0, 5).map(s => ({ name: s.sector, count: Math.round(s.pct) }))} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
              {sectorAllocation.slice(0, 5).map((item) => (
                <div key={item.sector} style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  padding: 'var(--sp-1)',
                  fontSize: 'var(--fs-xs)',
                }}>
                  <span style={{ color: 'var(--text-secondary)' }}>{item.sector}</span>
                  <span style={{ color: 'var(--brand-primary)', fontWeight: 700 }}>{item.pct.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </TechPanel>
        )}

        {/* Watchlist */}
        {watchRows.length > 0 && (
          <TechPanel title="Watchlist" active={true}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
              {watchRows.map((row) => (
                <div key={row.ticker} style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--sp-2)',
                  padding: 'var(--sp-2)',
                  background: 'rgba(0, 0, 0, 0.3)',
                  borderRadius: 'var(--r-xs)',
                }}>
                  <CompanyLogo company={row} size={28} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 'var(--fs-sm)' }}>{row.ticker}</div>
                  </div>
                  <div style={{ fontSize: 'var(--fs-lg)', fontWeight: 700, color: 'var(--brand-primary)' }}>{row.score}</div>
                  {row.dayChange != null && (
                    <div style={{
                      fontSize: 'var(--fs-sm)',
                      color: row.dayChange >= 0 ? '#00ff88' : '#ff4466'
                    }}>
                      {signedPct(row.dayChange)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </TechPanel>
        )}
      </div>

      {/* Footer */}
      <footer className="command-footer">
        <div className="command-footer-left">
          <span>Latest close: {String(data.generated_at).slice(0, 10)}</span>
          <span>Coverage: {rows.length} names</span>
        </div>
        <div className="command-footer-right">
          <span>Research-only • Not investment advice</span>
          <span>© 2024 ValueSignal</span>
        </div>
      </footer>
    </div>
  </div>
}
