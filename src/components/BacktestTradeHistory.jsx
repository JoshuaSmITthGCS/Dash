import { useState, useMemo } from 'react'
import { formatMetric } from '../lib/backtestEngine'

/**
 * Trade history drill-down component
 * Shows detailed entry/exit history for a specific stock or all stocks
 */
export default function BacktestTradeHistory({ results, selectedStrategy }) {
  const [selectedTicker, setSelectedTicker] = useState('all')

  // Extract trades from results
  const trades = useMemo(() => {
    if (!results) return []

    let allTrades = []

    if (selectedStrategy === 'all' || selectedStrategy === 'equalWeight') {
      allTrades = allTrades.concat(results.equalWeight.trades.map(t => ({ ...t, strategy: 'Equal-Weight' })))
    }

    if (selectedStrategy === 'all' || selectedStrategy === 'rankWeighted') {
      allTrades = allTrades.concat(results.rankWeighted.trades.map(t => ({ ...t, strategy: 'Rank-Weighted' })))
    }

    if (selectedStrategy === 'all' || selectedStrategy === 'spy') {
      allTrades = allTrades.concat(results.spy.trades.map(t => ({ ...t, strategy: 'SPY Benchmark' })))
    }

    // Sort by date (most recent first)
    allTrades.sort((a, b) => new Date(b.date) - new Date(a.date))

    return allTrades
  }, [results, selectedStrategy])

  // Get unique tickers
  const tickers = useMemo(() => {
    const uniqueTickers = [...new Set(trades.map(t => t.ticker))]
    return uniqueTickers.sort()
  }, [trades])

  // Filter trades by selected ticker
  const filteredTrades = selectedTicker === 'all'
    ? trades
    : trades.filter(t => t.ticker === selectedTicker)

  // Calculate per-stock stats
  const stockStats = useMemo(() => {
    const stats = {}

    trades.forEach(trade => {
      if (!stats[trade.ticker]) {
        stats[trade.ticker] = {
          ticker: trade.ticker,
          numTrades: 0,
          totalGain: 0,
          totalDeployed: 0,
          wins: 0,
          losses: 0
        }
      }

      if (trade.type === 'BUY') {
        stats[trade.ticker].totalDeployed += trade.value
      } else if (trade.type === 'SELL') {
        stats[trade.ticker].numTrades++
        stats[trade.ticker].totalGain += trade.gain || 0
        if ((trade.gain || 0) > 0) {
          stats[trade.ticker].wins++
        } else if ((trade.gain || 0) < 0) {
          stats[trade.ticker].losses++
        }
      }
    })

    // Convert to array and calculate percentages
    return Object.values(stats)
      .filter(s => s.numTrades > 0) // Only include stocks with completed trades
      .map(s => ({
        ...s,
        avgGain: s.numTrades > 0 ? s.totalGain / s.numTrades : 0,
        totalReturnPct: s.totalDeployed > 0 ? (s.totalGain / s.totalDeployed) * 100 : 0,
        winRate: s.numTrades > 0 ? (s.wins / s.numTrades) * 100 : 0
      }))
      .sort((a, b) => b.totalReturnPct - a.totalReturnPct)
  }, [trades])

  if (!results || trades.length === 0) {
    return (
      <div style={{ padding: 20, textAlign: 'center', opacity: 0.6 }}>
        No trade history available
      </div>
    )
  }

  return (
    <div>
      {/* Stock selector */}
      <div style={{ marginBottom: 20 }}>
        <label style={{ display: 'block', marginBottom: 8, fontSize: 13, fontWeight: 600 }}>
          Filter by stock:
        </label>
        <select
          value={selectedTicker}
          onChange={(e) => setSelectedTicker(e.target.value)}
          style={{
            padding: '8px 12px',
            borderRadius: 6,
            border: '1px solid var(--border)',
            background: 'var(--bg-elev)',
            fontSize: 13,
            minWidth: 200
          }}
        >
          <option value="all">All Stocks ({tickers.length})</option>
          {tickers.map(ticker => (
            <option key={ticker} value={ticker}>{ticker}</option>
          ))}
        </select>
      </div>

      {/* Per-stock summary (if showing all stocks) */}
      {selectedTicker === 'all' && stockStats.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 12 }}>Stock Performance Summary</h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: 13
            }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: '10px 12px', borderBottom: '2px solid var(--border)', fontSize: 12, opacity: 0.8 }}>
                    Ticker
                  </th>
                  <th style={{ textAlign: 'right', padding: '10px 12px', borderBottom: '2px solid var(--border)', fontSize: 12, opacity: 0.8 }}>
                    Trades
                  </th>
                  <th style={{ textAlign: 'right', padding: '10px 12px', borderBottom: '2px solid var(--border)', fontSize: 12, opacity: 0.8 }}>
                    Total Gain
                  </th>
                  <th style={{ textAlign: 'right', padding: '10px 12px', borderBottom: '2px solid var(--border)', fontSize: 12, opacity: 0.8 }}>
                    Return %
                  </th>
                  <th style={{ textAlign: 'right', padding: '10px 12px', borderBottom: '2px solid var(--border)', fontSize: 12, opacity: 0.8 }}>
                    Win Rate
                  </th>
                  <th style={{ textAlign: 'right', padding: '10px 12px', borderBottom: '2px solid var(--border)', fontSize: 12, opacity: 0.8 }}>
                    W/L
                  </th>
                </tr>
              </thead>
              <tbody>
                {stockStats.map((stock, i) => (
                  <tr key={stock.ticker} style={{
                    background: i % 2 === 0 ? 'transparent' : 'var(--bg-elev)',
                    cursor: 'pointer'
                  }}
                    onClick={() => setSelectedTicker(stock.ticker)}
                  >
                    <td style={{ padding: '10px 12px', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                      {stock.ticker}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                      {stock.numTrades}
                    </td>
                    <td style={{
                      padding: '10px 12px',
                      textAlign: 'right',
                      fontFamily: 'var(--font-mono)',
                      color: stock.totalGain > 0 ? 'var(--pos)' : stock.totalGain < 0 ? 'var(--neg)' : 'inherit'
                    }}>
                      {formatMetric(stock.totalGain, 'currency')}
                    </td>
                    <td style={{
                      padding: '10px 12px',
                      textAlign: 'right',
                      fontFamily: 'var(--font-mono)',
                      fontWeight: 600,
                      color: stock.totalReturnPct > 0 ? 'var(--pos)' : stock.totalReturnPct < 0 ? 'var(--neg)' : 'inherit'
                    }}>
                      {formatMetric(stock.totalReturnPct, 'percent')}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                      {stock.winRate.toFixed(1)}%
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                      {stock.wins}/{stock.losses}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Trade log */}
      <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 12 }}>
        {selectedTicker === 'all' ? 'All Trades' : `${selectedTicker} Trade History`}
      </h3>
      <div style={{ overflowX: 'auto' }}>
        <table style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: 13
        }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '10px 12px', borderBottom: '2px solid var(--border)', fontSize: 12, opacity: 0.8 }}>
                Date
              </th>
              <th style={{ textAlign: 'left', padding: '10px 12px', borderBottom: '2px solid var(--border)', fontSize: 12, opacity: 0.8 }}>
                Ticker
              </th>
              <th style={{ textAlign: 'left', padding: '10px 12px', borderBottom: '2px solid var(--border)', fontSize: 12, opacity: 0.8 }}>
                Type
              </th>
              <th style={{ textAlign: 'right', padding: '10px 12px', borderBottom: '2px solid var(--border)', fontSize: 12, opacity: 0.8 }}>
                Price
              </th>
              <th style={{ textAlign: 'right', padding: '10px 12px', borderBottom: '2px solid var(--border)', fontSize: 12, opacity: 0.8 }}>
                Shares
              </th>
              <th style={{ textAlign: 'right', padding: '10px 12px', borderBottom: '2px solid var(--border)', fontSize: 12, opacity: 0.8 }}>
                Value
              </th>
              <th style={{ textAlign: 'right', padding: '10px 12px', borderBottom: '2px solid var(--border)', fontSize: 12, opacity: 0.8 }}>
                Gain
              </th>
              <th style={{ textAlign: 'right', padding: '10px 12px', borderBottom: '2px solid var(--border)', fontSize: 12, opacity: 0.8 }}>
                Return %
              </th>
              {selectedStrategy === 'all' && (
                <th style={{ textAlign: 'left', padding: '10px 12px', borderBottom: '2px solid var(--border)', fontSize: 12, opacity: 0.8 }}>
                  Strategy
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {filteredTrades.map((trade, i) => (
              <tr key={i} style={{
                background: i % 2 === 0 ? 'transparent' : 'var(--bg-elev)'
              }}>
                <td style={{ padding: '10px 12px', fontSize: 12, opacity: 0.8 }}>
                  {new Date(trade.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                </td>
                <td style={{ padding: '10px 12px', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                  {trade.ticker}
                </td>
                <td style={{ padding: '10px 12px' }}>
                  <span className="chip" style={{
                    background: trade.type === 'BUY' ? 'var(--pos)' : 'var(--neg)',
                    color: 'white',
                    fontSize: 11,
                    padding: '2px 8px'
                  }}>
                    {trade.type}
                  </span>
                </td>
                <td style={{ padding: '10px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                  {formatMetric(trade.price, 'currency')}
                </td>
                <td style={{ padding: '10px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                  {trade.shares.toFixed(2)}
                </td>
                <td style={{ padding: '10px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                  {formatMetric(trade.value, 'currency')}
                </td>
                <td style={{
                  padding: '10px 12px',
                  textAlign: 'right',
                  fontFamily: 'var(--font-mono)',
                  color: trade.type === 'SELL' ? (trade.gain > 0 ? 'var(--pos)' : trade.gain < 0 ? 'var(--neg)' : 'inherit') : 'inherit'
                }}>
                  {trade.type === 'SELL' ? formatMetric(trade.gain, 'currency') : '—'}
                </td>
                <td style={{
                  padding: '10px 12px',
                  textAlign: 'right',
                  fontFamily: 'var(--font-mono)',
                  fontWeight: 600,
                  color: trade.type === 'SELL' ? (trade.gainPct > 0 ? 'var(--pos)' : trade.gainPct < 0 ? 'var(--neg)' : 'inherit') : 'inherit'
                }}>
                  {trade.type === 'SELL' ? formatMetric(trade.gainPct, 'percent') : '—'}
                </td>
                {selectedStrategy === 'all' && (
                  <td style={{ padding: '10px 12px', fontSize: 12, opacity: 0.7 }}>
                    {trade.strategy}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {filteredTrades.length === 0 && (
        <div style={{ padding: 20, textAlign: 'center', opacity: 0.6 }}>
          No trades found for {selectedTicker}
        </div>
      )}
    </div>
  )
}
