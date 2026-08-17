import { useId, useState } from 'react'
import { Link } from 'react-router-dom'
import ActionGuidance from './ActionGuidance'
import GrowthChart from './GrowthChart'
import ETFComparisonPanel from './ETFComparisonPanel'
import MetricSections from './MetricSections'
import { getRecommendation } from '../lib/recommendation'
import { bullBearScore } from '../lib/bullBearScore'
import { fixedBasisAlternative, positionGrowthSeries } from '../lib/portfolioPerformance'
import AnalysisLayers from './AnalysisLayers'
import RecommendationShadowPanel from './RecommendationShadowPanel'
import DipWatchBadge from './DipWatchBadge'
import useBodyScrollLock from '../lib/useBodyScrollLock'
import { useDialog } from '../lib/useDialog.js'
import ResearchRadarChart from './ResearchRadarChart'
import Icon from './Icons'
import SetupQualityBreakdown from './SetupQualityBreakdown'
import { watchlistGuidance } from '../lib/watchlistGuidance'
import WatchlistToggleButton from './WatchlistToggleButton.jsx'
import { usePreferences } from '../lib/PreferencesContext.jsx'
import ScoreExplainability, { FactorBars } from './ScoreExplainability.jsx'
import { useData } from '../lib/useData.js'
import modelSettings from '../../pipeline/config/settings.json'

const TABS = [
  ['evidence', 'Evidence'],
  ['metrics', 'All metrics'],
  ['performance', 'Vs S&P 500'],
]

function Kpi({ label, value, note, color }) {
  return (
    <div className="card kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={color ? { color } : undefined}>{value}</div>
      {note && <div className="kpi-note">{note}</div>}
    </div>
  )
}

const signed = (value, digits = 1, suffix = '%') =>
  value == null ? '–' : `${value > 0 ? '+' : ''}${value.toFixed(digits)}${suffix}`

const moveColor = (value) => (value == null ? undefined : value >= 0 ? 'var(--pos)' : 'var(--neg)')

/**
 * The arc lightens and breaks as data coverage falls. The quantity is completeness, not
 * reliability -- see src/lib/confidenceGate.js and
 * research/audit/CURRENT_MODEL_AUDIT.md section 4.
 */
function CoverageScoreDial({ score, dataCoverage }) {
  const dial = modelSettings.interface.score_dial
  const maskId = `score-mask-${useId().replaceAll(':', '')}`
  const safeScore = Math.max(0, Math.min(100, Number(score) || 0))
  const safeCoverage = Math.max(0, Math.min(1, Number(dataCoverage) || 0))
  const dash = dial.minimum_dash + safeCoverage * (dial.maximum_dash - dial.minimum_dash)
  const gap = dial.maximum_gap - safeCoverage * (dial.maximum_gap - dial.minimum_gap)
  const opacity = dial.minimum_opacity + safeCoverage * (1 - dial.minimum_opacity)
  return <div className="confidence-score-dial" style={{ '--dial-size': `${dial.size}px` }}>
    <svg viewBox={`0 0 ${dial.viewbox_size} ${dial.viewbox_size}`} role="img" aria-label={`Research score ${safeScore.toFixed(0)} with ${Math.round(safeCoverage * 100)} percent data coverage`}>
      <circle className="score-dial-track" cx={dial.center} cy={dial.center} r={dial.radius} strokeWidth={dial.stroke_width} />
      <defs><mask id={maskId}><circle cx={dial.center} cy={dial.center} r={dial.radius} pathLength="100" stroke="white" strokeWidth={dial.stroke_width} fill="none" strokeDasharray={`${safeScore} ${100 - safeScore}`} /></mask></defs>
      <circle className="score-dial-arc" cx={dial.center} cy={dial.center} r={dial.radius} pathLength="100" strokeWidth={dial.stroke_width} mask={`url(#${maskId})`} style={{ opacity, strokeDasharray: `${dash} ${gap}` }} />
    </svg>
    <div><span>1 · Research score</span><strong>{safeScore.toFixed(0)}</strong><small>{Math.round(safeCoverage * 100)}% data coverage</small></div>
  </div>
}

// `theme_exposure` rows are published as {theme_id, display_name, theme_exposure_score, ...};
// the older `exposure_score`/`score` spellings are kept as fallbacks for saved snapshots.
export const themeExposureScore = (entry) =>
  Number(entry?.theme_exposure_score ?? entry?.exposure_score ?? entry?.score)
