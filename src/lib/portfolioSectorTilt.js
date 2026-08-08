/**
 * The sector half of making the bucket planner portfolio-aware (see portfolioStyleTilt.js
 * for the long-term/short-term half - the two merge into one weight in Picks.jsx).
 *
 * Two questions, not one. "What sector am I light on" alone would happily overweight a
 * struggling sector just because it's currently 0% of the book. This also asks "of the
 * sectors I'm light on, which one is actually offering the better risk/growth setup right
 * now" - a peer-relative blend of growth (revenue growth where published, else 12-1 price
 * momentum as a market-priced growth-expectation proxy everywhere else) and risk-adjusted
 * return (Sharpe/Sortino-style, already computed for essentially the whole universe). A
 * sector only gets pushed hard when it's both underrepresented AND scores well on that blend;
 * being underrepresented in a weak sector barely moves it.
 */

import { peerPercentile } from './rankingModels'

const finite = (value) => typeof value === 'number' && Number.isFinite(value)

function growthPercentile(index, row) {
  const revenueGrowth = peerPercentile(index, row, (candidate) => candidate.revenue_growth)
  if (revenueGrowth) return revenueGrowth.value
  const momentum = peerPercentile(index, row, (candidate) => (
    candidate.technical_detail?.momentum_12_1_pct ?? candidate.technical_detail?.momentum_12_1
  ))
  return momentum ? momentum.value : null
}

function riskAdjustedPercentile(index, row) {
  const result = peerPercentile(index, row, (candidate) => candidate.technical_detail?.risk_adjusted)
  return result ? result.value : null
}

/** 0-100, higher is better on both legs; null when neither leg resolved for this row. */
export function opportunityScore(index, row) {
  const parts = [growthPercentile(index, row), riskAdjustedPercentile(index, row)].filter(finite)
  if (!parts.length) return null
  return parts.reduce((sum, value) => sum + value, 0) / parts.length
}

/**
 * `holdings` is `[{ row, value }]`, same shape currentStyleTilt takes. Returns
 * `Map<sector, pct>` of the user's current dollar value, or null with nothing held/priced.
 */
export function currentSectorTilt(holdings) {
  const totals = new Map()
  let total = 0
  for (const { row, value } of holdings || []) {
    if (!finite(value) || value <= 0 || !row?.sector) continue
    totals.set(row.sector, (totals.get(row.sector) || 0) + value)
    total += value
  }
  if (total <= 0) return null
  const pct = new Map()
  for (const [sector, amount] of totals) pct.set(sector, (amount / total) * 100)
  return pct
}

/** `Map<sector, 0-100 opportunity score>`, averaged over every row of that sector in `rows`. */
export function sectorOpportunity(index, rows) {
  const bySector = new Map()
  for (const row of rows || []) {
    if (!row.sector) continue
    const score = opportunityScore(index, row)
    if (!finite(score)) continue
    if (!bySector.has(row.sector)) bySector.set(row.sector, [])
    bySector.get(row.sector).push(score)
  }
  const result = new Map()
  for (const [sector, scores] of bySector) {
    result.set(sector, scores.reduce((sum, value) => sum + value, 0) / scores.length)
  }
  return result
}

/**
 * How much extra weight a candidate in `sector` should get. Two bounded, multiplied factors:
 *
 * - Underweight gap, against an even split across every sector present in the universe (not
 *   a market-cap benchmark - a flat "everyone gets a fair shot" target, the same simplification
 *   the long-term/short-term split uses with its flat 50/50 target). 0% in a sector with an
 *   11-sector universe (a ~9% target) reads as mildly underweight, not maximally - a single
 *   empty sector should not be able to dominate the split on its own.
 * - Opportunity, centered on 1x at a neutral (50) score so a so-so sector isn't boosted just
 *   for being empty, and discounted below 1x when the sector's own setup is weak.
 *
 * Bounded to [0.4, 2] combined so this nudges the split - it never lets a sector's tilt alone
 * outweigh what the score^power ranking already decided within that sector.
 */
export function sectorBoost(currentSectorPct, opportunityBySector, sector, sectorCount) {
  if (!currentSectorPct || !sector || !sectorCount) return 1
  const target = 100 / sectorCount
  const currentPct = currentSectorPct.get(sector) ?? 0
  const gapBoost = Math.min(1.75, Math.max(0.5, 1 + (target - currentPct) / 100))
  const opportunity = opportunityBySector?.get(sector) ?? 50
  const opportunityBoost = Math.min(1.3, Math.max(0.7, 1 + (opportunity - 50) / 100 * 0.6))
  return Math.min(2, Math.max(0.4, gapBoost * opportunityBoost))
}
