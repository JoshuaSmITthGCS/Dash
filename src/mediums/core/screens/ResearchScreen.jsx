import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useData, fmtPct } from '../../../lib/useData.js'
import { useMedium } from '../MediumContext.jsx'
import { cap } from '../capability.js'
import { RESEARCH_IDS } from './capabilityIds.js'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'
import { useWatchlist } from '../../../lib/useWatchlist.js'
import { useAlerts } from '../../../lib/useAlerts.js'
import { useAuth, AuthProvider as FirebaseAuthProvider } from '../../../lib/FirebaseAuthContext.jsx'
import { entryTiming } from '../../../lib/entryTiming.js'
import {
  RANKING_MODELS, isRankingModel, modelCoverage, modelReason, rankByModel,
} from '../../../lib/rankingModels.js'
import { buildRatingContext, researchRating } from '../../../lib/researchRating.js'
import { buildValueGrowthContext, valueGrowthScore } from '../../../lib/valueGrowthScore.js'
import { allocateFunds } from '../../../lib/fundsAllocation.js'
import { STRATEGY_LENSES, rankByLens, lensReason } from '../../../lib/researchScreens.js'
import { inverseVolatilityAllocations, watchlistGuidance } from '../../../lib/watchlistGuidance.js'
import { suggestPriceTargets } from '../../../lib/watchlistPriceTargets.js'

/**
 * Absorbs Picks, Search, and Watchlist behind `?q=` and `?view=picks|watchlist` (see
 * ROUTE-INVENTORY.md §2). This is the URL-addressability rule made concrete: `?q=` is read here
 * on mount, fixing the dead param Alerts has always produced but Search never consumed.
 *
 * Phase 2b: the search-and-list slice from Phase 2a (search input, result count, loading/empty)
 * is untouched below — wiring the rest of CAPABILITY-LEDGER.md §2 is additive around it: the
 * sector/sort/asset-type/ownership toolbar and ranked pool, per-row Buy $100/watchlist/alert
 * actions, the allocation planner, and the watchlist view absorbed behind `?view=watchlist`
 * (lens chips, sizing, price-target editor, dip alerts). `chart.*`-class rows are out of scope
 * for §2 (there are none); `link.global.buy-100-guard`-style cross-cutting rows live elsewhere.
 * The full per-`/research`-route Stock Detail Sheet is its own ledger section (§14, opened from
 * seven routes) — `detail.research.open-stock-detail` here opens a minimal inline research
 * summary rather than that full sheet, which is out of this screen's scope.
 */

function finite(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

const MODEL_LIMIT = 20
// Unlike the model-ranked branch (which already caps at MODEL_LIMIT), the default
// score/column-sorted branch had no display cap — with sector/asset-type/ownership filters off,
// it rendered every one of the ~900-name universe as a full card. Capped here for the same
// reason MODEL_LIMIT exists: a bounded, honestly-labeled list instead of an unbounded one.
const DISPLAY_LIMIT = 100
const RECENT_SEARCH_KEY = 'valuesignal.recent-searches'
const WATCHLIST_SIZING_KEY = 'valuesignal.watchlistSizing'
const WATCHLIST_FILTER_KEY = 'valuesignal.watchlistFilterSort'
const ASSET_TYPES = new Set(['all', 'stock', 'etf'])
const OWNERSHIPS = new Set(['all', 'bought', 'not-bought'])
const LENS_KEYS = Object.keys(STRATEGY_LENSES)

// Every capability id this screen renders beyond the four already wired in capabilityIds.js
// (RESEARCH_IDS, read-only). Copied verbatim from CAPABILITY-LEDGER.md §2.
const IDS = Object.freeze({
  sectorFilter: 'control.research.sector-filter',
  sort: 'control.research.sort',
  assetType: 'control.research.asset-type',
  ownershipFilter: 'control.research.ownership-filter',
  buy100: 'action.research.buy-100',
  watchlistToggle: 'control.research.watchlist-toggle',
  setLowAlert: 'alert.research.set-low-alert',
  secondaryMetricsToggle: 'control.research.secondary-metrics-toggle',
  openStockDetail: 'detail.research.open-stock-detail',
  plannerFunds: 'control.research.planner-funds',
  plannerDoubleDown: 'control.research.planner-double-down',
  modelSummary: 'figure.research.model-summary',
  columnRank: 'column.research.rank',
  columnStance: 'column.research.stance',
  columnRating: 'column.research.rating',
  columnModelScoreWhy: 'column.research.model-score-why',
  columnFundamentals: 'column.research.fundamentals',
  columnReturn20d: 'column.research.20d-return',
  columnConfidence: 'column.research.confidence',
  columnTiming: 'column.research.timing',
  columnPctPortfolio: 'column.research.pct-portfolio',
  mobileCard: 'figure.research.mobile-card',
  plannerBucketList: 'figure.research.planner-bucket-list',
  thinEvidenceChip: 'disclosure.research.thin-evidence-chip',
  lightDataChip: 'disclosure.research.light-data-chip',
  asOfLine: 'disclosure.research.as-of-line',
  modelWhyNa: 'disclosure.research.model-why-na',
  scoreCapped: 'disclosure.research.score-capped',
  plannerNotes: 'disclosure.research.planner-notes',
  pageDisclaimer: 'disclosure.research.page-disclaimer',
  etfModelMismatch: 'state.research.etf-model-mismatch',
  modelGateNotCleared: 'state.research.model-gate-not-cleared',
  noFilterMatch: 'state.research.no-filter-match',
  buyAlertStatus: 'state.research.buy-alert-status',
  watchlistSearch: 'control.research.watchlist-search',
  watchlistLensChips: 'figure.research.watchlist-lens-chips',
  watchlistSort: 'control.research.watchlist-sort',
  watchlistSizing: 'control.research.watchlist-sizing',
  watchlistAddTicker: 'control.research.watchlist-add-ticker',
  priceTargetEditor: 'control.research.price-target-editor',
  watchlistSizingNote: 'disclosure.research.watchlist-sizing-note',
  watchlistSignedOut: 'state.research.watchlist-signed-out',
  watchlistNoQuote: 'state.research.watchlist-no-quote',
  watchlistEmpty: 'state.research.watchlist-empty',
  watchlistNoFilterMatch: 'state.research.watchlist-no-filter-match',
})

const COLUMN_SORTS = {
  publishedScore: ['Published research score', (a, b) => (b.score ?? -1) - (a.score ?? -1)],
  return: ['20-day return', (a, b) => (b.technical_detail?.return_20d ?? -999) - (a.technical_detail?.return_20d ?? -999)],
  confidence: ['Data coverage', (a, b) => (b.data_coverage ?? -1) - (a.data_coverage ?? -1)],
  portfolioPct: ['% of my portfolio', (a, b) => (b.portfolioPct ?? -1) - (a.portfolioPct ?? -1)],
  undervalued: ['Most undervalued (cheap + growth)', (a, b) => (b.valueGrowthScore ?? -1) - (a.valueGrowthScore ?? -1)],
}

const WATCHLIST_SORTS = {
  recent: ['Recently added', null],
  setup: ['Best buy for the price (setup quality)', (a, b) => (b.guidance?.setupScore ?? -1) - (a.guidance?.setupScore ?? -1)],
  upside: ['Highest upside to price target', (a, b) => (b.guidance?.targetUpside ?? -Infinity) - (a.guidance?.targetUpside ?? -Infinity)],
}

const etfStance = (score) => (score >= 80 ? 'Attractive' : score >= 70 ? 'Promising' : score >= 55 ? 'Neutral' : 'Caution')

// Mirrors Picks.jsx's own ETF normalization so stocks and ETFs can share one ranked pool while
// keeping their two scoring models' scales separate everywhere they're actually compared.
function normalizeEtf(row) {
  const score = row.scores?.overall ?? row.quality_score ?? null
  return {
    ...row,
    is_etf: true,
    asset_type: 'etf',
    score,
    stance: etfStance(score),
    components: { fundamentals: row.scores?.quality, market_behavior: row.scores?.performance, news_sentiment: null },
    technical_detail: {
      return_20d: row.returns?.['1m'], return_252d: row.returns?.['1y'],
      max_drawdown_252d: row.max_drawdown, beta: row.beta,
    },
    strengths: [
      row.expense_ratio != null ? `${row.expense_ratio.toFixed(2)}% expense ratio` : null,
      row.peer_rank ? `#${row.peer_rank} of ${row.peer_group_size} in its peer group` : null,
    ].filter(Boolean),
    risks: [
      row.max_drawdown != null ? `${Math.abs(row.max_drawdown).toFixed(1)}% maximum drawdown in the measured window` : null,
      row.tracking_error_pct != null ? `${row.tracking_error_pct.toFixed(2)}% tracking error` : null,
    ].filter(Boolean),
  }
}

function isLightData(row) {
  return !row.is_etf && !finite(row.data_coverage)
}

function readJSON(key) {
  try {
    return JSON.parse(localStorage.getItem(key))
  } catch {
    return null
  }
}

function readList(key) {
  const value = readJSON(key)
  return Array.isArray(value) ? value : []
}

function writeJSON(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Best-effort only — a private window or a full quota falls back to session-only state.
  }
}

