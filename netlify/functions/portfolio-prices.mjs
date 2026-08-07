import { cert, getApps, initializeApp } from 'firebase-admin/app'
import { getAuth } from 'firebase-admin/auth'

const json = (statusCode, body) => ({
  statusCode,
  headers: {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
  },
  body: JSON.stringify(body),
})

function firebaseApp() {
  if (getApps().length) return getApps()[0]
  const raw = process.env.FIREBASE_SERVICE_ACCOUNT_JSON
  if (!raw) throw new Error('FIREBASE_SERVICE_ACCOUNT_JSON is not configured')
  return initializeApp({ credential: cert(JSON.parse(raw)) })
}

export function parseSymbols(body) {
  let payload = {}
  try {
    payload = JSON.parse(body || '{}')
  } catch {
    payload = {}
  }
  if (!Array.isArray(payload.symbols)) return []
  return [...new Set(payload.symbols
    .map((symbol) => String(symbol || '').trim().toUpperCase())
    .filter((symbol) => /^[A-Z][A-Z0-9.-]{0,9}$/.test(symbol))
  )].slice(0, 50)
}

function yahooSymbol(symbol) {
  return symbol.replaceAll('.', '-')
}

function finiteNumber(value) {
  if (value == null || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

// Yahoo's chart endpoint currently returns the extended-session candles even when its
// convenient postMarket* meta fields are null. Recover the latest real post-market trade
// from those candles so a successful refresh does not silently look like "no after-hours".
function latestPostMarketPrice(chart) {
  const timestamps = chart?.timestamp
  const closes = chart?.indicators?.quote?.[0]?.close
  const post = chart?.meta?.currentTradingPeriod?.post
  const postStart = finiteNumber(post?.start)
  const postEnd = finiteNumber(post?.end)
  if (!Array.isArray(timestamps) || !Array.isArray(closes) || postStart == null) return null

  for (let index = Math.min(timestamps.length, closes.length) - 1; index >= 0; index -= 1) {
    const timestamp = finiteNumber(timestamps[index])
    const close = finiteNumber(closes[index])
    if (timestamp != null && close != null && timestamp >= postStart && (postEnd == null || timestamp <= postEnd)) {
      return { price: close, time: timestamp }
    }
  }
  return null
}

export async function fetchPortfolioQuotes(symbols, fetchImpl = fetch) {
  const results = await Promise.all(symbols.map(async (symbol) => {
    try {
      // includePrePost=true is what puts postMarketPrice/postMarketChange in `meta` at all —
      // without it Yahoo only ever returns the regular-session price, before or after the bell.
      const response = await fetchImpl(
        `https://query2.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(yahooSymbol(symbol))}?interval=1m&range=1d&includePrePost=true`,
        {
          headers: {
            Accept: 'application/json',
            'User-Agent': 'Mozilla/5.0 ValueSignal/1.0',
          },
        },
      )
      if (!response.ok) throw new Error(`quote provider returned ${response.status}`)
      const payload = await response.json()
      const chart = payload?.chart?.result?.[0]
      const meta = chart?.meta
      const price = finiteNumber(meta?.regularMarketPrice)
      if (price == null) throw new Error('quote provider returned no price')
      const previousClose = finiteNumber(meta?.chartPreviousClose ?? meta?.previousClose)
      const candlePostMarket = latestPostMarketPrice(chart)
      const postMarketPrice = finiteNumber(meta?.postMarketPrice) ?? candlePostMarket?.price ?? null
      const postMarketChange = finiteNumber(meta?.postMarketChange)
        ?? (postMarketPrice == null ? null : postMarketPrice - price)
      const postMarketChangePercent = finiteNumber(meta?.postMarketChangePercent)
        ?? (postMarketChange == null || !price ? null : (postMarketChange / price) * 100)
      const postMarketTime = finiteNumber(meta?.postMarketTime) ?? candlePostMarket?.time ?? null
      return {
        ok: true,
        symbol,
        quote: {
          ticker: symbol,
          name: meta.longName || meta.shortName || symbol,
          price,
          previousClose,
          marketTime: finiteNumber(meta.regularMarketTime) != null
            ? new Date(Number(meta.regularMarketTime) * 1000).toISOString()
            : null,
          marketState: meta.marketState || null,
          currency: meta.currency || null,
          postMarketPrice,
          postMarketChange,
          postMarketChangePercent,
          postMarketTime: postMarketTime == null ? null : new Date(postMarketTime * 1000).toISOString(),
        },
      }
    } catch (error) {
      return { ok: false, symbol, error: error.message }
    }
  }))

  return {
    quotes: Object.fromEntries(
      results.filter((result) => result.ok).map((result) => [result.symbol, result.quote]),
    ),
    failed: results.filter((result) => !result.ok).map(({ symbol, error }) => ({ symbol, error })),
  }
}

export async function handler(event) {
  if (event.httpMethod !== 'POST') return json(405, { error: 'Method not allowed.' })

  const authorization = event.headers.authorization || event.headers.Authorization || ''
  const idToken = authorization.startsWith('Bearer ') ? authorization.slice(7) : ''
  if (!idToken) return json(401, { error: 'Sign in before refreshing portfolio prices.' })

  const symbols = parseSymbols(event.body)
  if (!symbols.length) return json(400, { error: 'No valid portfolio symbols were provided.' })

  try {
    await getAuth(firebaseApp()).verifyIdToken(idToken, true)
    const { quotes, failed } = await fetchPortfolioQuotes(symbols)
    if (!Object.keys(quotes).length) {
      return json(502, { error: 'The quote provider did not return any portfolio prices.', failed })
    }
    return json(200, {
      quotes,
      failed,
      fetchedAt: new Date().toISOString(),
      requested: symbols.length,
      updated: Object.keys(quotes).length,
    })
  } catch (error) {
    console.error('Portfolio price refresh failed:', error)
    return json(500, { error: 'Portfolio prices could not be refreshed. Please try again.' })
  }
}
