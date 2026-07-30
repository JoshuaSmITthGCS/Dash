import { useState, useEffect } from 'react'
import { Tier, MetricPills } from './Bits'

export default function StockDetailModal({ stock, onClose }) {
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [onClose])

  if (!stock) return null

  // Calculate sell strategy based on fundamentals and technical indicators
  const getSellStrategy = () => {
    const strategies = []
    const score = stock.score || 0
    const fundScore = stock.components?.fundamentals || 0
    const techDetail = stock.technical_detail || {}
    const valuation = stock.fundamental_detail?.valuation || {}

    // Profit-taking strategy
    if (techDetail.return_20d > 15) {
      strategies.push({
        type: 'Take Profits',
        reason: `Strong 20-day gain of ${techDetail.return_20d.toFixed(1)}%. Consider trimming position.`,
        action: 'Sell 25-50% to lock in gains',
        urgency: 'medium'
      })
    }

    // Fundamental deterioration
    if (fundScore < 60 && score < 65) {
      strategies.push({
        type: 'Exit',
        reason: 'Fundamentals deteriorating. Score below investment threshold.',
        action: 'Consider full exit and redeployment',
        urgency: 'high'
      })
    }

    // Valuation concerns
    if (valuation.forward_pe > 30 && stock.peg > 2.5) {
      strategies.push({
        type: 'Reduce',
        reason: 'Valuation stretched. High P/E and PEG suggest limited upside.',
        action: 'Reduce position by 30-40%',
        urgency: 'medium'
      })
    }

    // Rebalancing
    if (techDetail.return_20d < -10) {
      strategies.push({
        type: 'Review',
        reason: `20-day decline of ${techDetail.return_20d.toFixed(1)}%. Check if thesis still intact.`,
        action: fundScore > 70 ? 'Hold or add on weakness' : 'Consider tax-loss harvesting',
        urgency: 'low'
      })
    }

    // Hold recommendation
    if (score > 75 && fundScore > 70 && Math.abs(techDetail.return_20d || 0) < 10) {
      strategies.push({
        type: 'Hold',
        reason: 'Strong fundamentals and stable price action.',
        action: 'Maintain position. Consider adding on dips.',
        urgency: 'low'
      })
    }

    return strategies.length > 0 ? strategies : [{
      type: 'Hold',
      reason: 'No immediate action required.',
      action: 'Monitor quarterly earnings and fundamental updates',
      urgency: 'low'
    }]
  }

  const strategies = getSellStrategy()

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal stock-modal" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 20 }}>
          <div>
            <h2 style={{ marginBottom: 4 }}>{stock.ticker}</h2>
            <div style={{ opacity: 0.7, marginBottom: 8 }}>{stock.name}</div>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <Tier label={stock.stance} />
              <span className="mono" style={{ fontSize: 24, fontWeight: 600 }}>{stock.score}</span>
              <span style={{ opacity: 0.6, fontSize: 14 }}>{Math.round(stock.confidence * 100)}% confidence</span>
            </div>
          </div>
          <button className="chip button-chip" onClick={onClose}>✕ Close</button>
        </div>

        <MetricPills {...stock} fundamental_coverage={stock.fundamental_detail?.coverage} />

        <div style={{ marginTop: 24 }}>
          <h3 style={{ marginBottom: 12 }}>Key Metrics</h3>
          <div className="grid grid-4" style={{ marginBottom: 20 }}>
            <div className="card kpi">
              <div className="kpi-label">Current Price</div>
              <div className="kpi-value">${stock.price?.toFixed(2) || '—'}</div>
            </div>
            <div className="card kpi">
              <div className="kpi-label">Market Cap</div>
              <div className="kpi-value">{stock.market_cap ? `$${(stock.market_cap / 1e9).toFixed(1)}B` : '—'}</div>
            </div>
            <div className="card kpi">
              <div className="kpi-label">PEG Ratio</div>
              <div className="kpi-value">{stock.peg || '—'}</div>
            </div>
            <div className="card kpi">
              <div className="kpi-label">Forward P/E</div>
              <div className="kpi-value">{stock.forward_pe || '—'}</div>
            </div>
          </div>

          <div className="grid grid-4" style={{ marginBottom: 20 }}>
            <div className="card kpi">
              <div className="kpi-label">1-Day Return</div>
              <div className="kpi-value" style={{ color: stock.technical_detail?.return_1d >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                {stock.technical_detail?.return_1d != null ? `${stock.technical_detail.return_1d > 0 ? '+' : ''}${stock.technical_detail.return_1d.toFixed(1)}%` : '—'}
              </div>
            </div>
            <div className="card kpi">
              <div className="kpi-label">5-Day Return</div>
              <div className="kpi-value" style={{ color: stock.technical_detail?.return_5d >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                {stock.technical_detail?.return_5d != null ? `${stock.technical_detail.return_5d > 0 ? '+' : ''}${stock.technical_detail.return_5d.toFixed(1)}%` : '—'}
              </div>
            </div>
            <div className="card kpi">
              <div className="kpi-label">20-Day Return</div>
              <div className="kpi-value" style={{ color: stock.technical_detail?.return_20d >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                {stock.technical_detail?.return_20d != null ? `${stock.technical_detail.return_20d > 0 ? '+' : ''}${stock.technical_detail.return_20d.toFixed(1)}%` : '—'}
              </div>
            </div>
            <div className="card kpi">
              <div className="kpi-label">3-Month Return</div>
              <div className="kpi-value" style={{ color: stock.technical_detail?.return_60d >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                {stock.technical_detail?.return_60d != null ? `${stock.technical_detail.return_60d > 0 ? '+' : ''}${stock.technical_detail.return_60d.toFixed(1)}%` : '—'}
              </div>
            </div>
          </div>

          <h3 style={{ marginBottom: 12, marginTop: 32 }}>Sell Strategy & Recommendations</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {strategies.map((strategy, index) => (
              <div
                key={index}
                className="card"
                style={{
                  padding: 16,
                  borderLeft: `4px solid ${strategy.urgency === 'high' ? 'var(--neg)' : strategy.urgency === 'medium' ? 'var(--warn)' : 'var(--pos)'}`
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 8 }}>
                  <h4 style={{ margin: 0 }}>{strategy.type}</h4>
                  <span
                    className="chip"
                    style={{
                      background: strategy.urgency === 'high' ? 'var(--neg)' : strategy.urgency === 'medium' ? 'var(--warn)' : 'var(--pos)',
                      color: '#fff',
                      fontSize: 11
                    }}
                  >
                    {strategy.urgency.toUpperCase()}
                  </span>
                </div>
                <p style={{ margin: '0 0 8px 0', opacity: 0.8 }}>{strategy.reason}</p>
                <p style={{ margin: 0, fontWeight: 500 }}><strong>Action:</strong> {strategy.action}</p>
              </div>
            ))}
          </div>

          <div className="callout" style={{ marginTop: 24 }}>
            <strong>Disclaimer:</strong> These are algorithmic suggestions based on quantitative metrics. Not financial advice. Always conduct your own research and consult with a financial advisor before making investment decisions.
          </div>
        </div>
      </div>
    </div>
  )
}
