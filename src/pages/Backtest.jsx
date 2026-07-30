import { useState, useEffect } from 'react'
import { useAuth } from '../lib/FirebaseAuthContext'
import { collection, getDocs, query, orderBy } from 'firebase/firestore'
import { db } from '../lib/firebase'
import { simulateEqualWeight, simulateRankWeighted, simulateSPYBenchmark } from '../lib/backtestEngine'
import BacktestChart from '../components/BacktestChart'
import BacktestStatsTable from '../components/BacktestStatsTable'
import BacktestTradeHistory from '../components/BacktestTradeHistory'

export default function Backtest() {
  const { currentUser } = useAuth()
  const [signals, setSignals] = useState([])
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedStrategy, setSelectedStrategy] = useState('all')

  useEffect(() => {
    if (!currentUser) {
      setLoading(false)
      return
    }

    loadBacktestData()
  }, [currentUser])

  async function loadBacktestData() {
    try {
      // Load all entry/exit signals from Firestore
      const signalsRef = collection(db, 'backtestSignals')
      const q = query(signalsRef, orderBy('timestamp', 'asc'))
      const snapshot = await getDocs(q)

      const allSignals = snapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      }))

      setSignals(allSignals)

      // TODO: Load historical price data
      // For now, using mock price data - replace with actual API calls
      const mockPriceData = {}

      // Run simulations
      const equalWeightResults = simulateEqualWeight(allSignals, mockPriceData)
      const rankWeightedResults = simulateRankWeighted(allSignals, mockPriceData)
      const spyResults = simulateSPYBenchmark(allSignals, mockPriceData)

      setResults({
        equalWeight: equalWeightResults,
        rankWeighted: rankWeightedResults,
        spy: spyResults
      })

      setLoading(false)
    } catch (error) {
      console.error('Failed to load backtest data:', error)
      setLoading(false)
    }
  }

  if (!currentUser) {
    return (
      <div style={{ padding: 24 }}>
        <h1>Backtest Performance</h1>
        <div style={{
          padding: 24,
          background: 'var(--bg-elev)',
          borderRadius: 12,
          textAlign: 'center',
          marginTop: 24
        }}>
          <p style={{ opacity: 0.7 }}>Please log in to view backtest results</p>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div style={{ padding: 24 }}>
        <h1>Backtest Performance</h1>
        <div style={{ padding: 24, textAlign: 'center' }}>
          <p>Loading backtest data...</p>
        </div>
      </div>
    )
  }

  if (!results || signals.length === 0) {
    return (
      <div style={{ padding: 24 }}>
        <h1>Backtest Performance</h1>
        <div style={{
          padding: 24,
          background: 'var(--bg-elev)',
          borderRadius: 12,
          textAlign: 'center',
          marginTop: 24
        }}>
          <h3 style={{ marginBottom: 12 }}>No Signals Yet</h3>
          <p style={{ opacity: 0.7, marginBottom: 20 }}>
            Backtest results will appear once you start tracking entry and exit signals.
          </p>
          <p style={{ fontSize: 13, opacity: 0.6 }}>
            Entry signals are logged when a stock enters the top 20 or becomes "Attractive" or "Promising".<br />
            Exit signals are logged when a stock drops out of the top 20 or receives a "SELL" recommendation.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div style={{ padding: 24, maxWidth: 1400, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ marginBottom: 8 }}>Backtest Performance</h1>
        <p style={{ opacity: 0.7, fontSize: 14 }}>
          How would your portfolio have performed following these signals?
        </p>
      </div>

      {/* Honesty Disclaimer */}
      <div style={{
        background: 'color-mix(in srgb, var(--accent) 10%, transparent)',
        border: '1px solid var(--accent)',
        borderRadius: 12,
        padding: 16,
        marginBottom: 24,
        fontSize: 13
      }}>
        <strong>⚠️ Important Disclaimers:</strong>
        <ul style={{ marginTop: 8, marginBottom: 0, paddingLeft: 20, opacity: 0.9 }}>
          <li><strong>Past performance does not predict future returns.</strong> These are simulations based on historical signals.</li>
          <li><strong>Assumes perfect execution</strong> at signal prices with no slippage, commissions, or taxes.</li>
          <li><strong>Survivorship bias:</strong> Only includes stocks that existed during the signal period.</li>
          <li><strong>Signal timing:</strong> Real-world entry/exit may differ from exact signal timestamps.</li>
          <li><strong>This is research data, not investment advice.</strong> Consult a financial advisor before making decisions.</li>
        </ul>
      </div>

      {/* Strategy Selector */}
      <div style={{ marginBottom: 24, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          className={`tab ${selectedStrategy === 'all' ? 'active' : ''}`}
          onClick={() => setSelectedStrategy('all')}
          style={{ fontSize: 13 }}
        >
          All Strategies
        </button>
        <button
          className={`tab ${selectedStrategy === 'equalWeight' ? 'active' : ''}`}
          onClick={() => setSelectedStrategy('equalWeight')}
          style={{ fontSize: 13 }}
        >
          Equal-Weight
        </button>
        <button
          className={`tab ${selectedStrategy === 'rankWeighted' ? 'active' : ''}`}
          onClick={() => setSelectedStrategy('rankWeighted')}
          style={{ fontSize: 13 }}
        >
          Rank-Weighted
        </button>
        <button
          className={`tab ${selectedStrategy === 'spy' ? 'active' : ''}`}
          onClick={() => setSelectedStrategy('spy')}
          style={{ fontSize: 13 }}
        >
          SPY Benchmark
        </button>
      </div>

      {/* Performance Chart */}
      <div style={{
        background: 'var(--bg-card)',
        borderRadius: 12,
        padding: 20,
        marginBottom: 24,
        border: '1px solid var(--border)'
      }}>
        <h2 style={{ fontSize: 18, marginBottom: 16 }}>Cumulative Returns</h2>
        <BacktestChart results={results} selectedStrategy={selectedStrategy} />
      </div>

      {/* Stats Tables */}
      <div style={{
        background: 'var(--bg-card)',
        borderRadius: 12,
        padding: 20,
        border: '1px solid var(--border)'
      }}>
        <h2 style={{ fontSize: 18, marginBottom: 16 }}>Performance Metrics</h2>
        <BacktestStatsTable results={results} selectedStrategy={selectedStrategy} />
      </div>

      {/* Signal Summary */}
      <div style={{
        background: 'var(--bg-card)',
        borderRadius: 12,
        padding: 20,
        marginTop: 24,
        border: '1px solid var(--border)'
      }}>
        <h2 style={{ fontSize: 18, marginBottom: 16 }}>Signal Summary</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
          <div>
            <div style={{ fontSize: 12, opacity: 0.6, marginBottom: 4 }}>Total Signals</div>
            <div style={{ fontSize: 24, fontWeight: 600 }}>{signals.length}</div>
          </div>
          <div>
            <div style={{ fontSize: 12, opacity: 0.6, marginBottom: 4 }}>Entry Signals</div>
            <div style={{ fontSize: 24, fontWeight: 600, color: 'var(--pos)' }}>
              {signals.filter(s => s.type === 'entry').length}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, opacity: 0.6, marginBottom: 4 }}>Exit Signals</div>
            <div style={{ fontSize: 24, fontWeight: 600, color: 'var(--neg)' }}>
              {signals.filter(s => s.type === 'exit').length}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, opacity: 0.6, marginBottom: 4 }}>Unique Stocks</div>
            <div style={{ fontSize: 24, fontWeight: 600 }}>
              {new Set(signals.map(s => s.ticker)).size}
            </div>
          </div>
        </div>
      </div>

      {/* Trade History Drill-Down */}
      <div style={{
        background: 'var(--bg-card)',
        borderRadius: 12,
        padding: 20,
        marginTop: 24,
        border: '1px solid var(--border)'
      }}>
        <h2 style={{ fontSize: 18, marginBottom: 16 }}>Trade History</h2>
        <BacktestTradeHistory results={results} selectedStrategy={selectedStrategy} />
      </div>
    </div>
  )
}
