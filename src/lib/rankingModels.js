/**
 * Ten ranking models, one per question, instead of one score wearing ten hats.
 *
 * The design this replaces asked a single fundamentals-first score to serve long-term
 * investing, short-term catalysts, reversals and trend following at once, and then re-sorted
 * that one number for each. Different questions care about different evidence on different
 * time scales: a mediocre-valuation company that raised guidance yesterday should rank near
 * the top of the catalyst model and merely average on the long-term one, while a quality
 * compounder with no news for a month should barely be touched by the absence.
 *
 * Four rules the whole file is built on.
 *
 * 1. **Composition is declared, not implied.** Every model lists its components and weights
 *    in one object so the "why" panel and the score can never drift apart. The weights are
 *    starting priors, deliberately frozen so the point-in-time store accumulates observations
 *    under one fixed policy - they are not claims of measured optimality.
 *
 * 2. **Inapplicable components are dropped, never zeroed.** A metric a company cannot
 *    legitimately report (EV/EBITDA for an insurer, a drawdown for a row that was never
 *    polled) is removed and the remaining weights renormalize. Scoring it as zero would rank
 *    a company down for the shape of its balance sheet rather than its condition. What it
 *    costs instead is confidence, which is the honest place to pay.
 *
 * 3. **Percentiles against peers, not raw thresholds.** "Is a forward P/E of 18 cheap?" has no
 *    answer; "where does 18 sit among this industry's peers?" does. Every valuation and
 *    quality component ranks within the industry when the sample supports it and falls back
 *    to sector, then to the whole universe.
 *
 * 4. **Confidence shrinks the result.** Each model's raw score is pulled toward 50 by that
 *    model's own confidence (src/lib/modeConfidence.js) before ranking, so a 92 resting on one
 *    stray headline lands near 63 and cannot outrank a well-evidenced 80.
 */

import { modeConfidence } from './modeConfidence'
import { shrinkToConfidence } from './confidenceGate'

const finite = (value) => typeof value === 'number' && Number.isFinite(value)
const clamp = (value, low = 0, high = 100) => Math.min(high, Math.max(low, value))

/** Minimum peer sample before an industry percentile means anything. */
const MIN_PEER_SAMPLE = 8

// ---------------------------------------------------------------------------
// Peer-relative normalization
// ---------------------------------------------------------------------------

/**
 * Percentile ranks within the narrowest peer group that has a usable sample.
 *
 * Industry first, then sector, then the whole universe. A cheap bank and a cheap chipmaker
 * are not judged against each other, but a company in a three-name industry is not judged
 * against two peers either - that is noise dressed as precision.
 */
export function buildPeerIndex(rows) {
  const byIndustry = new Map()
  const bySector = new Map()
  for (const row of rows) {
    if (row.industry) {
      if (!byIndustry.has(row.industry)) byIndustry.set(row.industry, [])
      byIndustry.get(row.industry).push(row)
    }
    if (row.sector) {
      if (!bySector.has(row.sector)) bySector.set(row.sector, [])
      bySector.get(row.sector).push(row)
    }
  }
  return { rows, byIndustry, bySector }
}

function peerGroupFor(index, row) {
  const industry = row.industry ? index.byIndustry.get(row.industry) : null
  if (industry && industry.length >= MIN_PEER_SAMPLE) return { peers: industry, level: 'industry' }
  const sector = row.sector ? index.bySector.get(row.sector) : null
  if (sector && sector.length >= MIN_PEER_SAMPLE) return { peers: sector, level: 'sector' }
  return { peers: index.rows, level: 'universe' }
}

/**
 * Where `value` sits among its peers on a 0-100 scale, `higherIsBetter: false` inverting it.
 * Returns null when the peer sample cannot support a rank - the caller then drops the
 * component rather than inventing a middling 50 for it.
 */
export function peerPercentile(index, row, read, { higherIsBetter = true } = {}) {
  const value = read(row)
  if (!finite(value)) return null
  const { peers, level } = peerGroupFor(index, row)
  const sample = peers.map(read).filter(finite)
  if (sample.length < 3) return null
  const below = sample.filter((other) => other < value).length
  const equal = sample.filter((other) => other === value).length
  const percentile = ((below + equal / 2) / sample.length) * 100
  return { value: higherIsBetter ? percentile : 100 - percentile, level, sampleSize: sample.length }
}

