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

export function rankValueTurnarounds(rows, limit = 5) {
  return rows
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

export function rankGrowingEtfs(rows, limit = 5) {
  return rows
    .filter((row) => row.is_etf)
    .map((row) => {
      const technical = row.technical_detail || {}
      const weekReturn = finite(technical.return_5d) ? technical.return_5d : trailingWeekReturn(row)
      const monthReturn = technical.return_20d
      if (![weekReturn, monthReturn].every(finite) || monthReturn <= 0) return null

      const trend = finite(technical.trend) ? technical.trend : clamp(50 + monthReturn * 2)
      const upturn = clamp(50 + weekReturn * 5)
      return {
        ...row,
        screen: {
          weekReturn,
          monthReturn,
          rankScore: trend * 0.6 + upturn * 0.4,
        },
      }
    })
    .filter(Boolean)
    .sort((left, right) => right.screen.rankScore - left.screen.rankScore)
    .slice(0, limit)
}

export function rankMomentum(rows, limit = 5) {
  return rows
    .map((row) => {
      const technical = row.technical_detail || {}
      const weekReturn = finite(technical.return_5d)
        ? technical.return_5d
        : trailingWeekReturn(row)
      const monthReturn = technical.return_20d
      if (![weekReturn, monthReturn].every(finite) || weekReturn <= 0 || monthReturn <= 0) return null

      const trend = finite(technical.trend) ? technical.trend : clamp(50 + monthReturn * 2)
      const relative = finite(technical.relative_strength)
        ? technical.relative_strength
        : clamp(50 + (technical.relative_strength_20d || 0) * 3)
      const volume = finite(technical.volume_confirmation) ? technical.volume_confirmation : 50
      const risk = finite(technical.risk) ? technical.risk : 50
      return {
        ...row,
        screen: {
          weekReturn,
          monthReturn,
          relativeReturn: technical.relative_strength_20d,
          rankScore: trend * 0.4 + relative * 0.25 + volume * 0.15 + risk * 0.2,
        },
      }
    })
    .filter(Boolean)
    .sort((left, right) => right.screen.rankScore - left.screen.rankScore)
    .slice(0, limit)
}