/**
 * Renders through the active medium's Control when it implements one (per the wiring contract's
 * `manifest.components?.X || fallback` rule) — a plain, correctly-typed native element otherwise,
 * since Control's own fallback can't be a bare string tag (it takes `as`/`capId`/`pressed`, which
 * a plain 'select'/'input'/'button' string doesn't understand). Matches MarketsScreen.jsx's own
 * SelectField/SearchField/ButtonField helpers.
 */
function Field({ Control, as = 'button', capId, pressed, children, ...rest }) {
  if (Control) return <Control as={as} capId={capId} pressed={pressed} {...rest}>{children}</Control>
  const Tag = as
  return <Tag data-capability-id={capId} aria-pressed={pressed} {...rest}>{children}</Tag>
}

/** Dip-buy / good-buy price target editor, one capability id for the whole unit (ledger row
 * bundles the inputs, "Use suggested", save, and "Alert me at dip price" together). */
function PriceTargetEditor({ item, suggested, onSave, onCreateAlert, alertBusy }) {
  const [dip, setDip] = useState(item.dipPrice ?? '')
  const [goodBuy, setGoodBuy] = useState(item.goodBuyPrice ?? '')
  const [saved, setSaved] = useState(false)

  const save = async () => {
    await onSave({ dipPrice: dip === '' ? null : Number(dip), goodBuyPrice: goodBuy === '' ? null : Number(goodBuy) })
    setSaved(true)
    setTimeout(() => setSaved(false), 1800)
  }
  const useSuggested = () => {
    setDip(suggested.dipBuy?.price ?? '')
    setGoodBuy(suggested.goodBuy?.price ?? '')
  }

  return (
    <div className="watchlist-target-fields">
      <label>
        <span>Dip buy price</span>
        <input type="number" min="0" step="0.01" inputMode="decimal" placeholder="e.g. 142.50"
          value={dip} onChange={(event) => setDip(event.target.value)} />
      </label>
      <label>
        <span>Good buy price</span>
        <input type="number" min="0" step="0.01" inputMode="decimal" placeholder="e.g. 150.00"
          value={goodBuy} onChange={(event) => setGoodBuy(event.target.value)} />
      </label>
      {(suggested.dipBuy?.price != null || suggested.goodBuy?.price != null) && (
        <button type="button" onClick={useSuggested}>
          Use suggested{suggested.dipBuy?.price != null ? `: dip $${suggested.dipBuy.price.toFixed(2)}` : ''}
          {suggested.goodBuy?.price != null ? ` · good buy $${suggested.goodBuy.price.toFixed(2)}` : ''}
        </button>
      )}
      <button type="button" onClick={save}>{saved ? 'Saved' : 'Save targets'}</button>
      {dip !== '' && (
        <button type="button" disabled={alertBusy} onClick={() => onCreateAlert(Number(dip))}>
          {alertBusy ? 'Creating…' : 'Alert me at dip price'}
        </button>
      )}
    </div>
  )
}

