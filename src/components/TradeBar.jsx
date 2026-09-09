import { useEffect, useRef, useState } from 'react'
import Icon from './Icons.jsx'

const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10)

const round = (value, places = 4) => {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return ''
  return String(Number(numeric.toFixed(places)))
}

/**
 * The sticky buy/sell bar pinned to the bottom of the stock research modal.
 *
 * Two things about how this is built are load-bearing rather than stylistic:
 *
 *   1. Every field is local state. The portfolio page rebuilds ~900 rows of derived model on
 *      each render, so lifting these three inputs into it would put that work between each
 *      keystroke and the character appearing.
 *   2. It only commits through `onSubmit`, which returns { success, error }. It never writes
 *      to Firestore itself, so the ledger, rebalance capture and closed-position marker all
 *      stay in usePortfolioForms with the rest of the write path.
 */
export default function TradeBar({ ticker, currentPrice, position, onSubmit, closed = false, onReopen }) {
  const [open, setOpen] = useState(false)
  const [side, setSide] = useState(position?.shares > 0 ? 'sell' : 'buy')
  const [shares, setShares] = useState('')
  const [price, setPrice] = useState(() => round(currentPrice, 2))
  const [date, setDate] = useState(today)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState(null)
  const sharesRef = useRef(null)

  // The quote can land after the modal opens. Fill the price field from it only while the
  // user has not typed their own -- a sale is often booked at a price the live quote does
  // not know, and overwriting that would be the worst possible moment to be helpful.
  const priceTouched = useRef(false)
  useEffect(() => {
    if (priceTouched.current) return
    const next = round(currentPrice, 2)
    if (next) setPrice(next)
  }, [currentPrice])

  const held = Number(position?.shares) || 0
  const heldValue = held > 0 && Number.isFinite(Number(currentPrice)) ? held * Number(currentPrice) : null
  const quantity = parseFloat(shares)
  const unitPrice = parseFloat(price)
  const estimate = Number.isFinite(quantity) && Number.isFinite(unitPrice) ? quantity * unitPrice : null
  const overSells = side === 'sell' && Number.isFinite(quantity) && quantity > held + 1e-9

  const openPanel = (nextSide) => {
    setSide(nextSide)
    setStatus(null)
    setOpen(true)
    // The panel is rendered by this same commit, so focus has to wait for it to exist.
    window.requestAnimationFrame(() => sharesRef.current?.focus())
  }

  const submit = async (event) => {
    event.preventDefault()
    if (saving) return
    setSaving(true)
    setStatus(null)
    const result = await onSubmit({ side, ticker, shares, price, date })
    setSaving(false)
    if (result?.success === false) {
      setStatus({ error: true, message: result.error || 'That trade could not be saved.' })
      return
    }
    setStatus({ message: result?.message || 'Trade saved.' })
    setShares('')
    setOpen(false)
  }

  return (
    <div className="trade-bar" role="group" aria-label={`Trade ${ticker}`}>
      {status && (
        <p className={`trade-bar-status ${status.error ? 'error' : 'success'}`} role="status" aria-live="polite">
          {status.message}
        </p>
      )}

      {closed && !open && (
        <p className="trade-bar-closed" role="status">
          <span>You sold out of {ticker}. It stays out of your holdings and out of every portfolio total until you buy it back.</span>
          {onReopen && <button type="button" className="text-button" onClick={() => onReopen(ticker)}>Undo the sale record</button>}
        </p>
      )}

      {open ? (
        <form className="trade-bar-form" onSubmit={submit}>
          <div className="trade-bar-sides" role="group" aria-label="Trade side">
            <button type="button" className={`trade-side ${side === 'buy' ? 'active buy' : ''}`}
              aria-pressed={side === 'buy'} onClick={() => setSide('buy')}>Buy</button>
            <button type="button" className={`trade-side ${side === 'sell' ? 'active sell' : ''}`}
              aria-pressed={side === 'sell'} onClick={() => setSide('sell')} disabled={held <= 0}>Sell</button>
          </div>
          <div className="trade-bar-fields">
            <label>
              <span>Shares{side === 'sell' && held > 0 ? ` (of ${round(held)})` : ''}</span>
              <input ref={sharesRef} type="number" step="0.0001" min="0" inputMode="decimal" placeholder="0"
                value={shares} onChange={(event) => setShares(event.target.value)} required />
            </label>
            <label>
              <span>Price/share</span>
              <input type="number" step="0.01" min="0" inputMode="decimal" placeholder="0.00" value={price}
                onChange={(event) => { priceTouched.current = true; setPrice(event.target.value) }} required />
            </label>
            <label>
              <span>{side === 'sell' ? 'Sale date' : 'Purchase date'}</span>
              <input type="date" value={date} max={today()} onChange={(event) => setDate(event.target.value)} required />
            </label>
          </div>
          {side === 'sell' && held > 0 && (
            <div className="trade-bar-quick">
              <span>Sell</span>
              {[0.25, 0.5, 1].map((fraction) => (
                <button key={fraction} type="button" className="chip button-chip"
                  onClick={() => setShares(round(held * fraction))}>
                  {fraction === 1 ? 'All' : `${fraction * 100}%`}
                </button>
              ))}
            </div>
          )}
          <div className="trade-bar-actions">
            <p className="trade-bar-estimate">
              {overSells
                ? `You hold ${round(held)} ${ticker} share${held === 1 ? '' : 's'}.`
                : estimate == null
                  ? 'Enter a share count and price.'
                  : `${side === 'sell' ? 'Proceeds' : 'Cost'} ≈ $${estimate.toFixed(2)}`}
            </p>
            <button type="button" className="secondary-button" onClick={() => setOpen(false)} disabled={saving}>Cancel</button>
            <button type="submit" className={`primary-button trade-confirm ${side}`} disabled={saving || overSells}>
              {saving ? 'Saving…' : side === 'sell' ? `Confirm sale` : `Confirm buy`}
            </button>
          </div>
          <p className="trade-bar-note">
            Recorded in your own portfolio ledger only. Dash places no orders — enter the trade
            your broker actually filled, on the date it filled.
          </p>
        </form>
      ) : (
        <div className="trade-bar-launch">
          <div className="trade-bar-held">
            {held > 0
              ? <><strong>{round(held)} shares held</strong><small>{heldValue == null ? 'Value pending' : `$${heldValue.toFixed(2)}`}</small></>
              : <><strong>Not held</strong><small>{Number.isFinite(Number(currentPrice)) ? `$${Number(currentPrice).toFixed(2)} per share` : 'Price pending'}</small></>}
          </div>
          {held > 0 && (
            <button type="button" className="primary-button trade-launch sell" onClick={() => openPanel('sell')}>
              <Icon name="chevron" size={16} aria-hidden="true" />Sell {ticker}
            </button>
          )}
          <button type="button" className={`${held > 0 ? 'secondary-button' : 'primary-button'} trade-launch buy`} onClick={() => openPanel('buy')}>
            Buy {ticker}
          </button>
        </div>
      )}
    </div>
  )
}
