import { useState } from 'react'
import { useData } from '../lib/useData'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio'
import { useAuth } from '../lib/FirebaseAuthContext'
import { Loading } from '../components/Bits'

export default function Portfolio() {
  const { currentUser, userProfile, logout } = useAuth()
  const { data, loading: dataLoading } = useData('advisor.json')
  const { positions, loading: portfolioLoading, addPosition, removePosition, exportPortfolio } = useFirebasePortfolio()

  const [showAddForm, setShowAddForm] = useState(false)
  const [formData, setFormData] = useState({ ticker: '', shares: '', costBasis: '', purchaseDate: new Date().toISOString().split('T')[0] })
  const [viewMode, setViewMode] = useState('percentage') // 'percentage' or 'hypothetical'

  if (dataLoading || portfolioLoading) return <Loading />

  const priceData = {}
  if (data?.research) {
    data.research.forEach(stock => {
      if (stock.ticker && stock.price) {
        priceData[stock.ticker] = {
          price: stock.price,
          changes: stock.technical_detail || {},
          ...stock
        }
      }
    })
  }

  // Calculate portfolio metrics
  const portfolioStats = positions.reduce((acc, pos) => {
    const current = priceData[pos.ticker]
    const currentPrice = current?.price || pos.costBasis
    const totalCost = pos.shares * pos.costBasis
    const currentValue = pos.shares * currentPrice
    const gain = currentValue - totalCost
    const gainPct = ((currentValue - totalCost) / totalCost) * 100

    return {
      totalCost: acc.totalCost + totalCost,
      totalValue: acc.totalValue + currentValue,
      totalGain: acc.totalGain + gain,
      positions: [...acc.positions, {
        ...pos,
        currentPrice,
        totalCost,
        currentValue,
        gain,
        gainPct,
        priceInfo: current
      }]
    }
  }, { totalCost: 0, totalValue: 0, totalGain: 0, positions: [] })

  const totalGainPct = portfolioStats.totalCost > 0
    ? ((portfolioStats.totalValue - portfolioStats.totalCost) / portfolioStats.totalCost) * 100
    : 0

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

  // Calculate hypothetical $500 returns for stocks
  const calculate500Returns = (ticker) => {
    const stock = priceData[ticker]
    if (!stock?.price || !stock.technical_detail) return {}

    const shares = 500 / stock.price
    return {
      '1d': stock.technical_detail.return_1d ? (shares * stock.price * (stock.technical_detail.return_1d / 100)) : null,
      '5d': stock.technical_detail.return_5d ? (shares * stock.price * (stock.technical_detail.return_5d / 100)) : null,
      '20d': stock.technical_detail.return_20d ? (shares * stock.price * (stock.technical_detail.return_20d / 100)) : null,
      '3m': stock.technical_detail.return_60d ? (shares * stock.price * (stock.technical_detail.return_60d / 100)) : null,
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">My <span className="accent">Portfolio</span></h1>
          <p className="page-sub">Track your investments and performance. Logged in as: {userProfile?.displayName} ({currentUser?.email})</p>
        </div>
        <div>
          <button className="chip button-chip" onClick={logout} style={{ marginRight: 8 }}>
            Logout
          </button>
          <button className="chip button-chip" onClick={exportPortfolio}>
            Export
          </button>
        </div>
      </div>

      {/* Portfolio Summary */}
      <div className="grid grid-4" style={{ marginBottom: 28 }}>
        <div className="card kpi">
          <div className="kpi-label">Total Value</div>
          <div className="kpi-value">${portfolioStats.totalValue.toLocaleString('en-US', { maximumFractionDigits: 0 })}</div>
          <div className="kpi-note">Current market value</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Total Cost</div>
          <div className="kpi-value">${portfolioStats.totalCost.toLocaleString('en-US', { maximumFractionDigits: 0 })}</div>
          <div className="kpi-note">Total invested</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Total Gain/Loss</div>
          <div className="kpi-value" style={{ color: portfolioStats.totalGain >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
            {portfolioStats.totalGain >= 0 ? '+' : ''}${portfolioStats.totalGain.toLocaleString('en-US', { maximumFractionDigits: 0 })}
          </div>
          <div className="kpi-note" style={{ color: totalGainPct >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
            {totalGainPct >= 0 ? '+' : ''}{totalGainPct.toFixed(2)}%
          </div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Positions</div>
          <div className="kpi-value">{positions.length}</div>
          <div className="kpi-note">{new Set(positions.map(p => p.ticker)).size} unique stocks</div>
        </div>
      </div>

      {/* View Mode Toggle */}
      <div className="filters" style={{ marginBottom: 20 }}>
        <button
          className={`tab ${viewMode === 'percentage' ? 'active' : ''}`}
          onClick={() => setViewMode('percentage')}
        >
          My Holdings
        </button>
        <button
          className={`tab ${viewMode === 'hypothetical' ? 'active' : ''}`}
          onClick={() => setViewMode('hypothetical')}
        >
          $500 Calculator
        </button>
        <button className="tab active" onClick={() => setShowAddForm(!showAddForm)} style={{ marginLeft: 'auto' }}>
          + Add Position
        </button>
      </div>

      {/* Add Position Form */}
      {showAddForm && (
        <div className="card" style={{ marginBottom: 20, padding: 20 }}>
          <h3 style={{ marginBottom: 16 }}>Add New Position</h3>
          <form onSubmit={handleSubmit} style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr) auto', gap: 12, alignItems: 'end' }}>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Ticker</label>
              <input
                type="text"
                placeholder="AAPL"
                value={formData.ticker}
                onChange={(e) => setFormData({ ...formData, ticker: e.target.value.toUpperCase() })}
                required
              />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Shares</label>
              <input
                type="number"
                step="0.001"
                placeholder="10"
                value={formData.shares}
                onChange={(e) => setFormData({ ...formData, shares: e.target.value })}
                required
              />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Cost Basis</label>
              <input
                type="number"
                step="0.01"
                placeholder="150.00"
                value={formData.costBasis}
                onChange={(e) => setFormData({ ...formData, costBasis: e.target.value })}
                required
              />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Purchase Date</label>
              <input
                type="date"
                value={formData.purchaseDate}
                onChange={(e) => setFormData({ ...formData, purchaseDate: e.target.value })}
                required
              />
            </div>
            <div>
              <button type="submit" className="tab active">Add</button>
            </div>
          </form>
        </div>
      )}

      {/* Holdings Table */}
      {viewMode === 'percentage' && (
        <div className="card card-pad table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Company</th>
                <th className="num">Shares</th>
                <th className="num">Cost Basis</th>
                <th className="num">Current Price</th>
                <th className="num">Total Cost</th>
                <th className="num">Current Value</th>
                <th className="num">Gain/Loss</th>
                <th className="num">Return %</th>
                <th className="num">1D</th>
                <th className="num">5D</th>
                <th className="num">20D</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {portfolioStats.positions.map((pos) => (
                <tr key={pos.id || pos.ticker}>
                  <td className="mono">{pos.ticker}</td>
                  <td>{pos.priceInfo?.name || '—'}</td>
                  <td className="mono num">{pos.shares}</td>
                  <td className="mono num">${pos.costBasis.toFixed(2)}</td>
                  <td className="mono num">${pos.currentPrice.toFixed(2)}</td>
                  <td className="mono num">${pos.totalCost.toLocaleString('en-US', { maximumFractionDigits: 0 })}</td>
                  <td className="mono num">${pos.currentValue.toLocaleString('en-US', { maximumFractionDigits: 0 })}</td>
                  <td className="mono num" style={{ color: pos.gain >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                    {pos.gain >= 0 ? '+' : ''}${pos.gain.toFixed(0)}
                  </td>
                  <td className="mono num" style={{ color: pos.gainPct >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                    {pos.gainPct >= 0 ? '+' : ''}{pos.gainPct.toFixed(1)}%
                  </td>
                  <td className="mono num" style={{ color: pos.priceInfo?.technical_detail?.return_1d >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                    {pos.priceInfo?.technical_detail?.return_1d != null ? `${pos.priceInfo.technical_detail.return_1d > 0 ? '+' : ''}${pos.priceInfo.technical_detail.return_1d.toFixed(1)}%` : '—'}
                  </td>
                  <td className="mono num" style={{ color: pos.priceInfo?.technical_detail?.return_5d >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                    {pos.priceInfo?.technical_detail?.return_5d != null ? `${pos.priceInfo.technical_detail.return_5d > 0 ? '+' : ''}${pos.priceInfo.technical_detail.return_5d.toFixed(1)}%` : '—'}
                  </td>
                  <td className="mono num" style={{ color: pos.priceInfo?.technical_detail?.return_20d >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                    {pos.priceInfo?.technical_detail?.return_20d != null ? `${pos.priceInfo.technical_detail.return_20d > 0 ? '+' : ''}${pos.priceInfo.technical_detail.return_20d.toFixed(1)}%` : '—'}
                  </td>
                  <td>
                    <button className="chip button-chip" onClick={() => removePosition(pos.id)}>Remove</button>
                  </td>
                </tr>
              ))}
              {portfolioStats.positions.length === 0 && (
                <tr>
                  <td colSpan="13" style={{ textAlign: 'center', padding: 40, opacity: 0.5 }}>
                    No positions yet. Click "+ Add Position" to start tracking.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* $500 Calculator Table */}
      {viewMode === 'hypothetical' && (
        <div className="card card-pad table-wrap">
          <div style={{ marginBottom: 16, padding: '12px 16px', background: 'var(--bg-dim)', borderRadius: 8 }}>
            <strong>Hypothetical Returns:</strong> See what a $500 investment would be worth across different time periods
          </div>
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Company</th>
                <th className="num">Current Price</th>
                <th className="num">Shares ($500)</th>
                <th className="num">1 Day</th>
                <th className="num">5 Days</th>
                <th className="num">20 Days</th>
                <th className="num">3 Months</th>
              </tr>
            </thead>
            <tbody>
              {Object.keys(priceData).sort().map((ticker) => {
                const stock = priceData[ticker]
                const returns = calculate500Returns(ticker)
                const shares = (500 / stock.price).toFixed(3)

                return (
                  <tr key={ticker}>
                    <td className="mono">{ticker}</td>
                    <td>{stock.name}</td>
                    <td className="mono num">${stock.price?.toFixed(2)}</td>
                    <td className="mono num">{shares}</td>
                    <td className="mono num" style={{ color: returns['1d'] >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                      {returns['1d'] != null ? `${returns['1d'] >= 0 ? '+' : ''}$${returns['1d'].toFixed(2)}` : '—'}
                    </td>
                    <td className="mono num" style={{ color: returns['5d'] >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                      {returns['5d'] != null ? `${returns['5d'] >= 0 ? '+' : ''}$${returns['5d'].toFixed(2)}` : '—'}
                    </td>
                    <td className="mono num" style={{ color: returns['20d'] >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                      {returns['20d'] != null ? `${returns['20d'] >= 0 ? '+' : ''}$${returns['20d'].toFixed(2)}` : '—'}
                    </td>
                    <td className="mono num" style={{ color: returns['3m'] >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                      {returns['3m'] != null ? `${returns['3m'] >= 0 ? '+' : ''}$${returns['3m'].toFixed(2)}` : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
