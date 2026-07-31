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
import { withStopLoss } from '../lib/positionRisk'
import {
  benchmarkAlternative,
  fixedBasisAlternative,
  portfolioFixedBasisVsBenchmark,
  portfolioGrowthSeries,
  portfolioVsBenchmark,
} from '../lib/portfolioPerformance'
import Icon from '../components/Icons'
import { useAdvisorRefresh } from '../lib/useAdvisorRefresh'
import {
  nextPortfolioSort,
  PORTFOLIO_SORT_OPTIONS,
  sortPortfolioPositions,
} from '../lib/portfolioSort'

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

function PortfolioSortToolbar({ sort, selectedLabel, onSortKey, onToggleDirection }) {
  return (
    <div className="portfolio-sort-toolbar" aria-label="Portfolio sorting controls">
      <label>
        <span>Sort holdings</span>
        <select value={sort.key} onChange={(event) => onSortKey(event.target.value)}>
          {PORTFOLIO_SORT_OPTIONS.map((option) => (
            <option key={option.key} value={option.key}>{option.label}</option>
          ))}
        </select>
      </label>
      <button
        className="secondary-button portfolio-sort-direction"
        onClick={onToggleDirection}
        aria-label={`Reverse ${selectedLabel || 'portfolio'} sort order`}
      >
        {sort.direction === 'asc' ? 'Ascending ↑' : 'Descending ↓'}
      </button>
    </div>
  )
}

