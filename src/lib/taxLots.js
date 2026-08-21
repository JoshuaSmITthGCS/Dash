// Tax-lot accounting (Master Remediation Prompt v3, B3 -- see docs/BUILD-PLAN.md).
//
// Every stored position document already IS a lot: addPosition() (useFirebasePortfolio.js)
// creates a fresh document with its own id, share count, cost basis, and purchase date on
// every buy, rather than merging into one running-average position per ticker. What was
// missing was a way to sell a quantity of a ticker that spans more than one of those
// documents -- today's single-row Sell button already sells from exactly the lot the user
// clicked, which is specific identification of that one lot and needs no change here.
//
// This module is the FIFO depletion engine for a sale that spans multiple lots of the same
// ticker: IRS Publication 550's default treatment absent specific identification at the time
// of sale is first-in-first-out, oldest acquisition date first.

const finite = (value) => value !== null && value !== '' && Number.isFinite(Number(value))

/** A ticker's open lots (positions with shares > 0), oldest acquisition date first. */
export function lotsForTicker(positions = [], ticker) {
  const target = String(ticker || '').trim().toUpperCase()
  return positions
    .filter((row) => String(row.ticker || '').trim().toUpperCase() === target
      && finite(row.shares) && Number(row.shares) > 0)
    .slice()
    .sort((left, right) => String(left.purchaseDate || left.addedAt || '')
      .localeCompare(String(right.purchaseDate || right.addedAt || '')))
}

/**
 * FIFO depletion plan for selling `quantity` shares of `ticker` across as many lots as it
 * takes, oldest first. Each entry in `depletions` names the exact position document it draws
 * from and how many shares remain in it afterward, so the caller can update or remove that
 * document directly -- the same per-position update/remove the existing single-lot sell flow
 * already performs, just applied across more than one document when needed.
 */
export function planFifoSale(positions, ticker, quantity) {
  if (!finite(quantity) || Number(quantity) <= 0) {
    return { available: false, reason: 'Enter a positive share quantity.' }
  }
  const lots = lotsForTicker(positions, ticker)
  const totalHeld = lots.reduce((sum, lot) => sum + Number(lot.shares), 0)
  if (Number(quantity) > totalHeld + 1e-9) {
    return {
      available: false,
      reason: lots.length
        ? `Only ${totalHeld} shares of ${ticker} are held across ${lots.length} lot${lots.length === 1 ? '' : 's'}.`
        : `No open lots for ${ticker}.`,
    }
  }
  let remaining = Number(quantity)
  const depletions = []
  for (const lot of lots) {
    if (remaining <= 1e-9) break
    const quantityFromLot = Math.min(Number(lot.shares), remaining)
    depletions.push({
      positionId: lot.id,
      ticker: lot.ticker,
      purchaseDate: lot.purchaseDate || lot.addedAt || null,
      quantity: quantityFromLot,
      costBasisPerUnit: Number(lot.costBasis),
      remainingAfter: Number(lot.shares) - quantityFromLot,
    })
    remaining -= quantityFromLot
  }
  return { available: true, ticker, totalQuantity: Number(quantity), depletions }
}

/** Realized gain for a FIFO plan at a given per-share sale price, total and per lot. */
export function realizedGainForPlan(plan, pricePerShare) {
  if (!plan?.available || !finite(pricePerShare)) return null
  const perLot = plan.depletions.map((row) => ({
    ...row,
    proceeds: row.quantity * pricePerShare,
    costBasis: row.quantity * row.costBasisPerUnit,
    realizedGain: row.quantity * (pricePerShare - row.costBasisPerUnit),
  }))
  return {
    perLot,
    totalProceeds: perLot.reduce((sum, row) => sum + row.proceeds, 0),
    totalCostBasis: perLot.reduce((sum, row) => sum + row.costBasis, 0),
    totalRealizedGain: perLot.reduce((sum, row) => sum + row.realizedGain, 0),
  }
}

/** How many distinct open lots a ticker has, for deciding when the FIFO-across-lots sell
 * action is actually needed rather than just clicking Sell on the one lot that exists. */
export function lotCountsByTicker(positions = []) {
  const counts = {}
  for (const row of positions) {
    const ticker = String(row.ticker || '').trim().toUpperCase()
    if (!ticker || !finite(row.shares) || Number(row.shares) <= 0) continue
    counts[ticker] = (counts[ticker] || 0) + 1
  }
  return counts
}
