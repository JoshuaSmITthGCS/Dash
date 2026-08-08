const clamp = (value, minimum = 0, maximum = 100) =>
  Math.min(maximum, Math.max(minimum, value))

function finite(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

function weeklyCloses(row) {
  return (row?.history?.closes || row?.history?.growth || []).filter(finite)
}

export function trailingWeekReturn(row) {
  const closes = weeklyCloses(row)
  if (closes.length < 2 || !closes.at(-2)) return null
  return (closes.at(-1) / closes.at(-2) - 1) * 100
}

export function distanceAbove52WeekLow(row) {
  const closes = weeklyCloses(row).slice(-53)
  if (closes.length < 26) return null
  const low = Math.min(...closes)
  return low > 0 ? (closes.at(-1) / low - 1) * 100 : null
}

// Corroborated-first sort, mirroring rankThemeExposure's eligible-first pattern below: an
// uncorroborated top-scorer stays visible (it's still real information) but never
// outranks a row whose primary signal was independently confirmed. Never used to drop a
// row - only to order it - same "flag, don't hide" philosophy the theme screen already
// established.
function sortCorroboratedFirst(rows) {
  return rows.sort((left, right) => {
    if (left.screen.corroborated !== right.screen.corroborated) return left.screen.corroborated ? -1 : 1
    return right.screen.rankScore - left.screen.rankScore
  })
}

// Trust ordering for pipeline/config/settings.json's source_quality tiers, mirrored from
// the pipeline-side SOURCE_QUALITY_TRUST_ORDER in fetch_advisor.py. Reads whichever shape
// the row carries: `sentiment_summary` (screen_universe's lightweight projection) or the
// full `sentiment_detail.articles` (published leaderboard rows).
const SOURCE_QUALITY_TRUST_ORDER = ['regulatory_primary', 'established_press', 'neutral', 'aggregator_syndicated']
function newsCorroboration(row) {
  if (row.sentiment_summary) {
    return {
      articleCount: row.sentiment_summary.article_count ?? null,
      bestTier: row.sentiment_summary.best_source_quality_tier ?? null,
    }
  }
  const articles = row.sentiment_detail?.articles
  if (!Array.isArray(articles) || !articles.length) {
    return { articleCount: row.sentiment_detail?.article_count ?? null, bestTier: null }
  }
  const tiersPresent = new Set(articles.map((article) => article.source_quality_tier).filter(Boolean))
  const bestTier = SOURCE_QUALITY_TRUST_ORDER.find((tier) => tiersPresent.has(tier)) ?? null
  return { articleCount: row.sentiment_detail?.article_count ?? articles.length, bestTier }
}

// Every screen below reads fundamentals or technical fields shaped for individual
// companies (fundamental_categories, technical_detail.return_5d, ...). A fund holds no
// such per-security fundamentals, so an ETF can never legitimately clear one of these
// screens - reason code unsupported_security_type. Callers already keep their own stock
// and ETF pools separate (see src/pages/Picks.jsx), but this filter makes that invariant
// hold even if a caller ever passes a mixed array by mistake.
function stocksOnly(rows) {
  return rows.filter((row) => !row?.is_etf)
}

export function rankValueTurnarounds(rows, limit = 5) {
  const candidates = stocksOnly(rows)
    .map((row) => {
      const fundamentals = row.components?.fundamentals
      const valuation = row.fundamental_categories?.valuation
      const weekReturn = finite(row.technical_detail?.return_5d)
        ? row.technical_detail.return_5d
        : trailingWeekReturn(row)
      const aboveLow = finite(row.technical_detail?.pct_above_52w_low)
        ? row.technical_detail.pct_above_52w_low
        : distanceAbove52WeekLow(row)

      if (![fundamentals, valuation, weekReturn, aboveLow].every(finite)) return null
      if (fundamentals < 65 || valuation < 65 || weekReturn <= 0 || aboveLow > 35) return null

      const proximity = clamp(100 - (aboveLow / 35) * 100)
      const upturn = clamp(50 + weekReturn * 5)

      // Corroboration: a sharply negative recent earnings surprise means the cheapness
      // may reflect a genuinely deteriorating business, not just an overdone dip - flag
      // it rather than let the valuation/quality/proximity blend alone vouch for it.
      const corroborationGaps = []
      const corroborated = !(finite(row.earnings_surprise) && row.earnings_surprise < -8)
      if (!corroborated) corroborationGaps.push('recent earnings surprise was sharply negative - the cheapness may reflect a deteriorating business')

      return {
        ...row,
        screen: {
          weekReturn,
          aboveLow,
          rankScore: valuation * 0.4 + fundamentals * 0.3 + proximity * 0.2 + upturn * 0.1,
          corroborated,
          corroborationGaps,
        },
      }
    })
    .filter(Boolean)
  return sortCorroboratedFirst(candidates).slice(0, limit)
}

// ETFs are evaluated on their own, separate from the stock screens: a diversified fund
// doesn't carry the fundamentals ratios those screens gate on, and there's no meaningful
// "clears the bar" threshold for a fund the way there is for a single stock. The backend
// (pipeline/fetch_etfs.py) already ranks the full watchlist against itself on a blended
// performance/risk/cost/liquidity/quality score – this just re-sorts defensively and slices.
export function rankGrowingEtfs(rows, limit = 5) {
  return rows
    .filter((row) => finite(row.scores?.overall))
    .slice()
    .sort((left, right) => right.scores.overall - left.scores.overall)
    .slice(0, limit)
}

export function rankMomentum(rows, limit = 5) {
  const candidates = stocksOnly(rows)
    .map((row) => {
      const technical = row.technical_detail || {}
      const weekReturn = finite(technical.return_5d)
        ? technical.return_5d
        : trailingWeekReturn(row)
      const monthReturn = technical.return_20d
      if (![weekReturn, monthReturn].every(finite) || weekReturn <= 0 || monthReturn <= 0) return null

      // The backend now scores 12-1 momentum (12-month return skipping the most recent
      // month) rather than a raw recent-return formula. `trend` is the pre-rebuild field
      // name, kept as a fallback for snapshots that predate the change.
      const momentum = finite(technical.momentum_12_1)
        ? technical.momentum_12_1
        : finite(technical.trend)
          ? technical.trend
          : clamp(50 + monthReturn * 2)
      const relative = finite(technical.relative_strength)
        ? technical.relative_strength
        : clamp(50 + (technical.relative_strength_20d || 0) * 3)
      const volume = finite(technical.volume_confirmation) ? technical.volume_confirmation : 50
      // Real Sharpe/Sortino-derived risk, falling back to the old invented penalty.
      const risk = finite(technical.risk_adjusted)
        ? technical.risk_adjusted
        : finite(technical.risk)
          ? technical.risk
          : 50
      // Corroboration: multi-horizon breadth. A 5d/20d pop sitting inside a longer
      // 60/252-day downtrend is a weaker momentum case than the rankScore alone shows -
      // require at least one of the longer horizons not to be sharply negative. Missing
      // longer-horizon data (common for recently-scored names) is never penalized, only
      // an actual opposing longer trend is.
      const corroborationGaps = []
      const longer60 = technical.return_60d
      const longer252 = technical.return_252d
      const corroborated = !(finite(longer60) && finite(longer252) && longer60 < -5 && longer252 < -5)
      if (!corroborated) corroborationGaps.push('this pop sits inside a longer 60/252-day downtrend')

      return {
        ...row,
        screen: {
          weekReturn,
          monthReturn,
          momentum12m: technical.momentum_12_1_pct,
          relativeReturn: technical.relative_strength_20d,
          rankScore: momentum * 0.4 + relative * 0.25 + volume * 0.15 + risk * 0.2,
          corroborated,
          corroborationGaps,
        },
      }
    })
    .filter(Boolean)
  return sortCorroboratedFirst(candidates).slice(0, limit)
}

// Short-term reversal (Jegadeesh 1990; Lehmann 1990): a stock that pulled back over the
// medium term but has just turned up over the most recent week is a reversal candidate,
// not a falling knife. This is a daily-close screen built from already-published fields –
// unrelated to the Early-Session premarket/intraday screens, which stay killed until real
// reversal-detection logic (support zones, confirmation, trigger/invalidation) exists; see
// pipeline/early_session_research.py. A fundamentals floor keeps a genuinely deteriorating
// business from qualifying just because its price bounced.
export function rankReversal(rows, limit = 5) {
  const candidates = stocksOnly(rows)
    .map((row) => {
      const technical = row.technical_detail || {}
      const fundamentals = row.components?.fundamentals
      const weekReturn = finite(technical.return_5d) ? technical.return_5d : trailingWeekReturn(row)
      const monthReturn = technical.return_20d
      const drawdown = technical.drawdown_60d

      if (![weekReturn, monthReturn, drawdown, fundamentals].every(finite)) return null
      if (weekReturn <= 0 || monthReturn >= 0 || fundamentals < 50) return null

      const bounce = clamp(50 + weekReturn * 6)
      const pulledBack = clamp(50 + Math.abs(drawdown) * 1.2)

      // Corroboration: a sharply negative recent earnings surprise means the drop was
      // likely fundamentals-driven, not just a technical dip - unless elevated short
      // interest offers an alternate, squeeze-consistent reason for the bounce.
      const corroborationGaps = []
      const shortSqueezeSignal = finite(row.short_percent_of_float) && row.short_percent_of_float >= 0.05
      const corroborated = !(finite(row.earnings_surprise) && row.earnings_surprise < -8 && !shortSqueezeSignal)
      if (!corroborated) corroborationGaps.push('recent earnings surprise was sharply negative with no offsetting short-interest squeeze signal')

      return {
        ...row,
        screen: {
          weekReturn, monthReturn, drawdown,
          rankScore: bounce * 0.45 + pulledBack * 0.35 + clamp(fundamentals) * 0.20,
          corroborated,
          corroborationGaps,
        },
      }
    })
    .filter(Boolean)
  return sortCorroboratedFirst(candidates).slice(0, limit)
}

// Breakout in progress: catches a stock in the act of a sharp recent acceleration - the
// "NVDA V-shaped recovery", "SanDisk +33% in five days", "MSFT breaking out after a slog"
// pattern - rather than the steady, months-long drift rankMomentum already covers. The gate
// compares the pace of the most recent week against the pace set by the three weeks before it
// within the same month, so a name that has been quietly climbing all month at a constant rate
// doesn't crowd out one that just broke out this week.
//
// Named for what it actually detects: the move has ALREADY happened (weekReturn > 2, i.e.
// already up more than 2% this week) by the time a stock clears this screen. It was
// previously named rankFastGrowth, which read as "about to grow fast" - the opposite of what
// the gate requires. See rankEmergingGrowth below for the honestly-labeled attempt at
// pre-move detection.
export function rankBreakoutInProgress(rows, limit = 5) {
  return stocksOnly(rows)
    .map((row) => {
      const technical = row.technical_detail || {}
      const weekReturn = finite(technical.return_5d) ? technical.return_5d : trailingWeekReturn(row)
      const monthReturn = technical.return_20d
      const volumeRatio = technical.volume_ratio_60d
      if (![weekReturn, monthReturn].every(finite) || weekReturn <= 2 || monthReturn <= 0) return null

      const priorPace5d = (monthReturn - weekReturn) / 15 * 5
      const acceleration = weekReturn - priorPace5d
      if (acceleration <= 0) return null

      const burst = clamp(50 + weekReturn * 3)
      const accelScore = clamp(50 + acceleration * 2)
      const trend = clamp(50 + monthReturn * 1.2)
      const volume = finite(volumeRatio) ? clamp(50 + (volumeRatio - 1) * 40) : 50
      return {
        ...row,
        screen: {
          weekReturn, monthReturn, acceleration, volumeRatio,
          rankScore: burst * 0.4 + accelScore * 0.3 + trend * 0.2 + volume * 0.1,
        },
      }
    })
    .filter(Boolean)
    .sort((left, right) => right.screen.rankScore - left.screen.rankScore)
    .slice(0, limit)
}

// Emerging growth: an attempt at the thing rankBreakoutInProgress explicitly is NOT - names
// that have not yet made a big visible move but show measurables that sometimes precede one.
// research_status is "prospective_unvalidated" on every result: nothing in this codebase has
// tested whether this combination actually predicts a subsequent move (see
// docs/BASELINE-2026-08-06.md - the IC harness has 0 of 24 eligible periods). This is honest
// research scaffolding, not a claim that it works.
//
// Every input is something this row can genuinely answer, not an invented proxy:
//   - operating_margin_trend: current operating margin less the comparable prior period
//     (metric_registry.json) - a real margin-inflection signal, already computed.
//   - revenue_growth: TTM revenue growth, already computed - no "acceleration" (second
//     derivative) is available anywhere in this codebase (no time series of growth rates),
//     so this screen does not claim to detect acceleration, only a real current growth rate.
//   - volatility contraction: computed here from the row's own price history (stdev of
//     daily returns, last 10 sessions vs the trailing 60) - realized, not implied.
//   - early relative strength: a small POSITIVE relative_strength_20d that has NOT yet
//     cleared rankBreakoutInProgress's weekReturn > 2 gate - deliberately excludes anything
//     that screen already caught, so the two screens do not overlap.
//   - estimate_revision_breadth: optional bonus only when present (collect_estimates.py
//     covers a small ticker subset today) - never required, never penalized when absent.
export function rankEmergingGrowth(rows, limit = 5) {
  return stocksOnly(rows)
    .map((row) => {
      const technical = row.technical_detail || {}
      const fundamental = row.fundamental_detail || {}
      const closes = weeklyCloses(row)
      const weekReturn = finite(technical.return_5d) ? technical.return_5d : trailingWeekReturn(row)
      const revenueGrowth = fundamental.revenue_growth
      const marginTrend = fundamental.operating_margin_trend
      const relativeStrength = technical.relative_strength_20d

      // Excludes anything already caught by the breakout screen - this is meant to be a
      // distinct, earlier-stage population, not a relabeled duplicate of that list.
      if (!finite(weekReturn) || weekReturn > 2) return null
      if (!finite(revenueGrowth) || revenueGrowth <= 0.05) return null
      if (!finite(relativeStrength) || relativeStrength <= 0) return null

      let recentVol = null
      let longerVol = null
      if (closes.length >= 61) {
        const dailyReturn = (series) => series.slice(1).map((value, index) => value / series[index] - 1)
        const stdev = (values) => {
          if (values.length < 2) return null
          const avg = values.reduce((sum, value) => sum + value, 0) / values.length
          return Math.sqrt(values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / values.length)
        }
        recentVol = stdev(dailyReturn(closes.slice(-11)))
        longerVol = stdev(dailyReturn(closes.slice(-61)))
      }
      const volatilityContracting = finite(recentVol) && finite(longerVol) && longerVol > 0
        ? recentVol < longerVol * 0.85
        : null

      const growthScore = clamp(50 + revenueGrowth * 150)
      const marginScore = finite(marginTrend) ? clamp(50 + marginTrend * 300) : 50
      const strengthScore = clamp(50 + relativeStrength * 4)
      const contractionScore = volatilityContracting === null ? 50 : (volatilityContracting ? 70 : 40)
      const revisionBreadth = row.estimate_revision_breadth
      const revisionScore = finite(revisionBreadth) ? clamp(50 + revisionBreadth * 50) : null

      const weighted = [
        [growthScore, 0.35], [marginScore, 0.2], [strengthScore, 0.2], [contractionScore, 0.15],
        ...(revisionScore !== null ? [[revisionScore, 0.1]] : []),
      ]
      const totalWeight = weighted.reduce((sum, [, weight]) => sum + weight, 0)
      const rankScore = weighted.reduce((sum, [value, weight]) => sum + value * weight, 0) / totalWeight

      return {
        ...row,
        research_status: 'prospective_unvalidated',
        screen: {
          weekReturn, revenueGrowth, marginTrend, relativeStrength, volatilityContracting,
          revisionBreadth: revisionBreadth ?? null, rankScore,
        },
      }
    })
    .filter(Boolean)
    .sort((left, right) => right.screen.rankScore - left.screen.rankScore)
    .slice(0, limit)
}

// Short-term catalyst: for a quick-turnaround trade, fresh news flow and insider buying/
// selling matter far more than fundamentals - the inverse weighting of the long-term
// research score. Fundamentals stay in at a small weight, as a floor rather than a
// driver: a name that is not a strong long-term research score can still clear this
// screen, which is the point - a real catalyst on an otherwise-unremarkable business is
// exactly what this is meant to surface.
export function rankCatalyst(rows, limit = 5) {
  const candidates = stocksOnly(rows)
    .map((row) => {
      const technical = row.technical_detail || {}
      const insider = row.insider_activity || {}
      const newsSentiment = row.components?.news_sentiment
      const insiderPoints = finite(insider.points) ? insider.points
        : finite(insider.score_points) ? insider.score_points : null
      const weekReturn = finite(technical.return_5d) ? technical.return_5d : trailingWeekReturn(row)
      const volumeRatio = technical.volume_ratio_60d
      const fundamentals = row.components?.fundamentals

      const signals = []
      if (finite(newsSentiment)) signals.push([newsSentiment, 0.30])
      if (insider.available && finite(insiderPoints)) signals.push([clamp(50 + insiderPoints * 10), 0.30])
      if (finite(weekReturn)) signals.push([clamp(50 + weekReturn * 4), 0.25])
      if (finite(volumeRatio)) signals.push([clamp(50 + (volumeRatio - 1) * 40), 0.05])
      if (finite(fundamentals)) signals.push([clamp(fundamentals), 0.10])

      // Needs an actual catalyst (fresh, non-neutral news or opportunistic insider
      // activity) plus at least one other confirming signal - a quiet stock with only
      // stale/neutral inputs is not a "something is happening right now" candidate.
      const hasCatalyst = (finite(newsSentiment) && Math.abs(newsSentiment - 50) > 5) ||
        (insider.available && finite(insiderPoints) && insiderPoints !== 0)
      if (!hasCatalyst || signals.length < 2) return null

      const totalWeight = signals.reduce((sum, [, weight]) => sum + weight, 0)
      const rankScore = signals.reduce((sum, [value, weight]) => sum + value * weight, 0) / totalWeight

      // Corroboration: a catalyst resting on a single low-track-record insider or a
      // single low-quality news source is thinner evidence than the composite rankScore
      // alone shows. Checks only the leg(s) that actually qualified this row as having a
      // catalyst above - a row is corroborated if at least one qualifying leg is backed
      // by independent breadth/quality, not just the aggregate points/sentiment number.
      const corroborationGaps = []
      const legsCorroborated = []
      if (insider.available && finite(insiderPoints) && insiderPoints !== 0) {
        const cluster = insiderPoints > 0 ? insider.buy_cluster : insider.sell_cluster
        const breadthOk = finite(cluster?.insider_count) && cluster.insider_count >= 2
        const confidenceOk = finite(cluster?.pattern_confidence) && cluster.pattern_confidence >= 0.6
        const ok = breadthOk || confidenceOk
        legsCorroborated.push(ok)
        if (!ok) corroborationGaps.push('insider activity is a single trader with no established track record')
      }
      if (finite(newsSentiment) && Math.abs(newsSentiment - 50) > 5) {
        const { articleCount, bestTier } = newsCorroboration(row)
        const ok = (finite(articleCount) && articleCount >= 2) || (bestTier != null && bestTier !== 'aggregator_syndicated')
        legsCorroborated.push(ok)
        if (!ok) corroborationGaps.push('news sentiment rests on a single low-quality source')
      }
      const corroborated = legsCorroborated.some(Boolean)

      return {
        ...row,
        screen: {
          newsSentiment: newsSentiment ?? null,
          insiderPoints,
          weekReturn,
          rankScore,
          corroborated,
          corroborationGaps,
        },
      }
    })
    .filter(Boolean)
  return sortCorroboratedFirst(candidates).slice(0, limit)
}

// Analyst conviction: rising consensus target and bullish average rating from
// professional coverage - a different "the market hasn't fully repriced this yet"
// signal from Catalyst (news/insider) or Momentum (price trend). Point-in-time estimate
// *revision* history (rate of change in forward EPS estimates) is fetched by
// pipeline/collect_estimates.py but not yet published on individual research rows (see
// TODO.md); this screen uses what is actually published today - the level of consensus
// rating and target upside, not its trend - and should absorb revision data once that
// pipeline gap closes rather than staying a separate screen. Requires >=3 analysts,
// matching the coverage floor the backend's own expectations modifier uses
// (advisor_engine.py:315).
export function rankAnalystConviction(rows, limit = 5) {
  const candidates = stocksOnly(rows)
    .map((row) => {
      const count = row.analyst_count
      const rating = row.analyst_rating // Yahoo convention: 1 = strong buy, 5 = strong sell
      const upside = row.analyst_target_upside // percent, consensus target vs. current price
      const fundamentals = row.components?.fundamentals
      if (!finite(count) || count < 3) return null
      if (!finite(rating) && !finite(upside)) return null

      const ratingScore = finite(rating) ? clamp(50 + (3 - rating) * 25) : null
      const upsideScore = finite(upside) ? clamp(50 + upside * 1.5) : null
      const signals = [
        ...(ratingScore !== null ? [[ratingScore, 0.5]] : []),
        ...(upsideScore !== null ? [[upsideScore, 0.4]] : []),
        ...(finite(fundamentals) ? [[clamp(fundamentals), 0.1]] : []),
      ]
      const totalWeight = signals.reduce((sum, [, weight]) => sum + weight, 0)
      const rankScore = signals.reduce((sum, [value, weight]) => sum + value * weight, 0) / totalWeight

      // Corroboration: a large consensus upside on a name already trading in the most
      // expensive decile of its own sector is internally inconsistent - the target may
      // simply be stale relative to a price that has since run.
      const corroborationGaps = []
      const corroborated = !(finite(upside) && upside > 15 && finite(row.sector_valuation_percentile) && row.sector_valuation_percentile > 85)
      if (!corroborated) corroborationGaps.push('consensus target implies large upside but the stock already trades in the most expensive decile of its sector')

      return {
        ...row,
        screen: {
          analystCount: count,
          analystRating: rating ?? null,
          targetUpside: upside ?? null,
          rankScore,
          corroborated,
          corroborationGaps,
        },
      }
    })
    .filter(Boolean)
  return sortCorroboratedFirst(candidates).slice(0, limit)
}

// Structural-trend exposure is deliberately its own screen rather than a component of the
// research score. Blending a forward-looking thematic bet into the fundamentals score would
// make that score unreadable – you could no longer tell whether a stock ranked well because
// it was cheap and profitable or because it carried a fashionable tag.
//
// Two rules this ranking enforces, both aimed at the documented failure mode of thematic
// products (buying whatever already ran):
//   1. Names the backend excluded on valuation grounds sort below eligible ones. They stay
//      visible – high exposure at a euphoric price is worth knowing – but never lead.
//   2. Ordering uses opportunity_score (exposure × quality × valuation discipline), never
//      exposure alone, so the purest-play expensive name does not automatically win.
export function rankThemeExposure(theme, limit = 5) {
  const rows = theme?.rows || []
  return rows
    .filter((row) => finite(row.theme_exposure_score))
    .slice()
    .sort((left, right) => {
      if (left.eligible !== right.eligible) return left.eligible ? -1 : 1
      const leftScore = finite(left.opportunity_score) ? left.opportunity_score : -1
      const rightScore = finite(right.opportunity_score) ? right.opportunity_score : -1
      if (leftScore !== rightScore) return rightScore - leftScore
      return right.theme_exposure_score - left.theme_exposure_score
    })
    .slice(0, limit)
}

// Themes that actually produced scored rows, so the UI doesn't render an empty panel for a
// theme whose signals were all unavailable this run.
export function activeThemes(screen) {
  return (screen?.themes || []).filter((theme) => (theme.rows || []).length > 0)
}

