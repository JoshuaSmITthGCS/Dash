// "All holdings": the essential-only switch, the three comparison tabs, the add form,
// the holdings grid, and the sell sheet.

import { MobileSheet } from '../../components/MobileSheet.jsx'
import { PortfolioSortToolbar } from './PortfolioBits.jsx'
import HoldingCard from './HoldingCard.jsx'
import { BenchmarkTable, FixedBasisTable } from './ComparisonTables.jsx'
import { lotCountsByTicker } from '../../lib/taxLots.js'

function AddPositionForm({ formData, setFormData, onSubmit }) {
  return (
    <div className="card add-position-card">
      <h3>Add New Position</h3>
      <form onSubmit={onSubmit} className="add-position-form">
        <div>
          <label className="field-label" htmlFor="position-ticker">Ticker</label>
          <input id="position-ticker" type="text" placeholder="AAPL" value={formData.ticker} required
            onChange={(e) => setFormData({ ...formData, ticker: e.target.value.toUpperCase() })} />
        </div>
        <div>
          <label className="field-label" htmlFor="position-shares">Shares</label>
          <input id="position-shares" type="number" step="0.001" placeholder="10" value={formData.shares} required
            onChange={(e) => setFormData({ ...formData, shares: e.target.value })} />
        </div>
        <div>
          <label className="field-row-label">
            <span>Cost basis</span>
            <select className="field-mode-select" value={formData.costMode}
              aria-label="Cost basis units"
              onChange={(e) => setFormData({ ...formData, costMode: e.target.value })}>
              <option value="share">$/share</option>
              <option value="total">Total $</option>
            </select>
          </label>
          <input type="number" step="0.01" id="position-cost"
            aria-label={formData.costMode === 'total' ? 'Total cost basis in dollars' : 'Cost basis per share in dollars'}
            placeholder={formData.costMode === 'total' ? '200.00' : '150.00'}
            value={formData.costBasis} required
            onChange={(e) => setFormData({ ...formData, costBasis: e.target.value })} />
        </div>
        <div>
          <label className="field-label" htmlFor="position-date">Purchase Date</label>
          <input id="position-date" type="date" value={formData.purchaseDate} required
            onChange={(e) => setFormData({ ...formData, purchaseDate: e.target.value })} />
        </div>
        <div><button type="submit" className="tab active">Add</button></div>
      </form>
    </div>
  )
}

function SellSheet({ position, forms }) {
  const { sellForm, setSellForm, sellSaving, cancelSell, saveSell } = forms
  return (
    <MobileSheet open title={`Sell ${position.ticker}`} onClose={cancelSell} className="holding-edit-sheet">
      <div className="holding-edit-form">
        <label><span>Shares to sell (of {position.shares})</span>
          <input className="inline-edit-input" type="number" step="0.001" min="0" max={position.shares} value={sellForm.shares}
            onChange={(e) => setSellForm({ ...sellForm, shares: e.target.value })} />
        </label>
        <label><span>Sale price/share</span>
          <input className="inline-edit-input" type="number" step="0.01" min="0" value={sellForm.price}
            onChange={(e) => setSellForm({ ...sellForm, price: e.target.value })} />
        </label>
        <label><span>Sale date</span>
          <input className="inline-edit-input" type="date" value={sellForm.saleDate}
            onChange={(e) => setSellForm({ ...sellForm, saleDate: e.target.value })} />
        </label>
      </div>
      <div className="holding-edit-sheet-actions">
        <button className="secondary-button" onClick={cancelSell} disabled={sellSaving}>Cancel</button>
        <button className="primary-button" onClick={() => saveSell(position)} disabled={sellSaving}>{sellSaving ? 'Selling…' : 'Confirm sale'}</button>
      </div>
    </MobileSheet>
  )
}

// FIFO-across-lots sale (B3): sells a total share count for a ticker that may span more than
// one purchase (each a separate position document / lot), depleting the oldest first -- IRS
// Publication 550's default absent specific identification. The existing per-row Sell above
// already covers specific identification of one lot and is untouched by this.
function LotSellSheet({ ticker, forms }) {
  const { lotSellForm, setLotSellForm, lotSellSaving, lotSellPlan, cancelLotSell, saveLotSell } = forms
  return (
    <MobileSheet open title={`Sell ${ticker} across lots`} onClose={cancelLotSell} className="holding-edit-sheet">
      <div className="holding-edit-form">
        <label><span>Total shares to sell</span>
          <input className="inline-edit-input" type="number" step="0.001" min="0" value={lotSellForm.shares}
            onChange={(e) => setLotSellForm({ ...lotSellForm, shares: e.target.value })} />
        </label>
        <label><span>Sale price/share</span>
          <input className="inline-edit-input" type="number" step="0.01" min="0" value={lotSellForm.price}
            onChange={(e) => setLotSellForm({ ...lotSellForm, price: e.target.value })} />
        </label>
        <label><span>Sale date</span>
          <input className="inline-edit-input" type="date" value={lotSellForm.saleDate}
            onChange={(e) => setLotSellForm({ ...lotSellForm, saleDate: e.target.value })} />
        </label>
      </div>
      {lotSellPlan?.available && (
        <ul className="lot-sell-preview">
          {lotSellPlan.depletions.map((row) => (
            <li key={row.positionId}>
              <span>{row.quantity} sh @ ${row.costBasisPerUnit.toFixed(2)}</span>
              <span>{row.purchaseDate || 'undated lot'}</span>
              <span>{row.remainingAfter > 0.0000001 ? `${row.remainingAfter} sh remain` : 'fully sold'}</span>
            </li>
          ))}
        </ul>
      )}
      {lotSellPlan && !lotSellPlan.available && lotSellForm.shares && (
        <p className="lot-sell-error">{lotSellPlan.reason}</p>
      )}
      <div className="holding-edit-sheet-actions">
        <button className="secondary-button" onClick={cancelLotSell} disabled={lotSellSaving}>Cancel</button>
        <button className="primary-button" onClick={saveLotSell} disabled={lotSellSaving || !lotSellPlan?.available}>
          {lotSellSaving ? 'Selling…' : 'Confirm sale'}
        </button>
      </div>
    </MobileSheet>
  )
}

