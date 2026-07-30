import { useState } from 'react'
import { useData } from '../lib/useData'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio'
import { useAuth } from '../lib/FirebaseAuthContext'
import { Loading } from '../components/Bits'
import { ActionPill } from '../components/ActionGuidance'
import GrowthChart from '../components/GrowthChart'
import StockDetailModal from '../components/StockDetailModal'
import { getRecommendation } from '../lib/recommendation'
import { benchmarkAlternative, portfolioGrowthSeries, portfolioVsBenchmark } from '../lib/portfolioPerformance'

const money = (value, digits = 0) =>
  value == null ? '—' : `$${value.toLocaleString('en-US', { maximumFractionDigits: digits })}`

const signedPct = (value, digits = 1) =>
  value == null ? '—' : `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`

const moveColor = (value) => (value == null ? undefined : value >= 0 ? 'var(--pos)' : 'var(--neg)')

function Move({ value, digits = 1 }) {
  return <span className="mono" style={{ color: moveColor(value) }}>{signedPct(value, digits)}</span>
}

export default function Portfolio() {
  const { currentUser, userProfile, logout } = useAuth()
  const { data, loading: dataLoading } = useData('advisor.json')
  const { positions, loading: portfolioLoading, addPosition, removePosition, exportPortfolio } = useFirebasePortfolio()

  const [showAddForm, setShowAddForm] = useState(false)
  const [formData, setFormData] = useState({ ticker: '', shares: '', costBasis: '', purchaseDate: new Date().toISOString().split('T')[0] })
  const [viewMode, setViewMode] = useState('holdings')
  const [selectedStock, setSelectedStock] = useState(null)

  if (dataLoading || portfolioLoading) return <Loading />

  const research = data?.research || []
  const benchmarkHistory = data?.benchmark_history
  const priceData = Object.fromEntries(research.filter((row) => row.ticker).map((row) => [row.ticker, row]))

  const portfolioStats = positions.reduce((acc, pos) => {
    const current = priceData[pos.ticker]
    const currentPrice = current?.price || pos.costBasis
    const totalCost = pos.shares * pos.costBasis
    const currentValue = pos.shares * currentPrice
    const gain = currentValue - totalCost
    const enriched = {
      ...pos,
      currentPrice,
      totalCost,
      currentValue,
      gain,
      gainPct: (gain / totalCost) * 100,
      priceInfo: current,
      recommendation: current ? getRecommendation(current) : null,
      versusBenchmark: benchmarkAlternative({ ...pos, currentValue }, benchmarkHistory),
    }
    return {
      totalCost: acc.totalCost + totalCost,
      totalValue: acc.totalValue + currentValue,
      totalGain: acc.totalGain + gain,
      positions: [...acc.positions, enriched],
    }
  }, { totalCost: 0, totalValue: 0, totalGain: 0, positions: [] })

  const totalGainPct = portfolioStats.totalCost > 0
    ? ((portfolioStats.totalValue - portfolioStats.totalCost) / portfolioStats.totalCost) * 100
    : 0

  const versusIndex = portfolioVsBenchmark(portfolioStats.positions, benchmarkHistory)
  const growth = portfolioGrowthSeries(portfolioStats.positions, priceData, benchmarkHistory)
  const actionable = portfolioStats.positions.filter(
    (pos) => pos.recommendation && pos.recommendation.action !== 'HOLD')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!formData.ticker || !formData.shares || !formData.costBasis) {
      alert('Please fill in all required fields')
      return
    }
    addPosition(formData.ticker, formData.shares, formData.costBasis, formData.purchaseDate)
    setFormData({ ticker: '', shares: '', costBasis: '', purchaseDate: new Date().toISOString().split('T')[0] })
    setShowAddForm(false)
  }

  const basis = data?.hypothetical_basis || 500

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">My <span className="accent">Portfolio</span></h1>
          <p className="page-sub">
            Holdings, action guidance, and how the same money would have done in the S&P 500.
            Signed in as {userProfile?.displayName} ({currentUser?.email}).
          </p>
        </div>
        <div>
          <button className="chip button-chip" onClick={logout} style={{ marginRight: 8 }}>Logout</button>
          <button className="chip button-chip" onClick={exportPortfolio}>Export</button>
        </div>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 20 }}>
        <div className="card kpi">
          <div className="kpi-label">Total Value</div>
          <div className="kpi-value">{money(portfolioStats.totalValue)}</div>
          <div className="kpi-note">{positions.length} positions · {money(portfolioStats.totalCost)} invested</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Total Gain/Loss</div>
          <div className="kpi-value" style={{ color: moveColor(portfolioStats.totalGain) }}>
            {portfolioStats.totalGain >= 0 ? '+' : '−'}{money(Math.abs(portfolioStats.totalGain))}
          </div>
          <div className="kpi-note" style={{ color: moveColor(totalGainPct) }}>{signedPct(totalGainPct, 2)}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Vs S&P 500</div>
          <div className="kpi-value" style={{ color: moveColor(versusIndex?.dollarsAhead) }}>
            {versusIndex
              ? `${versusIndex.dollarsAhead >= 0 ? '+' : '−'}${money(Math.abs(versusIndex.dollarsAhead))}`
              : '—'}
          </div>
          <div className="kpi-note">
            {versusIndex
              ? `${signedPct(versusIndex.excessReturnPct)} against the index on ${versusIndex.comparable} position${versusIndex.comparable === 1 ? '' : 's'}`
              : 'Add a purchase date inside the charted window'}
          </div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Action Needed</div>
          <div className="kpi-value" style={{ color: actionable.length ? 'var(--warn)' : 'var(--pos)' }}>
            {actionable.length}
          </div>
          <div className="kpi-note">
            {actionable.length
              ? actionable.map((pos) => pos.ticker).join(', ')
              : 'No multi-factor deterioration'}
          </div>
        </div>
      </div>

      {actionable.length > 0 && (
        <div className="card card-pad" style={{ marginBottom: 20 }}>
          <div className="sec-label">Suggested actions</div>
          <div style={{ display: 'grid', gap: 10 }}>
            {actionable.map((pos) => (
              <div key={pos.id || pos.ticker} style={{
                display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap',
                paddingBottom: 10, borderBottom: '1px solid var(--border)',
              }}>
                <ActionPill recommendation={pos.recommendation} />
                <b className="mono">{pos.ticker}</b>
                <span style={{ color: 'var(--text-dim)', fontSize: 13, flex: 1, minWidth: 200 }}>
                  {pos.recommendation.summary}
                </span>
                {pos.recommendation.suggestedTrimPct > 0 && (
                  <span className="mono" style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                    {((pos.shares * pos.recommendation.suggestedTrimPct) / 100).toFixed(2)} of {pos.shares} shares
                    {' '}≈ {money((pos.currentValue * pos.recommendation.suggestedTrimPct) / 100)}
                  </span>
                )}
                <button className="chip button-chip" onClick={() => setSelectedStock(pos)}>Why</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {growth && (
        <div className="card card-pad" style={{ marginBottom: 20 }}>
          <GrowthChart
            dates={growth.dates}
            series={[
              { label: 'My holdings', values: growth.holdings, color: 'var(--series-stock)', emphasis: true },
              { label: 'Same dollars in the S&P 500', values: growth.benchmark, color: 'var(--series-benchmark)', dashed: true },
            ]}
            title="Holdings vs the S&P 500"
            caption={`Both lines start from what these holdings were worth at the beginning of the window. Covers ${growth.trackedTickers.length} position${growth.trackedTickers.length === 1 ? '' : 's'} with published price history${growth.untrackedCount ? `; ${growth.untrackedCount} not in the current research universe` : ''}.`}
          />
        </div>
      )}

      <div className="filters" style={{ marginBottom: 20 }}>
        <button className={`tab ${viewMode === 'holdings' ? 'active' : ''}`} onClick={() => setViewMode('holdings')}>
          My Holdings
        </button>
        <button className={`tab ${viewMode === 'benchmark' ? 'active' : ''}`} onClick={() => setViewMode('benchmark')}>
          Vs S&P 500
        </button>
        <button className={`tab ${viewMode === 'hypothetical' ? 'active' : ''}`} onClick={() => setViewMode('hypothetical')}>
          ${basis} Calculator
        </button>
        <button className="tab active" onClick={() => setShowAddForm(!showAddForm)} style={{ marginLeft: 'auto' }}>
          + Add Position
        </button>
      </div>

      {showAddForm && (
        <div className="card" style={{ marginBottom: 20, padding: 20 }}>
          <h3 style={{ marginBottom: 16 }}>Add New Position</h3>
          <form onSubmit={handleSubmit} style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr) auto', gap: 12, alignItems: 'end' }}>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Ticker</label>
              <input type="text" placeholder="AAPL" value={formData.ticker} required
                onChange={(e) => setFormData({ ...formData, ticker: e.target.value.toUpperCase() })} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Shares</label>
              <input type="number" step="0.001" placeholder="10" value={formData.shares} required
                onChange={(e) => setFormData({ ...formData, shares: e.target.value })} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Cost Basis</label>
              <input type="number" step="0.01" placeholder="150.00" value={formData.costBasis} required
                onChange={(e) => setFormData({ ...formData, costBasis: e.target.value })} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Purchase Date</label>
              <input type="date" value={formData.purchaseDate} required
                onChange={(e) => setFormData({ ...formData, purchaseDate: e.target.value })} />
            </div>
            <div><button type="submit" className="tab active">Add</button></div>
          </form>
        </div>
      )}

      {viewMode === 'holdings' && (
        <div className="card card-pad table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ticker</th><th>Company</th><th>Signal</th>
                <th className="num">Shares</th><th className="num">Cost</th><th className="num">Price</th>
                <th className="num">Value</th><th className="num">Gain/Loss</th><th className="num">Return</th>
                <th className="num">Score</th><th className="num">20D</th><th>Action</th>
              </tr>
            </thead>
            <tbody>
              {portfolioStats.positions.map((pos) => (
                <tr key={pos.id || pos.ticker}>
                  <td className="mono">{pos.ticker}</td>
                  <td>{pos.priceInfo?.name || '—'}</td>
                  <td><ActionPill recommendation={pos.recommendation} /></td>
                  <td className="mono num">{pos.shares}</td>
                  <td className="mono num">${pos.costBasis.toFixed(2)}</td>
                  <td className="mono num">${pos.currentPrice.toFixed(2)}</td>
                  <td className="mono num">{money(pos.currentValue)}</td>
                  <td className="mono num" style={{ color: moveColor(pos.gain) }}>
                    {pos.gain >= 0 ? '+' : '−'}{money(Math.abs(pos.gain))}
                  </td>
                  <td className="num"><Move value={pos.gainPct} /></td>
                  <td className="mono num score-cell">{pos.priceInfo?.score ?? '—'}</td>
                  <td className="num"><Move value={pos.priceInfo?.technical_detail?.return_20d} /></td>
                  <td style={{ display: 'flex', gap: 6 }}>
                    {pos.priceInfo && (
                      <button className="chip button-chip" onClick={() => setSelectedStock(pos)}>Details</button>
                    )}
                    <button className="chip button-chip" onClick={() => removePosition(pos.id)}>Remove</button>
                  </td>
                </tr>
              ))}
              {portfolioStats.positions.length === 0 && (
                <tr>
                  <td colSpan="12" style={{ textAlign: 'center', padding: 40, opacity: 0.5 }}>
                    No positions yet. Click "+ Add Position" to start tracking.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {viewMode === 'benchmark' && (
        <div className="card card-pad table-wrap">
          <div className="callout" style={{ margin: '0 0 16px' }}>
            <strong>The only fair comparison:</strong> what each position is worth now against
            what the identical dollars, invested on the identical day, would be worth in the S&P 500.
          </div>
          <table>
            <thead>
              <tr>
                <th>Ticker</th><th className="num">Purchased</th><th className="num">Invested</th>
                <th className="num">Now</th><th className="num">Return</th>
                <th className="num">S&P instead</th><th className="num">S&P return</th>
                <th className="num">Dollars ahead</th>
              </tr>
            </thead>
            <tbody>
              {portfolioStats.positions.map((pos) => (
                <tr key={pos.id || pos.ticker}>
                  <td className="mono">{pos.ticker}</td>
                  <td className="mono num">{pos.purchaseDate || '—'}</td>
                  <td className="mono num">{money(pos.totalCost)}</td>
                  <td className="mono num">{money(pos.currentValue)}</td>
                  <td className="num"><Move value={pos.gainPct} /></td>
                  <td className="mono num">{pos.versusBenchmark ? money(pos.versusBenchmark.value) : '—'}</td>
                  <td className="num">
                    {pos.versusBenchmark ? <Move value={pos.versusBenchmark.gainPct} /> : <span className="mono">—</span>}
                  </td>
                  <td className="mono num" style={{ color: moveColor(pos.versusBenchmark ? pos.currentValue - pos.versusBenchmark.value : null) }}>
                    {pos.versusBenchmark
                      ? `${pos.currentValue - pos.versusBenchmark.value >= 0 ? '+' : '−'}${money(Math.abs(pos.currentValue - pos.versusBenchmark.value))}`
                      : '—'}
                  </td>
                </tr>
              ))}
              {versusIndex && (
                <tr style={{ fontWeight: 600 }}>
                  <td className="mono">TOTAL</td>
                  <td className="num">—</td>
                  <td className="mono num">{money(versusIndex.invested)}</td>
                  <td className="mono num">{money(versusIndex.holdingsValue)}</td>
                  <td className="num"><Move value={versusIndex.holdingsReturnPct} /></td>
                  <td className="mono num">{money(versusIndex.benchmarkValue)}</td>
                  <td className="num"><Move value={versusIndex.benchmarkReturnPct} /></td>
                  <td className="mono num" style={{ color: moveColor(versusIndex.dollarsAhead) }}>
                    {versusIndex.dollarsAhead >= 0 ? '+' : '−'}{money(Math.abs(versusIndex.dollarsAhead))}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <p style={{ color: 'var(--text-faint)', fontSize: 12, marginTop: 12 }}>
            Positions bought before the published benchmark window show “—” rather than being
            compared against the wrong entry price.
          </p>
        </div>
      )}

      {viewMode === 'hypothetical' && (
        <div className="card card-pad table-wrap">
          <div className="callout" style={{ margin: '0 0 16px' }}>
            <strong>Hypothetical returns:</strong> ${basis} put into each researched company at the
            start of the charted window, against the same ${basis} in the S&P 500.
          </div>
          <table>
            <thead>
              <tr>
                <th>Ticker</th><th>Company</th><th className="num">Price</th>
                <th className="num">${basis} would be</th><th className="num">Return</th>
                <th className="num">S&P instead</th><th className="num">Dollars ahead</th><th>Action</th>
              </tr>
            </thead>
            <tbody>
              {research.map((row) => (
                <tr key={row.ticker}>
                  <td className="mono">{row.ticker}</td>
                  <td>{row.name}</td>
                  <td className="mono num">{row.price ? `$${row.price.toFixed(2)}` : '—'}</td>
                  <td className="mono num">{row.hypothetical ? money(row.hypothetical.stock_value) : '—'}</td>
                  <td className="num">
                    {row.hypothetical ? <Move value={row.hypothetical.stock_return_pct} /> : <span className="mono">—</span>}
                  </td>
                  <td className="mono num">{row.hypothetical ? money(row.hypothetical.benchmark_value) : '—'}</td>
                  <td className="mono num" style={{ color: moveColor(row.hypothetical?.dollars_ahead) }}>
                    {row.hypothetical
                      ? `${row.hypothetical.dollars_ahead >= 0 ? '+' : '−'}${money(Math.abs(row.hypothetical.dollars_ahead))}`
                      : '—'}
                  </td>
                  <td><button className="chip button-chip" onClick={() => setSelectedStock(row)}>Details</button></td>
                </tr>
              ))}
              {research.length === 0 && (
                <tr><td colSpan="8" style={{ textAlign: 'center', padding: 40, opacity: 0.5 }}>No research data yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {selectedStock && (
        <StockDetailModal
          stock={selectedStock.priceInfo || selectedStock}
          position={selectedStock.shares ? { shares: selectedStock.shares, price: selectedStock.currentPrice } : null}
          benchmarkHistory={benchmarkHistory}
          onClose={() => setSelectedStock(null)}
        />
      )}
    </>
  )
}
