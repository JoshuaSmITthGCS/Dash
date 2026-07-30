import { useState } from 'react'
import { groupByScoreBand, SCORE_BANDS, getScoreBandDisclaimer } from '../lib/scoreBands'

/**
 * Score Band View
 *
 * Displays stocks grouped by tier instead of exact ranks.
 * More honest: acknowledges that small score differences aren't meaningful.
 */
export default function ScoreBandView({ stocks, onStockClick }) {
  const [expandedBand, setExpandedBand] = useState('A') // Default to showing Tier A
  const [showDisclaimer, setShowDisclaimer] = useState(false)

  const bandGroups = groupByScoreBand(stocks, stocks.length)
  const disclaimer = getScoreBandDisclaimer()

  return (
    <div>
      {/* Disclaimer Toggle */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
        <button
          className="chip button-chip"
          onClick={() => setShowDisclaimer(!showDisclaimer)}
          style={{ fontSize: 12 }}
        >
          {showDisclaimer ? 'Hide' : 'Show'} Tier Explanation
        </button>
      </div>

      {/* Disclaimer Panel */}
      {showDisclaimer && (
        <div style={{
          background: 'var(--bg-elev)',
          border: '1px solid var(--border)',
          borderRadius: 12,
          padding: 16,
          marginBottom: 20
        }}>
          <h3 style={{ margin: '0 0 12px', fontSize: 15, fontWeight: 600 }}>
            {disclaimer.title}
          </h3>
          <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, opacity: 0.9 }}>
            {disclaimer.points.map((point, i) => (
              <li key={i} style={{ marginBottom: 6 }}>{point}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Band Groups */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {['A', 'B', 'C', 'D', 'E'].map(tier => {
          const band = SCORE_BANDS[tier]
          const stocksInBand = bandGroups[tier]
          const isExpanded = expandedBand === tier

          if (stocksInBand.length === 0) return null

          const avgScore = stocksInBand.reduce((sum, s) => sum + (s.score || 0), 0) / stocksInBand.length

          return (
            <div
              key={tier}
              style={{
                background: 'var(--bg-card)',
                border: `2px solid ${isExpanded ? band.color : 'var(--border)'}`,
                borderRadius: 12,
                overflow: 'hidden',
                transition: 'all 0.2s'
              }}
            >
              {/* Band Header */}
              <div
                style={{
                  background: band.bgColor,
                  padding: 16,
                  cursor: 'pointer',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  borderBottom: isExpanded ? `1px solid ${band.color}40` : 'none'
                }}
                onClick={() => setExpandedBand(isExpanded ? null : tier)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ fontSize: 24 }}>{band.icon}</div>
                  <div>
                    <div style={{
                      fontWeight: 700,
                      fontSize: 16,
                      color: band.color,
                      marginBottom: 2
                    }}>
                      {band.label}
                    </div>
                    <div style={{ fontSize: 12, opacity: 0.8 }}>
                      {band.description}
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 11, opacity: 0.6 }}>Stocks</div>
                    <div style={{ fontSize: 18, fontWeight: 700 }}>{stocksInBand.length}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 11, opacity: 0.6 }}>Avg Score</div>
                    <div style={{ fontSize: 18, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                      {avgScore.toFixed(1)}
                    </div>
                  </div>
                  <div style={{
                    fontSize: 20,
                    opacity: 0.6,
                    transition: 'transform 0.2s',
                    transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)'
                  }}>
                    ▼
                  </div>
                </div>
              </div>

              {/* Stocks List */}
              {isExpanded && (
                <div style={{ padding: 16 }}>
                  <div style={{ display: 'grid', gap: 10 }}>
                    {stocksInBand.map((stock, i) => (
                      <div
                        key={stock.ticker}
                        style={{
                          background: 'var(--bg-elev)',
                          border: '1px solid var(--border)',
                          borderRadius: 8,
                          padding: 12,
                          cursor: onStockClick ? 'pointer' : 'default',
                          transition: 'all 0.2s'
                        }}
                        onClick={() => onStockClick?.(stock)}
                        onMouseEnter={(e) => {
                          if (onStockClick) {
                            e.currentTarget.style.borderColor = band.color
                            e.currentTarget.style.background = band.bgColor
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (onStockClick) {
                            e.currentTarget.style.borderColor = 'var(--border)'
                            e.currentTarget.style.background = 'var(--bg-elev)'
                          }
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ flex: 1 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                              <span style={{
                                fontWeight: 700,
                                fontSize: 15,
                                fontFamily: 'var(--font-mono)'
                              }}>
                                {stock.ticker}
                              </span>
                              <span style={{
                                fontSize: 11,
                                opacity: 0.6,
                                fontFamily: 'var(--font-mono)'
                              }}>
                                #{stock.rank}
                              </span>
                              {stock.stance && (
                                <span className="chip" style={{
                                  fontSize: 10,
                                  padding: '2px 6px',
                                  background: stock.stance === 'Attractive' ? 'var(--pos)' :
                                             stock.stance === 'Promising' ? '#3b82f6' :
                                             stock.stance === 'Neutral' ? 'gray' :
                                             stock.stance === 'Caution' ? 'orange' : 'var(--neg)',
                                  color: 'white'
                                }}>
                                  {stock.stance}
                                </span>
                              )}
                            </div>
                            <div style={{ fontSize: 12, opacity: 0.7 }}>
                              {stock.company_name || stock.name || '—'}
                            </div>
                          </div>

                          <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
                            <div style={{ textAlign: 'right' }}>
                              <div style={{ fontSize: 10, opacity: 0.6 }}>Score</div>
                              <div style={{
                                fontSize: 16,
                                fontWeight: 700,
                                fontFamily: 'var(--font-mono)',
                                color: band.color
                              }}>
                                {stock.score?.toFixed(1) || '—'}
                              </div>
                            </div>

                            {stock.price && (
                              <div style={{ textAlign: 'right' }}>
                                <div style={{ fontSize: 10, opacity: 0.6 }}>Price</div>
                                <div style={{ fontSize: 14, fontFamily: 'var(--font-mono)' }}>
                                  ${stock.price.toFixed(2)}
                                </div>
                              </div>
                            )}

                            {stock.market_cap && (
                              <div style={{ textAlign: 'right' }}>
                                <div style={{ fontSize: 10, opacity: 0.6 }}>Mkt Cap</div>
                                <div style={{ fontSize: 14, fontFamily: 'var(--font-mono)' }}>
                                  ${(stock.market_cap / 1e9).toFixed(1)}B
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
