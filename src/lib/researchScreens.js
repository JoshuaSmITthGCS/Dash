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
  return stocksOnly(rows)
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
      return {
        ...row,
        screen: {
          weekReturn,
          aboveLow,
          rankScore: valuation * 0.4 + fundamentals * 0.3 + proximity * 0.2 + upturn * 0.1,
        },
      }
    })
    .filter(Boolean)
    .sort((left, right) => right.screen.rankScore - left.screen.rankScore)
    .slice(0, limit)
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
  return stocksOnly(rows)
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
      return {
        ...row,
        screen: {
          weekReturn,
          monthReturn,
          momentum12m: technical.momentum_12_1_pct,
          relativeReturn: technical.relative_strength_20d,
          rankScore: momentum * 0.4 + relative * 0.25 + volume * 0.15 + risk * 0.2,
        },
      }
    })
    .filter(Boolean)
    .sort((left, right) => right.screen.rankScore - left.screen.rankScore)
    .slice(0, limit)
}

// Short-term reversal (Jegadeesh 1990; Lehmann 1990): a stock that pulled back over the
// medium term but has just turned up over the most recent week is a reversal candidate,
// not a falling knife. This is a daily-close screen built from already-published fields –
// unrelated to the Early-Session premarket/intraday screens, which stay killed until real
// reversal-detection logic (support zones, confirmation, trigger/invalidation) exists; see
// pipeline/early_session_research.py. A fundamentals floor keeps a genuinely deteriorating
// business from qualifying just because its price bounced.
export function rankReversal(rows, limit = 5) {
  return stocksOnly(rows)
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
      return {
        ...row,
        screen: {
          weekReturn, monthReturn, drawdown,
          rankScore: bounce * 0.45 + pulledBack * 0.35 + clamp(fundamentals) * 0.20,
        },
      }
    })
    .filter(Boolean)
    .sort((left, right) => right.screen.rankScore - left.screen.rankScore)
    .slice(0, limit)
}

// Fast growth / breakout: catches a stock in the act of a sharp recent acceleration - the
// "NVDA V-shaped recovery", "SanDisk +33% in five days", "MSFT breaking out after a slog"
// pattern - rather than the steady, months-long drift rankMomentum already covers. The gate
// compares the pace of the most recent week against the pace set by the three weeks before it
// within the same month, so a name that has been quietly climbing all month at a constant rate
// doesn't crowd out one that just broke out this week.
export function rankFastGrowth(rows, limit = 5) {
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