export const themeExposureName = (entry) =>
  entry?.display_name || entry?.theme_id || entry?.theme || entry?.name

function primaryTheme(stock) {
  const themes = Array.isArray(stock.theme_exposure) ? stock.theme_exposure : []
  if (!themes.length) return null
  return themes.slice().sort((left, right) =>
    (themeExposureScore(right) || 0) - (themeExposureScore(left) || 0))[0]
}

export function mergeResearchStock(suppliedStock, fullResearch) {
  if (!suppliedStock) return suppliedStock
  const fullStock = fullResearch?.research?.find((row) => row.ticker === suppliedStock.ticker)
    || fullResearch?.portfolio_coverage?.find((row) => row.ticker === suppliedStock.ticker)
    || fullResearch?.screen_universe?.find((row) => row.ticker === suppliedStock.ticker)
  if (!fullStock) return suppliedStock
  return {
    ...fullStock,
    ...suppliedStock,
    analysis_v2: { ...(fullStock.analysis_v2 || {}), ...(suppliedStock.analysis_v2 || {}) },
  }
}

// SEC Form 4 buys vs sells (pipeline/insider_signal.py). The pipeline already scores this
// into the modifier, but never surfaced the raw grouping – show it only once real filings
// were reviewed, so a quiet run (no SEC_USER_AGENT, no filings this window) renders nothing
// rather than a false "0 buys · 0 sells".
function InsiderActivityView({ insider }) {
  const buys = insider?.recent_acquisitions || 0
  const sells = insider?.recent_disposals || 0
  if (!insider?.records_reviewed || (!buys && !sells)) return null
  const buyPct = (buys / (buys + sells)) * 100
  return (
    <div>
      <div className="sec-label">Insider activity: buys vs. sells</div>
      <div className="insider-activity-view" aria-label="Insider buying versus selling">
        <div className="insider-activity-bar" aria-hidden="true">
          <span className="insider-buys" style={{ width: `${buyPct}%` }} />
          <span className="insider-sells" style={{ width: `${100 - buyPct}%` }} />
        </div>
        <div className="insider-activity-counts">
          <span className="positive">{buys} buy{buys === 1 ? '' : 's'}</span>
          <span className="negative">{sells} sell{sells === 1 ? '' : 's'}</span>
        </div>
      </div>
      <p className="evidence-footnote">
        {insider.records_reviewed} Form 4 filing{insider.records_reviewed === 1 ? '' : 's'} reviewed. Routine,
        scheduled trades are weighted down in the score; this grouping is raw counts, not the scored signal.
      </p>
    </div>
  )
}

const CONGRESS_FLAG_LABELS = {
  EXTRAORDINARY_BUY: "First trade in a small, unfamiliar company",
  CLUSTER_TRADE: '3+ representatives, 14-day span',
  BUY_SELL_FLIP: 'Round trip within 60 days',
}

// Congress + institutional 13F, merged and pre-filtered to notable rows only
// (pipeline/build_inside_information_screen.py) - a compact 2-3 line block, not the full
// table the /screens/inside-information page shows. Renders nothing for the vast majority
// of tickers, which never cleared the notability bar upstream.
export function InsideInformationView({ info }) {
  if (!info) return null
  return (
    <div>
      <div className="sec-label">Inside information: notable disclosed activity</div>
      <div className="congress-flag-row" aria-label="Notable institutional and Congressional activity">
        {info.institutional_flag && (
          <span className={`chip ${info.institutional_flag === 'CLUSTER_ACCUMULATION' ? 'pos' : 'neg'}`}>
            {info.institutional_flag === 'CLUSTER_ACCUMULATION' ? 'Curated managers accumulating' : 'Curated managers distributing'}
          </span>
        )}
        {(info.congress_flags || []).map((flag) => (
          <span key={flag} className="chip">{CONGRESS_FLAG_LABELS[flag] || flag}</span>
        ))}
      </div>
      <p className="evidence-footnote">
        Combined score {info.score?.toFixed(2) ?? '–'}. <Link to="/screens/inside-information">See the full Inside Information screen →</Link>
      </p>
    </div>
  )
}