/**
 * Two-tailed: reward the reasonable middle and penalize both extremes.
 *
 * Asset growth is the standard case - a company shrinking its asset base fast and one
 * expanding it fast are both making a statement, and neither is the steady middle.
 */
export function moderationScore(index, row, read) {
  const ranked = peerPercentile(index, row, read)
  if (!ranked) return null
  return { ...ranked, value: clamp(100 - Math.abs(ranked.value - 50) * 2) }
}

// ---------------------------------------------------------------------------
// Component readers
// ---------------------------------------------------------------------------

const technical = (row) => row.technical_detail || {}
const evidence = (row) => row.evidence_summary || row.evidence || {}
const estimates = (row) => row.estimate_detail || {}

/** A 0-100 reading straight off the row, when it is already on that scale. */
const direct = (read) => (index, row) => {
  const value = read(row)
  return finite(value) ? { value: clamp(value), level: 'row', sampleSize: null } : null
}

/** A signed measure mapped onto 0-100 around neutral, `scale` points per unit. */
const centered = (read, scale) => (index, row) => {
  const value = read(row)
  return finite(value) ? { value: clamp(50 + value * scale), level: 'row', sampleSize: null } : null
}

const percentileOf = (read, options) => (index, row) => peerPercentile(index, row, read, options)

// ---------------------------------------------------------------------------
// Thesis-break gate
// ---------------------------------------------------------------------------

/**
 * Event types that mean a decline is price discovery, not an overreaction.
 *
 * Without this the reversal model is a "find falling knives" button: a stock down 15% because
 * it cut guidance 25% and lost its auditor looks statistically identical to one down 15% on
 * nothing. The gate caps the score rather than deleting the row, so the name stays visible
 * with its reason attached.
 */
export const THESIS_BREAK_EVENTS = ['restatement', 'auditor', 'guidance', 'financing', 'regulatory', 'litigation']
const THESIS_BREAK_CAP = 45

export function thesisBreak(row) {
  const detail = evidence(row)
  const types = detail.dominant_event_types || []
  const direction = detail.news_score
  // Only a *negative* material event breaks a thesis. A guidance raise is the same event
  // type as a guidance cut and obviously does not disqualify a bounce.
  if (!finite(direction) || direction >= 45) return null
  const hit = THESIS_BREAK_EVENTS.find((type) => types.includes(type))
  if (!hit) return null
  return {
    type: hit,
    reason: `recent negative ${hit.replace(/_/g, ' ')} news (${detail.dominant_event || 'material event'})`
      + ' – the decline may be price discovery rather than an overreaction',
  }
}

// ---------------------------------------------------------------------------
// Swing-horizon negative screen
// ---------------------------------------------------------------------------

/**
 * Short interest is a negative screen here, never a leg.
 *
 * Boehmer, Jones and Zhang (2008) find heavily shorted names underperform lightly shorted by
 * ~1.16% over the following 20 trading days - a short-side result a long-only book cannot
 * harvest. The honest use of it is therefore suppression: the name stays visible with its
 * reason attached and its score capped, rather than being scored as if the finding were
 * tradable from the long side. Thresholds mirror pipeline/swing_signals.py exactly.
 */
const SHORT_PERCENT_OF_FLOAT_LIMIT = 0.10
const DAYS_TO_COVER_LIMIT = 5
const SHORT_INTEREST_CAP = 45
/** Below this in average dollar volume, spread cost eats a swing-horizon edge at retail size. */
const SWING_MIN_DOLLAR_VOLUME = 2e6

export function shortInterestSuppressed(row) {
  const shortPercent = row?.short_percent_of_float
  const daysToCover = row?.days_to_cover
  const hits = []
  if (finite(shortPercent) && shortPercent >= SHORT_PERCENT_OF_FLOAT_LIMIT) {
    hits.push(`${(shortPercent * 100).toFixed(1)}% of float is short`)
  }
  if (finite(daysToCover) && daysToCover >= DAYS_TO_COVER_LIMIT) {
    hits.push(`${daysToCover.toFixed(1)} days to cover`)
  }
  return hits.length
    ? `${hits.join(' and ')} – heavily shorted names underperform at roughly this horizon, `
      + 'and a long-only book cannot take the other side of that'
    : null
}

