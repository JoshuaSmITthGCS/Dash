import { useEffect, useState } from 'react'
import { Tier } from './Bits'
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
  value == null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(digits)}${suffix}`

const moveColor = (value) => (value == null ? undefined : value >= 0 ? 'var(--pos)' : 'var(--neg)')

export default function StockDetailModal({ stock, onClose, benchmarkHistory, position, recommendationOverride, stopLoss }) {
  const [tab, setTab] = useState('evidence')

  useBodyScrollLock(!!stock)

  useEffect(() => {
    const handleEscape = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [onClose])

  if (!stock) return null

  // A caller that already merged in position-specific guidance (e.g. a portfolio
  // stop-loss check) passes it here — recomputing from the raw research row would
  // silently drop that, since the row itself knows nothing about your cost basis.
  const recommendation = recommendationOverride || getRecommendation(stock)
  const isEtf = stock.is_etf || String(stock.asset_type || '').toLowerCase() === 'etf' || stock.sector === 'ETF'
  const technical = stock.technical_detail || {}
  const categories = stock.fundamental_categories || {}
  const thesis = bullBearScore(stock)
  const analysis = stock.analysis_v2
  const structural = analysis?.structural
  const percentile = stock.valuation_percentile

  // A held position with a purchase date gets its own since-you-bought-it comparison — the
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
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 20, gap: 16 }}>
          <div>
            <h2 style={{ marginBottom: 4 }}>{stock.ticker}</h2>
            <div style={{ opacity: 0.7, marginBottom: 8 }}>{stock.name} · {stock.industry || stock.sector || '—'}</div>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <Tier label={analysis?.company_classification || stock.stance} />
              <span className="mono" style={{ fontSize: 24, fontWeight: 600 }}>{structural?.effective_score ?? stock.score}</span>
              <span style={{ opacity: 0.7, fontSize: 14 }}>
                {Math.round((structural?.confidence ?? stock.confidence) * 100)}% confidence · {Math.round((structural?.coverage ?? 0) * 100)}% coverage
              </span>
              {percentile?.display_value != null && (
                <span className="chip" title={`${percentile.peer_count_with_valid_data} valid of ${percentile.peer_count_total} ${percentile.peer_group_label}`}>
                  cheaper than approximately {percentile.display_value.toFixed(0)}% of {percentile.peer_group_label} · n={percentile.peer_count_with_valid_data}
                </span>
              )}
            </div>
          </div>
          <button className="chip button-chip" onClick={onClose}>✕ Close</button>
        </div>

        <div style={{ marginBottom: 22 }}>
          <ActionGuidance recommendation={recommendation} position={position} stopLoss={stopLoss} />
        </div>

        <RecommendationShadowPanel legacy={recommendation} shadow={stock.recommendation_v2} />

        <AnalysisLayers analysis={analysis} />

        <div className="grid grid-4" style={{ marginBottom: 20 }}>
          <Kpi label="Current price" value={stock.price ? `$${stock.price.toFixed(2)}` : '—'} />
          <Kpi label="Market cap" value={stock.market_cap ? `$${(stock.market_cap / 1e9).toFixed(1)}B` : '—'} />
          <Kpi label="20-day move" value={signed(technical.return_20d)} color={moveColor(technical.return_20d)} />
          <Kpi label="1-year move" value={signed(technical.return_252d)} color={moveColor(technical.return_252d)} />
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

        <div className="tabs">
          {TABS.map(([key, label]) => (
            <button key={key} className={`tab ${tab === key ? 'active' : ''}`} onClick={() => setTab(key)}>
              {label}
            </button>
          ))}
        </div>

        {tab === 'evidence' && (
          <div style={{ display: 'grid', gap: 20 }}>
            <div>
              <div className="sec-label">Score components</div>
              <div className="component-scores">
                {Object.entries(stock.components || {}).map(([key, value]) => (
                  <div key={key}>
                    <span>{key.replace(/_/g, ' ')}</span>
                    <b>{value == null ? '—' : Math.round(value)}</b>
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
                      <b>{value == null ? '—' : Math.round(value)}</b>
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

            {stock.modifiers?.notes?.length > 0 && (
              <div>
                <div className="sec-label">Score modifiers ({signed(stock.modifiers.total, 1, ' pts')})</div>
                <ul className="method-list">
                  {stock.modifiers.notes.map((note) => <li key={note}>{note}</li>)}
                </ul>
                <p style={{ color: 'var(--text-faint)', fontSize: 12, marginTop: 6 }}>
                  Applied on top of the {stock.base_score ?? '—'} evidence score. Modifiers refine
                  a ranking; they never outweigh the fundamentals behind it.
                </p>
              </div>
            )}
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
                  title={`Legacy growth comparison — ${stock.ticker}`}
                  caption="Retained during the schema 4 rollout. This legacy series may use a generic SPY comparison and should not be interpreted as tracking difference."
                  zoomable />
              </details>}
            </> : <>
            <GrowthChart
              dates={chartDates}
              series={chartSeries}
              title={scopedSeries
                ? `Growth of $${basis.toFixed(0)} — ${stock.ticker} vs the S&P 500 since you bought it (${position.purchaseDate})`
                : `Growth of $${basis.toFixed(0)} — ${stock.ticker} vs the S&P 500`}
              caption={scopedSeries
                ? 'Same dollars, invested the day you actually bought this position, in the stock and in the S&P 500. The gap is what picking this name earned or cost against simply buying the index from that same day.'
                : 'Same dollars, same start date, same window. The gap is what picking this name earned or cost against simply buying the index.'}
              zoomable
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
              <Kpi label="Volatility" value={technical.annualized_volatility ? `${technical.annualized_volatility.toFixed(0)}%` : '—'} />
              <Kpi label="Vs SPY (20d)" value={signed(technical.relative_strength_20d)} color={moveColor(technical.relative_strength_20d)} />
              <Kpi label="Beta" value={technical.beta != null ? technical.beta.toFixed(2) : '—'} />
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
