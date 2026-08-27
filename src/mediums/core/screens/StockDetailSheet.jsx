import { useId, useState } from 'react'
import { useMedium } from '../MediumContext.jsx'
import { useRenderer } from '../useRenderer.js'
import { cap } from '../capability.js'
import { STOCK_DETAIL_IDS as IDS } from './capabilityIds.js'
import { useStockDetail } from '../useStockDetail.js'
import { canonicalArtifactState, canonicalMetricState, confidenceOf } from '../states.js'
import { useData } from '../../../lib/useData.js'
import { useDialog } from '../../../lib/useDialog.js'
import useBodyScrollLock from '../../../lib/useBodyScrollLock.js'
import { useWatchlist } from '../../../lib/useWatchlist.js'
import { getRecommendation } from '../../../lib/recommendation.js'
import { bullBearScore } from '../../../lib/bullBearScore.js'
import { fixedBasisAlternative, positionGrowthSeries } from '../../../lib/portfolioPerformance.js'
import { watchlistGuidance } from '../../../lib/watchlistGuidance.js'
import { dipWatch } from '../../../lib/dipWatch.js'
import { mergeResearchStock } from '../../../lib/mergeResearchStock.js'
import { buildStockCopyText } from '../../../lib/stockCopyText.js'
import { resolvedMetricSections } from '../../../lib/resolvedMetricSections.js'
import { parseEtfComparison, comparisonLines } from '../../../lib/etfComparison.js'

/**
 * The Stock Detail Sheet — reference call target for every `openStockDetail(ticker)` caller
 * across the app (CAPABILITY-LEDGER.md §14, opened from 7 routes). Takes NO props: it reads
 * `?ticker=` itself via `useStockDetail()`, so integrating it anywhere is `<StockDetailSheet />`
 * mounted once near a screen's root plus a button/row that calls `openStockDetail(ticker)`.
 *
 * Ground-up rebuild against `src/components/StockDetailModal.jsx` (the Classic implementation)
 * as a DATA/LOGIC reference only — nothing here imports from `src/components/*` (ESLint-blocked
 * for anything outside `src/mediums/classic/**`). Markup is fresh, built through
 * `manifest.components.Container` and the shared chart-renderer contract instead of Classic's
 * own CSS-specific DOM.
 */

// --- Small pure helpers, replicated from StockDetailModal.jsx (kept inline — each is a handful
// of lines and none is reused anywhere else in core/) --------------------------------------

const signed = (value, digits = 1, suffix = '%') =>
  value == null ? '–' : `${value > 0 ? '+' : ''}${value.toFixed(digits)}${suffix}`
const signedPoints = (value) => (value == null ? '–' : `${value >= 0 ? '+' : '−'}${Math.abs(value).toFixed(2)}`)
const moveColor = (value) => (value == null ? undefined : value >= 0 ? 'var(--pos)' : 'var(--neg)')

/**
 * Whether a coverage measurement exists at all — deliberately stricter than `Number(value)`,
 * which maps both null and '' to a perfectly finite 0. An unmeasured `data_coverage` renders
 * "Not measured — this is not a reading of zero", never a coverage of 0%. Mirrors
 * StockDetailModal.jsx's own `isMeasuredCoverage` exactly; the two must agree.
 */
function isMeasuredCoverage(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

const themeExposureScore = (entry) =>
  Number(entry?.theme_exposure_score ?? entry?.exposure_score ?? entry?.score)
const themeExposureName = (entry) =>
  entry?.display_name || entry?.theme_id || entry?.theme || entry?.name

function primaryTheme(stock) {
  const themes = Array.isArray(stock.theme_exposure) ? stock.theme_exposure : []
  if (!themes.length) return null
  return themes.slice().sort((left, right) =>
    (themeExposureScore(right) || 0) - (themeExposureScore(left) || 0))[0]
}

function ordinal(value) {
  const rounded = Math.round(value)
  const remainder = rounded % 100
  if (remainder >= 11 && remainder <= 13) return `${rounded}th`
  return `${rounded}${{ 1: 'st', 2: 'nd', 3: 'rd' }[rounded % 10] || 'th'}`
}

// Section-score radar entries — replicated from ResearchRadarChart.jsx's own `radarEntries()`,
// which deliberately reads only `fundamental_categories` (see that file's own comment on why
// `analysis_v2.structural.categories` is a different model's reading and must not be mixed in).
function radarEntries(stock) {
  const source = stock?.fundamental_categories || stock?.analysis_v2?.structural?.categories || stock?.scores || {}
  return Object.entries(source)
    .filter(([, value]) => Number.isFinite(Number(value)))
    .slice(0, 8)
    .map(([key, value]) => ({
      key, label: key.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()),
      value: Math.max(0, Math.min(100, Number(value))),
    }))
}

const ETF_STANCE_BANDS = [[80, 'Attractive'], [70, 'Promising'], [55, 'Neutral'], [-Infinity, 'Caution']]
const etfStance = (score) => (ETF_STANCE_BANDS.find(([floor]) => score >= floor) || ETF_STANCE_BANDS.at(-1))[1]

