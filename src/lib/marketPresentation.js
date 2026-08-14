const finite = (value) => typeof value === 'number' && Number.isFinite(value)

function latestClosePair(row) {
  const closes = row?.analytics_history?.closes || row?.history?.closes || []
  const usable = closes.filter(finite)
  if (usable.length < 2) return null
  return { previousClose: usable.at(-2), price: usable.at(-1) }
}

export function dailyMove(row) {
  const livePrice = finite(row?.price) ? row.price : null
  const livePrevious = finite(row?.previousClose) ? row.previousClose : null
  const pair = livePrice != null && livePrevious != null
    ? { price: livePrice, previousClose: livePrevious }
    : latestClosePair(row)
  if (!pair || !pair.previousClose) return { available: false, price: livePrice, previousClose: livePrevious, delta: null, pct: null }
  const delta = pair.price - pair.previousClose
  return {
    available: true,
    price: pair.price,
    previousClose: pair.previousClose,
    delta,
    pct: delta / pair.previousClose * 100,
  }
}

export function dailyMoveForPosition(position) {
  const move = dailyMove(position?.priceInfo)
  const shares = Number(position?.shares)
  return {
    ...move,
    positionDelta: move.available && Number.isFinite(shares) ? move.delta * shares : null,
  }
}

export function rankDailyStocks(rows = []) {
  return rows
    .map((row) => ({ ...row, dailyMove: dailyMove(row) }))
    .filter((row) => row.dailyMove.available)
    .sort((left, right) => right.dailyMove.pct - left.dailyMove.pct)
}

export function rankDailySectors(rows = []) {
  const sectors = new Map()
  for (const row of rankDailyStocks(rows)) {
    const sector = row.sector || 'Unclassified'
    if (sector === 'Unclassified') continue
    const current = sectors.get(sector) || { sector, totalPct: 0, count: 0, leaders: [] }
    current.totalPct += row.dailyMove.pct
    current.count += 1
    current.leaders.push(row)
    sectors.set(sector, current)
  }
  return [...sectors.values()]
    .map((sector) => ({
      ...sector,
      averagePct: sector.totalPct / sector.count,
      leaders: sector.leaders.sort((left, right) => right.dailyMove.pct - left.dailyMove.pct),
    }))
    .sort((left, right) => right.averagePct - left.averagePct)
}

export function marketType(rows = []) {
  const ranked = rankDailyStocks(rows)
  if (!ranked.length) return { label: 'Awaiting prices', tone: 'neutral', breadthPct: null, averagePct: null }
  const advancing = ranked.filter((row) => row.dailyMove.pct > 0).length
  const breadthPct = advancing / ranked.length * 100
  const averagePct = ranked.reduce((sum, row) => sum + row.dailyMove.pct, 0) / ranked.length
  if (breadthPct >= 62 && averagePct > 0.25) return { label: 'Risk-on session', tone: 'positive', breadthPct, averagePct }
  if (breadthPct <= 38 && averagePct < -0.25) return { label: 'Risk-off session', tone: 'negative', breadthPct, averagePct }
  return { label: 'Mixed session', tone: 'neutral', breadthPct, averagePct }
}

export function priceSeriesFromSnapshot(snapshot) {
  const rows = snapshot?.price_series?.fund || []
  const usable = rows.filter((row) => row?.date && finite(row.adjusted_close))
  return {
    dates: usable.map((row) => row.date),
    values: usable.map((row) => row.adjusted_close),
  }
}