function SortableHeader({ sortKey, sort, onSort, children, numeric = false }) {
  const active = sort.key === sortKey
  return (
    <th
      scope="col"
      className={numeric ? 'num' : undefined}
      aria-sort={active ? (sort.direction === 'asc' ? 'ascending' : 'descending') : undefined}
    >
      <button
        className={`sort-header ${active ? 'active' : ''}`}
        onClick={() => onSort(sortKey)}
      >
        {children}
        <span className="sort-arrows" aria-hidden="true">
          <i className={`sort-arrow up ${active && sort.direction === 'asc' ? 'selected' : ''}`} />
          <i className={`sort-arrow down ${active && sort.direction === 'desc' ? 'selected' : ''}`} />
        </span>
      </button>
    </th>
  )
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
  const [portfolioSort, setPortfolioSort] = useState({ key: 'ticker', direction: 'asc' })
  const refresh = useAdvisorRefresh(
    data?.generated_at,
    reload,
    positions.map((position) => position.ticker),
  )

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
    const gainPct = gain == null || !totalCost ? null : (gain / totalCost) * 100
    const recommendation = current
      ? withStopLoss(getRecommendation(current), { gainPct, currentPrice, purchaseDate: pos.purchaseDate, priceInfo: current })
      : null
    const enriched = {
      ...pos,
      ticker,
      currentPrice,
      totalCost,
      currentValue,
      gain,
      gainPct,
      trendValues,
      trendPct: recentReturn(trendValues),
      quoteSource: current?.price ? 'Research refresh' : pos.snapshotPrice ? pos.snapshotSource : null,
      priceInfo: current,
      recommendation,
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
  const basis = data?.hypothetical_basis || 500
  const fixedBasisTotal = portfolioFixedBasisVsBenchmark(portfolioStats.positions, priceData, benchmarkHistory, basis)
  const growth = portfolioGrowthSeries(portfolioStats.positions, priceData, benchmarkHistory)
  const actionable = portfolioStats.positions.filter(
    (pos) => pos.recommendation && pos.recommendation.action !== 'HOLD')
  const sortedPositions = sortPortfolioPositions(
    portfolioStats.positions,
    portfolioSort.key,
    portfolioSort.direction,
  )
  const setSortKey = (key) => setPortfolioSort((current) => nextPortfolioSort(current, key))
  const toggleSortDirection = () => setPortfolioSort((current) => ({
    ...current,
    direction: current.direction === 'asc' ? 'desc' : 'asc',
  }))
  const selectedSort = PORTFOLIO_SORT_OPTIONS.find((option) => option.key === portfolioSort.key)

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
          <div className="kpi-value" style={{ color: moveColor(versusIndex?.excessReturnPct) }}>
            {versusIndex
              ? signedPct(versusIndex.excessReturnPct)
              : '—'}
          </div>
          <div className="kpi-note">
            {versusIndex
              ? `${versusIndex.dollarsAhead >= 0 ? '+' : '−'}${money(Math.abs(versusIndex.dollarsAhead))} versus the index · ${versusIndex.comparable} compared position${versusIndex.comparable === 1 ? '' : 's'}`
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
            <div className="comparison-summary-side">
              {versusIndex && (
                <span className="comparison-edge" style={{ color: moveColor(versusIndex.excessReturnPct) }}>
                  {signedPct(versusIndex.excessReturnPct)} vs S&amp;P
                </span>
              )}
              <span className="comparison-toggle" aria-hidden="true"><Icon name="chevron" size={18} /></span>
            </div>
          </summary>
          <div className="portfolio-comparison-chart">
            <GrowthChart
              dates={growth.dates}
              series={[
                { label: 'My holdings', values: growth.holdings, color: 'var(--series-stock)', emphasis: true },
                { label: 'S&P 500, same deposits', values: growth.benchmark, color: 'var(--series-benchmark)', dashPattern: '7 5' },
                { label: 'Deposits held as cash', values: growth.cash, color: 'var(--series-cash)', dashPattern: '2 5' },
              ]}
              title="One-to-one performance from your investment dates"
              caption={`Each holding starts with its exact cost-basis dollars on its recorded purchase date, then follows that stock’s price return. The S&P receives the identical dollars on the identical date; cash holds the same deposits. Jumps show new money entering, not investment gains. Covers ${growth.trackedTickers.length} dated position${growth.trackedTickers.length === 1 ? '' : 's'} from ${growth.firstInvestmentDate}${growth.untrackedCount ? `; ${growth.untrackedCount} missing a usable date or published history` : ''}.`}
              zoomable
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
        <PortfolioSortToolbar
          sort={portfolioSort}
          selectedLabel={selectedSort?.label}
          onSortKey={setSortKey}
          onToggleDirection={toggleSortDirection}
        />
        <div className="portfolio-mobile-list">
          {sortedPositions.map((pos) => (
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
                <SortableHeader sortKey="ticker" sort={portfolioSort} onSort={setSortKey}>Ticker</SortableHeader>
                <SortableHeader sortKey="company" sort={portfolioSort} onSort={setSortKey}>Company</SortableHeader>
                <SortableHeader sortKey="signal" sort={portfolioSort} onSort={setSortKey}>Signal</SortableHeader>
                <SortableHeader numeric sortKey="shares" sort={portfolioSort} onSort={setSortKey}>Shares</SortableHeader>
                <SortableHeader numeric sortKey="cost" sort={portfolioSort} onSort={setSortKey}>Cost</SortableHeader>
                <SortableHeader numeric sortKey="price" sort={portfolioSort} onSort={setSortKey}>Price</SortableHeader>
                <SortableHeader numeric sortKey="value" sort={portfolioSort} onSort={setSortKey}>Value</SortableHeader>
                <SortableHeader numeric sortKey="gain" sort={portfolioSort} onSort={setSortKey}>Gain/Loss</SortableHeader>
                <SortableHeader numeric sortKey="return" sort={portfolioSort} onSort={setSortKey}>Return</SortableHeader>
                <SortableHeader numeric sortKey="score" sort={portfolioSort} onSort={setSortKey}>Score</SortableHeader>
                <SortableHeader numeric sortKey="trend" sort={portfolioSort} onSort={setSortKey}>1M trend</SortableHeader>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {sortedPositions.map((pos) => (
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
        <>
        <PortfolioSortToolbar
          sort={portfolioSort}
          selectedLabel={selectedSort?.label}
          onSortKey={setSortKey}
          onToggleDirection={toggleSortDirection}
        />
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
              {sortedPositions.map((pos) => (
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
        </>
      )}

      {viewMode === 'hypothetical' && (
        <>
        <PortfolioSortToolbar
          sort={portfolioSort}
          selectedLabel={selectedSort?.label}
          onSortKey={setSortKey}
          onToggleDirection={toggleSortDirection}
        />
        <div className="card card-pad table-wrap">
          <div className="callout" style={{ margin: '0 0 16px' }}>
            <strong>${basis} calculator:</strong> what ${basis} would be worth today if it went into
            each position on the day you actually bought it, against the same ${basis} in the
            S&amp;P 500 from that same day. Not what you actually invested — same fair, same-day
            comparison as "Vs S&amp;P 500", just a flat ${basis} everywhere.
          </div>
          <table>
            <thead>
              <tr>
                <th>Ticker</th><th className="num">Purchased</th><th className="num">${basis} invested</th>
                <th className="num">Now</th><th className="num">Return</th>
                <th className="num">S&P instead</th><th className="num">S&P return</th>
                <th className="num">Dollars ahead</th>
              </tr>
            </thead>
            <tbody>
              {sortedPositions.map((pos) => {
                const calc = fixedBasisAlternative(pos, pos.priceInfo?.history, benchmarkHistory, basis)
                return (
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
                    <td className="mono num">{money(basis)}</td>
                    <td className="mono num">{calc ? money(calc.stockValue) : '—'}</td>
                    <td className="num">
                      {calc ? <Move value={calc.stockReturnPct} /> : <span className="mono">—</span>}
                    </td>
                    <td className="mono num">{calc ? money(calc.benchmarkValue) : '—'}</td>
                    <td className="num">
                      {calc ? <Move value={calc.benchmarkReturnPct} /> : <span className="mono">—</span>}
                    </td>
                    <td className="mono num" style={{ color: moveColor(calc?.dollarsAhead) }}>
                      {calc
                        ? `${calc.dollarsAhead >= 0 ? '+' : '−'}${money(Math.abs(calc.dollarsAhead))}`
                        : '—'}
                    </td>
                  </tr>
                )
              })}
              {fixedBasisTotal && (
                <tr style={{ fontWeight: 600 }}>
                  <td className="mono">TOTAL</td>
                  <td className="num">—</td>
                  <td className="mono num">{money(fixedBasisTotal.invested)}</td>
                  <td className="mono num">{money(fixedBasisTotal.stockValue)}</td>
                  <td className="num"><Move value={fixedBasisTotal.stockReturnPct} /></td>
                  <td className="mono num">{money(fixedBasisTotal.benchmarkValue)}</td>
                  <td className="num"><Move value={fixedBasisTotal.benchmarkReturnPct} /></td>
                  <td className="mono num" style={{ color: moveColor(fixedBasisTotal.dollarsAhead) }}>
                    {fixedBasisTotal.dollarsAhead >= 0 ? '+' : '−'}{money(Math.abs(fixedBasisTotal.dollarsAhead))}
                  </td>
                </tr>
              )}
              {portfolioStats.positions.length === 0 && (
                <tr>
                  <td colSpan="8" style={{ textAlign: 'center', padding: 40, opacity: 0.5 }}>
                    No positions yet. Click "+ Add Position" to start tracking.
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
        </>
      )}

      {selectedStock && (
        <StockDetailModal
          stock={selectedStock.priceInfo || selectedStock}
          position={selectedStock.shares
            ? { shares: selectedStock.shares, price: selectedStock.currentPrice, purchaseDate: selectedStock.purchaseDate }
            : null}
          benchmarkHistory={benchmarkHistory}
          onClose={() => setSelectedStock(null)}
        />
      )}
    </>
  )
}
