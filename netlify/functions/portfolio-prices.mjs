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
      const meta = payload?.chart?.result?.[0]?.meta
      const price = Number(meta?.regularMarketPrice)
      if (!Number.isFinite(price)) throw new Error('quote provider returned no price')
      const previousClose = Number(meta?.chartPreviousClose ?? meta?.previousClose)
      // Only present once the session has actually moved past the closing bell with a real
      // post-market trade — Yahoo omits these fields entirely during regular hours, and that
      // absence is the honest signal, not a 0 to paper over.
      const postMarketPrice = Number(meta?.postMarketPrice)
      const postMarketChange = Number(meta?.postMarketChange)
      const postMarketChangePercent = Number(meta?.postMarketChangePercent)
      return {
        ok: true,
        symbol,
        quote: {
          ticker: symbol,
          name: meta.longName || meta.shortName || symbol,
          price,
          previousClose: Number.isFinite(previousClose) ? previousClose : null,
          marketTime: Number.isFinite(Number(meta.regularMarketTime))
            ? new Date(Number(meta.regularMarketTime) * 1000).toISOString()
            : null,
          marketState: meta.marketState || null,
          currency: meta.currency || null,
          postMarketPrice: Number.isFinite(postMarketPrice) ? postMarketPrice : null,
          postMarketChange: Number.isFinite(postMarketChange) ? postMarketChange : null,
          postMarketChangePercent: Number.isFinite(postMarketChangePercent) ? postMarketChangePercent : null,
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
