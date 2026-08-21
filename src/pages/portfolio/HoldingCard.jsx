import { RatingBadge } from '../../components/Bits'
import { ActionPill } from '../../components/ActionGuidance'
import Sparkline from '../../components/Sparkline'
import InfoTag from '../../components/InfoTag.jsx'
import CompanyLogo from '../../components/CompanyLogo.jsx'
import { MobileSheet } from '../../components/MobileSheet.jsx'
import { money, signedPct } from './format.js'
import { Move, StopLossNote } from './PortfolioBits.jsx'

/** One holding. Collapsed to identity + today's move under "Essential only". */
export default function HoldingCard({ pos, essentialOnly, forms, onSelectStock, lotCount = 1 }) {
  const {
    editingId, editForm, setEditForm, editSaving, startEdit, cancelEdit, saveEdit,
    sellingId, startSell, removingId, handleRemove, startLotSell,
  } = forms
  const editing = editingId === pos.id
  const selling = sellingId === pos.id

  return (
    <article className={`portfolio-stock-tile ${pos.dayMove?.pct == null ? 'tone-flat' : pos.dayMove.pct >= 0 ? 'tone-up' : 'tone-down'}`}>
      <button type="button" className="portfolio-stock-primary" onClick={() => pos.priceInfo && onSelectStock(pos)} disabled={!pos.priceInfo}
        aria-label={`${pos.ticker}, ${signedPct(pos.dayMove?.pct, 2)} today, ${pos.currentPrice == null ? 'price unavailable' : `${money(pos.currentPrice, 2)} per share`}${pos.priceInfo ? '. Open research' : ''}`}>
        <span className="portfolio-stock-identity">
          <CompanyLogo company={pos.priceInfo || pos} size={26} />
          <span><strong>{pos.ticker}</strong><small title={pos.priceInfo?.name || 'Coverage pending'}>{pos.priceInfo?.name || 'Coverage pending'}</small></span>
        </span>
        <span className="portfolio-stock-move">
          <strong><span aria-hidden="true">{pos.dayMove?.pct == null ? '•' : pos.dayMove.pct >= 0 ? '▲' : '▼'}</span>{signedPct(pos.dayMove?.pct, 2)}</strong>
          <small>{pos.currentPrice == null ? 'Price pending' : money(pos.currentPrice, 2)}</small>
        </span>
      </button>

      {!essentialOnly && <div className="portfolio-stock-details">
        <div className="portfolio-stock-allocation">{pos.allocationPct == null ? 'Allocation unavailable' : `${pos.allocationPct.toFixed(1)}% of portfolio`}</div>
        <div className="holding-value">
          <div><span>Current price</span><strong>{pos.currentPrice == null ? 'Unavailable' : money(pos.currentPrice, 2)}</strong></div>
          <div><span>Position value</span><strong>{pos.currentValue == null ? 'Unavailable' : money(pos.currentValue)}</strong></div>
        </div>
        <div className="holding-block-status"><ActionPill recommendation={pos.recommendation} /><RatingBadge value={pos.rating} title="-5 (worst) to +5 (best) vs. its research pool" /><span>{signedPct(pos.gainPct)} total return</span></div>
        <small className="as-of-line">As of {pos.priceInfo?.history?.dates?.at(-1) || pos.priceInfo?.data_as_of || 'the latest available close'}</small>
        {editing ? (
          <MobileSheet open title={`Edit ${pos.ticker}`} onClose={cancelEdit} className="holding-edit-sheet"><div className="holding-edit-form">
            <label><span>Shares</span>
              <input className="inline-edit-input" type="number" step="0.001" min="0" value={editForm.shares}
                onChange={(e) => setEditForm({ ...editForm, shares: e.target.value })} />
            </label>
            <label>
              <span className="field-mode-row">
                Cost basis
                <select value={editForm.costMode} onChange={(e) => setEditForm({ ...editForm, costMode: e.target.value })}
                  className="field-mode-select">
                  <option value="share">$/share</option>
                  <option value="total">Total $</option>
                </select>
              </span>
              <input className="inline-edit-input" type="number" step="0.01" min="0" value={editForm.costBasis}
                onChange={(e) => setEditForm({ ...editForm, costBasis: e.target.value })} />
            </label>
            <label><span>Purchase date</span>
              <input className="inline-edit-input" type="date" value={editForm.purchaseDate}
                onChange={(e) => setEditForm({ ...editForm, purchaseDate: e.target.value })} />
            </label>
          </div><div className="holding-edit-sheet-actions"><button className="secondary-button" onClick={cancelEdit} disabled={editSaving}>Cancel</button><button className="primary-button" onClick={() => saveEdit(pos.id)} disabled={editSaving}>{editSaving ? 'Saving…' : 'Save changes'}</button></div></MobileSheet>
        ) : (
          <div className="holding-meta">
            <span>{pos.shares} shares</span><span>Avg. cost/share {money(pos.costBasis, 2)}</span>
            <span>{pos.quoteSource || 'Live quote unavailable'}</span>
            <StopLossNote stopLoss={pos.stopLoss} />
          </div>
        )}
        {!editing && !selling && pos.trendValues.length > 1 && (
          <div className="holding-trend">
            <div><span>1-month trend
              <InfoTag label="1-month trend">
                <strong>1-month trend</strong>
                <p>Trailing 30-day price movement for this holding - direction and shape only,
                  not a substitute for the full research score.</p>
              </InfoTag>
            </span><Move value={pos.trendPct} /></div>
            <Sparkline values={pos.trendValues} label={`${pos.ticker} one-month price trend`} height={48} />
          </div>
        )}
        <div className="holding-actions">
          {!editing && !selling && (
            <>
              {pos.priceInfo && <button className="secondary-button" onClick={() => onSelectStock(pos)}>Research</button>}
              <button className="text-button" onClick={() => startEdit(pos)}>Edit</button>
              <button className="text-button" onClick={() => startSell(pos)}>Sell</button>
              {lotCount > 1 && (
                <button className="text-button" onClick={() => startLotSell(pos.ticker)}
                  title={`You hold ${pos.ticker} across ${lotCount} separate lots; this sells oldest-first across as many as it takes`}>
                  Sell across {lotCount} lots
                </button>
              )}
              <button className="text-button danger" onClick={() => handleRemove(pos.id)} disabled={removingId === pos.id}>
                {removingId === pos.id ? 'Removing…' : 'Remove'}
              </button>
            </>
          )}
        </div>
      </div>}
    </article>
  )
}