// ---------------------------------------------------------------------------
// The models
// ---------------------------------------------------------------------------

/**
 * Each model: the question it answers, its declared components with weights, and an optional
 * `gate` that a row must clear to belong in the list at all. Components are
 * [key, label, weight, score(index, row)] and return null when they do not apply.
 */
export const RANKING_MODELS = {
  research: {
    label: 'Research score (long-term)',
    question: 'Is this a good business, at this price, to own for years?',
    components: [
      ['quality', 'Business quality', 0.35, percentileOf((row) => row.components?.fundamentals)],
      ['valuation', 'Valuation vs peers', 0.20, direct((row) => row.sector_valuation_percentile)],
      ['growth', 'Growth', 0.15, percentileOf((row) => row.revenue_growth)],
      ['health', 'Financial health', 0.10, percentileOf((row) => row.interest_coverage)],
      ['capital', 'Capital allocation', 0.10, percentileOf((row) => row.net_buyback_yield)],
      ['momentum', 'Price momentum', 0.05, direct((row) => technical(row).momentum_12_1)],
      ['revisions', 'Expectation change', 0.05, direct((row) => evidence(row).expectation_score)],
    ],
  },

  valuation: {
    label: 'Sector valuation',
    question: 'Is it cheap against the peers it should be compared with?',
    components: [
      ['sector_percentile', 'Sector valuation percentile', 0.7, direct((row) => row.sector_valuation_percentile)],
      ['category', 'Valuation category score', 0.3, direct((row) => row.fundamental_categories?.valuation)],
    ],
  },

  fundamentals: {
    label: 'Fundamentals',
    question: 'How strong is the business itself, price aside?',
    components: [
      ['profitability', 'Profitability', 0.30, percentileOf((row) => row.operating_margin)],
      ['cash_quality', 'Cash quality', 0.20, percentileOf((row) => row.free_cash_flow_yield)],
      ['health', 'Financial health', 0.20, percentileOf((row) => row.interest_coverage)],
      ['growth', 'Growth', 0.15, percentileOf((row) => row.revenue_growth)],
      ['capital', 'Capital allocation', 0.15, percentileOf((row) => row.net_buyback_yield)],
    ],
  },

  // The model that changes most from a static score: it reads dated events, not averages.
  catalyst: {
    label: 'Short-term catalyst (news + insider)',
    question: 'Has new information arrived that the market may still be digesting?',
    components: [
      ['news', 'Material recent news', 0.55, direct((row) => evidence(row).news_score)],
      ['insider', 'Insider conviction', 0.25, direct((row) => evidence(row).insider_score)],
      ['expectations', 'Expectation change', 0.20, direct((row) => evidence(row).expectation_score)],
    ],
    // A catalyst model with no catalyst in it is just a re-sort. At least one leg must be
    // present, and it has to say something other than "neutral".
    gate: (row) => {
      const detail = evidence(row)
      const legs = [detail.news_score, detail.insider_score, detail.expectation_score].filter(finite)
      if (!legs.length) return 'no dated news, insider or revision evidence on this row'
      if (!legs.some((leg) => Math.abs(leg - 50) > 5)) return 'evidence resolved but is directionally neutral'
      return null
    },
  },

  momentum: {
    label: 'Momentum',
    question: 'Is an established trend continuing, with confirmation?',
    components: [
      ['long_horizon', '12-1 momentum', 0.35, percentileOf((row) => technical(row).momentum_12_1_pct
        ?? technical(row).momentum_12_1)],
      ['medium_horizon', '3-month relative momentum', 0.20, centered((row) => technical(row).return_60d, 1.2)],
      ['proximity', 'Proximity to 52-week high', 0.15, (index, row) => {
        const fromHigh = technical(row).pct_from_52w_high
        return finite(fromHigh) ? { value: clamp(100 + fromHigh * 2), level: 'row', sampleSize: null } : null
      }],
      ['volume', 'Volume confirmation', 0.15, direct((row) => technical(row).volume_confirmation)],
      ['trend_quality', 'Trend quality', 0.10, direct((row) => technical(row).risk_adjusted)],
      ['drawdown', 'Drawdown control', 0.05, centered((row) => technical(row).drawdown_60d, 1.0)],
    ],
    gate: (row) => {
      const detail = technical(row)
      if (!finite(detail.return_20d) || !finite(detail.return_5d)) return 'no recent return history'
      if (detail.return_20d <= 0 || detail.return_5d <= 0) return 'not currently trending up'
      return null
    },
  },

  reversal: {
    label: 'Reversal',
    question: 'Has the price fallen further than the information justifies?',
    components: [
      // Volatility-scaled, not raw: -12% in a 70%-volatility biotech and -12% in a utility
      // are not the same event.
      ['shock', 'Volatility-scaled price shock', 0.30, (index, row) => {
        const monthReturn = technical(row).return_20d
        if (!finite(monthReturn) || monthReturn >= 0) return null
        const drawdown = technical(row).drawdown_60d
        const normalVolatility = finite(drawdown) ? Math.max(5, Math.abs(drawdown) / 2) : 12
        return { value: clamp(50 + (Math.abs(monthReturn) / normalVolatility) * 25), level: 'row', sampleSize: null }
      }],
      ['overextension', 'Statistical overextension', 0.20, (index, row) => {
        const drawdown = technical(row).drawdown_60d
        return finite(drawdown) ? { value: clamp(50 + Math.abs(drawdown) * 1.2), level: 'row', sampleSize: null } : null
      }],
      ['exhaustion', 'Selling exhaustion', 0.15, (index, row) => {
        const week = technical(row).return_5d
        return finite(week) ? { value: clamp(50 + week * 5), level: 'row', sampleSize: null } : null
      }],
      ['shield', 'Fundamental shield', 0.20, percentileOf((row) => row.components?.fundamentals)],
      ['fresh_evidence', 'Fresh confirming evidence', 0.15, (index, row) => {
        const detail = evidence(row)
        const legs = [detail.news_score, detail.insider_score].filter(finite)
        return legs.length ? { value: clamp(legs.reduce((a, b) => a + b, 0) / legs.length), level: 'row', sampleSize: null } : null
      }],
    ],
    gate: (row) => {
      const detail = technical(row)
      if (!finite(detail.return_20d) || !finite(detail.return_5d)) return 'no recent return history'
      if (!finite(detail.drawdown_60d)) return 'no 60-day drawdown published for this row'
      if (detail.return_20d >= 0) return 'has not pulled back over the medium term'
      if (detail.return_5d <= 0) return 'has not yet turned up over the most recent week'
      if (finite(row.components?.fundamentals) && row.components.fundamentals < 50) {
        return 'fundamentals below the floor – a bounce alone does not qualify a deteriorating business'
      }
      return null
    },
    cap: (row) => {
      const broken = thesisBreak(row)
      return broken ? { limit: THESIS_BREAK_CAP, reason: broken.reason } : null
    },
  },

  valueTurnaround: {
    label: 'Value turnaround',
    question: 'Is it cheap AND is something measurably getting better?',
    components: [
      ['discount', 'Valuation discount', 0.35, direct((row) => row.sector_valuation_percentile)],
      ['operating', 'Operating improvement', 0.25, centered((row) => row.operating_margin_trend, 300)],
      ['revisions', 'Expectation change', 0.15, direct((row) => evidence(row).expectation_score)],
      ['cash_flow', 'Cash-flow improvement', 0.15, percentileOf((row) => row.fcf_growth_3y)],
      ['stabilization', 'Price stabilization', 0.10, (index, row) => {
        const monthReturn = technical(row).return_20d
        // Best when the price has stopped falling without having already run: a flat-to-
        // slightly-up month is the shape of a market starting to agree.
        return finite(monthReturn)
          ? { value: clamp(100 - Math.abs(monthReturn - 2) * 6), level: 'row', sampleSize: null }
          : null
      }],
    ],
    gate: (row) => {
      const fundamentals = row.components?.fundamentals
      const valuation = row.fundamental_categories?.valuation
      if (!finite(fundamentals) || !finite(valuation)) return 'no fundamentals or valuation score'
      if (valuation < 60) return 'not cheap relative to its sector'
      if (fundamentals < 55) return 'business quality below the floor – cheap alone is a value trap'
      return null
    },
  },

  analystConviction: {
    label: 'Analyst conviction',
    question: 'Are professional expectations being revised upward, and how fast?',
    components: [
      // Change, not level: a static 2.6/5 consensus is already in the price.
      ['revisions', 'EPS revision strength', 0.40, (index, row) => {
        const breadth = estimates(row).revision_breadth_30d
        const magnitude = estimates(row).eps_revision_30d_pct
        const legs = []
        if (finite(breadth)) legs.push(clamp(50 + breadth * 50))
        if (finite(magnitude)) legs.push(clamp(50 + magnitude * 200))
        return legs.length ? { value: legs.reduce((a, b) => a + b, 0) / legs.length, level: 'row', sampleSize: null } : null
      }],
      ['upgrades', 'Upgrades vs downgrades', 0.25, centered((row) => estimates(row).net_upgrades_90d, 6)],
      ['target_upside', 'Target upside', 0.15, centered((row) => row.analyst_target_upside, 1.5)],
      ['consensus', 'Recommendation distribution', 0.10, (index, row) => {
        const rating = row.analyst_rating // Yahoo: 1 strong buy .. 5 strong sell
        return finite(rating) ? { value: clamp(50 + (3 - rating) * 25), level: 'row', sampleSize: null } : null
      }],
      ['coverage', 'Analyst breadth', 0.10, (index, row) => {
        const count = row.analyst_count
        return finite(count) ? { value: clamp(Math.min(100, count * 5)), level: 'row', sampleSize: null } : null
      }],
    ],
    gate: (row) => {
      if (!finite(row.analyst_count) || row.analyst_count < 3) return 'fewer than three analysts covering'
      const detail = estimates(row)
      const hasChange = finite(detail.revision_breadth_30d) || finite(detail.eps_revision_30d_pct)
        || finite(detail.net_upgrades_90d) || finite(detail.target_change_30d_pct)
      const hasLevel = finite(row.analyst_rating) || finite(row.analyst_target_upside)
      if (!hasChange && !hasLevel) return 'no rating, target or revision history'
      return null
    },
  },

  // The swing-horizon layer, 2 trading days to 8 weeks. Same five legs, same declared
  // weights and same negative screen as the published screen at /screens/swing
  // (pipeline/swing_signals.py) - this is that model read off the advisor row so the
  // research list can be ranked by it directly, not a second opinion about swing setups.
  //
  // The one thing this model exists to get right is the sign flip: the same raw trailing
  // return predicts reversal at 2-10 days and continuation at 3-12 months. So the
  // contrarian leg reads only the last five sessions, the continuation leg is 52-week-high
  // proximity (George-Hwang, which carries no recent-month return at all), and no trailing
  // return is read twice. A single "past return" factor spanning the whole window averages
  // to noise.
  swing: {
    label: 'Swing setup (2 days–8 weeks)',
    question: 'Is there evidence at the swing horizon, from the signals that survive costs?',
    components: [
      // Bernard & Thomas 1989/1990: drift in the direction of the surprise over ~60 trading
      // days, monotone in SUE. The best evidence-to-cost ratio at this horizon; dropped and
      // renormalized on rows where no surprise history resolved.
      ['pead', 'Post-earnings drift (surprise)', 0.30, percentileOf((row) => row.earnings_surprise)],
      // Jegadeesh-Kim-Krische-Lee 2004: the *change* in consensus predicts, the level mostly
      // does not. Every input here is a change over a stated window.
      ['revisions', 'Analyst revision (change)', 0.25, (index, row) => {
        const detail = estimates(row)
        const legs = []
        if (finite(detail.revision_breadth_30d)) legs.push(clamp(50 + detail.revision_breadth_30d * 50))
        if (finite(detail.eps_revision_30d_pct)) legs.push(clamp(50 + detail.eps_revision_30d_pct * 200))
        if (finite(detail.net_upgrades_90d)) legs.push(clamp(50 + detail.net_upgrades_90d * 6))
        if (finite(detail.target_change_30d_pct)) legs.push(clamp(50 + detail.target_change_30d_pct * 200))
        return legs.length ? { value: legs.reduce((a, b) => a + b, 0) / legs.length, level: 'row', sampleSize: null } : null
      }],
      // Gervais-Kaniel-Mingelgrin 2001: unusually high volume over a day or a week is
      // followed by appreciation over the next month. Measured against the stock's own
      // normal first (volume_ratio_60d), then ranked across peers.
      ['volume', 'High-volume premium', 0.20, percentileOf((row) => technical(row).volume_ratio_60d)],
      ['proximity', '52-week-high proximity', 0.15, (index, row) => {
        const fromHigh = technical(row).pct_from_52w_high
        return finite(fromHigh) ? { value: clamp(100 + fromHigh * 2), level: 'row', sampleSize: null } : null
      }],
      // Jegadeesh 1990, reversed - and deliberately the smallest weight. Da-Liu-Schaumburg
      // 2014 cut the risk-adjusted alpha to 0.33%/month at t=1.37, and it is the most
      // cost-constrained strategy in Frazzini-Israel-Moskowitz, so the gate below refuses to
      // score it at all outside liquid names.
      ['reversal', 'Prior-week reversal', 0.10, (index, row) => {
        const week = technical(row).return_5d
        return finite(week) ? { value: clamp(50 - week * 5), level: 'row', sampleSize: null } : null
      }],
    ],
    gate: (row) => {
      const detail = technical(row)
      if (!finite(detail.return_5d)) return 'no recent return history'
      // Spread, not market impact, is the binding cost at retail size - and it is worst in
      // exactly the small illiquid names where the published effect sizes are largest.
      if (finite(row.average_dollar_volume) && row.average_dollar_volume < SWING_MIN_DOLLAR_VOLUME) {
        return 'below the liquidity floor where spread cost eats a swing-horizon edge'
      }
      const legs = [
        row.earnings_surprise, estimates(row).revision_breadth_30d, estimates(row).eps_revision_30d_pct,
        detail.volume_ratio_60d, detail.pct_from_52w_high,
      ].filter(finite)
      // One resolved input is not a composite, and a five-leg model resting on the reversal
      // leg alone is just "sell whatever moved last week".
      if (legs.length < 2) return 'fewer than two swing-horizon signals resolved on this row'
      return null
    },
    // Boehmer-Jones-Zhang 2008 is a short-side result and this book is long-only, so heavy
    // short interest suppresses rather than scoring a leg - the same negative-screen
    // treatment /screens/swing applies, expressed as the cap this framework already has.
    cap: (row) => {
      const flagged = shortInterestSuppressed(row)
      return flagged ? { limit: SHORT_INTEREST_CAP, label: 'Crowded short', reason: flagged } : null
    },
  },

  tailwind: {
    label: 'Peer read-through / not yet re-rated',
    question: 'Is the evidence improving faster than the price has re-rated?',
    components: [
      ['read_through', 'Peer read-through', 0.25, (index, row) => {
        const best = (row.theme_exposure || [])
          .filter((exposure) => finite(exposure.opportunity_score))
          .sort((a, b) => b.opportunity_score - a.opportunity_score)[0]
        return best ? { value: clamp(best.theme_exposure_score ?? best.opportunity_score), level: 'theme', sampleSize: null } : null
      }],
      ['revisions', 'Own expectation revisions', 0.25, direct((row) => evidence(row).expectation_score)],
      ['valuation_gap', 'Valuation discount', 0.20, direct((row) => row.sector_valuation_percentile)],
      // The lag itself is the opportunity: a name that has already run is, by definition,
      // re-rated. Price momentum contributes nothing positive to this model by design.
      ['price_lag', 'Relative price lag', 0.20, (index, row) => {
        const relative = technical(row).relative_strength_20d
        return finite(relative) ? { value: clamp(50 - relative * 2), level: 'row', sampleSize: null } : null
      }],
      ['quality', 'Business quality', 0.10, percentileOf((row) => row.components?.fundamentals)],
    ],
    gate: (row) => {
      const best = (row.theme_exposure || []).filter((exposure) => finite(exposure.opportunity_score))
      if (!best.length) return 'no scored structural-trend exposure'
      // Otherwise this is just "buy the weakest company in a hot industry".
      const expectation = evidence(row).expectation_score
      if (finite(expectation) && expectation < 45) return 'own expectations are being revised down'
      const news = evidence(row).news_score
      if (finite(news) && news < 35) return 'own recent material news is negative'
      return null
    },
  },
}

