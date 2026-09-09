// Reconstructs exactly what an account's holdings looked like on any past date, by replaying
// a baseline position list forward through a chronological list of buy/sell events. This
// answers "what should this account have held on date D" independent of what any recorded
// snapshot from that date actually says -- which is the question scripts/lib/
// portfolio-snapshot-correction.mjs needs answered before it can tell whether a saved daily
// total was wrong, and if so, by how much.

import { planFifoSale } from '../../src/lib/taxLots.js'

const normalizeTicker = (ticker) => String(ticker || '').trim().toUpperCase()

/**
 * Replays `events` (buy/sell only -- deposits, withdrawals, and dividends never change share
 * counts) in date order on top of `baselinePositions`, and returns one checkpoint per event:
 * the exact position list immediately after that event took effect. The baseline itself is
 * checkpoint zero, dated `null`, so `holdingsAsOf` below can answer for any date at or before
 * the first event too.
 */
export function positionTimeline(baselinePositions, events) {
  const sorted = [...events]
    .filter((event) => event.kind === 'buy' || event.kind === 'sell')
    .sort((left, right) => String(left.date).localeCompare(String(right.date)))

  let positions = baselinePositions.map((position) => ({ ...position }))
  const checkpoints = [{ date: null, positions: positions.map((position) => ({ ...position })) }]

  for (const event of sorted) {
    const ticker = normalizeTicker(event.ticker)
    if (event.kind === 'buy') {
      const shares = Number(event.shares)
      const costBasis = Number(event.cost) / shares
      positions = [...positions, {
        id: `${ticker}-${event.date}-timeline`, ticker, shares, costBasis, purchaseDate: event.date,
      }]
    } else {
      const plan = planFifoSale(positions, ticker, Number(event.shares))
      if (plan.available) {
        positions = positions
          .map((position) => {
            const depletion = plan.depletions.find((row) => row.positionId === position.id)
            if (!depletion) return position
            return depletion.remainingAfter > 1e-7 ? { ...position, shares: depletion.remainingAfter } : null
          })
          .filter(Boolean)
      }
      // An event that can't be planned (selling a ticker with no open lot, etc.) is a data
      // problem the reconciliation planner already surfaces as an error -- silently skipped
      // here rather than thrown, since the timeline's job is best-effort reconstruction for
      // snapshot correction, not validation.
    }
    checkpoints.push({ date: event.date, positions: positions.map((position) => ({ ...position })) })
  }

  return checkpoints
}

/**
 * Shares and total cost basis per ticker, as of (on or before) `date` -- aggregated across
 * every open lot of that ticker at that point in the timeline. `date === null` means "as of
 * the baseline, before any event."
 */
export function holdingsAsOf(checkpoints, date) {
  let chosen = checkpoints[0]
  for (const checkpoint of checkpoints) {
    if (checkpoint.date === null || (date != null && checkpoint.date <= date)) chosen = checkpoint
    else break
  }
  const byTicker = new Map()
  for (const position of chosen.positions) {
    const ticker = normalizeTicker(position.ticker)
    const previous = byTicker.get(ticker) || { shares: 0, costBasisTotal: 0 }
    byTicker.set(ticker, {
      shares: previous.shares + Number(position.shares || 0),
      costBasisTotal: previous.costBasisTotal + Number(position.shares || 0) * Number(position.costBasis || 0),
    })
  }
  return byTicker
}