// A row opened from an ETF ticker never appears in report.json's research/portfolio_coverage/
// screen_universe (those are stocks only) — it lives in etfs.json instead, shaped completely
// differently. Normalized the same way ResearchScreen.jsx's own (private, unexported)
// `normalizeEtf` does, so the rest of this sheet can treat a normalized ETF row exactly like a
// stock row: score, stance, components, technical_detail, strengths, risks.
function normalizeEtfRow(row) {
  const score = row.scores?.overall ?? row.quality_score ?? null
  return {
    ...row,
    is_etf: true,
    asset_type: 'etf',
    score,
    stance: Number.isFinite(score) ? etfStance(score) : null,
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

function findInReport(report, ticker) {
  return report?.research?.find((row) => row.ticker === ticker)
    || report?.portfolio_coverage?.find((row) => row.ticker === ticker)
    || report?.screen_universe?.find((row) => row.ticker === ticker)
    || null
}

const CONGRESS_FLAG_LABELS = {
  EXTRAORDINARY_BUY: 'First trade in a small, unfamiliar company',
  CLUSTER_TRADE: '3+ representatives, 14-day span',
  BUY_SELL_FLIP: 'Round trip within 60 days',
}

// --- Small presentational pieces ------------------------------------------------------------

function Kpi({ label, value, note, color }) {
  return (
    <div>
      <div>{label}</div>
      <div style={color ? { color, fontWeight: 600 } : { fontWeight: 600 }}>{value}</div>
      {note && <div><small>{note}</small></div>}
    </div>
  )
}

function CopyDataButton({ stock, insideInfo }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(buildStockCopyText(stock, insideInfo))
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard access can be denied (permissions, an insecure context) — nothing to
      // recover into beyond leaving the button in its normal state.
    }
  }
  return (
    <button type="button" {...cap(IDS.copyData)} onClick={handleCopy}
      aria-label={`Copy ${stock.ticker} research data: metrics, insider activity, and disclosed positioning`}
      title="Copy all data: metrics, insider activity, and disclosed positioning">
      Copy data
      <span role="status" style={{ marginLeft: '0.4em' }}>{copied ? 'Copied' : ''}</span>
    </button>
  )
}