/**
 * Wraps ResearchScreenContent in its own local FirebaseAuthProvider — /v2's root (MediumApp.jsx)
 * never mounts one (that's the point of the Phase 4a Firebase-deferral fix), but this screen's
 * watchlist/portfolio/alerts absorption (added in Phase 4b) calls useAuth()/useFirebasePortfolio()
 * directly. Same pattern as PortfolioScreen.jsx/ScreensScreen.jsx/EvidenceScreen.jsx.
 */
export default function ResearchScreen() {
  return <FirebaseAuthProvider><ResearchScreenContent /></FirebaseAuthProvider>
}

function ResearchScreenContent() {
  const manifest = useMedium()
  const Container = manifest.components?.Container || 'section'
  const Control = manifest.components?.Control || null
  const [searchParams, setSearchParams] = useSearchParams()
  const view = searchParams.get('view') || 'picks'
  const [query, setQuery] = useState(searchParams.get('q') || '')

  const { data: report, loading } = useData('report.json')
  const { data: etfData } = useData('etfs.json')
  const { positions, addPosition } = useFirebasePortfolio()
  const watchlist = useWatchlist()
  const { createRule } = useAlerts()
  const { currentUser, authError, retryAuth } = useAuth()

  // --- Phase 2a slice, untouched ---------------------------------------------------------
  const results = useMemo(() => {
    const rows = report?.research || []
    if (!query.trim()) return rows
    const needle = query.trim().toUpperCase()
    return rows.filter((row) => row.ticker?.toUpperCase().includes(needle) || row.name?.toUpperCase().includes(needle))
  }, [report, query])

  const onSearchChange = (event) => {
    const value = event.target.value
    setQuery(value)
    const next = new URLSearchParams(searchParams)
    if (value) next.set('q', value); else next.delete('q')
    setSearchParams(next, { replace: true })
  }
  // -------------------------------------------------------------------------------------

  const setParam = (key, value) => {
    const next = new URLSearchParams(searchParams)
    if (value === null || value === undefined || value === '') next.delete(key)
    else next.set(key, String(value))
    setSearchParams(next, { replace: true })
  }
  const setView = (nextView) => setParam('view', nextView === 'picks' ? null : nextView)

  // control.research.watchlist-search: recent-search chips absorbed as persistent chrome,
  // dataSource is localStorage (was Search.jsx's RECENT_KEY) — no URL param, matching the
  // ledger's own dataSource column, which lists localStorage only.
  const [recentSearches, setRecentSearches] = useState(() => readList(RECENT_SEARCH_KEY))
  const recordRecentSearch = (ticker) => {
    setRecentSearches((current) => {
      const next = [ticker, ...current.filter((item) => item !== ticker)].slice(0, 8)
      writeJSON(RECENT_SEARCH_KEY, next)
      return next
    })
  }
  const pickRecentSearch = (ticker) => { setQuery(ticker); setParam('q', ticker) }
  const clearRecentSearches = () => { setRecentSearches([]); writeJSON(RECENT_SEARCH_KEY, []) }

  // --- Toolbar filters, all URL-addressable (ROUTE-INVENTORY.md §2) ----------------------
  const rawSort = searchParams.get('sort')
  const sort = rawSort && (COLUMN_SORTS[rawSort] || isRankingModel(rawSort)) ? rawSort : 'publishedScore'
  const sectorsParam = searchParams.get('sectors')
  const sectorFilterOn = sectorsParam !== null
  const enabledSectors = useMemo(
    () => new Set(sectorFilterOn ? sectorsParam.split(',').filter(Boolean) : []),
    [sectorFilterOn, sectorsParam],
  )
  const rawAssetType = searchParams.get('assetType')
  const assetType = ASSET_TYPES.has(rawAssetType) ? rawAssetType : 'all'
  const rawOwnership = searchParams.get('ownership')
  const ownership = OWNERSHIPS.has(rawOwnership) ? rawOwnership : 'all'
  const plannerFunds = searchParams.get('funds') || ''
  const doubleDown = searchParams.get('doubleDown') !== '0'

  // --- Merged stock + ETF universe, same construction as Picks.jsx -----------------------
  const etfTickers = useMemo(() => new Set((etfData?.etfs || []).map((row) => row.ticker)), [etfData])
  const stockResearch = useMemo(() => [...new Map(
    [...(report?.research || []), ...(report?.screen_universe || [])]
      .filter((row) => !row.is_etf && !etfTickers.has(row.ticker))
      .map((row) => [row.ticker, row]),
  ).values()], [report, etfTickers])
  const universe = useMemo(() => [
    ...stockResearch.map((row) => ({ ...row, researchType: 'Stock' })),
    ...(etfData?.etfs || []).map(normalizeEtf),
  ], [stockResearch, etfData])

  const positionValueByTicker = useMemo(() => {
    const priceByTicker = new Map(universe.map((row) => [row.ticker, row.price]))
    const totals = new Map()
    for (const position of positions) {
      const ticker = String(position.ticker || '').toUpperCase()
      const price = priceByTicker.get(ticker)
      if (!finite(price) || !finite(position.shares)) continue
      totals.set(ticker, (totals.get(ticker) || 0) + position.shares * price)
    }
    return totals
  }, [universe, positions])
  const totalPortfolioValue = useMemo(
    () => [...positionValueByTicker.values()].reduce((sum, value) => sum + value, 0),
    [positionValueByTicker],
  )
  const ratingContext = useMemo(() => buildRatingContext(universe), [universe])
  const valueGrowthContext = useMemo(() => buildValueGrowthContext(universe), [universe])
  const universeWithMeta = useMemo(() => universe.map((row) => ({
    ...row,
    portfolioPct: totalPortfolioValue > 0 ? ((positionValueByTicker.get(row.ticker) || 0) / totalPortfolioValue) * 100 : null,
    rating: researchRating(row, ratingContext),
    valueGrowthScore: valueGrowthScore(row, valueGrowthContext),
  })), [universe, positionValueByTicker, totalPortfolioValue, ratingContext, valueGrowthContext])
  const heldTickers = useMemo(() => new Set(positions.map((position) => String(position.ticker || '').toUpperCase())), [positions])
  const sectors = useMemo(() => [...new Set(stockResearch.map((row) => row.sector).filter(Boolean))].sort(), [stockResearch])

  const normalizedQuery = query.trim().toUpperCase()
  const poolFiltered = universeWithMeta
    .filter((row) => !sectorFilterOn || enabledSectors.has(row.sector))
    .filter((row) => ownership === 'all' || (ownership === 'bought') === heldTickers.has(row.ticker))
    .filter((row) => !normalizedQuery || row.ticker?.toUpperCase().includes(normalizedQuery) || String(row.name || '').toUpperCase().includes(normalizedQuery))
  const poolStocks = poolFiltered.filter((row) => !row.is_etf)
  const poolEtfs = poolFiltered.filter((row) => row.is_etf)
  const modelActive = isRankingModel(sort)
  const coverage = modelActive ? modelCoverage(poolStocks, sort) : null
  const columnSort = COLUMN_SORTS[sort]?.[1] || COLUMN_SORTS.publishedScore[1]
  const stockRows = modelActive ? rankByModel(poolStocks, sort, MODEL_LIMIT) : poolStocks.slice().sort(columnSort)
  const etfRows = modelActive ? [] : poolEtfs.slice().sort(columnSort)
  const showStocks = assetType !== 'etf'
  const showEtfs = assetType !== 'stock' && !modelActive
  const poolRows = [...(showStocks ? stockRows : []), ...(showEtfs ? etfRows : [])]

  // --- Per-row actions ---------------------------------------------------------------------
  const [buyingTicker, setBuyingTicker] = useState('')
  const [buyStatuses, setBuyStatuses] = useState({})
  const [alertingTicker, setAlertingTicker] = useState('')
  const [alertStatuses, setAlertStatuses] = useState({})
  const [expandedTickers, setExpandedTickers] = useState(() => new Set())
  const [openTicker, setOpenTicker] = useState(null)

  const handleBuy = async (row) => {
    const price = Number(row.price)
    if (!Number.isFinite(price) || price <= 0 || heldTickers.has(row.ticker)) return
    const shares = Number((100 / price).toFixed(6))
    const localToday = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10)
    setBuyingTicker(row.ticker)
    setBuyStatuses((current) => ({ ...current, [row.ticker]: null }))
    const result = await addPosition(row.ticker, shares, price, localToday, 'share')
    setBuyingTicker('')
    setBuyStatuses((current) => ({
      ...current,
      [row.ticker]: result?.success
        ? { message: `${shares.toFixed(4)} ${row.ticker} shares added at $${price.toFixed(2)} for $100 on ${localToday}.` }
        : { error: true, message: result?.error ? `Could not add ${row.ticker}: ${result.error}` : 'Reconnect Firebase to add this trade to your portfolio.' },
    }))
  }

  const handleSetLowAlert = async (row, timing) => {
    setAlertingTicker(row.ticker)
    setAlertStatuses((current) => ({ ...current, [row.ticker]: null }))
    const result = await createRule({ type: 'price_cross', ticker: row.ticker, direction: 'below', threshold: timing.alertPrice })
    setAlertingTicker('')
    setAlertStatuses((current) => ({
      ...current,
      [row.ticker]: result?.success
        ? { message: `Alert set: ${row.ticker} below $${timing.alertPrice.toFixed(2)}.` }
        : { error: true, message: result?.error || `Could not set an alert for ${row.ticker}.` },
    }))
  }

  const toggleExpanded = (ticker) => setExpandedTickers((current) => {
    const next = new Set(current)
    if (next.has(ticker)) next.delete(ticker); else next.add(ticker)
    return next
  })

  const openDetail = (row) => {
    setOpenTicker(row.ticker)
    recordRecentSearch(row.ticker)
  }

  // --- Allocation planner ------------------------------------------------------------------
  const allocationPool = assetType === 'etf' ? etfRows : stockRows
  const allocationCandidates = doubleDown ? allocationPool : allocationPool.filter((row) => !heldTickers.has(row.ticker))
  const allocation = allocateFunds(allocationCandidates, Number(plannerFunds), {
    limit: 8,
    scoreOf: modelActive ? ((row) => row.modelScore?.score) : undefined,
  })

  // --- Watchlist absorbed view -------------------------------------------------------------
  const storedSizing = useMemo(() => readJSON(WATCHLIST_SIZING_KEY) || {}, [])
  const budget = searchParams.get('budget') ?? (storedSizing.budget ?? '')
  const maxPositionPct = searchParams.get('maxpct') ?? (storedSizing.maxPositionPct ?? '5')
  const setSizing = (nextBudget, nextMaxPct) => {
    const next = new URLSearchParams(searchParams)
    if (nextBudget === '') next.delete('budget'); else next.set('budget', nextBudget)
    if (nextMaxPct === '') next.delete('maxpct'); else next.set('maxpct', nextMaxPct)
    setSearchParams(next, { replace: true })
    writeJSON(WATCHLIST_SIZING_KEY, { budget: nextBudget, maxPositionPct: nextMaxPct })
  }

  const storedFilterSort = useMemo(() => readJSON(WATCHLIST_FILTER_KEY) || {}, [])
  const lensParam = searchParams.get('lens')
  const activeLenses = useMemo(() => {
    if (lensParam !== null) return lensParam.split(',').filter((key) => LENS_KEYS.includes(key))
    return Array.isArray(storedFilterSort.filters) ? storedFilterSort.filters.filter((key) => LENS_KEYS.includes(key)) : []
  }, [lensParam, storedFilterSort])
  const wsortParam = searchParams.get('wsort')
  const wsort = wsortParam && WATCHLIST_SORTS[wsortParam] ? wsortParam
    : (WATCHLIST_SORTS[storedFilterSort.sort] ? storedFilterSort.sort : 'recent')
  const setWatchlistFilterSort = (filters, nextSort) => {
    const next = new URLSearchParams(searchParams)
    if (filters.length) next.set('lens', filters.join(',')); else next.delete('lens')
    if (nextSort && nextSort !== 'recent') next.set('wsort', nextSort); else next.delete('wsort')
    setSearchParams(next, { replace: true })
    writeJSON(WATCHLIST_FILTER_KEY, { filters, sort: nextSort })
  }

  const byTickerReport = useMemo(() => Object.fromEntries([
    ...(report?.research || []),
    ...(report?.portfolio_coverage || []),
  ].map((row) => [row.ticker, row])), [report])
  const watchTickers = watchlist.items.map((item) => item.ticker)
  const watchRows = useMemo(() => watchTickers.map((ticker) => byTickerReport[ticker]).filter(Boolean), [watchTickers, byTickerReport])
  const numericBudget = Number(budget)
  const numericMaxPct = Number(maxPositionPct)
  const volatilityAllocations = useMemo(
    () => inverseVolatilityAllocations(watchRows, numericBudget, numericMaxPct),
    [watchRows, numericBudget, numericMaxPct],
  )
  const lensMatches = useMemo(() => Object.fromEntries(LENS_KEYS.map((key) => [
    key, new Map(rankByLens(watchRows, key, watchRows.length).map((row) => [row.ticker, row])),
  ])), [watchRows])
  const decoratedWatch = watchlist.items.map((item) => {
    const ticker = item.ticker
    const row = byTickerReport[ticker]
    const guidance = row ? watchlistGuidance(row, numericBudget, numericMaxPct, { volatilityAllocation: volatilityAllocations[ticker] }) : null
    const matchedLensKeys = LENS_KEYS.filter((key) => lensMatches[key].has(ticker))
    return { item, ticker, row, guidance, matchedLensKeys }
  })
  const visibleWatchItems = activeLenses.length
    ? decoratedWatch.filter((entry) => entry.matchedLensKeys.some((key) => activeLenses.includes(key)))
    : decoratedWatch
  const sortedWatchItems = WATCHLIST_SORTS[wsort][1] ? visibleWatchItems.slice().sort(WATCHLIST_SORTS[wsort][1]) : visibleWatchItems

  const [watchInput, setWatchInput] = useState('')
  const addWatchTicker = async () => {
    const value = watchInput.trim().toUpperCase()
    if (value && !watchlist.isWatched(value)) await watchlist.addTicker(value)
    setWatchInput('')
  }
  const [dipAlertBusyTicker, setDipAlertBusyTicker] = useState('')
  const [dipAlertNotice, setDipAlertNotice] = useState(null)
  const handleCreateDipAlert = async (item, dipPrice) => {
    setDipAlertBusyTicker(item.ticker)
    const result = await createRule({ type: 'price_cross', ticker: item.ticker, direction: 'below', threshold: dipPrice })
    setDipAlertBusyTicker('')
    setDipAlertNotice(result?.success
      ? { error: false, message: `Alert created: ${item.ticker} price below $${dipPrice.toFixed(2)}.` }
      : { error: true, message: result?.error || 'Could not create the alert.' })
  }

  if (loading) return <div role="status" aria-live="polite">Loading…</div>

  const openRow = openTicker ? universeWithMeta.find((row) => row.ticker === openTicker) : null

  return (
    <div data-screen="research" data-view={view}>
      <Container {...cap(RESEARCH_IDS.searchInput)}>
        <input
          type="search"
          value={query}
          onChange={onSearchChange}
          aria-label="Search research"
          placeholder="Search ticker or company"
        />
      </Container>
      <Container {...cap(RESEARCH_IDS.resultCount)}>
        <span data-testid="result-count">{results.length} result{results.length === 1 ? '' : 's'}</span>
      </Container>
      {results.length === 0 && (
        <div {...cap(RESEARCH_IDS.empty)} role="status">No companies match those filters.</div>
      )}
      <ul data-testid="research-results">
        {results.slice(0, 25).map((row) => (
          <li key={row.ticker}>{row.ticker} — {row.name} — {row.score != null ? row.score.toFixed(1) : '–'}</li>
        ))}
      </ul>

      <div className="research-view-tabs" role="tablist" aria-label="Research view">
        <button type="button" role="tab" aria-selected={view === 'picks'} data-testid="view-tab-picks" onClick={() => setView('picks')}>Research list</button>
        <button type="button" role="tab" aria-selected={view === 'watchlist'} data-testid="view-tab-watchlist" onClick={() => setView('watchlist')}>Watchlist</button>
      </div>

      {view === 'picks' && !query.trim() && recentSearches.length > 0 && (
        <Container {...cap(IDS.watchlistSearch)}>
          <span>Recent searches</span>
          {recentSearches.map((ticker) => (
            <button key={ticker} type="button" onClick={() => pickRecentSearch(ticker)}>{ticker}</button>
          ))}
          <button type="button" onClick={clearRecentSearches}>Clear</button>
        </Container>
      )}

      {view === 'picks' && (
        <>
          <div className="research-toolbar">
            <Container {...cap(IDS.sectorFilter)}>
              <label>
                <input type="checkbox" checked={sectorFilterOn} onChange={(event) => {
                  setParam('sectors', event.target.checked ? sectors.join(',') : null)
                }} />
                <span>Filter by sector{sectorFilterOn ? ` (${enabledSectors.size}/${sectors.length})` : ''}</span>
              </label>
              {sectorFilterOn && (
                <div role="group" aria-label="Sectors to include">
                  {sectors.map((item) => (
                    <label key={item}>
                      <input type="checkbox" checked={enabledSectors.has(item)} onChange={(event) => {
                        const next = new Set(enabledSectors)
                        if (event.target.checked) next.add(item); else next.delete(item)
                        setParam('sectors', [...next].join(','))
                      }} />
                      <span>{item}</span>
                    </label>
                  ))}
                </div>
              )}
            </Container>

            <Field Control={Control} as="select" capId={IDS.sort} aria-label="Sort research"
              value={sort} onChange={(event) => setParam('sort', event.target.value === 'publishedScore' ? null : event.target.value)}>
              <optgroup label="Sort the full list">
                {Object.keys(COLUMN_SORTS).map((key) => <option key={key} value={key}>Sort: {COLUMN_SORTS[key][0]}</option>)}
              </optgroup>
              <optgroup label="Rank by model (top 20)">
                {Object.keys(RANKING_MODELS).map((key) => (
                  <option key={key} value={key} title={RANKING_MODELS[key].question}>Model: {RANKING_MODELS[key].label}</option>
                ))}
              </optgroup>
            </Field>

            <Field Control={Control} as="select" capId={IDS.assetType} aria-label="Filter by asset type"
              value={assetType} onChange={(event) => setParam('assetType', event.target.value === 'all' ? null : event.target.value)}>
              <option value="all">Stocks &amp; ETFs</option><option value="stock">Stocks</option><option value="etf">ETFs</option>
            </Field>

            <Field Control={Control} as="select" capId={IDS.ownershipFilter} aria-label="Filter by ownership"
              value={ownership} onChange={(event) => setParam('ownership', event.target.value === 'all' ? null : event.target.value)}>
              <option value="all">Bought &amp; not bought</option><option value="bought">Bought</option><option value="not-bought">Not bought</option>
            </Field>
          </div>

          {modelActive && coverage && (
            <Container {...cap(IDS.modelSummary)} aria-label={`${RANKING_MODELS[sort].label} model coverage`}>
              <p><strong>{RANKING_MODELS[sort].label}</strong> — {RANKING_MODELS[sort].question}</p>
              <p>
                {coverage.qualified === 0
                  ? `No company clears this model's gate under the current filters, out of ${coverage.scanned} scanned.`
                  : `Showing the top ${stockRows.length} of ${coverage.qualified} ${coverage.qualified === 1 ? 'company that clears' : 'companies that clear'} it, scored against all ${coverage.scanned} companies in the universe.`}
              </p>
              {coverage.excluded > 0 && (
                <p>{coverage.excluded} of {coverage.scanned} did not clear the gate.
                  {coverage.binding ? ` Most common reason: ${coverage.binding.reason} (${coverage.binding.count}).` : ''}</p>
              )}
            </Container>
          )}
          {!modelActive && poolRows.length > DISPLAY_LIMIT && (
            <p data-testid="pool-display-cap">Showing the top {DISPLAY_LIMIT} of {poolRows.length} matching the current filters, sorted as shown above.</p>
          )}

          <div data-testid="research-pool">
            {poolRows.slice(0, modelActive ? poolRows.length : DISPLAY_LIMIT).map((row, index) => {
              const timing = entryTiming(row)
              const expanded = expandedTickers.has(row.ticker)
              const held = heldTickers.has(row.ticker)
              const watched = watchlist.isWatched(row.ticker)
              return (
                <Container key={row.ticker} {...cap(IDS.mobileCard)} data-testid={`research-row-${row.ticker}`}>
                  <div className="research-row-head">
                    <span {...cap(IDS.columnRank)}>#{index + 1}</span>
                    <strong>{row.ticker}</strong>
                    <span>{row.name}</span>
                    <span>{row.is_etf ? 'ETF' : 'Stock'}</span>
                    <span {...cap(IDS.columnStance)}>{row.stance || '–'}</span>
                    <span {...cap(IDS.columnRating)}>{row.rating == null ? '–' : (row.rating > 0 ? `+${row.rating}` : row.rating)}</span>
                    {row.modelScore?.cap ? (
                      <span {...cap(IDS.thinEvidenceChip)} title={row.modelScore.cap.reason}>{row.modelScore.cap.label || 'Thesis risk'}</span>
                    ) : row.modelScore && row.modelScore.confidencePercent < 50 ? (
                      <span {...cap(IDS.thinEvidenceChip)}
                        title={`This model resolved ${row.modelScore.confidencePercent}% of the inputs it reads.`}>Thin evidence</span>
                    ) : null}
                    {isLightData(row) && (
                      <span {...cap(IDS.lightDataChip)} title="Scored on the lighter universe data set: price/valuation/analyst inputs only.">Lighter data</span>
                    )}
                  </div>

                  {modelActive && row.modelScore && (
                    <p {...cap(IDS.columnModelScoreWhy)}>{Math.round(row.modelScore.score)} — {modelReason(row) || '–'}</p>
                  )}

                  <dl className="research-row-metrics">
                    <div><dt>Fundamentals</dt><dd {...cap(IDS.columnFundamentals)}>{row.components?.fundamentals == null ? '–' : Math.round(row.components.fundamentals)}</dd></div>
                    <div><dt>20-day return</dt><dd {...cap(IDS.columnReturn20d)}>{fmtPct(row.technical_detail?.return_20d)}</dd></div>
                    <div><dt>Data coverage</dt><dd {...cap(IDS.columnConfidence)}>{finite(row.data_coverage) ? `${Math.round(row.data_coverage * 100)}%` : '–'}</dd></div>
                    <div><dt>% of my portfolio</dt><dd {...cap(IDS.columnPctPortfolio)}>{row.portfolioPct == null ? '–' : `${row.portfolioPct.toFixed(1)}%`}</dd></div>
                  </dl>

                  <div {...cap(IDS.columnTiming)}>
                    {timing?.verdict === 'set_low_alert' ? (
                      <>
                        <Field Control={Control} capId={IDS.setLowAlert} disabled={alertingTicker === row.ticker}
                          onClick={() => handleSetLowAlert(row, timing)} title={timing.reason}>
                          {alertingTicker === row.ticker ? 'Setting alert…' : `Set Low Alert · $${timing.alertPrice.toFixed(2)}`}
                        </Field>
                        {alertStatuses[row.ticker] && (
                          <span {...cap(IDS.buyAlertStatus)} role="status">{alertStatuses[row.ticker].message}</span>
                        )}
                      </>
                    ) : timing ? <span title={timing.reason}>{timing.label}</span> : <span>–</span>}
                  </div>

                  {row.modelScore?.droppedComponents?.length > 0 && (
                    <p {...cap(IDS.modelWhyNa)}>
                      Not applicable to this company, weight redistributed rather than scored zero:{' '}
                      {row.modelScore.droppedComponents.map((component) => component.label.toLowerCase()).join(', ')}.
                    </p>
                  )}
                  {row.modelScore?.cap && (
                    <p {...cap(IDS.scoreCapped)}>Score capped at {row.modelScore.cap.limit}: {row.modelScore.cap.reason}.</p>
                  )}
                  <small {...cap(IDS.asOfLine)}>{isLightData(row)
                    ? 'Scored on the lighter universe data set – no published price history for this row'
                    : `As of ${row.history?.dates?.at(-1) || row.data_as_of || 'the latest published close'}`}</small>

                  <div className="research-row-actions">
                    <Field Control={Control} capId={IDS.watchlistToggle} pressed={watched}
                      onClick={() => (watched ? watchlist.removeTicker(row.ticker) : watchlist.addTicker(row.ticker))}>
                      {watched ? 'Watching' : 'Watch'}
                    </Field>
                    <Field Control={Control} capId={IDS.buy100} disabled={held || buyingTicker === row.ticker || !row.price}
                      onClick={() => handleBuy(row)}>
                      {held ? 'Bought' : buyingTicker === row.ticker ? 'Adding…' : 'Buy $100'}
                    </Field>
                    <Field Control={Control} capId={IDS.openStockDetail} onClick={() => openDetail(row)}>Open research</Field>
                    <Field Control={Control} capId={IDS.secondaryMetricsToggle} pressed={expanded} aria-expanded={expanded}
                      onClick={() => toggleExpanded(row.ticker)}>
                      {expanded ? 'Hide secondary metrics' : 'Show secondary metrics'}
                    </Field>
                  </div>
                  {buyStatuses[row.ticker] && <p {...cap(IDS.buyAlertStatus)} role="status">{buyStatuses[row.ticker].message}</p>}

                  {expanded && (
                    <div className="research-row-expanded">
                      <div><strong>Strengths</strong><ul>{(row.strengths || []).map((item) => <li key={item}>{item}</li>)}</ul></div>
                      <div><strong>Risks &amp; gaps</strong><ul>{(row.risks || []).map((item) => <li key={item}>{item}</li>)}</ul></div>
                    </div>
                  )}
                </Container>
              )
            })}
          </div>

          {poolRows.length === 0 && (
            modelActive ? (
              assetType === 'etf' ? (
                <div {...cap(IDS.etfModelMismatch)} role="status">
                  {RANKING_MODELS[sort].label} is a per-security model – it reads fundamentals, news, insider and theme data a fund does not report. Switch the asset filter back to stocks, or sort by published score to rank ETFs.
                </div>
              ) : (
                <div {...cap(IDS.modelGateNotCleared)} role="status">
                  No company clears the {RANKING_MODELS[sort].label} gate under these filters. The coverage panel above counts why.
                </div>
              )
            ) : (
              <div {...cap(IDS.noFilterMatch)} role="status">No companies match those filters.</div>
            )
          )}

          {openRow && (
            <Container data-testid="research-detail">
              <button type="button" onClick={() => setOpenTicker(null)} aria-label="Close research detail">Close</button>
              <h2>{openRow.ticker} — {openRow.name}</h2>
              <p>
                {openRow.price != null ? `$${Number(openRow.price).toFixed(2)}` : 'Price unavailable'} · Score {openRow.score ?? '–'} · {openRow.stance || '–'}
              </p>
              <div><strong>Strengths</strong><ul>{(openRow.strengths || []).map((item) => <li key={item}>{item}</li>)}</ul></div>
              <div><strong>Risks &amp; gaps</strong><ul>{(openRow.risks || []).map((item) => <li key={item}>{item}</li>)}</ul></div>
            </Container>
          )}

          <section className="allocation-planner" aria-labelledby="research-planner-title">
            <h2 id="research-planner-title">Split available funds by rank</h2>
            <Container {...cap(IDS.plannerFunds)}>
              <label>
                <span>Available funds</span>
                <input type="number" min="0" step="1" inputMode="decimal" placeholder="Available funds"
                  value={plannerFunds} onChange={(event) => setParam('funds', event.target.value)} />
              </label>
            </Container>
            <label {...cap(IDS.plannerDoubleDown)}>
              <input type="checkbox" checked={doubleDown} onChange={(event) => setParam('doubleDown', event.target.checked ? null : '0')} />
              <span>Double down on positions I already own</span>
            </label>
            <p {...cap(IDS.plannerNotes)}>
              Weighted by {modelActive ? `${RANKING_MODELS[sort].label.toLowerCase()} model score` : 'published score'} against
              the top {Math.min(allocationCandidates.length, 8)} {assetType === 'etf' ? 'ETFs' : 'stocks'} in the current sort
              and filters{doubleDown ? '' : ' that you don\'t already own'}. This is not an even split.
            </p>
            {allocation.available ? (
              <div {...cap(IDS.plannerBucketList)}>
                {allocation.buckets.map((bucket) => (
                  <div key={bucket.ticker} className="allocation-bucket-row">
                    <strong>{bucket.ticker}</strong>
                    <span>{bucket.isEtf ? 'ETF' : 'Stock'} · score {Math.round(bucket.score)}</span>
                    <span>${bucket.amount.toFixed(2)} · {bucket.weightPct.toFixed(1)}%{bucket.shares != null ? ` · ${bucket.shares.toFixed(4)} sh` : ''}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p>{plannerFunds ? allocation.reason : 'Enter available funds to see a suggested bucket split.'}</p>
            )}
          </section>

          <div {...cap(IDS.pageDisclaimer)}>
            Research covers {(report?.research || []).length} fully published companies plus {(report?.screen_universe || []).length} more
            scored on a lighter data set ({stockResearch.length} total), and {etfData?.etfs?.length || 0} ETFs. Each ranking model scores
            against industry or sector peers, drops components a company cannot legitimately report rather than scoring them zero, shrinks
            the result by how much of its own input set resolved, and publishes the top {MODEL_LIMIT}. The weights are frozen starting
            priors, not measured optima. The -5..+5 rating is a percentile read of the published score against its own pool, shrunk toward
            0 by data coverage. "Buy $100" records a fractional-share portfolio entry at the displayed current price and today's date; it
            does not place a brokerage order. Rankings do not imply suitability or portfolio allocation.
          </div>
        </>
      )}

      {view === 'watchlist' && (
        !currentUser ? (
          <div {...cap(IDS.watchlistSignedOut)}>
            <p>{authError || 'Firebase is connecting to your solo workspace.'}</p>
            <button type="button" onClick={retryAuth}>Reconnect Firebase</button>
          </div>
        ) : (
          <div data-testid="watchlist-view">
            <Container {...cap(IDS.watchlistAddTicker)}>
              <label>
                <span>Ticker symbol</span>
                <input autoCapitalize="characters" placeholder="AAPL" value={watchInput}
                  onChange={(event) => setWatchInput(event.target.value)}
                  onKeyDown={(event) => event.key === 'Enter' && addWatchTicker()} />
              </label>
              <button type="button" onClick={addWatchTicker}>Add ticker</button>
            </Container>

            <Container {...cap(IDS.watchlistSizing)}>
              <label>
                <span>Investable budget</span>
                <input type="number" min="0" step="100" inputMode="decimal" placeholder="10000"
                  value={budget} onChange={(event) => setSizing(event.target.value, maxPositionPct)} />
              </label>
              <label>
                <span>Maximum per stock</span>
                <input type="number" min="0.1" max="100" step="0.5" inputMode="decimal"
                  value={maxPositionPct} onChange={(event) => setSizing(budget, event.target.value)} />
              </label>
            </Container>
            <p {...cap(IDS.watchlistSizingNote)}>
              Illustrative position sizing based on this budget and cap. Only a low-confidence block or published Sell forces $0.
            </p>

            <div {...cap(IDS.watchlistLensChips)} role="group" aria-label="Filter by research screen">
              <button type="button" aria-pressed={activeLenses.length === 0} onClick={() => setWatchlistFilterSort([], wsort)}>All</button>
              {LENS_KEYS.map((key) => (
                <button key={key} type="button" aria-pressed={activeLenses.includes(key)}
                  onClick={() => setWatchlistFilterSort(
                    activeLenses.includes(key) ? activeLenses.filter((item) => item !== key) : [...activeLenses, key],
                    wsort,
                  )}>
                  {STRATEGY_LENSES[key].label} ({lensMatches[key].size})
                </button>
              ))}
            </div>

            <Field Control={Control} as="select" capId={IDS.watchlistSort} aria-label="Sort watchlist"
              value={wsort} onChange={(event) => setWatchlistFilterSort(activeLenses, event.target.value)}>
              {Object.keys(WATCHLIST_SORTS).map((key) => <option key={key} value={key}>Sort: {WATCHLIST_SORTS[key][0]}</option>)}
            </Field>

            {dipAlertNotice && <div role="status">{dipAlertNotice.message}</div>}

            <div data-testid="watchlist-items">
              {sortedWatchItems.map(({ item, ticker, row, guidance, matchedLensKeys }) => {
                const suggested = row ? suggestPriceTargets(row) : { dipBuy: null, goodBuy: null }
                return (
                  <Container key={ticker} data-testid={`watchlist-row-${ticker}`}>
                    <div className="watchlist-card-head">
                      <strong>{ticker}</strong><span>{row?.name || 'Not in published research'}</span>
                      <button type="button" onClick={() => watchlist.removeTicker(ticker)} aria-label={`Remove ${ticker} from watchlist`}>Remove</button>
                    </div>
                    {matchedLensKeys.map((key) => (
                      <span key={key} title={lensReason(lensMatches[key].get(ticker), key) || STRATEGY_LENSES[key].label}>
                        {STRATEGY_LENSES[key].label}
                      </span>
                    ))}
                    {row ? (
                      <>
                        <div className="watchlist-stats">
                          <span>Price {row.price ? `$${row.price.toFixed(2)}` : '–'}</span>
                          <span>Setup {guidance.setupScore.toFixed(0)}</span>
                          <span>Score {row.score}</span>
                          <span>Upside {guidance.targetUpside == null ? '–' : `${guidance.targetUpside >= 0 ? '+' : ''}${guidance.targetUpside.toFixed(1)}%`}</span>
                          <span>Max size {guidance.allocation > 0 ? `$${guidance.allocation.toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '$0'}</span>
                        </div>
                        <Container {...cap(IDS.priceTargetEditor)}>
                          <PriceTargetEditor item={item} suggested={suggested}
                            onSave={(updates) => watchlist.updateTargets(ticker, updates)}
                            onCreateAlert={(dipPrice) => handleCreateDipAlert(item, dipPrice)}
                            alertBusy={dipAlertBusyTicker === ticker} />
                        </Container>
                      </>
                    ) : (
                      <div {...cap(IDS.watchlistNoQuote)} role="status">
                        This ticker is saved, but no current quote or research record was published. It will populate after a successful pipeline refresh that covers it.
                      </div>
                    )}
                  </Container>
                )
              })}
            </div>

            {!watchTickers.length && (
              <div {...cap(IDS.watchlistEmpty)} role="status">
                Your watchlist is empty. Add a ticker above to start a focused research list.
              </div>
            )}
            {Boolean(watchTickers.length) && !sortedWatchItems.length && (
              <div {...cap(IDS.watchlistNoFilterMatch)} role="status">
                <p>No saved names match this filter</p>
                <button type="button" onClick={() => setWatchlistFilterSort([], wsort)}>Clear filters</button>
              </div>
            )}
          </div>
        )
      )}
    </div>
  )
}