export const MODEL_KEYS = Object.keys(RANKING_MODELS)

export function isRankingModel(key) {
  return Object.prototype.hasOwnProperty.call(RANKING_MODELS, key)
}

// ---------------------------------------------------------------------------
// Scoring
// ---------------------------------------------------------------------------

/**
 * Score one row under one model.
 *
 * Returns null when the row fails the model's gate - a screen lists names that clear its bar,
 * and a padded ordering of everything else is what made every lens look like the fundamentals
 * leaderboard in the first place.
 */
export function scoreRow(index, row, modelKey) {
  const model = RANKING_MODELS[modelKey]
  if (!model || !row || row.is_etf) return null
  const blocked = model.gate ? model.gate(row) : null
  if (blocked) return null

  const applied = []
  const dropped = []
  for (const [key, label, weight, score] of model.components) {
    const result = score(index, row)
    if (!result || !finite(result.value)) {
      dropped.push({ key, label, weight })
      continue
    }
    applied.push({ key, label, weight, value: result.value, level: result.level, sampleSize: result.sampleSize })
  }
  if (!applied.length) return null

  // Renormalize over what applied. A company that cannot report a metric is not scored zero
  // for it - it is scored on the rest, and it pays for the gap in confidence instead.
  const appliedWeight = applied.reduce((sum, item) => sum + item.weight, 0)
  let raw = applied.reduce((sum, item) => sum + item.value * item.weight, 0) / appliedWeight

  const cap = model.cap ? model.cap(row) : null
  if (cap && raw > cap.limit) raw = cap.limit

  const confidence = modeConfidence(row, modelKey)
  const shrunk = shrinkToConfidence(raw, (confidence?.confidence ?? 0) * 100)

  return {
    model: modelKey,
    raw: Number(raw.toFixed(1)),
    score: Number(shrunk.toFixed(1)),
    confidence: confidence?.confidence ?? 0,
    confidencePercent: confidence?.percent ?? 0,
    confidenceInputs: confidence?.inputs || [],
    components: applied.map((item) => ({
      ...item,
      value: Number(item.value.toFixed(1)),
      // Share of the final score this component actually carried, after renormalization.
      contribution: Number(((item.weight / appliedWeight) * 100).toFixed(1)),
    })),
    droppedComponents: dropped,
    coverage: Number((appliedWeight / model.components.reduce((sum, [, , weight]) => sum + weight, 0)).toFixed(3)),
    cap: cap || null,
  }
}