export default function StockDetailModal({ stock: suppliedStock, onClose, benchmarkHistory, position, recommendationOverride, stopLoss }) {
  const [tab, setTab] = useState('evidence')
  const [showMore, setShowMore] = useState(false)
  const { preferences } = usePreferences()
  const { data: fullResearch } = useData(suppliedStock && !suppliedStock.explainability ? 'advisor.json' : null)
  const { data: insideInformation } = useData(suppliedStock ? 'screens/inside-information.json' : null)

  useBodyScrollLock(!!suppliedStock)
  // Escape, focus trap, initial focus and focus restore — see src/lib/useDialog.js.
  const dialogRef = useDialog(!!suppliedStock, onClose)
  const titleId = useId()

  if (!suppliedStock) return null
  // Browse/portfolio routes open immediately from report.json. Once the deep snapshot arrives,
  // fill in evidence, modifiers and explainability while preserving any newer live quote or
  // position-specific fields the calling route already placed on the row.
  const stock = mergeResearchStock(suppliedStock, fullResearch)
  const explainableStock = stock

  // A caller that already merged in position-specific guidance (e.g. a portfolio
  // stop-loss check) passes it here – recomputing from the raw research row would
  // silently drop that, since the row itself knows nothing about your cost basis.
  const recommendation = recommendationOverride || getRecommendation(stock)
  const isEtf = stock.is_etf || String(stock.asset_type || '').toLowerCase() === 'etf' || stock.sector === 'ETF'
  const technical = stock.technical_detail || {}
  const categories = stock.fundamental_categories || {}
  const thesis = bullBearScore(stock)
  const analysis = stock.analysis_v2
  const structural = analysis?.structural
  const percentile = stock.valuation_percentile
  const setupGuidance = watchlistGuidance(stock, null, null, { sizingMode: preferences.watchlistSizingMode })
  const score = stock.score ?? structural?.effective_score
  const dataCoverage = stock.data_coverage ?? structural?.coverage ?? 0
  const theme = primaryTheme(stock)
  const themeName = themeExposureName(theme) || 'No material theme identified'
  const themeScore = theme ? themeExposureScore(theme) : undefined
  // A company can sit in several structural trends at once, and which ones it shares is part
  // of the picture - a name carrying grid, reshoring and AI-buildout exposure is a different
  // proposition from a pure play on any one of them.
  const otherThemes = (Array.isArray(stock.theme_exposure) ? stock.theme_exposure : [])
    .filter((entry) => entry !== theme && Number.isFinite(themeExposureScore(entry)))
  const dataAsOf = stock.generated_at || stock.recommendation_v2?.generated_at || fullResearch?.generated_at

  // A held position with a purchase date gets its own since-you-bought-it comparison – the
  // full charted window (often a year) is the wrong question once you actually own the stock.
  const basis = stock.hypothetical?.basis || 500
  const scopedSeries = position?.purchaseDate
    ? positionGrowthSeries(position, stock.history, benchmarkHistory, basis)
    : null
  const scopedHypothetical = position?.purchaseDate
    ? fixedBasisAlternative(position, stock.history, benchmarkHistory, basis)
    : null
  const hypothetical = scopedHypothetical
    ? {
        basis,
        stock_value: scopedHypothetical.stockValue,
        benchmark_value: scopedHypothetical.benchmarkValue,
        stock_return_pct: scopedHypothetical.stockReturnPct,
        benchmark_return_pct: scopedHypothetical.benchmarkReturnPct,
        dollars_ahead: scopedHypothetical.dollarsAhead,
        excess_return_pct: (scopedHypothetical.dollarsAhead / basis) * 100,
      }
    : stock.hypothetical

  const chartSeries = []
  if (scopedSeries) {
    chartSeries.push({ label: stock.ticker, values: scopedSeries.stock, color: 'var(--series-stock)', emphasis: true })
    chartSeries.push({ label: 'S&P 500 (SPY)', values: scopedSeries.benchmark, color: 'var(--series-benchmark)', dashed: true })
  } else {
    if (stock.history?.growth) {
      chartSeries.push({ label: stock.ticker, values: stock.history.growth, color: 'var(--series-stock)', emphasis: true })
    }
    if (benchmarkHistory?.growth) {
      chartSeries.push({ label: 'S&P 500 (SPY)', values: benchmarkHistory.growth, color: 'var(--series-benchmark)', dashed: true })
    }
  }
  const chartDates = scopedSeries ? scopedSeries.dates : (stock.history?.dates || benchmarkHistory?.dates)

  return (
    <div
      className="modal-overlay"
      role="presentation"
      // pointerdown on the layer itself, so a drag that starts inside the dialog
      // and releases on the backdrop does not close it mid-selection.
      onPointerDown={(event) => { if (event.target === event.currentTarget) onClose() }}
    >
      <div
        ref={dialogRef}
        className="modal stock-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex="-1"
      >
        <header className="stock-detail-head">
          <div><span className="eyebrow">Company research</span><h2 id={titleId}>{stock.ticker}</h2><p>{stock.name} · {stock.industry || stock.sector || 'Unclassified'}</p>{dataAsOf && <small>As of {String(dataAsOf).slice(0, 10)}</small>}</div>
          <WatchlistToggleButton stock={stock} />
          <button className="icon-button" onClick={onClose} aria-label="Close stock research"><Icon name="close" /></button>
        </header>

        <section className="stock-concept-hero" aria-label="Research summary">
          <CoverageScoreDial score={score} dataCoverage={dataCoverage} />
          <div className="stock-concept-list">
            <article><span>2 · Data coverage</span><strong>{Math.round(dataCoverage * 100)}%</strong><p>How much of the evidence this model intends to use actually resolved. Not a reliability score and not a probability of a price move; the arc lightens as coverage falls.</p></article>
            <article><span>3 · Guidance</span><strong>{recommendation?.action || 'Watch'}</strong><p>{recommendation?.summary || 'Review the evidence before acting.'}</p></article>
            <article><span>4 · Theme exposure</span><strong>{themeName}</strong><p>{!Number.isFinite(themeScore) ? 'No material long-term theme exposure is published for this company.' : `${themeScore.toFixed(0)} out of 100. Theme exposure stays independent from the research score.`}{otherThemes.length > 0 && ` Also exposed to ${otherThemes.map(themeExposureName).join(', ')}.`}</p></article>
          </div>
        </section>

        <button className="expand-button show-more-toggle" aria-expanded={showMore} onClick={() => setShowMore((value) => !value)}>
          {showMore ? 'Hide full research detail' : 'Explore the evidence'}
          <Icon name="chevron" size={17} className={showMore ? 'rotated' : ''} />
        </button>

        {showMore && <div className="stock-detail-expanded">
          <ActionGuidance recommendation={recommendation} position={position} stopLoss={stopLoss} />
          <SetupQualityBreakdown guidance={setupGuidance} />
          <FactorBars bars={stock.explainability?.factor_bars} />
          <div className="grid grid-4">
          <Kpi label="Current price" value={stock.price ? `$${stock.price.toFixed(2)}` : '–'} />
          <Kpi label="Market cap" value={stock.market_cap ? `$${(stock.market_cap / 1e9).toFixed(1)}B` : '–'} />
          <Kpi label="20-day move" value={signed(technical.return_20d)} color={moveColor(technical.return_20d)} />
          <Kpi label="1-year move" value={signed(technical.return_252d)} color={moveColor(technical.return_252d)} />
          {typeof stock.earnings_surprise === 'number' && (
            <Kpi label="Earnings vs. estimate" value={signed(stock.earnings_surprise)} color={moveColor(stock.earnings_surprise)}
              note="Recent quarters vs. expectations, newest weighted heaviest" />
          )}
          </div>

          <DipWatchBadge stock={stock} />

        {thesis && !analysis && (
          <section className="bull-bear-detail" aria-label={`Bull bear thesis score ${thesis.score} out of 10`}>
            <div>
              <span>Bull / bear thesis</span>
              <strong className="mono" style={{
                color: thesis.score === 5 ? 'var(--text-dim)' : moveColor(thesis.score - 5),
              }}>
                {thesis.score.toFixed(1)}
              </strong>
              <small>0 bearish · 5 neutral · 10 bullish</small>
            </div>
            <div className="bull-bear-track" aria-hidden="true">
              <span className="bull-bear-zero" />
              <span
                className={thesis.score >= 5 ? 'positive' : 'negative'}
                style={{
                  left: thesis.score >= 5 ? '50%' : `${thesis.score * 10}%`,
                  width: `${Math.abs(thesis.score - 5) * 10}%`,
                }}
              />
            </div>
            <p>
              40% fundamentals · 30% price behavior · 20% news sentiment · 10% risk quality.
              {' '}{thesis.coverage}% of those inputs were available.
            </p>
          </section>
        )}

          <div className="stock-shadow-detail">
            <RecommendationShadowPanel legacy={recommendation} shadow={stock.recommendation_v2} />
            <AnalysisLayers analysis={analysis} />
          </div>
          {/* Tiers, never a percentage. The old sentence read "Cheaper than approximately
              85% of Property & casualty insurers, based on 14 valid peers" for a name in the
              expensive half of its group on both book and tangible book -- the ranked
              quantity is a composite of discrete bands, and with n=14 the resolution was
              7.7 points anyway. Groups under the minimum publish nothing at all now. */}
          {percentile?.peer_context
            ? <p className="stock-peer-context" title={`${percentile.peer_count_with_valid_data} valid of ${percentile.peer_count_total} ${percentile.peer_group_label}. ${percentile.peer_context.ranked_quantity_note}`}>
                Valuation score {percentile.peer_context.tier_phrase} {percentile.peer_group_label} ({percentile.peer_context.tier_count} of {percentile.peer_context.peer_count_with_valid_data} names). Ranks this model&rsquo;s valuation composite, not a price multiple.
              </p>
            : percentile && <p className="stock-peer-context">
                No peer comparison published: {percentile.peer_count_with_valid_data} valid {percentile.peer_group_label} peers, below the {percentile.minimum_peer_count} needed to rank against.
              </p>}
        </div>}

        <div className="tabs">
          {TABS.map(([key, label]) => (
            <button key={key} className={`tab ${tab === key ? 'active' : ''}`} onClick={() => setTab(key)}>
              {label}
            </button>
          ))}
        </div>

        {tab === 'evidence' && (
          <div className="stock-tab-panel">
            {!showMore && (
              <p className="evidence-collapsed-note">
                Score breakdowns, fundamental categories, the evidence list, modifiers, and insider activity are
                collapsed. Use “Explore the evidence” above to expand them.
              </p>
            )}
            {showMore && <>
              <ScoreExplainability stock={explainableStock} />
              <ResearchRadarChart stock={stock} />
              <div>
                <div className="sec-label">Score components</div>
                <div className="component-scores">
                  {Object.entries(stock.components || {}).map(([key, value]) => (
                    <div key={key}>
                      <span>{key.replace(/_/g, ' ')}</span>
                      <b>{value == null ? '–' : Math.round(value)}</b>
                      <i><em style={{ width: `${value || 0}%` }} /></i>
                    </div>
                  ))}
                </div>
              </div>

              {Object.keys(categories).length > 0 && (
                <div>
                  <div className="sec-label">Fundamental categories</div>
                  <div className="component-scores component-scores--fluid">
                    {Object.entries(categories).map(([key, value]) => {
                      // A category score renormalizes onto whatever metrics resolved, so a
                      // 90 built from 2 of 8 metrics and one built from all 8 read the same
                      // without the evidence count published alongside it.
                      const evidence = stock.fundamental_detail?.category_coverage?.[key]
                      return (
                        <div key={key}>
                          <span>{key.replace(/_/g, ' ')}</span>
                          <b>{value == null ? '–' : Math.round(value)}</b>
                          {evidence != null && evidence.metrics_applicable > 0 && (
                            <small className="metric-coverage-note">
                              {evidence.metrics_used}/{evidence.metrics_applicable} metrics
                            </small>
                          )}
                          <i><em style={{ width: `${value || 0}%` }} /></i>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              <div className="evidence-grid">
                <div>
                  <b>Evidence for</b>
                  <ul>{(stock.strengths || []).map((item) => <li key={item}>{item}</li>)}</ul>
                </div>
                <div>
                  <b>Risks / gaps</b>
                  <ul>{(stock.risks || []).map((item) => <li key={item}>{item}</li>)}</ul>
                </div>
              </div>

              <InsiderActivityView insider={stock.insider_activity} />
              <InsideInformationView info={insideInformation?.by_ticker?.[stock.ticker]} />

              {stock.modifiers?.notes?.length > 0 && (
                <div>
                  <div className="sec-label">Score modifiers ({signed(stock.modifiers.total, 1, ' pts')})</div>
                  <ul className="method-list">
                    {stock.modifiers.notes.map((note) => <li key={note}>{note}</li>)}
                  </ul>
                  <p className="evidence-footnote">
                    Applied on top of the {stock.base_score ?? '–'} evidence score. Modifiers refine
                    a ranking; they never outweigh the fundamentals behind it.
                  </p>
                </div>
              )}
            </>}
          </div>
        )}

        {tab === 'metrics' && <MetricSections stock={stock} />}

        {tab === 'performance' && (
          <div className="stock-tab-panel">
            {isEtf ? <>
              <ETFComparisonPanel ticker={stock.ticker} />
              {chartSeries.length > 0 && <details className="card card-pad">
                <summary>Legacy comparison view</summary>
                <GrowthChart dates={chartDates} series={chartSeries}
                  title={`Legacy growth comparison: ${stock.ticker}`}
                  caption="Retained during the schema 4 rollout. This legacy series may use a generic SPY comparison and should not be interpreted as tracking difference."
                  zoomable />
              </details>}
            </> : <>
            <GrowthChart
              dates={chartDates}
              series={chartSeries}
              title={scopedSeries
                ? `Growth of $${basis.toFixed(0)}: ${stock.ticker} vs the S&P 500 since you bought it (${position.purchaseDate})`
                : `Growth of $${basis.toFixed(0)}: ${stock.ticker} vs the S&P 500`}
              caption={scopedSeries
                ? 'Same dollars, invested the day you actually bought this position, in the stock and in the S&P 500. The gap is what picking this name earned or cost against simply buying the index from that same day.'
                : 'Same dollars, same start date, same window. The gap is what picking this name earned or cost against simply buying the index.'}
              zoomable
              earningsMarker={typeof stock.earnings_surprise === 'number' ? {
                value: stock.earnings_surprise,
                label: `Latest earnings vs. estimate: ${signed(stock.earnings_surprise)} (recent quarters, newest weighted heaviest, not a single dated report)`,
              } : null}
            />
            {hypothetical && (
              <div className="grid grid-4">
                <Kpi
                  label={`$${hypothetical.basis} in ${stock.ticker}`}
                  value={`$${hypothetical.stock_value.toFixed(0)}`}
                  note={signed(hypothetical.stock_return_pct)}
                  color={moveColor(hypothetical.stock_return_pct)}
                />
                <Kpi
                  label={`$${hypothetical.basis} in the S&P 500`}
                  value={`$${hypothetical.benchmark_value.toFixed(0)}`}
                  note={signed(hypothetical.benchmark_return_pct)}
                  color={moveColor(hypothetical.benchmark_return_pct)}
                />
                <Kpi
                  label="Dollars ahead"
                  value={`${hypothetical.dollars_ahead >= 0 ? '+' : '−'}$${Math.abs(hypothetical.dollars_ahead).toFixed(0)}`}
                  note="versus the index"
                  color={moveColor(hypothetical.dollars_ahead)}
                />
                <Kpi
                  label="Excess return"
                  value={signed(hypothetical.excess_return_pct)}
                  note="over the charted window"
                  color={moveColor(hypothetical.excess_return_pct)}
                />
              </div>
            )}
            <div className="grid grid-4">
              <Kpi label="Max drawdown (1y)" value={signed(technical.max_drawdown_252d)} color={moveColor(technical.max_drawdown_252d)} />
              <Kpi label="Volatility" value={technical.annualized_volatility ? `${technical.annualized_volatility.toFixed(0)}%` : '–'} />
              <Kpi label="Vs SPY (20d)" value={signed(technical.relative_strength_20d)} color={moveColor(technical.relative_strength_20d)} />
              <Kpi label="Beta" value={technical.beta != null ? technical.beta.toFixed(2) : '–'} />
              {/* Level versus change: "Vs SPY (20d)" is how far ahead this name is, this is
                  whether that lead is still widening. Shown in standard errors, not percent -
                  see risk_metrics.relative_acceleration. */}
              <Kpi
                label="Accel vs market"
                value={signed(technical.relative_acceleration, 2, 'σ')}
                note={technical.relative_acceleration_detail
                  ? `${signed(technical.relative_acceleration_detail.recent_excess_pct)} this quarter vs ${signed(technical.relative_acceleration_detail.prior_excess_pct)} last, market-adjusted`
                  : 'Needs two quarters of history against the index'}
                color={moveColor(technical.relative_acceleration)}
              />
            </div>
            </>}
          </div>
        )}

        <div className="callout callout--modal-gap">
          <strong>Disclaimer:</strong> Algorithmic research from quantitative metrics, not financial
          advice. Verify the filings and your own suitability before acting.
        </div>
      </div>
    </div>
  )
}