export default function StockDetailSheet() {
  const { ticker, closeStockDetail } = useStockDetail()
  const manifest = useMedium()
  const renderer = useRenderer()
  const Container = manifest.components?.Container || 'section'
  const TabsComponent = manifest.components?.Tabs || null
  const watchlist = useWatchlist()
  const titleId = useId()
  const [tab, setTab] = useState('evidence')
  const [showMore, setShowMore] = useState(false)
  const [variant, setVariant] = useState('champion')

  const open = Boolean(ticker)

  // report.json first — the base row for the overwhelming majority of tickers. etfs.json is
  // only reached for once report.json has resolved and the ticker genuinely isn't a stock row
  // (ETFs are a completely separate file/shape, never mixed into report.json's stock lists).
  const { data: report, loading: reportLoading } = useData(open ? 'report.json' : null)
  const stockRow = report ? findInReport(report, ticker) : null
  const needsEtfLookup = open && Boolean(report) && !reportLoading && !stockRow
  const { data: etfsData, loading: etfsLoading } = useData(needsEtfLookup ? 'etfs.json' : null)
  const etfRow = etfsData?.etfs?.find((row) => row.ticker === ticker) || null
  const suppliedStock = stockRow || (etfRow ? normalizeEtfRow(etfRow) : null)
  const loading = open && (reportLoading || (needsEtfLookup && etfsLoading))
  const notFound = open && !loading && !suppliedStock

  // Lazy-upgrade to the deep advisor.json snapshot only when the lighter row lacks
  // explainability — same condition StockDetailModal.jsx itself gates on.
  const { data: fullResearch } = useData(suppliedStock && !suppliedStock.explainability ? 'advisor.json' : null)
  const { data: insideInformation } = useData(suppliedStock ? 'screens/inside-information.json' : null)
  // Computed off `suppliedStock` (available before the loading/not-found early return below),
  // not the post-merge `stock` — this useData call must run in the same position on every
  // render, so it cannot sit after a conditional early return. `suppliedStock` already carries
  // is_etf/asset_type/sector from either the report.json row or normalizeEtfRow(), so the ETF
  // determination is identical either way.
  const preliminaryIsEtf = suppliedStock
    ? (suppliedStock.is_etf || String(suppliedStock.asset_type || '').toLowerCase() === 'etf' || suppliedStock.sector === 'ETF')
    : false
  const { data: etfComparisonRaw } = useData(preliminaryIsEtf ? `etf/${suppliedStock?.ticker || ticker}.json` : null)

  useBodyScrollLock(open)
  const dialogRef = useDialog(open, closeStockDetail)

  if (!open) return null

  const stock = mergeResearchStock(suppliedStock, fullResearch)

  if (loading || notFound) {
    return (
      <div role="presentation" onPointerDown={(event) => { if (event.target === event.currentTarget) closeStockDetail() }}
        style={{ position: 'fixed', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.4)', zIndex: 1000 }}>
        <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex="-1"
          {...cap(IDS.dialogShell)} style={{ background: 'var(--surface, #fff)', padding: '2rem', maxWidth: '32rem' }}>
          <h2 id={titleId}>{ticker}</h2>
          <p role="status">{loading ? 'Loading research…' : `No published research found for ${ticker}.`}</p>
          <button type="button" {...cap(IDS.close)} onClick={closeStockDetail} aria-label="Close stock research">Close</button>
        </div>
      </div>
    )
  }

  const isEtf = stock.is_etf || String(stock.asset_type || '').toLowerCase() === 'etf' || stock.sector === 'ETF'
  const technical = stock.technical_detail || {}
  const categories = stock.fundamental_categories || {}
  const thesis = bullBearScore(stock)
  const analysis = stock.analysis_v2
  const structural = analysis?.structural
  const shadow = stock.recommendation_v2
  const percentile = stock.valuation_percentile
  const recommendation = getRecommendation(stock)
  const setupGuidance = watchlistGuidance(stock, null, null, {})
  const score = stock.score ?? structural?.effective_score
  const coverageSource = stock.data_coverage ?? structural?.coverage ?? stock.score_variants?.champion?.data_coverage
  const dataCoverage = isMeasuredCoverage(coverageSource) ? coverageSource : null
  const theme = primaryTheme(stock)
  const themeName = themeExposureName(theme) || 'No material theme identified'
  const themeScore = theme ? themeExposureScore(theme) : undefined
  const otherThemes = (Array.isArray(stock.theme_exposure) ? stock.theme_exposure : [])
    .filter((entry) => entry !== theme && Number.isFinite(themeExposureScore(entry)))
  const dataAsOf = stock.generated_at || stock.recommendation_v2?.generated_at || fullResearch?.generated_at
  const insideInfo = insideInformation?.by_ticker?.[stock.ticker]
  const watched = watchlist.isWatched(stock.ticker)

  // Stage 0 has no caller-supplied `position`/`benchmarkHistory` — nothing yet passes
  // position context through the URL (the 7 call sites all open by ticker only). Both code
  // paths are built exactly as StockDetailModal.jsx builds them so a future position-aware
  // caller only has to supply the data, not new logic — see the TODO below.
  // TODO(position-context): once a call site (e.g. Portfolio's held-position row) has a
  // concrete mechanism for passing `position`/`benchmarkHistory` through to this
  // no-props sheet (a `?position=` scheme was deliberately NOT invented here — see the final
  // report), wire `position`/`benchmarkHistory` in and this scoped branch activates itself.
  const position = null
  const benchmarkHistory = report?.benchmark_history || null
  const basis = stock.hypothetical?.basis || 500
  const scopedSeries = position?.purchaseDate ? positionGrowthSeries(position, stock.history, benchmarkHistory, basis) : null
  const scopedHypothetical = position?.purchaseDate ? fixedBasisAlternative(position, stock.history, benchmarkHistory, basis) : null
  const hypothetical = scopedHypothetical ? {
    basis,
    stock_value: scopedHypothetical.stockValue,
    benchmark_value: scopedHypothetical.benchmarkValue,
    stock_return_pct: scopedHypothetical.stockReturnPct,
    benchmark_return_pct: scopedHypothetical.benchmarkReturnPct,
    dollars_ahead: scopedHypothetical.dollarsAhead,
    excess_return_pct: (scopedHypothetical.dollarsAhead / basis) * 100,
  } : stock.hypothetical

  // Every medium's `line()` renders exactly one series per call (never a multi-line chart) —
  // confirmed by reading gallery/chalkboard/classic's own implementations, none of which accept
  // more than one named line. Two lines on one comparison means two `line()` calls as small
  // multiples inside one labeled container, the same pattern PortfolioScreen.jsx's
  // InsightsView already uses for "the account, then each index" — never a fabricated
  // multi-series prop shape the contract doesn't support.
  const stockGrowthDates = scopedSeries ? scopedSeries.dates : stock.history?.dates
  const stockGrowthValues = scopedSeries ? scopedSeries.stock : stock.history?.growth
  const benchmarkGrowthDates = scopedSeries ? scopedSeries.dates : benchmarkHistory?.dates
  const benchmarkGrowthValues = scopedSeries ? scopedSeries.benchmark : benchmarkHistory?.growth
  const stockLinePoints = (stockGrowthDates && stockGrowthValues)
    ? stockGrowthDates.map((date, index) => ({ x: date, y: stockGrowthValues[index] })) : []
  const benchmarkLinePoints = (benchmarkGrowthDates && benchmarkGrowthValues)
    ? benchmarkGrowthDates.map((date, index) => ({ x: date, y: benchmarkGrowthValues[index] })) : []

  const established = canonicalArtifactState({ status: 'success' })
  const confidence = confidenceOf({ confidence: dataCoverage })

  const explainability = stock.explainability
  const attribution = explainability?.attribution?.[variant]
  const explainMetrics = explainability?.metrics?.[variant] || []
  const waterfallLines = attribution ? [
    ...(attribution.evidence || []),
    { key: 'confidence', label: 'confidence shrinkage', points: attribution.confidence_shrinkage_points },
    ...(attribution.modifiers || []),
  ].filter((line) => line.key !== 'score_rounding' || Math.abs(line.points || 0) >= 0.01) : []
  const waterfallValues = attribution ? [attribution.base, ...waterfallLines.map((line) => line.points || 0)] : []
  const reconciledScore = attribution?.final_score
  const divergence = (typeof reconciledScore === 'number' && typeof stock.score === 'number'
    && Math.abs(reconciledScore - stock.score) >= 0.05) ? reconciledScore - stock.score : null

  const scoreHistory = explainability?.score_history
  const historyState = canonicalMetricState(scoreHistory ? {
    status: scoreHistory.status === 'available' ? 'ready' : 'accumulating',
    observations: scoreHistory.stored_months,
    required_observations: scoreHistory.required_months,
    status_message: `${scoreHistory.stored_months ?? 0} of ${scoreHistory.required_months ?? 6} stored months`,
  } : null)
  const historyPoints = (scoreHistory?.points || []).filter((point) => Number.isFinite(point.champion_score))

  const profileValues = radarEntries(stock).map((entry) => ({ label: entry.label, value: entry.value }))
  const factorBars = stock.explainability?.factor_bars || {}
  const factorBarEntries = Object.entries(factorBars)

  let etfComparison = null
  let etfComparisonError = null
  if (etfComparisonRaw) {
    try { etfComparison = parseEtfComparison(etfComparisonRaw) } catch (parseError) { etfComparisonError = parseError }
  }

  const TABS = [
    ['evidence', 'Evidence'],
    ['metrics', 'All metrics'],
    ['performance', 'Vs S&P 500'],
  ]

  return (
    <div role="presentation"
      onPointerDown={(event) => { if (event.target === event.currentTarget) closeStockDetail() }}
      style={{ position: 'fixed', inset: 0, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', background: 'rgba(0,0,0,0.45)', zIndex: 1000, overflowY: 'auto', padding: '2rem 1rem' }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex="-1"
        {...cap(IDS.dialogShell)}
        style={{ background: 'var(--surface, #fff)', color: 'var(--ink-primary, inherit)', maxWidth: '48rem', width: '100%', padding: '1.5rem' }}>

        <header style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
          <div style={{ flex: 1 }}>
            <span>Company research</span>
            <h2 id={titleId}>{stock.ticker}</h2>
            <p>{stock.name} · {stock.industry || stock.sector || 'Unclassified'}</p>
            {dataAsOf && <small {...cap(IDS.asOfLine)}>As of {String(dataAsOf).slice(0, 10)}</small>}
          </div>
          <CopyDataButton stock={stock} insideInfo={insideInfo} />
          <button type="button" {...cap(IDS.watchlistStar)} aria-pressed={watched}
            onClick={() => (watched ? watchlist.removeTicker(stock.ticker) : watchlist.addTicker(stock.ticker))}
            aria-label={watched ? `Remove ${stock.ticker} from watchlist` : `Add ${stock.ticker} to watchlist`}>
            {watched ? '★ Watching' : '☆ Watch'}
          </button>
          <button type="button" {...cap(IDS.close)} onClick={closeStockDetail} aria-label="Close stock research">Close</button>
        </header>

        <Container aria-label="Research summary" style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', marginTop: '1rem' }}>
          <div {...cap(IDS.researchScoreDial)}>
            {renderer && renderer.dial({
              metricId: `${stock.ticker}-research-score`,
              values: [Math.max(0, Math.min(100, Number(score) || 0))],
              domain: [0, 100],
              state: established,
              confidence,
              ariaLabel: isMeasuredCoverage(dataCoverage)
                ? `Research score ${Math.round(score || 0)} with ${Math.round(dataCoverage * 100)} percent data coverage`
                : `Research score ${Math.round(score || 0)}, data coverage not measured for this row`,
              width: 120, height: 120,
            })}
            <div><span>1 · Research score</span><strong>{Math.round(score || 0)}</strong></div>
          </div>
          <article {...cap(IDS.dataCoverage)}>
            <span>2 · Data coverage</span>
            <strong>{dataCoverage === null ? 'Not measured' : `${Math.round(dataCoverage * 100)}%`}</strong>
            <p>{dataCoverage === null
              ? 'No coverage measurement was published for this row, so there is nothing to report here yet. This is not a reading of zero.'
              : 'How much of the evidence this model intends to use actually resolved. Not a reliability score and not a probability of a price move.'}</p>
          </article>
          <article {...cap(IDS.guidance)}>
            <span>3 · Guidance</span>
            <strong>{recommendation?.action || 'Watch'}</strong>
            <p>{recommendation?.summary || 'Review the evidence before acting.'}</p>
          </article>
          <article {...cap(IDS.themeExposure)}>
            <span>4 · Theme exposure</span>
            <strong>{themeName}</strong>
            <p>
              {!Number.isFinite(themeScore)
                ? 'No material long-term theme exposure is published for this company.'
                : `${themeScore.toFixed(0)} out of 100. Theme exposure stays independent from the research score.`}
              {otherThemes.length > 0 && ` Also exposed to ${otherThemes.map(themeExposureName).join(', ')}.`}
            </p>
          </article>
        </Container>

        <button type="button" {...cap(IDS.evidenceExpander)} aria-expanded={showMore} onClick={() => setShowMore((value) => !value)}>
          {showMore ? 'Hide full research detail' : 'Explore the evidence'}
        </button>

        {showMore && <div>
          <div {...cap(IDS.actionGuidance)}>
            <h4>{recommendation?.action || 'Hold'}{recommendation?.suggestedTrimPct > 0 ? ` ${recommendation.suggestedTrimPct}%` : ''}</h4>
            <p>{recommendation?.summary}</p>
            {recommendation?.reasons?.length > 0 && <ul>{recommendation.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
            <small>
              Guidance never moves off Hold on price action alone, or on a single headline. Two of three independent
              factors — business fundamentals, market behaviour, and positioning/sentiment — have to agree first.
            </small>
          </div>

          {setupGuidance && <div {...cap(IDS.setupQualityBreakdown)} aria-label={`Setup quality ${setupGuidance.setupScore} out of 100`}>
            <div><span>Setup quality</span><strong>{setupGuidance.setupLabel}</strong><b>{setupGuidance.setupScore}/100</b></div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.5rem' }}>
              {setupGuidance.subscores.map((item) => (
                <div key={item.key}>
                  <span>{item.label}</span><b>{Math.round(item.value * 100)}</b>
                  <i aria-hidden="true" style={{ display: 'block', height: '4px', background: 'var(--rule-hairline, #ccc)' }}>
                    <em style={{ display: 'block', height: '100%', width: `${item.value * 100}%`, background: 'currentColor' }} />
                  </i>
                </div>
              ))}
            </div>
            {setupGuidance.hardBlocked && <p>{setupGuidance.hardBlockReasons.join('. ')}.</p>}
          </div>}

          {factorBarEntries.length > 0 && <div {...cap(IDS.factorBars)} aria-label="Research factor summary">
            {renderer && renderer.bar({
              metricId: `${stock.ticker}-factor-bars`,
              values: factorBarEntries.map(([, value]) => value ?? 0),
              state: established, confidence,
              ariaLabel: `Factor bars: ${factorBarEntries.map(([key, value]) => `${key} ${value == null ? 'N/A' : Math.round(value)}`).join(', ')}`,
              width: 280, height: 90,
            })}
            <dl>{factorBarEntries.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value == null ? 'N/A' : Math.round(value)}</dd></div>)}</dl>
          </div>}

          <Container {...cap(IDS.kpiGrid)} style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem' }}>
            <Kpi label="Current price" value={stock.price ? `$${stock.price.toFixed(2)}` : '–'} />
            <Kpi label="Market cap" value={stock.market_cap ? `$${(stock.market_cap / 1e9).toFixed(1)}B` : '–'} />
            <Kpi label="20-day move" value={signed(technical.return_20d)} color={moveColor(technical.return_20d)} />
            <Kpi label="1-year move" value={signed(technical.return_252d)} color={moveColor(technical.return_252d)} />
            {typeof stock.earnings_surprise === 'number' && (
              <Kpi label="Earnings vs. estimate" value={signed(stock.earnings_surprise)} color={moveColor(stock.earnings_surprise)}
                note="Recent quarters vs. expectations, newest weighted heaviest" />
            )}
          </Container>

          {(() => {
            const watch = dipWatch(stock)
            if (!watch) return null
            return (
              <div {...cap(IDS.dipWatchBadge)} aria-label="Buy-the-dip watch">
                <strong>{watch.status === 'near_floor' ? 'Near the floor' : watch.status === 'recovering' ? 'Recovering' : 'Still working lower'}</strong>
                <div><span>Floor (est. bottom)</span><b>${watch.floor.toFixed(2)}</b></div>
                <div><span>Recovery level</span><b>${watch.max.toFixed(2)}</b></div>
                <p>A reasonable pair of broker alerts: drops below ${watch.floor.toFixed(2)}, rises above ${watch.max.toFixed(2)}.</p>
              </div>
            )
          })()}

          {thesis && !analysis && (
            <section {...cap(IDS.bullBearThesisTrack)} aria-label={`Bull bear thesis score ${thesis.score} out of 10`}>
              <div>
                <span>Bull / bear thesis</span>
                <strong style={{ color: thesis.score === 5 ? 'var(--text-dim)' : moveColor(thesis.score - 5) }}>{thesis.score.toFixed(1)}</strong>
                <small>0 bearish · 5 neutral · 10 bullish</small>
              </div>
              <div aria-hidden="true" style={{ position: 'relative', height: '6px', background: 'var(--rule-hairline, #ccc)' }}>
                <span style={{
                  position: 'absolute', height: '100%', background: thesis.score >= 5 ? 'var(--pos)' : 'var(--neg)',
                  left: thesis.score >= 5 ? '50%' : `${thesis.score * 10}%`, width: `${Math.abs(thesis.score - 5) * 10}%`,
                }} />
              </div>
              <p>40% fundamentals · 30% price behavior · 20% news sentiment · 10% risk quality. {thesis.coverage}% of those inputs were available.</p>
            </section>
          )}

          {shadow && (() => {
            const company = shadow.company?.action || {}
            const position2 = shadow.position_action || {}
            const structuralLayer = shadow.company_structural_state || shadow.company?.structural || {}
            const timelinessLayer = shadow.company_timeliness_state || shadow.company?.timeliness || {}
            const layerText = (layer) => layer?.effective_score == null
              ? (layer?.unavailable_reason || 'No inputs resolved, so no score is published')
              : `${Math.round(layer.effective_score)} effective · ${Math.round((layer.evidence_weight_resolved || 0) * 100)}% of evidence weight resolved`
            return (
              <section {...cap(IDS.recommendationShadowPanel)} aria-label="Shadow recommendation policy comparison">
                <h3>Active guidance vs. shadow model</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem' }}>
                  <div><span>Active legacy policy</span><strong>{recommendation?.action || 'Unavailable'}</strong></div>
                  <div><span>Shadow company action</span><strong>{String(company.label || 'unavailable').replace(/_/g, ' ')}</strong></div>
                  <div><span>Shadow position action</span><strong>{String(position2.label || 'unavailable').replace(/_/g, ' ')}</strong></div>
                </div>
                <div>
                  <div><span>Business thesis</span><strong>{String(structuralLayer.classification || 'unavailable').replace(/_/g, ' ')}</strong><small>{layerText(structuralLayer)}</small></div>
                  <div><span>Earnings timeliness</span><strong>{String(timelinessLayer.classification || 'unavailable').replace(/_/g, ' ')}</strong><small>{layerText(timelinessLayer)}</small></div>
                  {(structuralLayer.evidence_weight_resolved != null && structuralLayer.evidence_weight_resolved < 0.4) && (
                    <small>Insufficient evidence: this layer cannot issue prescriptive company guidance.</small>
                  )}
                </div>
              </section>
            )
          })()}

          {percentile?.peer_context
            ? <p {...cap(IDS.peerValuation)} title={`${percentile.peer_count_with_valid_data} valid of ${percentile.peer_count_total} ${percentile.peer_group_label}. ${percentile.peer_context.ranked_quantity_note}`}>
                Valuation score {percentile.peer_context.tier_phrase} {percentile.peer_group_label} ({percentile.peer_context.tier_count} of {percentile.peer_context.peer_count_with_valid_data} names).
                Ranks this model&rsquo;s valuation composite, not a price multiple.
              </p>
            : percentile && <p {...cap(IDS.peerValuation)}>
                No peer comparison published: {percentile.peer_count_with_valid_data} valid {percentile.peer_group_label} peers, below the {percentile.minimum_peer_count} needed to rank against.
              </p>}
        </div>}

        {TabsComponent ? (
          <TabsComponent capId={IDS.tabs} items={TABS.map(([id, label]) => ({ id, label }))} active={tab} onSelect={setTab} />
        ) : (
          <div role="tablist" aria-label="Stock detail view" {...cap(IDS.tabs)}>
            {TABS.map(([key, label]) => (
              <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>{label}</button>
            ))}
          </div>
        )}

        {tab === 'evidence' && (
          <div>
            {!showMore && (
              <p {...cap(IDS.evidenceTabCollapsedNote)}>
                Score breakdowns, fundamental categories, the evidence list, modifiers, and insider activity are
                collapsed. Use &ldquo;Explore the evidence&rdquo; above to expand them.
              </p>
            )}
            {showMore && <>
              {explainability && (
                <Container {...cap(IDS.scoreExplainability)} aria-label="Score explainability">
                  <div role="group" aria-label="Score model variant">
                    {['champion', 'challenger'].map((key) => explainability.attribution?.[key] && (
                      <button key={key} type="button" aria-pressed={variant === key} onClick={() => setVariant(key)}>{key}</button>
                    ))}
                  </div>
                  <h3>Why the {variant} score is {attribution?.final_score?.toFixed(1) ?? 'unavailable'}</h3>

                  {profileValues.length >= 3 && renderer && (
                    <div aria-label="Research profile">
                      {renderer.profile({
                        metricId: `${stock.ticker}-profile`, values: profileValues,
                        state: established, confidence,
                        ariaLabel: `${stock.ticker} section scores: ${profileValues.map((v) => `${v.label} ${Math.round(v.value)} out of 100`).join(', ')}`,
                        width: 220, height: 160,
                      })}
                    </div>
                  )}

                  {stock.components && (
                    <div>
                      <div>Score components</div>
                      {Object.entries(stock.components).map(([key, value]) => (
                        <div key={key}>
                          <span>{key.replace(/_/g, ' ')}</span><b>{value == null ? '–' : Math.round(value)}</b>
                          <i aria-hidden="true" style={{ display: 'block', height: '4px', background: 'var(--rule-hairline, #ccc)' }}>
                            <em style={{ display: 'block', height: '100%', width: `${value || 0}%`, background: 'currentColor' }} />
                          </i>
                        </div>
                      ))}
                    </div>
                  )}

                  {attribution && (
                    <div {...cap(IDS.scoreWaterfall)}>
                      {renderer && renderer.waterfall({
                        metricId: `${stock.ticker}-waterfall-${variant}`, values: waterfallValues,
                        annotations: [{ label: 'Start from neutral', kind: 'event' }],
                        state: established, confidence,
                        ariaLabel: `Score waterfall: starts at ${attribution.base}, ends at ${attribution.final_score?.toFixed(1)}`,
                        width: 320, height: 110,
                      })}
                      <div><span>Start from neutral</span><strong>{attribution.base?.toFixed(1)}</strong></div>
                      <ul>
                        {waterfallLines.map((line) => (
                          <li key={line.key}>{line.label}: <b>{signedPoints(line.points)}</b></li>
                        ))}
                      </ul>
                      <div><span>Final score</span><strong>{attribution.final_score?.toFixed(1)}</strong></div>
                      {divergence !== null && (
                        <p {...cap(IDS.waterfallDivergence)}>
                          This reconciles the {variant} variant, not the published score of {stock.score?.toFixed(1)} — a difference
                          of {divergence > 0 ? '+' : ''}{divergence.toFixed(1)} points.
                        </p>
                      )}
                    </div>
                  )}

                  {explainMetrics.length > 0 && (
                    <ul {...cap(IDS.metricLevelEvidence)}>
                      {explainMetrics.map((metric) => {
                        const metricState = canonicalMetricState({
                          status: metric.sector_percentile == null ? 'accumulating' : 'ready',
                          status_message: 'peer percentile is accumulating',
                        })
                        const peer = metric.sector_percentile == null
                          ? metricState.reason
                          : `${ordinal(metric.sector_percentile)} percentile in ${metric.normalization_scope === 'sector' ? (stock.sector || 'its sector') : 'the full universe'}`
                        const own = !metric.own_history_status
                          ? 'own-history comparison does not apply'
                          : metric.own_history_percentile == null
                            ? `${metric.own_history_observations || 0} own-history observations accumulated`
                            : `${ordinal(metric.own_history_percentile)} percentile versus its own ${metric.own_history_years}-year history`
                        return <li key={metric.metric}>
                          <strong>{metric.label}</strong> {peer}, {own}, worth <b>{signedPoints(metric.final_point_contribution)} points</b>.
                        </li>
                      })}
                    </ul>
                  )}

                  <div {...cap(IDS.scoreHistory)}>
                    {historyPoints.length >= 2 ? (() => {
                      const width = 280; const height = 90
                      const plotted = historyPoints.map((point, index) => ({
                        ...point,
                        x: historyPoints.length === 1 ? 0 : (index / (historyPoints.length - 1)) * width,
                        y: height - (point.champion_score / 100) * height,
                      }))
                      const changes = plotted.filter((point, index) => index > 0 && point.champion_stance !== plotted[index - 1].champion_stance)
                      const driver = scoreHistory?.largest_category_driver
                      return <>
                        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Research score history">
                          <polyline points={plotted.map((point) => `${point.x},${point.y}`).join(' ')} fill="none" stroke="currentColor" strokeWidth="2" />
                          {changes.map((point) => <circle key={point.refresh_id} cx={point.x} cy={point.y} r="3" />)}
                        </svg>
                        <p>Score moved from {historyPoints[0].champion_score.toFixed(0)} to {historyPoints.at(-1).champion_score.toFixed(0)}
                          {driver ? `, driven mainly by ${driver.category.replace(/_/g, ' ')}` : ''}.</p>
                      </>
                    })() : (
                      <div role="status">
                        <strong>Score history is accumulating</strong>
                        <p>{historyState.reason || `${scoreHistory?.stored_months ?? 0} of ${scoreHistory?.required_months ?? 6} stored months.`} A chart appears
                          after enough distinct monthly snapshots exist.</p>
                      </div>
                    )}
                  </div>

                  {explainability.anomalies?.length > 0 && (
                    <ul {...cap(IDS.anomalies)} aria-label="Divergence flags">
                      {explainability.anomalies.map((flag) => <li key={flag.id} data-severity={flag.severity}>{flag.message}</li>)}
                    </ul>
                  )}
                </Container>
              )}

              {Object.keys(categories).length > 0 && (
                <Container {...cap(IDS.fundamentalCategories)}>
                  <div>Fundamental categories</div>
                  {Object.entries(categories).map(([key, value]) => {
                    const evidence = stock.fundamental_detail?.category_coverage?.[key]
                    return (
                      <div key={key}>
                        <span>{key.replace(/_/g, ' ')}</span><b>{value == null ? '–' : Math.round(value)}</b>
                        {evidence != null && evidence.metrics_applicable > 0 && (
                          <small>{evidence.metrics_used}/{evidence.metrics_applicable} metrics</small>
                        )}
                        <i aria-hidden="true" style={{ display: 'block', height: '4px', background: 'var(--rule-hairline, #ccc)' }}>
                          <em style={{ display: 'block', height: '100%', width: `${value || 0}%`, background: 'currentColor' }} />
                        </i>
                      </div>
                    )
                  })}
                </Container>
              )}

              <div {...cap(IDS.evidenceRisksLists)}>
                <div><b>Evidence for</b><ul>{(stock.strengths || []).map((item) => <li key={item}>{item}</li>)}</ul></div>
                <div><b>Risks / gaps</b><ul>{(stock.risks || []).map((item) => <li key={item}>{item}</li>)}</ul></div>
              </div>

              {(() => {
                const insider = stock.insider_activity
                const buys = insider?.recent_acquisitions || 0
                const sells = insider?.recent_disposals || 0
                // StockDetailModal.jsx's own InsiderActivityView gates on `insider.records_reviewed`,
                // a field that doesn't exist on the published shape (`pipeline/insider_signal.py`
                // publishes `transactions_reviewed` — confirmed against real advisor.json) — the
                // Classic panel never renders for any ticker as a result. Not a Classic file this
                // rebuild is allowed to touch, so left alone there; fixed here since this is fresh
                // markup, with the old field kept as a fallback for any older cached snapshot.
                const reviewed = insider?.transactions_reviewed ?? insider?.records_reviewed
                if (!reviewed || (!buys && !sells)) return null
                const buyPct = (buys / (buys + sells)) * 100
                return (
                  <div {...cap(IDS.insiderActivity)} aria-label="Insider buying versus selling">
                    <div>Insider activity: buys vs. sells</div>
                    <div aria-hidden="true" style={{ display: 'flex', height: '6px' }}>
                      <span style={{ width: `${buyPct}%`, background: 'var(--pos)' }} />
                      <span style={{ width: `${100 - buyPct}%`, background: 'var(--neg)' }} />
                    </div>
                    <span>{buys} buy{buys === 1 ? '' : 's'}</span> <span>{sells} sell{sells === 1 ? '' : 's'}</span>
                    <p>{reviewed} Form 4 filing{reviewed === 1 ? '' : 's'} reviewed. Routine, scheduled
                      trades are weighted down in the score; this grouping is raw counts, not the scored signal.</p>
                  </div>
                )
              })()}

              {insideInfo && (
                <div {...cap(IDS.insideInformationView)} aria-label="Notable institutional and Congressional activity">
                  <div>Disclosed positioning: notable activity</div>
                  {insideInfo.institutional_flag && (
                    <span>{insideInfo.institutional_flag === 'CLUSTER_ACCUMULATION' ? 'Curated managers accumulating' : 'Curated managers distributing'}</span>
                  )}
                  {(insideInfo.congress_flags || []).map((flag) => <span key={flag}>{CONGRESS_FLAG_LABELS[flag] || flag}</span>)}
                  <p>Combined score {insideInfo.score?.toFixed(2) ?? '–'}. <a href="/screens/inside-information">See the full Disclosed Positioning screen →</a></p>
                </div>
              )}

              {stock.modifiers?.notes?.length > 0 && (
                <div {...cap(IDS.scoreModifiers)}>
                  <div>Score modifiers ({signed(stock.modifiers.total, 1, ' pts')})</div>
                  <ul>{stock.modifiers.notes.map((note) => <li key={note}>{note}</li>)}</ul>
                  <p>Applied on top of the {stock.base_score ?? '–'} evidence score. Modifiers refine a ranking; they never outweigh the fundamentals behind it.</p>
                </div>
              )}
            </>}
          </div>
        )}

        {tab === 'metrics' && (
          <div {...cap(IDS.metricSections)}>
            {resolvedMetricSections(stock).map((section) => (
              <div key={section.title}>
                <h3>{section.title}</h3>
                {section.note && <p><small>{section.note}</small></p>}
                <dl>
                  {section.resolved.map((metric) => (
                    <div key={metric.key}>
                      <dt title={metric.why}>{metric.label}</dt>
                      <dd>{metric.format(metric.value)}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}
          </div>
        )}

        {tab === 'performance' && (
          <div>
            {isEtf ? (
              <div {...cap(IDS.etfComparisonPanel)}>
                {!etfComparisonRaw ? (
                  <div role="status">Loading ETF and benchmark history…</div>
                ) : etfComparisonError ? (
                  <div role="alert">ETF comparison could not be loaded: {etfComparisonError.message}</div>
                ) : !etfComparison || etfComparison.status === 'unavailable' ? (
                  <div role="status">Benchmark history unavailable. Reason: {etfComparison?.reason_code || 'EMPTY_RESPONSE'}</div>
                ) : (() => {
                  const rangeOrder = ['1M', '3M', '6M', 'YTD', '1Y', '3Y', '5Y', 'MAX']
                  const available = rangeOrder.filter((key) => etfComparison.chart_ranges?.[key])
                  const rangeKey = available.includes('1Y') ? '1Y' : available[0]
                  const range = etfComparison.chart_ranges?.[rangeKey]
                  const benchmark = etfComparison.benchmark || {}
                  const benchmarkLabel = benchmark.display_name || benchmark.ticker || 'Benchmark'
                  if (!range || range.status !== 'success' || range.series.length < 2) {
                    return <div role="status">Benchmark history unavailable for this range. Reason: {range?.reason_code || etfComparison.reason_code || 'NO_VALID_COMPARISON_SERIES'}</div>
                  }
                  const lines = comparisonLines(range, 'growth', stock.ticker, benchmarkLabel)
                  const metrics = range.metrics || {}
                  return <>
                    <h3>{benchmarkLabel}</h3>
                    {/* One `renderer.line()` call per line — see the note above `stockLinePoints`:
                        no medium's line() accepts more than one named series per call. */}
                    {renderer && lines.map((line) => (
                      <div key={line.key}>
                        <span>{line.label}</span>
                        {renderer.line({
                          metricId: `${stock.ticker}-etf-comparison-${line.key}`,
                          series: range.series.map((row) => ({ x: row.date, y: row[line.key] })),
                          state: established, confidence,
                          ariaLabel: `${line.label}: normalized growth of 100`,
                          width: 320, height: 110,
                        })}
                      </div>
                    ))}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.5rem' }}>
                      <Kpi label="Fund return" value={signed(metrics.fund_return, 2)} />
                      <Kpi label="Benchmark return" value={signed(metrics.benchmark_return, 2)} />
                      <Kpi label="Excess return" value={signed(metrics.excess_return, 2)} />
                      <Kpi label="Beta" value={metrics.beta != null ? metrics.beta.toFixed(2) : '–'} />
                      <Kpi label="Sharpe" value={metrics.sharpe != null ? metrics.sharpe.toFixed(2) : '–'} />
                      <Kpi label="Sortino" value={metrics.sortino != null ? metrics.sortino.toFixed(2) : '–'} />
                      <Kpi label="Max drawdown" value={signed(metrics.fund_max_drawdown, 2)} />
                    </div>
                    <p>{range.observation_count} overlapping sessions · {range.actual_start} to {range.end}</p>
                  </>
                })()}
              </div>
            ) : (
              <>
                <div {...cap(IDS.growthVsSpy)}>
                  <h3>{scopedSeries
                    ? `Growth of $${basis.toFixed(0)}: ${stock.ticker} vs the S&P 500 since you bought it (${position.purchaseDate})`
                    : `Growth of $${basis.toFixed(0)}: ${stock.ticker} vs the S&P 500`}</h3>
                  {/* Two lines, two `line()` calls (small multiples) — see the note above
                      `stockLinePoints`. */}
                  {renderer && stockLinePoints.length > 0 && (
                    <div>
                      <span>{stock.ticker}</span>
                      {renderer.line({
                        metricId: `${stock.ticker}-growth-vs-spy-stock`,
                        series: stockLinePoints,
                        state: established, confidence,
                        ariaLabel: `${stock.ticker} growth of $${basis.toFixed(0)}`,
                        annotations: typeof stock.earnings_surprise === 'number'
                          ? [{ kind: 'event', label: `Latest earnings vs. estimate: ${signed(stock.earnings_surprise)}` }]
                          : [],
                        width: 400, height: 140,
                      })}
                    </div>
                  )}
                  {renderer && benchmarkLinePoints.length > 0 && (
                    <div>
                      <span>S&amp;P 500 (SPY)</span>
                      {renderer.line({
                        metricId: `${stock.ticker}-growth-vs-spy-benchmark`,
                        series: benchmarkLinePoints,
                        state: established, confidence,
                        ariaLabel: `S&P 500 growth of $${basis.toFixed(0)}`,
                        annotations: [],
                        width: 400, height: 140,
                      })}
                    </div>
                  )}
                  <p>
                    {scopedSeries
                      ? 'Same dollars, invested the day you actually bought this position, in the stock and in the S&P 500. The gap is what picking this name earned or cost against simply buying the index from that same day.'
                      : 'Same dollars, same start date, same window. The gap is what picking this name earned or cost against simply buying the index.'}
                  </p>
                </div>

                {hypothetical && (
                  <Container {...cap(IDS.hypotheticalKpiGrid)} style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem' }}>
                    <Kpi label={`$${hypothetical.basis} in ${stock.ticker}`} value={`$${hypothetical.stock_value.toFixed(0)}`}
                      note={signed(hypothetical.stock_return_pct)} color={moveColor(hypothetical.stock_return_pct)} />
                    <Kpi label={`$${hypothetical.basis} in the S&P 500`} value={`$${hypothetical.benchmark_value.toFixed(0)}`}
                      note={signed(hypothetical.benchmark_return_pct)} color={moveColor(hypothetical.benchmark_return_pct)} />
                    <Kpi label="Dollars ahead" value={`${hypothetical.dollars_ahead >= 0 ? '+' : '−'}$${Math.abs(hypothetical.dollars_ahead).toFixed(0)}`}
                      note="versus the index" color={moveColor(hypothetical.dollars_ahead)} />
                    <Kpi label="Excess return" value={signed(hypothetical.excess_return_pct)} note="over the charted window" color={moveColor(hypothetical.excess_return_pct)} />
                  </Container>
                )}

                <Container {...cap(IDS.riskKpiGrid)} style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '0.75rem' }}>
                  <Kpi label="Max drawdown (1y)" value={signed(technical.max_drawdown_252d)} color={moveColor(technical.max_drawdown_252d)} />
                  <Kpi label="Volatility" value={technical.annualized_volatility ? `${technical.annualized_volatility.toFixed(0)}%` : '–'} />
                  <Kpi label="Vs SPY (20d)" value={signed(technical.relative_strength_20d)} color={moveColor(technical.relative_strength_20d)} />
                  <Kpi label="Beta" value={technical.beta != null ? technical.beta.toFixed(2) : '–'} />
                  <Kpi label="Accel vs market" value={signed(technical.relative_acceleration, 2, 'σ')}
                    note={technical.relative_acceleration_detail
                      ? `${signed(technical.relative_acceleration_detail.recent_excess_pct)} this quarter vs ${signed(technical.relative_acceleration_detail.prior_excess_pct)} last, market-adjusted`
                      : 'Needs two quarters of history against the index'}
                    color={moveColor(technical.relative_acceleration)} />
                </Container>
              </>
            )}
          </div>
        )}

        <div {...cap(IDS.footerDisclaimer)}>
          <strong>Disclaimer:</strong> Algorithmic research from quantitative metrics, not financial advice.
          Verify the filings and your own suitability before acting.
        </div>
      </div>
    </div>
  )
}
