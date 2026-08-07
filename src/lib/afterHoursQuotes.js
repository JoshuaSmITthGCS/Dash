/**
 * Rolls Yahoo's per-symbol post-market quotes (netlify/functions/portfolio-prices.mjs) up
 * into a single portfolio-level after-hours dollar and percent move.
 *
 * Yahoo only reports `postMarketChange` once the regular session has actually closed and a
 * post-market trade has printed – during market hours, or for a symbol with no after-hours
 * activity, the field is absent. A position missing it is simply left out of the total
 * rather than treated as a $0 move, so a partially-covered portfolio still gets an honest
 * (if partial) number instead of a diluted one.
 */

const finite = (value) => typeof value === 'number' && Number.isFinite(value)

export function afterHoursPortfolioReturn(positions, quotes = {}) {
  const rows = (positions || [])
    .map((position) => {
      const quote = quotes[String(position.ticker || '').toUpperCase()]
      const shares = Number(position.shares)
      if (!quote || !finite(shares) || !finite(quote.postMarketChange)) return null
      const priorClose = finite(quote.postMarketPrice) ? quote.postMarketPrice - quote.postMarketChange : null
      return {
        ticker: position.ticker,
        dollarReturn: quote.postMarketChange * shares,
        priorValue: priorClose != null ? priorClose * shares : null,
      }
    })
    .filter(Boolean)

  if (!rows.length) {
    return { available: false, reason: 'No after-hours quote is available yet for any held position.', coverage: 0 }
  }

  const dollarReturn = rows.reduce((sum, row) => sum + row.dollarReturn, 0)
  const priorValues = rows.filter((row) => row.priorValue != null)
  const priorValue = priorValues.reduce((sum, row) => sum + row.priorValue, 0)

  return {
    available: true,
    dollarReturn,
    returnPct: priorValues.length === rows.length && priorValue ? (dollarReturn / priorValue) * 100 : null,
    coverage: rows.length,
    tickers: rows.map((row) => row.ticker),
  }
}

/**
 * The portfolio's live day-so-far dollar and percent move: each holding's fetched price
 * versus its own previousClose (Yahoo's `chartPreviousClose`, carried onto the merged price
 * row by mergePortfolioQuotes), summed across whichever holdings currently have a live
 * quote. Falls back to nothing (`available: false`) when no holding has one yet, so a caller
 * can fall back to the report's close-to-close move instead of showing a false $0.
 */
export function liveTodayPortfolioReturn(positions, priceData = {}) {
  const rows = (positions || [])
    .map((position) => {
      const source = priceData[String(position.ticker || '').toUpperCase()]
      const shares = Number(position.shares)
      if (!source?.portfolioQuote || !finite(shares) || !finite(source.price) || !finite(source.previousClose) || !source.previousClose) return null
      return {
        ticker: position.ticker,
        dollarReturn: (source.price - source.previousClose) * shares,
        priorValue: source.previousClose * shares,
      }
    })
    .filter(Boolean)

  if (!rows.length) {
    return { available: false, reason: 'No live quote is available yet for any held position.', coverage: 0 }
  }

  const dollarReturn = rows.reduce((sum, row) => sum + row.dollarReturn, 0)
  const priorValue = rows.reduce((sum, row) => sum + row.priorValue, 0)

  return {
    available: true,
    dollarReturn,
    returnPct: priorValue ? (dollarReturn / priorValue) * 100 : null,
    coverage: rows.length,
    tickers: rows.map((row) => row.ticker),
  }
}