export default function Holdings({
  holdings,
  sortedPositions,
  positionCount,
  sort,
  viewMode,
  onViewModeChange,
  essentialOnly,
  onEssentialOnlyChange,
  forms,
  onSelectStock,
}) {
  const { basis, versusIndex, fixedBasisTotal, benchmarkHistory } = holdings
  // Rendered once, outside both the mobile card list and the desktop table, so triggering a
  // sale from either (only one is visible at a given viewport width) still shows the sheet.
  const sellingPosition = sortedPositions.find((pos) => (pos.id || pos.ticker) === forms.sellingId)
  const lotCounts = lotCountsByTicker(sortedPositions)
  const sortToolbar = <PortfolioSortToolbar {...sort} />

  return (
    <section className="portfolio-holdings-section" aria-labelledby="portfolio-holdings-title">
      <header className="portfolio-subsection-heading">
        <div><span className="eyebrow">Your positions</span><h3 id="portfolio-holdings-title">All holdings</h3></div>
        <div className="portfolio-holdings-heading-actions">
          <span>{positionCount} holding{positionCount === 1 ? '' : 's'}</span>
          <label className="portfolio-essential-control">
            <span><strong>Essential only</strong><small>{essentialOnly ? 'Extra details hidden' : 'All details shown'}</small></span>
            <span className="switch">
              <input type="checkbox" checked={essentialOnly} onChange={(event) => onEssentialOnlyChange(event.target.checked)} />
              <span aria-hidden="true" />
            </span>
          </label>
        </div>
      </header>

      <div className="filters filters--gap">
        <button className={`tab ${viewMode === 'holdings' ? 'active' : ''}`} onClick={() => onViewModeChange('holdings')}>
          My Holdings
        </button>
        <button className={`tab ${viewMode === 'benchmark' ? 'active' : ''}`} onClick={() => onViewModeChange('benchmark')}>
          Vs S&P 500
        </button>
        <button className={`tab ${viewMode === 'hypothetical' ? 'active' : ''}`} onClick={() => onViewModeChange('hypothetical')}>
          ${basis} Calculator
        </button>
        <button className="tab active add-position-toggle" onClick={() => forms.setShowAddForm(!forms.showAddForm)}>
          + Add Position
        </button>
      </div>

      {forms.showAddForm && (
        <AddPositionForm formData={forms.formData} setFormData={forms.setFormData} onSubmit={forms.handleSubmit} />
      )}

      {viewMode === 'holdings' && (
        <>
        {sortToolbar}
        <div className={`portfolio-mobile-list portfolio-stock-grid ${essentialOnly ? 'essential' : 'expanded'}`}>
          {sortedPositions.map((pos) => (
            <HoldingCard key={pos.id || pos.ticker} pos={pos} essentialOnly={essentialOnly} forms={forms} onSelectStock={onSelectStock}
              lotCount={lotCounts[String(pos.ticker || '').toUpperCase()] || 1} />
          ))}
          {sortedPositions.length === 0 && <div className="portfolio-holdings-empty">No positions yet. Add a position to start tracking.</div>}
        </div>
        {sellingPosition && <SellSheet position={sellingPosition} forms={forms} />}
        {forms.lotSellTicker && <LotSellSheet ticker={forms.lotSellTicker} forms={forms} />}
        </>
      )}

      {viewMode === 'benchmark' && (
        <>
        {sortToolbar}
        <BenchmarkTable
          sortedPositions={sortedPositions}
          versusIndex={versusIndex}
          onPurchaseDateChange={forms.handlePurchaseDateChange}
        />
        </>
      )}

      {viewMode === 'hypothetical' && (
        <>
        {sortToolbar}
        <FixedBasisTable
          sortedPositions={sortedPositions}
          fixedBasisTotal={fixedBasisTotal}
          basis={basis}
          benchmarkHistory={benchmarkHistory}
          positionCount={holdings.portfolioStats.positions.length}
          onPurchaseDateChange={forms.handlePurchaseDateChange}
        />
        </>
      )}
    </section>
  )
}