/** Rank a universe under one model: qualifying rows only, best first. */
export function rankByModel(rows, modelKey, limit = 20) {
  const stocks = (rows || []).filter((row) => !row?.is_etf)
  const index = buildPeerIndex(stocks)
  const scored = []
  for (const row of stocks) {
    const result = scoreRow(index, row, modelKey)
    if (result) scored.push({ ...row, modelScore: result })
  }
  scored.sort((left, right) => right.modelScore.score - left.modelScore.score)
  return scored.slice(0, limit)
}

/**
 * Why a model returned the list it returned: how many rows it could see, how many cleared the
 * gate, and the reasons the rest did not - counted, so "this screen is short" always has an
 * answer in the data rather than in a guess.
 */
export function modelCoverage(rows, modelKey) {
  const model = RANKING_MODELS[modelKey]
  if (!model) return null
  const stocks = (rows || []).filter((row) => !row?.is_etf)
  const reasons = new Map()
  let qualified = 0
  for (const row of stocks) {
    const blocked = model.gate ? model.gate(row) : null
    if (!blocked) {
      qualified += 1
      continue
    }
    reasons.set(blocked, (reasons.get(blocked) || 0) + 1)
  }
  const ranked = [...reasons.entries()]
    .map(([reason, count]) => ({ reason, count }))
    .sort((left, right) => right.count - left.count)
  return {
    scanned: stocks.length,
    qualified,
    excluded: stocks.length - qualified,
    reasons: ranked,
    binding: ranked[0] || null,
  }
}

/** One-line statement of what the model liked, strongest contributor first. */
export function modelReason(row) {
  const result = row?.modelScore
  if (!result) return ''
  return result.components
    .slice()
    .sort((left, right) => (right.value * right.weight) - (left.value * left.weight))
    .slice(0, 3)
    .map((item) => `${item.label.toLowerCase()} ${Math.round(item.value)}`)
    .join(' · ')
}
