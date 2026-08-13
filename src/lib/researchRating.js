/**
 * Turns the published 0-100 score into a signed -5..+5 read: "how good vs. bad is this,
 * at a glance" rather than a raw number that needs the score's own scale memorized.
 *
 * Stocks and ETFs use two different score models with different scales and distributions
 * (see fundsAllocation.js and rankingModels.js for the same split), so each is rated against
 * its own pool, never against each other - an 80 on the ETF fund score and an 80 on the
 * stock fundamentals-first score are not the same claim.
 *
 * The rating is a percentile within that pool, not a fixed threshold on the score itself:
 * the published leaderboard alone runs ~75-86 and the full screened universe runs ~18-86, so
 * a fixed "score/10 - 5" mapping would almost never reach the tails. Percentile against the
 * pool the row actually competes in keeps the full -5..+5 range meaningful.
 *
 * Confidence shrinks the rating toward 0, the same treatment src/lib/rankingModels.js gives
 * every model score - a percentile resting on thin data should not read as equally certain
 * as one resting on a fully resolved row. Rows with no confidence field at all (the lighter
 * screen_universe projection) are shrunk by a fixed factor instead, since "how much of the
 * confidence inputs resolved" was never computed for them.
 */

const finite = (value) => typeof value === 'number' && Number.isFinite(value)
const MIN_POOL = 5
const LIGHT_DATA_SHRINK = 0.7
const MIN_CONFIDENCE_SHRINK = 0.2

function percentileRank(sortedAscending, value) {
  const below = sortedAscending.filter((entry) => entry < value).length
  const equal = sortedAscending.filter((entry) => entry === value).length
  return ((below + equal / 2) / sortedAscending.length) * 100
}

/** Build once per render of a rows list; reused for every row's rating() call. */
export function buildRatingContext(rows) {
  return {
    stockScores: (rows || []).filter((row) => !row.is_etf && finite(row.score)).map((row) => row.score),
    etfScores: (rows || []).filter((row) => row.is_etf && finite(row.score)).map((row) => row.score),
  }
}

/** -5 (worst in its pool) .. +5 (best in its pool), or null when there isn't enough to rate. */
export function researchRating(row, context) {
  if (!row || !finite(row.score) || !context) return null
  const pool = row.is_etf ? context.etfScores : context.stockScores
  if (pool.length < MIN_POOL) return null
  const percentile = percentileRank(pool, row.score)
  let rating = ((percentile - 50) / 50) * 5
  rating *= finite(row.data_coverage) ? Math.max(MIN_CONFIDENCE_SHRINK, row.data_coverage) : LIGHT_DATA_SHRINK
  return Math.max(-5, Math.min(5, Math.round(rating)))
}
