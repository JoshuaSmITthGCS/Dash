import { useEffect, useState } from 'react'
import { Tier } from './Bits'
import ActionGuidance from './ActionGuidance'
import GrowthChart from './GrowthChart'
import MetricSections from './MetricSections'
import { getRecommendation } from '../lib/recommendation'

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

export default function StockDetailModal({ stock, onClose, benchmarkHistory, position }) {
  const [tab, setTab] = useState('evidence')

  useEffect(() => {
    const handleEscape = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [onClose])

  if (!stock) return null

  const recommendation = getRecommendation(stock)
  const technical = stock.technical_detail || {}
  const hypothetical = stock.hypothetical
  const categories = stock.fundamental_categories || {}

  const chartSeries = []
  if (stock.history?.growth) {
    chartSeries.push({ label: stock.ticker, values: stock.history.growth, color: 'var(--series-stock)', emphasis: true })
  }
  const benchmark = benchmarkHistory?.growth
  if (benchmark) {
    chartSeries.push({ label: 'S&P 500 (SPY)', values: benchmark, color: 'var(--series-benchmark)', dashed: true })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal stock-modal" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 20, gap: 16 }}>
          <div>
            <h2 style={{ marginBottom: 4 }}>{stock.ticker}</h2>
            <div style={{ opacity: 0.7, marginBottom: 8 }}>{stock.name} · {stock.industry || stock.sector || '—'}</div>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <Tier label={stock.stance} />
              <span className="mono" style={{ fontSize: 24, fontWeight: 600 }}>{stock.score}</span>
              <span style={{ opacity: 0.6, fontSize: 14 }}>{Math.round(stock.confidence * 100)}% confidence</span>
              {stock.sector_valuation_percentile != null && (
                <span className="chip">cheaper than {stock.sector_valuation_percentile.toFixed(0)}% of its sector</span>
              )}
            </div>
          </div>
          <button className="chip button-chip" onClick={onClose}>✕ Close</button>
        </div>

        <div style={{ marginBottom: 22 }}>
          <ActionGuidance recommendation={recommendation} position={position} />
        </div>

        <div className="grid grid-4" style={{ marginBottom: 20 }}>
          <Kpi label="Current price" value={stock.price ? `$${stock.price.toFixed(2)}` : '—'} />
          <Kpi label="Market cap" value={stock.market_cap ? `$${(stock.market_cap / 1e9).toFixed(1)}B` : '—'} />
          <Kpi label="20-day move" value={signed(technical.return_20d)} color={moveColor(technical.return_20d)} />
          <Kpi label="1-year move" value={signed(technical.return_252d)} color={moveColor(technical.return_252d)} />
        </div>

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
            <GrowthChart
              dates={stock.history?.dates || benchmarkHistory?.dates}
              series={chartSeries}
              title={`Growth of $${(hypothetical?.basis || 500).toFixed(0)} — ${stock.ticker} vs the S&P 500`}
              caption="Same dollars, same start date, same window. The gap is what picking this name earned or cost against simply buying the index."
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
