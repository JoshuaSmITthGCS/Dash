// Portfolio page shell. Loads the data, derives the shared view models once, and hands
// them to whichever of the three views the route asked for. The views themselves live in
// src/pages/portfolio/ — see portfolioModels.js for the read path and usePortfolioForms.js
// for the write path.

import { useState } from 'react'
import { useData } from '../lib/useData'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio'
import { useAuth } from '../lib/FirebaseAuthContext'
import { Loading, RefreshProgress } from '../components/Bits'
import StockDetailModal from '../components/StockDetailModal'
import Icon from '../components/Icons'
import { useAdvisorRefresh } from '../lib/useAdvisorRefresh'
import { nextPortfolioSort, PORTFOLIO_SORT_OPTIONS, sortPortfolioPositions } from '../lib/portfolioSort'
import { usePortfolioQuotes } from '../lib/usePortfolioQuotes'
import { usePullToRefresh } from '../lib/usePullToRefresh'
import PullToRefreshIndicator from '../components/PullToRefreshIndicator.jsx'
import { usePreferences } from '../lib/PreferencesContext.jsx'
import { usePortfolioTracking } from '../lib/usePortfolioTracking.js'
import { currentHoldingsSeries } from '../lib/portfolioAnalytics.js'
import StockTickerTape from '../components/StockTickerTape.jsx'
import modelSettings from '../../pipeline/config/settings.json'

import { sessionSetting } from './portfolio/format.js'
import { PORTFOLIO_PAGE_COPY, PortfolioNavigation } from './portfolio/PortfolioBits.jsx'
import { buildBenchmarkModel, buildHoldingsModel, buildPriceModel } from './portfolio/portfolioModels.js'
import { buildAnalyticsModel } from './portfolio/portfolioAnalyticsModel.js'
import { usePortfolioForms } from './portfolio/usePortfolioForms.js'
import Summary from './portfolio/Summary.jsx'
import Performance from './portfolio/Performance.jsx'
import DataOverview from './portfolio/DataOverview.jsx'

export { PORTFOLIO_NAV, PortfolioNavigation } from './portfolio/PortfolioBits.jsx'

