import { useState } from 'react'
import { useData } from '../lib/useData'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio'
import { useAuth } from '../lib/FirebaseAuthContext'
import { Loading } from '../components/Bits'
import { ActionPill } from '../components/ActionGuidance'
import GrowthChart from '../components/GrowthChart'
import Sparkline from '../components/Sparkline'
import StockDetailModal from '../components/StockDetailModal'
import { getRecommendation } from '../lib/recommendation'
import { benchmarkAlternative, portfolioGrowthSeries, portfolioVsBenchmark } from '../lib/portfolioPerformance'
import Icon from '../components/Icons'
import { useAdvisorRefresh } from '../lib/useAdvisorRefresh'

const money = (value, digits = 0) =>
  value == null ? '—' : `$${value.toLocaleString('en-US', { maximumFractionDigits: digits })}`

const signedPct = (value, digits = 1) =>
  value == null ? '—' : `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`

const moveColor = (value) => (value == null ? undefined : value >= 0 ? 'var(--pos)' : 'var(--neg)')

function Move({ value, digits = 1 }) {
  return <span className="mono" style={{ color: moveColor(value) }}>{signedPct(value, digits)}</span>
}

function recentReturn(values, points = 5) {
  const clean = (values || []).filter(Number.isFinite).slice(-points)
  if (clean.length < 2 || !clean[0]) return null
  return (clean.at(-1) / clean[0] - 1) * 100
}

