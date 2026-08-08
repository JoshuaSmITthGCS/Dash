/**
 * Makes the bucket planner see what the user already owns, not just what's on screen.
 *
 * "Split available funds by rank" used to be blind to the current portfolio: two users
 * looking at the same research list with the same available funds got the same split, one
 * whose book is all quality compounders and one who is already all-in on this week's
 * catalysts alike. This classifies both the current holdings and the candidates on screen
 * into the same two lanes the ranking models already imply - `research` ("a good business to
 * own for years") vs `catalyst` ("new information the market may still be digesting") - and
 * hands back a per-lane multiplier the planner can lean on new money with, so a portfolio
 * that is long-term-heavy gets pushed toward short-term candidates and vice versa, without
 * ever overriding which candidate is best *within* a lane.
 */

import { scoreRow } from './rankingModels'

const finite = (value) => typeof value === 'number' && Number.isFinite(value)

// A catalyst score below this just means "no evidence either way" (the catalyst model's own
// gate already filters out rows with no dated news/insider/revision evidence at all) - only a
// score clearing the model's own neutral band counts as an active, evidence-backed catalyst.
const SHORT_TERM_FLOOR = 55

const STYLES = ['long_term', 'short_term']

/**
 * ETFs and any stock without an active, evidence-backed catalyst read as long_term - the
 * default a diversified core holding or a quality compounder with no news this month
 * actually is, not an absence of style.
 */
export function styleOf(index, row) {
  if (!row || row.is_etf) return 'long_term'
  const catalyst = scoreRow(index, row, 'catalyst')
  return catalyst && catalyst.score >= SHORT_TERM_FLOOR ? 'short_term' : 'long_term'
}

/**
 * `holdings` is `[{ row, value }]` - the research/ETF row behind each ticker the user owns,
 * paired with its current dollar value. Returns the percentage of that value in each style,
 * or null when there's nothing held (or nothing priced) to measure - the caller's cue to
 * leave the planner exactly as it was.
 */
export function currentStyleTilt(index, holdings) {
  const totals = { long_term: 0, short_term: 0 }
  for (const { row, value } of holdings || []) {
    if (!finite(value) || value <= 0) continue
    totals[styleOf(index, row)] += value
  }
  const total = totals.long_term + totals.short_term
  if (total <= 0) return null
  return {
    long_term: (totals.long_term / total) * 100,
    short_term: (totals.short_term / total) * 100,
  }
}

/**
 * How much extra weight a `style` candidate should get in the new-money split. Targets an
 * even 50/50 book: a style sitting at 10% of current value gets boosted toward 1.4x, one
 * already at 90% gets discounted toward 0.6x. Bounded to [0.5, 1.75] so this nudges the split
 * toward diversification - it never lets a weak scorer outweigh a strong one in the other lane
 * outright, since it multiplies the same score^power weight rather than replacing it.
 */
export function styleBoost(tilt, style) {
  if (!tilt) return 1
  const currentPct = tilt[style] ?? 0
  const gap = 50 - currentPct
  return Math.min(1.75, Math.max(0.5, 1 + gap / 100))
}

export const PORTFOLIO_STYLES = STYLES
