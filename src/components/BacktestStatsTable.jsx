import { formatMetric } from '../lib/backtestEngine'

export default function BacktestStatsTable({ results, selectedStrategy }) {
  if (!results) {
    return (
      <div style={{ padding: 20, textAlign: 'center', opacity: 0.6 }}>
        No metrics available
      </div>
    )
  }

  const { equalWeight, rankWeighted, spy } = results

  // Determine which strategies to show
  const strategies = []
  if (selectedStrategy === 'all' || selectedStrategy === 'equalWeight') {
    strategies.push({ name: 'Equal-Weight', data: equalWeight, color: '#3b82f6' })
  }
  if (selectedStrategy === 'all' || selectedStrategy === 'rankWeighted') {
    strategies.push({ name: 'Rank-Weighted', data: rankWeighted, color: '#8b5cf6' })
  }
  if (selectedStrategy === 'all' || selectedStrategy === 'spy') {
    strategies.push({ name: 'SPY Benchmark', data: spy, color: '#6b7280' })
  }

  // Metrics to display
  const metrics = [
    { key: 'totalDeployed', label: 'Total Invested', format: 'currency' },
    { key: 'finalValue', label: 'Final Value', format: 'currency' },
    { key: 'totalReturn', label: 'Total Return', format: 'currency' },
    { key: 'totalReturnPct', label: 'Total Return %', format: 'percent' },
    { key: 'numTrades', label: 'Number of Trades', format: 'number' },
    { key: 'numWins', label: 'Winning Trades', format: 'number' },
    { key: 'numLosses', label: 'Losing Trades', format: 'number' },
    { key: 'avgGain', label: 'Avg Gain %', format: 'percent' },
    { key: 'maxDrawdown', label: 'Max Drawdown %', format: 'percent' },
    { key: 'sharpeRatio', label: 'Sharpe Ratio', format: 'number' },
    { key: 'turnover', label: 'Turnover', format: 'number' }
  ]

  // Win rate calculation
  const calculateWinRate = (strategy) => {
    const wins = strategy.metrics.numWins || 0
    const losses = strategy.metrics.numLosses || 0
    const total = wins + losses
    return total > 0 ? ((wins / total) * 100).toFixed(1) : '—'
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{
        width: '100%',
        borderCollapse: 'collapse',
        fontSize: 14
      }}>
        <thead>
          <tr>
            <th style={{
              textAlign: 'left',
              padding: '12px 16px',
              borderBottom: '2px solid var(--border)',
              fontWeight: 600,
              fontSize: 13,
              opacity: 0.8
            }}>
              Metric
            </th>
            {strategies.map((strategy, i) => (
              <th key={i} style={{
                textAlign: 'right',
                padding: '12px 16px',
                borderBottom: '2px solid var(--border)',
                fontWeight: 600,
                fontSize: 13
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8 }}>
                  <div style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    background: strategy.color
                  }} />
                  {strategy.name}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map((metric, i) => (
            <tr key={i} style={{
              background: i % 2 === 0 ? 'transparent' : 'var(--bg-elev)'
            }}>
              <td style={{
                padding: '10px 16px',
                fontWeight: 500,
                opacity: 0.9
              }}>
                {metric.label}
              </td>
              {strategies.map((strategy, j) => {
                const value = strategy.data.metrics[metric.key]
                const formattedValue = formatMetric(value, metric.format)

                // Color coding for specific metrics
                let color = 'inherit'
                if (metric.key === 'totalReturnPct') {
                  color = value > 0 ? 'var(--pos)' : value < 0 ? 'var(--neg)' : 'inherit'
                } else if (metric.key === 'maxDrawdown') {
                  color = value > 20 ? 'var(--neg)' : value > 10 ? 'orange' : 'inherit'
                }

                return (
                  <td key={j} style={{
                    padding: '10px 16px',
                    textAlign: 'right',
                    fontFamily: 'var(--font-mono)',
                    fontWeight: 600,
                    color
                  }}>
                    {formattedValue}
                  </td>
                )
              })}
            </tr>
          ))}

          {/* Win Rate (calculated) */}
          <tr style={{
            background: metrics.length % 2 === 0 ? 'transparent' : 'var(--bg-elev)'
          }}>
            <td style={{
              padding: '10px 16px',
              fontWeight: 500,
              opacity: 0.9
            }}>
              Win Rate %
            </td>
            {strategies.map((strategy, j) => {
              const winRate = calculateWinRate(strategy.data)
              return (
                <td key={j} style={{
                  padding: '10px 16px',
                  textAlign: 'right',
                  fontFamily: 'var(--font-mono)',
                  fontWeight: 600
                }}>
                  {winRate !== '—' ? `${winRate}%` : winRate}
                </td>
              )
            })}
          </tr>
        </tbody>
      </table>

      {/* Comparison vs SPY (if showing multiple strategies) */}
      {strategies.length > 1 && spy && (
        <div style={{
          marginTop: 24,
          padding: 16,
          background: 'var(--bg-elev)',
          borderRadius: 8,
          border: '1px solid var(--border)'
        }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Outperformance vs SPY</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
            {strategies.filter(s => s.name !== 'SPY Benchmark').map((strategy, i) => {
              const strategyReturn = strategy.data.metrics.totalReturnPct || 0
              const spyReturn = spy.metrics.totalReturnPct || 0
              const outperformance = strategyReturn - spyReturn
              const isPositive = outperformance > 0

              return (
                <div key={i} style={{
                  padding: 12,
                  background: 'var(--bg-card)',
                  borderRadius: 8,
                  border: `1px solid ${isPositive ? 'var(--pos)' : 'var(--neg)'}`
                }}>
                  <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 4 }}>
                    {strategy.name}
                  </div>
                  <div style={{
                    fontSize: 20,
                    fontWeight: 700,
                    fontFamily: 'var(--font-mono)',
                    color: isPositive ? 'var(--pos)' : 'var(--neg)'
                  }}>
                    {isPositive ? '+' : ''}{outperformance.toFixed(2)}%
                  </div>
                  <div style={{ fontSize: 10, opacity: 0.6, marginTop: 4 }}>
                    {isPositive ? '✓ Beats SPY' : '✗ Trails SPY'}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Risk-adjusted performance note */}
      {strategies.length > 0 && (
        <div style={{
          marginTop: 16,
          padding: 12,
          background: 'var(--bg-elev)',
          borderRadius: 8,
          fontSize: 12,
          opacity: 0.7
        }}>
          <strong>Sharpe Ratio:</strong> Higher is better. Measures risk-adjusted return (return per unit of volatility).
          <br />
          <strong>Max Drawdown:</strong> Largest peak-to-trough decline. Lower is better.
          <br />
          <strong>Turnover:</strong> Total traded value / total deployed. Higher means more frequent trading.
        </div>
      )}
    </div>
  )
}
