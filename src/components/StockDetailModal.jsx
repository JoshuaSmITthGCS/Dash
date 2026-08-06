import { useEffect, useId, useState } from 'react'
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
import ResearchRadarChart from './ResearchRadarChart'
import Icon from './Icons'
import SetupQualityBreakdown from './SetupQualityBreakdown'
import { watchlistGuidance } from '../lib/watchlistGuidance'
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

function ConfidenceScoreDial({ score, confidence }) {
  const dial = modelSettings.interface.score_dial
  const maskId = `score-mask-${useId().replaceAll(':', '')}`
  const safeScore = Math.max(0, Math.min(100, Number(score) || 0))
  const safeConfidence = Math.max(0, Math.min(1, Number(confidence) || 0))
  const dash = dial.minimum_dash + safeConfidence * (dial.maximum_dash - dial.minimum_dash)
  const gap = dial.maximum_gap - safeConfidence * (dial.maximum_gap - dial.minimum_gap)
  const opacity = dial.minimum_opacity + safeConfidence * (1 - dial.minimum_opacity)
  return <div className="confidence-score-dial" style={{ width: dial.size }}>
    <svg viewBox={`0 0 ${dial.viewbox_size} ${dial.viewbox_size}`} role="img" aria-label={`Research score ${safeScore.toFixed(0)} with ${Math.round(safeConfidence * 100)} percent confidence`}>
      <circle className="score-dial-track" cx={dial.center} cy={dial.center} r={dial.radius} strokeWidth={dial.stroke_width} />
      <defs><mask id={maskId}><circle cx={dial.center} cy={dial.center} r={dial.radius} pathLength="100" stroke="white" strokeWidth={dial.stroke_width} fill="none" strokeDasharray={`${safeScore} ${100 - safeScore}`} /></mask></defs>
      <circle className="score-dial-arc" cx={dial.center} cy={dial.center} r={dial.radius} pathLength="100" strokeWidth={dial.stroke_width} mask={`url(#${maskId})`} style={{ opacity, strokeDasharray: `${dash} ${gap}` }} />
    </svg>
    <div><span>1 · Research score</span><strong>{safeScore.toFixed(0)}</strong><small>{Math.round(safeConfidence * 100)}% evidence confidence</small></div>
  </div>
}

function primaryTheme(stock) {
  const themes = Array.isArray(stock.theme_exposure) ? stock.theme_exposure : []
  if (!themes.length) return null
  return themes.slice().sort((left, right) => Number(right.exposure_score ?? right.score ?? 0) - Number(left.exposure_score ?? left.score ?? 0))[0]
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
      <p style={{ color: 'var(--text-faint)', fontSize: 12, marginTop: 6 }}>
        {insider.records_reviewed} Form 4 filing{insider.records_reviewed === 1 ? '' : 's'} reviewed. Routine,
        scheduled trades are weighted down in the score; this grouping is raw counts, not the scored signal.
      </p>
    </div>
  )
}