export default function Portfolio({ view = 'summary' }) {
  const { currentUser } = useAuth()
  const { data, loading: dataLoading, reload } = useData('report.json')
  const { data: etfData } = useData('etfs.json')
  const { data: factorData } = useData('factors/french.json')
  const { data: signalMetrics } = useData('validation/signal_metrics.json')
  const { data: monteCarlo, error: monteCarloError } = useData('validation/monte_carlo_projection.json')
  const { data: spySnapshot } = useData('etf/SPY.json')
  const { data: rspSnapshot } = useData('etf/RSP.json')
  const { data: iwmSnapshot } = useData('etf/IWM.json')
  const { data: ijrSnapshot } = useData('etf/IJR.json')
  const portfolio = useFirebasePortfolio()
  const { loading: portfolioLoading, exportPortfolio, syncState } = portfolio
  const previewPortfolio = import.meta.env.DEV
    && new window.URLSearchParams(window.location.search).get('portfolioPreview') === '1'
  const positions = previewPortfolio ? modelSettings.interface.mobile_preview_positions : portfolio.positions
  const tracking = usePortfolioTracking()
  const { preferences, updatePreferences } = usePreferences()
  const { data: selectedBenchmarkSnapshot } = useData(`etf/${preferences.defaultBenchmark || 'SPY'}.json`)

  const [viewMode, setViewMode] = useState('holdings')
  const [selectedStock, setSelectedStock] = useState(null)
  const [portfolioSort, setPortfolioSort] = useState(preferences.holdingSort)
  const [analyticsScope, setAnalyticsScope] = useState(() => sessionSetting('valuesignal.analytics.scope', 'since_algorithm'))
  const [summaryPeriod, setSummaryPeriod] = useState('1D')
  const [performancePeriod, setPerformancePeriod] = useState('1M')
  const [attributionPeriod, setAttributionPeriod] = useState('1D')
  const [essentialOnly, setEssentialOnly] = useState(true)
  const [suggestedActionsOpen, setSuggestedActionsOpen] = useState(preferences.suggestedActionsDefault === 'expanded')

  const refresh = useAdvisorRefresh(
    data?.generated_at,
    reload,
    positions.map((position) => position.ticker),
  )
  // SPY rides along with the portfolio's own quote requests so the move-explanation
  // widget's market leg can use a live intraday benchmark return too, not just the
  // holdings - same refresh cadence, same Netlify function, one extra symbol.
  const portfolioQuotes = usePortfolioQuotes([...positions.map((position) => position.ticker), 'SPY'])
  const pullToRefresh = usePullToRefresh({
    onRefresh: portfolioQuotes.requestRefresh,
    enabled: positions.length > 0,
    refreshing: portfolioQuotes.refreshing,
  })
  const forms = usePortfolioForms({ portfolio, tracking, previewPortfolio })

  const { priceData, pricesUpdatedAt, benchmarkQuote } = buildPriceModel({ data, positions, quotes: portfolioQuotes })
  const holdings = buildHoldingsModel({ data, positions, priceData, etfData })
  const benchmarks = buildBenchmarkModel({
    data,
    snapshots: { spy: spySnapshot, rsp: rspSnapshot, iwm: iwmSnapshot, ijr: ijrSnapshot, selected: selectedBenchmarkSnapshot },
  })
  const holdingsSeriesFull = currentHoldingsSeries(positions, priceData, benchmarks.analyticsBenchmarkSeries?.dates || [])
  // The full statistics pass is only rendered by the Data overview, and it is by far the
  // most expensive derivation on this page, so the other two routes skip it entirely.
  const analytics = view === 'data'
    ? buildAnalyticsModel({
      data,
      positions,
      portfolioPositions: holdings.portfolioPositions,
      etfData,
      factorData,
      signalMetrics,
      analyticsScope,
      benchmarks,
      holdingsSeriesFull,
    })
    : null

  const commitSort = (next) => { setPortfolioSort(next); updatePreferences({ holdingSort: next }) }
  const sort = {
    sort: portfolioSort,
    selectedLabel: PORTFOLIO_SORT_OPTIONS.find((option) => option.key === portfolioSort.key)?.label,
    onSortKey: (key) => commitSort(nextPortfolioSort(portfolioSort, key)),
    onToggleDirection: () => commitSort({ ...portfolioSort, direction: portfolioSort.direction === 'asc' ? 'desc' : 'asc' }),
  }
  const sortedPositions = sortPortfolioPositions(holdings.portfolioPositions, portfolioSort.key, portfolioSort.direction)

  if (dataLoading || portfolioLoading) return <Loading />

  const pageCopy = PORTFOLIO_PAGE_COPY[view] || PORTFOLIO_PAGE_COPY.summary

  return (
    <>
      <PullToRefreshIndicator pullDistance={pullToRefresh.pullDistance} armed={pullToRefresh.armed} refreshing={portfolioQuotes.refreshing} settling={pullToRefresh.settling} />
      <StockTickerTape positions={holdings.portfolioPositions} />
      <div className="page-head">
        <div>
          <span className="eyebrow">Your money</span>
          <h1 className="page-title">{pageCopy.title}</h1>
          <p className="page-sub">{pageCopy.description}</p>
        </div>
        <div className={`cloud-sync-state ${syncState.connected ? 'connected' : 'disconnected'}`} role="status">
          <span aria-hidden="true" />
          <div><strong>{syncState.connected ? 'Firebase live sync on' : 'Firebase sync unavailable'}</strong><small>{syncState.connected ? `${currentUser?.email || 'Solo workspace'} · devices update automatically${syncState.lastSyncedAt ? ` · ${new Date(syncState.lastSyncedAt).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}` : ''}` : syncState.error || 'Connecting your solo cloud workspace'}</small></div>
        </div>
      </div>
      {view === 'summary' && holdings.actionable.length > 0 && <a className="portfolio-sell-alert" href="#sell-signals"><Icon name="bell" size={17} /><span><strong>{holdings.actionable.length} sell signal{holdings.actionable.length === 1 ? '' : 's'} need review</strong><small>{holdings.actionable.map((position) => position.ticker).join(', ')} · Hold positions are not shown here.</small></span><Icon name="chevron" size={16} /></a>}
      {forms.syncMessage && <div className="sync-message" role="status">{forms.syncMessage}</div>}
      {(portfolioQuotes.message || portfolioQuotes.error) && (
        <div className={`sync-message refresh-message ${portfolioQuotes.error ? 'error' : 'success'}`} role="status" aria-live="polite">
          {portfolioQuotes.error || portfolioQuotes.message}
        </div>
      )}
      <RefreshProgress active={refresh.refreshing} elapsedLabel={refresh.elapsedLabel}
        percent={refresh.progress} stage={refresh.stage} />
      {refresh.message && (
        <div className={`sync-message refresh-message ${refresh.status}`} role="status" aria-live="polite">
          {refresh.message}
        </div>
      )}

      <div className="portfolio-sticky-tools">
        <PortfolioNavigation />
        <div className="portfolio-sticky-actions">
          <button className="primary-button compact portfolio-sticky-refresh" onClick={portfolioQuotes.requestRefresh} disabled={portfolioQuotes.refreshing || positions.length === 0}>
            <Icon name="sync" size={16} className={portfolioQuotes.refreshing ? 'refresh-spin' : ''} />
            <span>{portfolioQuotes.refreshing ? 'Updating…' : 'Refresh prices'}</span>
          </button>
          <details className="portfolio-data-menu">
            <summary><span>Data actions</span><Icon name="chevron" size={15} aria-hidden="true" /></summary>
            <div className="portfolio-data-popover">
              <div className="portfolio-data-status">
                <span className="eyebrow">Portfolio prices</span>
                <time dateTime={pricesUpdatedAt || undefined}>{pricesUpdatedAt ? `Updated ${new Date(pricesUpdatedAt).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}` : 'Not updated yet'}</time>
              </div>
              <button className="secondary-button" onClick={refresh.requestRefresh} disabled={refresh.refreshing}><Icon name="sync" size={17} className={refresh.refreshing && refresh.activeMode === 'data' ? 'refresh-spin' : ''} />{refresh.refreshing && refresh.activeMode === 'data' ? 'Refreshing all data…' : 'Refresh all research'}</button>
              <button className="secondary-button" onClick={refresh.requestReanalyze} disabled={refresh.refreshing}><Icon name="research" size={17} className={refresh.refreshing && refresh.activeMode === 'rescore' ? 'refresh-spin' : ''} />{refresh.refreshing && refresh.activeMode === 'rescore' ? 'Reanalyzing…' : 'Reanalyze portfolio'}</button>
              <button className="secondary-button" onClick={forms.handleReferenceSync}>Reapply Aug 14 Fidelity snapshot</button>
              <button className="secondary-button" onClick={exportPortfolio}><Icon name="download" size={17} />Export portfolio</button>
            </div>
          </details>
        </div>
      </div>

      {view === 'summary' && (
        <Summary
          holdings={holdings}
          positions={positions}
          priceData={priceData}
          holdingsSeriesFull={holdingsSeriesFull}
          trackingSnapshots={tracking.snapshots}
          quotesRefreshing={portfolioQuotes.refreshing}
          summaryPeriod={summaryPeriod}
          onSummaryPeriodChange={setSummaryPeriod}
          suggestedActionsOpen={suggestedActionsOpen}
          onSuggestedActionsToggle={setSuggestedActionsOpen}
          onSelectStock={setSelectedStock}
          sortedPositions={sortedPositions}
          sort={sort}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          essentialOnly={essentialOnly}
          onEssentialOnlyChange={setEssentialOnly}
          forms={forms}
        />
      )}

      {view === 'performance' && (
        <Performance
          holdings={holdings}
          holdingsSeriesFull={holdingsSeriesFull}
          benchmarks={benchmarks}
          performancePeriod={performancePeriod}
          onPerformancePeriodChange={setPerformancePeriod}
        />
      )}

      {view === 'data' && (
        <DataOverview
          holdings={holdings}
          benchmarkQuote={benchmarkQuote}
          analytics={analytics}
          benchmarks={benchmarks}
          signalMetrics={signalMetrics}
          monteCarlo={monteCarlo}
          monteCarloError={monteCarloError}
          attributionPeriod={attributionPeriod}
          onAttributionPeriodChange={setAttributionPeriod}
          analyticsScope={analyticsScope}
          onAnalyticsScopeChange={(next) => {
            setAnalyticsScope(next)
            try { globalThis.sessionStorage?.setItem('valuesignal.analytics.scope', next) } catch { /* optional session persistence */ }
          }}
        />
      )}

      {selectedStock && (
        <StockDetailModal
          stock={selectedStock.priceInfo || selectedStock}
          recommendationOverride={selectedStock.recommendation}
          stopLoss={selectedStock.stopLoss}
          position={selectedStock.shares
            ? { shares: selectedStock.shares, price: selectedStock.currentPrice, purchaseDate: selectedStock.purchaseDate }
            : null}
          benchmarkHistory={holdings.benchmarkHistory}
          onClose={() => setSelectedStock(null)}
        />
      )}
    </>
  )
}
