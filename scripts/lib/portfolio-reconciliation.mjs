// Pure planning logic for applying a dated list of real brokerage events (buys, sells,
// deposits, dividends) on top of whatever positions an account already holds. This is what
// scripts/reconcile-portfolio-activity.mjs (WP2) uses to bring an account's Firestore ledger
// up to date with real trading activity that happened outside the app, or that a bug (like the
// LULU resurrection) once undid.
//
// It writes through the exact same primitives the app itself uses -- planFifoSale /
// realizedGainForPlan from taxLots.js for sells, the same activity-row shapes usePortfolioForms
// and useFirebasePortfolio write -- so a reconciled account is indistinguishable from one whose
// history was entered by hand through the UI.
//
// Idempotent by construction: every write carries a deterministic id derived from the event's
// own (kind, ticker, date, amount), and a second run of the same event file against an account
// that already has those ids produces zero writes for them.

import { planFifoSale, realizedGainForPlan } from '../../src/lib/taxLots.js'

const finite = (value) => value !== null && value !== '' && Number.isFinite(Number(value))
const normalizeTicker = (ticker) => String(ticker || '').trim().toUpperCase()
const cents = (amount) => Math.round(Number(amount) * 100)

/** The deterministic Firestore document ids this event would write, before any plan is built. */
export function eventActivityIds(event) {
  const ticker = normalizeTicker(event.ticker)
  const date = event.date
  switch (event.kind) {
    case 'deposit':
      return [`deposit-${date}-${cents(event.amount)}`]
    case 'withdrawal':
      return [`withdrawal-${date}-${cents(event.amount)}`]
    case 'dividend':
      return [`dividend-${ticker}-${date}-${cents(event.amount)}`]
    case 'buy':
      return [`position-added-${ticker}-${date}`, `stock_purchase-${ticker}-${date}`]
    case 'sell':
      return [`realized_gain-${ticker}-${date}-${cents(event.proceeds)}`, `sale_proceeds-${ticker}-${date}-${cents(event.proceeds)}`]
    default:
      return []
  }
}

function validateEvent(event) {
  const ticker = event.ticker ? normalizeTicker(event.ticker) : null
  if (!event.date) return `${event.kind}: missing date`
  if (event.kind === 'deposit' || event.kind === 'withdrawal') {
    if (!finite(event.amount) || Number(event.amount) <= 0) return `${event.kind} on ${event.date}: amount must be a positive number`
    return null
  }
  if (event.kind === 'dividend') {
    if (!ticker) return `dividend on ${event.date}: missing ticker`
    if (!finite(event.amount) || Number(event.amount) <= 0) return `${ticker} dividend on ${event.date}: amount must be a positive number`
    return null
  }
  if (event.kind === 'buy') {
    if (!ticker) return `buy on ${event.date}: missing ticker`
    if (!finite(event.shares) || Number(event.shares) <= 0) return `${ticker} buy on ${event.date}: shares must be a positive number`
    if (!finite(event.cost) || Number(event.cost) <= 0) return `${ticker} buy on ${event.date}: cost must be a positive number`
    return null
  }
  if (event.kind === 'sell') {
    if (!ticker) return `sell on ${event.date}: missing ticker`
    if (!finite(event.shares) || Number(event.shares) <= 0) return `${ticker} sell on ${event.date}: shares must be a positive number`
    if (!finite(event.proceeds) || Number(event.proceeds) <= 0) return `${ticker} sell on ${event.date}: proceeds must be a positive number`
    return null
  }
  return `unrecognized event kind "${event.kind}"`
}

/**
 * Plans every write for one event against the *current* in-memory position list, and returns
 * the updated position list so the next event in the batch sees this one's effect (a buy
 * followed later by a sell of the same ticker in the same file has to see the new lot).
 */