export default function StockDetailModal({ stock, onClose, benchmarkHistory, position, recommendationOverride, stopLoss }) {
  const [tab, setTab] = useState('evidence')
  const [showMore, setShowMore] = useState(false)
  const { preferences } = usePreferences()
  const { data: fullResearch } = useData(stock && !stock.explainability ? 'advisor.json' : null)

  useBodyScrollLock(!!stock)

  useEffect(() => {
    const handleEscape = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [onClose])

  if (!stock) return null
  const explainability = stock.explainability
    || fullResearch?.research?.find((row) => row.ticker === stock.ticker)?.explainability
  const explainableStock = explainability ? { ...stock, explainability } : stock

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
  const confidence = stock.confidence ?? structural?.confidence ?? 0
  const theme = primaryTheme(stock)
  const themeName = theme?.theme || theme?.name || 'No material theme identified'
  const themeScore = theme?.exposure_score ?? theme?.score
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
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal stock-modal" onClick={(e) => e.stopPropagation()}>
        <header className="stock-detail-head">
          <div><span className="eyebrow">Company research</span><h2>{stock.ticker}</h2><p>{stock.name} · {stock.industry || stock.sector || 'Unclassified'}</p>{dataAsOf && <small>As of {String(dataAsOf).slice(0, 10)}</small>}</div>
          <button className="icon-button" onClick={onClose} aria-label="Close stock research"><Icon name="close" /></button>
        </header>

        <section className="stock-concept-hero" aria-label="Research summary">
          <ConfidenceScoreDial score={score} confidence={confidence} />
          <div className="stock-concept-list">
            <article><span>2 · Confidence</span><strong>{Math.round(confidence * 100)}%</strong><p>How complete and reliable the evidence is. The score arc becomes lighter and more broken when certainty falls.</p></article>
            <article><span>3 · Guidance</span><strong>{recommendation?.action || 'Watch'}</strong><p>{recommendation?.summary || 'Review the evidence before acting.'}</p></article>
            <article><span>4 · Theme exposure</span><strong>{themeName}</strong><p>{themeScore == null ? 'No material long-term theme exposure is published for this company.' : `${Number(themeScore).toFixed(0)} out of 100. Theme exposure stays independent from the research score.`}</p></article>
          </div>
        </section>

        <button className="expand-button show-more-toggle" aria-expanded={showMore} onClick={() => setShowMore((value) => !value)}>
          {showMore ? 'Hide full research detail' : 'Explore the evidence'}
          <Icon name="chevron" size={17} className={showMore ? 'rotated' : ''} />
        </button>

        {showMore && <div className="stock-detail-expanded">
          <ActionGuidance recommendation={recommendation} position={position} stopLoss={stopLoss} />
          <SetupQualityBreakdown guidance={setupGuidance} />
          <FactorBars bars={explainability?.factor_bars} />
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
          {percentile?.display_value != null && <p className="stock-peer-context" title={`${percentile.peer_count_with_valid_data} valid of ${percentile.peer_count_total} ${percentile.peer_group_label}`}>Cheaper than approximately {percentile.display_value.toFixed(0)}% of {percentile.peer_group_label}, based on {percentile.peer_count_with_valid_data} valid peers.</p>}
        </div>}

        <div className="tabs">
          {TABS.map(([key, label]) => (
            <button key={key} className={`tab ${tab === key ? 'active' : ''}`} onClick={() => setTab(key)}>
              {label}
            </button>
          ))}
        </div>

        {tab === 'evidence' && (
          <div style={{ display: 'grid', gap: 20 }}>
            {!showMore && (
              <p style={{ color: 'var(--text-faint)', fontSize: 12.5 }}>
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
                  <div className="component-scores" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
                    {Object.entries(categories).map(([key, value]) => (
                      <div key={key}>
                        <span>{key.replace(/_/g, ' ')}</span>
                        <b>{value == null ? '–' : Math.round(value)}</b>
                        <i><em style={{ width: `${value || 0}%` }} /></i>
                      </div>
                    ))}
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

              {stock.modifiers?.notes?.length > 0 && (
                <div>
                  <div className="sec-label">Score modifiers ({signed(stock.modifiers.total, 1, ' pts')})</div>
                  <ul className="method-list">
                    {stock.modifiers.notes.map((note) => <li key={note}>{note}</li>)}
                  </ul>
                  <p style={{ color: 'var(--text-faint)', fontSize: 12, marginTop: 6 }}>
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
          <div style={{ display: 'grid', gap: 20 }}>
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
            </div>
            </>}
          </div>
        )}

        <div className="callout" style={{ marginTop: 24 }}>
          <strong>Disclaimer:</strong> Algorithmic research from quantitative metrics, not financial
          advice. Verify the filings and your own suitability before acting.
        </div>
      </div>
    </div>
  )
}
