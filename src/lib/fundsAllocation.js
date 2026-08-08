/**
 * Splits available funds across ranked research rows without spreading them evenly.
 *
 * An equal split treats a 95-score company the same as a 55-score one, which contradicts
 * the whole point of ranking them. Weighting by score alone (linear) still under-rewards
 * the leaders, so each row's weight is its score raised to `power` (default 2) – a modest
 * convexity that gives the better-ranked names a meaningfully larger bucket while still
 * leaving every eligible row something, rather than winner-take-all.
 */

const finite = (value) => typeof value === 'number' && Number.isFinite(value)

export function allocateFunds(rows, availableFunds, { limit = 8, power = 2, scoreOf } = {}) {
  if (!finite(availableFunds) || availableFunds <= 0) {
    return { available: false, reason: 'Enter an available funds amount greater than $0.', buckets: [] }
  }

  // `scoreOf` lets a caller weight by the ranking actually on screen. Under a strategy
  // lens the visible order is that lens's rank score, and weighting those rows by the
  // long-term research score instead would hand the largest bucket to whichever name
  // happens to rank well on a measure the user deliberately looked past.
  const scoreFor = scoreOf || ((row) => row.score)
  const eligible = (rows || [])
    .filter((row) => finite(scoreFor(row)) && scoreFor(row) > 0)
    .slice(0, limit)

  if (!eligible.length) {
    return { available: false, reason: 'No scored companies in the current view to allocate across.', buckets: [] }
  }

  const weights = eligible.map((row) => scoreFor(row) ** power)
  const totalWeight = weights.reduce((sum, weight) => sum + weight, 0)

  const buckets = eligible.map((row, index) => {
    const weightPct = (weights[index] / totalWeight) * 100
    const amount = availableFunds * (weights[index] / totalWeight)
    const price = finite(row.price) && row.price > 0 ? row.price : null
    return {
      ticker: row.ticker,
      name: row.name,
      score: scoreFor(row),
      isEtf: Boolean(row.is_etf),
      weightPct,
      amount,
      price,
      shares: price ? amount / price : null,
    }
  })

  return { available: true, buckets, power, totalFunds: availableFunds }
}
