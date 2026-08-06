import { useState } from 'react'
import { getScoreBandFromRank } from '../lib/scoreBands'
import DataFreshnessIndicator from './DataFreshnessIndicator'

/**
 * Stock Card Component
 *
 * Mobile-first expandable card replacing dense tables.
 * Collapsed: ticker, score, stance
 * Expanded: full metrics, components breakdown, evidence strength
 */
export default function StockCard({ stock, rank, totalStocks = 20, defaultExpanded = false }) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  const band = getScoreBandFromRank(rank, totalStocks)

  // Component scores (if available)
  const components = stock.components || {}
  const hasComponents = Object.keys(components).length > 0

  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: `2px solid ${expanded ? band.color : 'var(--border)'}`,
        borderRadius: 12,
        overflow: 'hidden',
        transition: 'all 0.2s'
      }}
    >
      {/* Collapsed View (Always Visible) */}
      <div
        style={{
          padding: 16,
          cursor: 'pointer',
          background: expanded ? band.bgColor : 'transparent'
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
          {/* Left: Ticker & Band */}
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ fontSize: 20 }}>{band.icon}</span>
              <span style={{
                fontWeight: 700,
                fontSize: 18,
                fontFamily: 'var(--font-mono)',
                color: band.color
              }}>
                {stock.ticker}
              </span>
              <span style={{
                fontSize: 11,
                opacity: 0.6,
                fontFamily: 'var(--font-mono)'
              }}>
                #{rank}
              </span>
            </div>
            <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 4 }}>
              {stock.company_name || stock.name || '–'}
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {stock.stance && (
                <span className="chip" style={{
                  fontSize: 10,
                  padding: '3px 8px',
                  background: stock.stance === 'Attractive' ? 'var(--pos)' :
                             stock.stance === 'Promising' ? '#3b82f6' :
                             stock.stance === 'Neutral' ? 'gray' :
                             stock.stance === 'Caution' ? 'orange' : 'var(--neg)',
                  color: 'white'
                }}>
                  {stock.stance}
                </span>
              )}
              <span className="chip" style={{
                fontSize: 10,
                padding: '3px 8px',
                background: band.bgColor,
                color: band.color,
                border: `1px solid ${band.color}`
              }}>
                {band.shortLabel}
              </span>
            </div>
          </div>

          {/* Right: Score & Price */}
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 11, opacity: 0.6, marginBottom: 2 }}>Score</div>
            <div style={{
              fontSize: 28,
              fontWeight: 700,
              fontFamily: 'var(--font-mono)',
              color: band.color,
              marginBottom: 4
            }}>
              {stock.score?.toFixed(1) || '–'}
            </div>
            {stock.price && (
              <div style={{ fontSize: 14, fontFamily: 'var(--font-mono)', opacity: 0.8 }}>
                ${stock.price.toFixed(2)}
              </div>
            )}
          </div>
        </div>

        {/* Expand indicator */}
        <div style={{
          marginTop: 12,
          textAlign: 'center',
          fontSize: 12,
          opacity: 0.5,
          transition: 'transform 0.2s',
          transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)'
        }}>
          ▼
        </div>
      </div>

      {/* Expanded View */}
      {expanded && (
        <div style={{
          padding: 16,
          borderTop: `1px solid ${band.color}40`
        }}>
          {/* Key Metrics Grid */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: 12,
            marginBottom: 16
          }}>
            {stock.market_cap && (
              <MetricCard
                label="Market Cap"
                value={`$${(stock.market_cap / 1e9).toFixed(1)}B`}
              />
            )}
            {stock.ratios?.pe && (
              <MetricCard
                label="P/E Ratio"
                value={stock.ratios.pe.toFixed(1)}
              />
            )}
            {stock.ratios?.debt_to_equity !== undefined && (
              <MetricCard
                label="Debt/Equity"
                value={stock.ratios.debt_to_equity.toFixed(2)}
              />
            )}
            {stock.financials?.revenue && (
              <MetricCard
                label="Revenue"
                value={`$${(stock.financials.revenue / 1e9).toFixed(1)}B`}
              />
            )}
            {stock.financials?.earnings !== undefined && (
              <MetricCard
                label="Earnings"
                value={stock.financials.earnings > 0 ? `$${(stock.financials.earnings / 1e9).toFixed(1)}B` : `($${Math.abs(stock.financials.earnings / 1e9).toFixed(1)}B)`}
                valueColor={stock.financials.earnings > 0 ? 'var(--pos)' : 'var(--neg)'}
              />
            )}
            {stock.ratios?.current_ratio && (
              <MetricCard
                label="Current Ratio"
                value={stock.ratios.current_ratio.toFixed(2)}
              />
            )}
          </div>

          {/* Component Scores */}
          {hasComponents && (
            <div style={{ marginBottom: 16 }}>
              <h4 style={{ margin: '0 0 10px', fontSize: 13, fontWeight: 600, opacity: 0.8 }}>
                Score Components
              </h4>
              <div style={{ display: 'grid', gap: 8 }}>
                {components.fundamentals !== undefined && (
                  <ComponentBar
                    label="Fundamentals"
                    value={components.fundamentals}
                    color="#22c55e"
                  />
                )}
                {components.market_behavior !== undefined && (
                  <ComponentBar
                    label="Market Behavior"
                    value={components.market_behavior}
                    color="#3b82f6"
                  />
                )}
                {components.news_sentiment !== undefined && (
                  <ComponentBar
                    label="News Sentiment"
                    value={components.news_sentiment}
                    color="#8b5cf6"
                  />
                )}
              </div>
            </div>
          )}

          {/* Evidence Strength */}
          {stock.evidence_strength !== undefined && (
            <div style={{
              padding: 12,
              background: 'var(--bg-elev)',
              borderRadius: 8,
              marginBottom: 12
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <span style={{ fontSize: 12, fontWeight: 600 }}>Evidence Strength</span>
                <span style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                  {(stock.evidence_strength * 100).toFixed(0)}%
                </span>
              </div>
              <div style={{
                width: '100%',
                height: 6,
                background: 'var(--bg-card)',
                borderRadius: 3,
                overflow: 'hidden'
              }}>
                <div style={{
                  width: `${stock.evidence_strength * 100}%`,
                  height: '100%',
                  background: stock.evidence_strength >= 0.8 ? 'var(--pos)' :
                             stock.evidence_strength >= 0.6 ? '#3b82f6' :
                             stock.evidence_strength >= 0.4 ? 'orange' : 'var(--neg)',
                  transition: 'width 0.3s'
                }} />
              </div>
              <div style={{ fontSize: 10, opacity: 0.6, marginTop: 4 }}>
                Data completeness, freshness, and agreement
              </div>
            </div>
          )}

          {/* Data Freshness */}
          {stock.priceUpdatedAt && (
            <div style={{
              padding: 10,
              background: 'var(--bg-elev)',
              borderRadius: 8,
              fontSize: 12,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <span style={{ opacity: 0.7 }}>Last updated:</span>
              <DataFreshnessIndicator timestamp={stock.priceUpdatedAt} type="price" threshold={7} />
            </div>
          )}

          {/* Sell/Watch Recommendation (if present) */}
          {stock.recommendation && stock.recommendation.action !== 'HOLD' && (
            <div style={{
              marginTop: 12,
              padding: 12,
              background: stock.recommendation.action === 'SELL' ? 'color-mix(in srgb, var(--neg) 10%, transparent)' :
                         stock.recommendation.action === 'TRIM' ? 'color-mix(in srgb, orange 10%, transparent)' :
                         'color-mix(in srgb, var(--accent) 10%, transparent)',
              border: `1px solid ${stock.recommendation.action === 'SELL' ? 'var(--neg)' :
                                   stock.recommendation.action === 'TRIM' ? 'orange' : 'var(--accent)'}`,
              borderRadius: 8
            }}>
              <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 13 }}>
                {stock.recommendation.action === 'SELL' ? '🔴' :
                 stock.recommendation.action === 'TRIM' ? '⚠️' : 'ℹ️'} {stock.recommendation.action}
              </div>
              <div style={{ fontSize: 11, opacity: 0.9 }}>
                {stock.recommendation.reason || 'No specific reason provided'}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Metric Card (mini component)
 */
function MetricCard({ label, value, valueColor = 'inherit' }) {
  return (
    <div style={{
      padding: 10,
      background: 'var(--bg-elev)',
      borderRadius: 8,
      border: '1px solid var(--border)'
    }}>
      <div style={{ fontSize: 10, opacity: 0.6, marginBottom: 4 }}>{label}</div>
      <div style={{
        fontSize: 14,
        fontWeight: 600,
        fontFamily: 'var(--font-mono)',
        color: valueColor
      }}>
        {value}
      </div>
    </div>
  )
}

/**
 * Component Bar (mini component)
 */
function ComponentBar({ label, value, color }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
        <span>{label}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
          {value.toFixed(1)}
        </span>
      </div>
      <div style={{
        width: '100%',
        height: 6,
        background: 'var(--bg-card)',
        borderRadius: 3,
        overflow: 'hidden'
      }}>
        <div style={{
          width: `${(value / 100) * 100}%`,
          height: '100%',
          background: color,
          transition: 'width 0.3s'
        }} />
      </div>
    </div>
  )
}