export default function Portfolio() {
  const { logout } = useAuth()
  const { data, loading: dataLoading, reload } = useData('advisor.json')
  const {
    positions,
    loading: portfolioLoading,
    addPosition,
    removePosition,
    updatePosition,
    exportPortfolio,
    syncReferencePortfolio,
  } = useFirebasePortfolio()

  const [showAddForm, setShowAddForm] = useState(false)
  const [formData, setFormData] = useState({ ticker: '', shares: '', costBasis: '', purchaseDate: new Date().toISOString().split('T')[0] })
  const [viewMode, setViewMode] = useState('holdings')
  const [selectedStock, setSelectedStock] = useState(null)
  const [syncMessage, setSyncMessage] = useState('')
  const refresh = useAdvisorRefresh(data?.generated_at, reload)

  if (dataLoading || portfolioLoading) return <Loading />

  const research = data?.research || []
  const portfolioCoverage = data?.portfolio_coverage || []
  const benchmarkHistory = data?.benchmark_history
  const priceData = Object.fromEntries([...research, ...portfolioCoverage]
    .filter((row) => row.ticker && row.price != null)
    .map((row) => [String(row.ticker).trim().toUpperCase(), row]))

  const portfolioStats = positions.reduce((acc, pos) => {
    const ticker = String(pos.ticker || '').trim().toUpperCase()
    const current = priceData[ticker]
    const currentPrice = current?.price ?? pos.snapshotPrice ?? null
    const totalCost = pos.shares * pos.costBasis
    const currentValue = currentPrice == null ? null : pos.shares * currentPrice
    const gain = currentValue == null ? null : currentValue - totalCost
    const trendValues = current?.history?.closes?.filter(Number.isFinite).slice(-5) || []
    const enriched = {
      ...pos,
      ticker,
      currentPrice,
      totalCost,
      currentValue,
      gain,
      gainPct: gain == null || !totalCost ? null : (gain / totalCost) * 100,
      trendValues,
      trendPct: recentReturn(trendValues),
      quoteSource: current?.price ? 'Research refresh' : pos.snapshotPrice ? pos.snapshotSource : null,
      priceInfo: current,
      recommendation: current ? getRecommendation(current) : null,
      versusBenchmark: benchmarkAlternative({ ...pos, currentValue }, benchmarkHistory),
    }
    return {
      totalCost: acc.totalCost + totalCost,
      totalValue: acc.totalValue + (currentValue || 0),
      totalGain: acc.totalGain + (gain || 0),
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

  const handleReferenceSync = async () => {
    setSyncMessage('Syncing…')
    const result = await syncReferencePortfolio()
    setSyncMessage(result.success
      ? `${result.added} holding${result.added === 1 ? '' : 's'} added · ${result.updated} refreshed`
      : `Sync failed: ${result.error}`)
  }

  const handlePurchaseDateChange = async (positionId, purchaseDate) => {
    const result = await updatePosition(positionId, { purchaseDate })
    setSyncMessage(result?.success ? 'Purchase date saved' : `Could not save date: ${result?.error || 'Unknown error'}`)
  }

  const basis = data?.hypothetical_basis || 500

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Your money</span>
          <h1 className="page-title">My <span className="accent">portfolio</span></h1>
          <p className="page-sub">
            Holdings, action guidance, and a fair same-dollar comparison with the S&amp;P 500.
          </p>
        </div>
        <div className="page-actions">
          <button className="secondary-button" onClick={refresh.requestRefresh} disabled={refresh.refreshing}>
            <Icon name="sync" size={17} className={refresh.refreshing ? 'refresh-spin' : ''} />
            {refresh.refreshing ? 'Refreshing…' : 'Refresh prices'}
          </button>
          <button className="secondary-button" onClick={handleReferenceSync}>Sync holdings</button>
          <button className="icon-button" onClick={exportPortfolio} aria-label="Export portfolio"><Icon name="download" /></button>
          <button className="icon-button" onClick={logout} aria-label="Sign out"><Icon name="logout" /></button>
        </div>
      </div>
      {syncMessage && <div className="sync-message" role="status">{syncMessage}</div>}
      {refresh.message && (
        <div className={`sync-message refresh-message ${refresh.status}`} role="status" aria-live="polite">
          {refresh.message}
        </div>
      )}

      <div className="portfolio-summary">
        <div className="portfolio-value-card">
          <div className="kpi-label">Total Value</div>
          <div className="kpi-value">{money(portfolioStats.totalValue)}</div>
          <div className="portfolio-delta" style={{ color: moveColor(portfolioStats.totalGain) }}>
            {portfolioStats.totalGain >= 0 ? '+' : '−'}{money(Math.abs(portfolioStats.totalGain))} · {signedPct(totalGainPct, 2)}
          </div>
          <div className="kpi-note">{positions.length} positions · {money(portfolioStats.totalCost)} cost basis</div>
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
        <details className="card portfolio-comparison">
          <summary>
            <div>
              <span className="eyebrow">Opportunity cost</span>
              <strong>What if I chose the S&amp;P 500—or did not invest?</strong>
              <small>Same contributions, added on your recorded purchase dates</small>
            </div>
            <span className="comparison-toggle" aria-hidden="true"><Icon name="chevron" size={18} /></span>
          </summary>
          <div className="portfolio-comparison-chart">
            <GrowthChart
              dates={growth.dates}
              series={[
                { label: 'My holdings', values: growth.holdings, color: 'var(--series-stock)', emphasis: true },
                { label: 'S&P 500, same deposits', values: growth.benchmark, color: 'var(--series-benchmark)', dashPattern: '7 5' },
                { label: 'Deposits held as cash', values: growth.cash, color: 'var(--series-cash)', dashPattern: '2 5' },
              ]}
              title="Portfolio value from your investment dates"
              caption={`Each holding enters on its recorded purchase date. The S&P line receives the same cost-basis dollars on those dates; cash holds those deposits with no interest or inflation adjustment. Jumps show new money entering the portfolio. Covers ${growth.trackedTickers.length} dated position${growth.trackedTickers.length === 1 ? '' : 's'} from ${growth.firstInvestmentDate}${growth.untrackedCount ? `; ${growth.untrackedCount} missing a usable date or published history` : ''}.`}
            />
          </div>
        </details>
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
        <>
        <div className="portfolio-mobile-list">
          {portfolioStats.positions.map((pos) => (
            <article className="holding-card" key={pos.id || pos.ticker}>
              <div className="holding-card-head">
                <div><strong>{pos.ticker}</strong><span>{pos.priceInfo?.name || 'Coverage pending'}</span></div>
                <ActionPill recommendation={pos.recommendation} />
              </div>
              <div className="holding-value">
                <div><span>Position value</span><strong>{pos.currentValue == null ? 'Unavailable' : money(pos.currentValue)}</strong></div>
                <Move value={pos.gainPct} />
              </div>
              <div className="holding-meta">
                <span>{pos.shares} shares</span><span>Cost {money(pos.costBasis, 2)}</span>
                <span>{pos.quoteSource || 'Live quote unavailable'}</span>
              </div>
              {pos.trendValues.length > 1 && (
                <div className="holding-trend">
                  <div><span>1-month trend</span><Move value={pos.trendPct} /></div>
                  <Sparkline values={pos.trendValues} label={`${pos.ticker} one-month price trend`} height={48} />
                </div>
              )}
              <div className="holding-actions">
                {pos.priceInfo && <button className="secondary-button" onClick={() => setSelectedStock(pos)}>Research</button>}
                <button className="text-button danger" onClick={() => removePosition(pos.id)}>Remove</button>
              </div>
            </article>
          ))}
        </div>
        <div className="card card-pad table-wrap portfolio-table">
          <table>
            <thead>
              <tr>
                <th>Ticker</th><th>Company</th><th>Signal</th>
                <th className="num">Shares</th><th className="num">Cost</th><th className="num">Price</th>
                <th className="num">Value</th><th className="num">Gain/Loss</th><th className="num">Return</th>
                <th className="num">Score</th><th className="num">1M trend</th><th>Action</th>
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
                  <td className="mono num">{pos.currentPrice == null ? '—' : `$${pos.currentPrice.toFixed(2)}`}</td>
                  <td className="mono num">{pos.currentValue == null ? '—' : money(pos.currentValue)}</td>
                  <td className="mono num" style={{ color: moveColor(pos.gain) }}>
                    {pos.gain == null ? '—' : `${pos.gain >= 0 ? '+' : '−'}${money(Math.abs(pos.gain))}`}
                  </td>
                  <td className="num"><Move value={pos.gainPct} /></td>
                  <td className="mono num score-cell">{pos.priceInfo?.score ?? '—'}</td>
                  <td className="num portfolio-trend-cell">
                    {pos.trendValues.length > 1 ? (
                      <>
                        <Sparkline values={pos.trendValues} label={`${pos.ticker} one-month price trend`} height={34} />
                        <Move value={pos.trendPct} />
                      </>
                    ) : <span className="mono">—</span>}
                  </td>
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
        </>
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
                  <td className="mono num">
                    <input
                      className="portfolio-date-input"
                      type="date"
                      value={pos.purchaseDate || ''}
                      aria-label={`${pos.ticker} purchase date`}
                      onChange={(event) => handlePurchaseDateChange(pos.id, event.target.value)}
                    />
                  </td>
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
            Add or correct a purchase date above to calculate the same-day comparison. Positions
            bought before the published benchmark window show “—” rather than being compared
            against the wrong entry price.
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