function planOneEvent(positions, event, { closedTickers, generatedAt }) {
  const ticker = normalizeTicker(event.ticker)
  const writes = []

  if (event.kind === 'deposit' || event.kind === 'withdrawal') {
    const [id] = eventActivityIds(event)
    writes.push({
      collection: 'activity', op: 'set', id,
      data: {
        type: event.kind, amount: Number(event.amount), effectiveDate: event.date,
        recordedAt: generatedAt, source: 'fidelity_activity_reconcile',
        ...(event.note ? { note: event.note } : {}),
      },
    })
    return { positions, writes }
  }

  if (event.kind === 'dividend') {
    const [id] = eventActivityIds(event)
    writes.push({
      collection: 'activity', op: 'set', id,
      data: {
        type: 'dividend', ticker, amount: Number(event.amount), effectiveDate: event.date,
        recordedAt: generatedAt, source: 'fidelity_activity_reconcile',
      },
    })
    return { positions, writes }
  }

  if (event.kind === 'buy') {
    const shares = Number(event.shares)
    const cost = Number(event.cost)
    const costBasis = cost / shares
    const positionId = `${ticker}-${event.date}-reconcile`
    const [addedId, purchaseId] = eventActivityIds(event)
    writes.push({
      collection: 'positions', op: 'set', id: positionId,
      data: {
        ticker, shares, costBasis, costBasisUnit: 'per_share', costBasisInputMode: 'total',
        purchaseDate: event.date, addedAt: generatedAt, id: positionId,
        source: 'fidelity_activity_reconcile',
      },
    })
    // A buy clears any closed-ticker marker, exactly as addPosition() does -- this is a
    // re-entry into a name the account had sold out of, not a resurrection of the old lot.
    if (closedTickers.has(ticker)) {
      writes.push({ collection: 'closedPositions', op: 'delete', id: ticker })
    }
    writes.push({
      collection: 'activity', op: 'set', id: addedId,
      data: {
        type: 'position_added', ticker, shares, pricePerShare: costBasis, amount: cost,
        effectiveDate: event.date, recordedAt: generatedAt, source: 'fidelity_activity_reconcile',
      },
    })
    writes.push({
      collection: 'activity', op: 'set', id: purchaseId,
      data: {
        type: 'stock_purchase', ticker, amount: cost, effectiveDate: event.date,
        recordedAt: generatedAt, source: 'fidelity_activity_reconcile',
      },
    })
    return { positions: [...positions, { id: positionId, ticker, shares, costBasis }], writes }
  }

  // sell
  const plan = planFifoSale(positions, ticker, Number(event.shares))
  if (!plan.available) {
    return { positions, writes, error: `${ticker} sell on ${event.date}: ${plan.reason}` }
  }
  const gain = realizedGainForPlan(plan, Number(event.proceeds) / Number(event.shares))
  // realizedGainForPlan prices every lot at one implied per-share price (proceeds / shares in
  // this event). That is correct here: a single Fidelity fill sells at one execution price.
  const [gainId, proceedsId] = eventActivityIds(event)
  const lotSummary = gain.perLot
    .map((row) => `${row.quantity} @ $${row.costBasisPerUnit.toFixed(2)} (${row.purchaseDate || 'undated lot'})`)
    .join('; ')

  for (const depletion of plan.depletions) {
    writes.push(depletion.remainingAfter > 1e-7
      ? { collection: 'positions', op: 'set', id: depletion.positionId, data: { shares: depletion.remainingAfter } }
      : { collection: 'positions', op: 'delete', id: depletion.positionId })
  }

  writes.push({
    collection: 'activity', op: 'set', id: gainId,
    data: {
      type: 'realized_gain', ticker, amount: gain.totalRealizedGain, effectiveDate: event.date,
      recordedAt: generatedAt, source: 'fidelity_activity_reconcile',
      note: `${ticker} sale (${plan.depletions.length} lot${plan.depletions.length === 1 ? '' : 's'}, FIFO): ${lotSummary}`,
    },
  })
  writes.push({
    collection: 'activity', op: 'set', id: proceedsId,
    data: {
      type: 'sale_proceeds', ticker, amount: gain.totalProceeds, effectiveDate: event.date,
      recordedAt: generatedAt, source: 'fidelity_activity_reconcile',
      note: `${event.shares} ${ticker} share${event.shares === 1 ? '' : 's'} sold.`,
    },
  })

  const afterSell = positions
    .map((position) => {
      const depletion = plan.depletions.find((row) => row.positionId === position.id)
      if (!depletion) return position
      return depletion.remainingAfter > 1e-7 ? { ...position, shares: depletion.remainingAfter } : null
    })
    .filter(Boolean)

  const remainingTotal = afterSell
    .filter((position) => normalizeTicker(position.ticker) === ticker)
    .reduce((sum, position) => sum + Number(position.shares || 0), 0)
  if (remainingTotal <= 1e-7) {
    writes.push({
      collection: 'closedPositions', op: 'set', id: ticker,
      data: {
        ticker, saleDate: event.date, closedAt: generatedAt,
        realizedGain: gain.totalRealizedGain, shares: Number(event.shares), price: Number(event.proceeds) / Number(event.shares),
      },
    })
  }

  return { positions: afterSell, writes }
}

/**
 * Plans the whole event file against the account's current positions.
 *
 * `existingActivityIds` (a Set of activity document ids already present in Firestore) makes
 * this idempotent: an event whose deterministic ids are already all present is skipped
 * entirely -- neither its position writes nor its activity writes are re-emitted -- so running
 * the same file twice against an already-reconciled account plans zero writes the second time.
 */
export function planActivityReconciliation(existingPositions, events, {
  existingActivityIds = new Set(),
  closedTickers = new Set(),
  generatedAt = new Date().toISOString(),
} = {}) {
  let positions = existingPositions.map((position) => ({ ...position }))
  const closed = new Set([...closedTickers].map(normalizeTicker))
  const writes = []
  const errors = []
  const skipped = []
  const summary = { buy: 0, sell: 0, deposit: 0, withdrawal: 0, dividend: 0, skipped: 0 }

  const sorted = [...events].sort((left, right) => String(left.date).localeCompare(String(right.date)))

  for (const event of sorted) {
    const validationError = validateEvent(event)
    if (validationError) { errors.push(validationError); continue }

    const ids = eventActivityIds(event)
    if (ids.length && ids.every((id) => existingActivityIds.has(id))) {
      skipped.push({ event, ids })
      summary.skipped += 1
      continue
    }

    const result = planOneEvent(positions, event, { closedTickers: closed, generatedAt })
    if (result.error) { errors.push(result.error); continue }
    positions = result.positions
    writes.push(...result.writes)
    summary[event.kind] = (summary[event.kind] || 0) + 1
    if (event.kind === 'sell') {
      const ticker = normalizeTicker(event.ticker)
      const stillHeld = positions.some((position) => normalizeTicker(position.ticker) === ticker)
      if (stillHeld) closed.delete(ticker); else closed.add(ticker)
    }
    if (event.kind === 'buy') closed.delete(normalizeTicker(event.ticker))
  }

  return { writes, errors, skipped, summary, positionsAfter: positions }
}
