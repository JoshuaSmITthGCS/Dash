import { cert, getApps, initializeApp } from 'firebase-admin/app'
import { getFirestore } from 'firebase-admin/firestore'
import { fetchPortfolioQuotes } from './portfolio-prices.mjs'

const QUOTE_BATCH_SIZE = 50
const FRESH_QUOTE_MS = 15 * 60 * 1000
// Extended-hours snapshots only fire once every 30 minutes (see isHalfHourMark), so a quote
// has to survive six ticks of this five-minute cron rather than one -- give it more slack
// than the regular-hours check before calling the tape stale.
const EXTENDED_HOURS_FRESH_QUOTE_MS = 40 * 60 * 1000
const PORTFOLIO_COLLECTION = 'portfolios'

// Still every five minutes -- isHalfHourMark below is what actually limits extended-hours
// writes to :00/:30, so this cron doesn't need its own schedule for that cadence.
export const config = { schedule: '*/5 * * * *' }

function firebaseApp() {
  if (getApps().length) return getApps()[0]
  const raw = process.env.FIREBASE_SERVICE_ACCOUNT_JSON
  if (!raw) throw new Error('FIREBASE_SERVICE_ACCOUNT_JSON is not configured')
  return initializeApp({ credential: cert(JSON.parse(raw)) })
}

function easternParts(value) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(value)
  return Object.fromEntries(parts.map((part) => [part.type, part.value]))
}

export function marketDate(value = new Date()) {
  const parts = easternParts(value)
  return `${parts.year}-${parts.month}-${parts.day}`
}

export function isRegularMarketWindow(value = new Date()) {
  const parts = easternParts(value)
  if (parts.weekday === 'Sat' || parts.weekday === 'Sun') return false
  const minutes = Number(parts.hour) * 60 + Number(parts.minute)
  return minutes >= (9 * 60 + 30) && minutes < 16 * 60
}

// Yahoo's post-market session (the one `postMarketPrice`/`postMarketTime` are populated from,
// see portfolio-prices.mjs) runs 4:00pm-8:00pm ET.
export function isAfterHoursWindow(value = new Date()) {
  const parts = easternParts(value)
  if (parts.weekday === 'Sat' || parts.weekday === 'Sun') return false
  const minutes = Number(parts.hour) * 60 + Number(parts.minute)
  return minutes >= 16 * 60 && minutes < 20 * 60
}

// Yahoo's pre-market session (`preMarketPrice`/`preMarketTime`) runs 4:00am-9:30am ET, right
// up to where isRegularMarketWindow takes over.
export function isPreMarketWindow(value = new Date()) {
  const parts = easternParts(value)
  if (parts.weekday === 'Sat' || parts.weekday === 'Sun') return false
  const minutes = Number(parts.hour) * 60 + Number(parts.minute)
  return minutes >= 4 * 60 && minutes < (9 * 60 + 30)
}

export function isHalfHourMark(value = new Date()) {
  return Number(easternParts(value).minute) % 30 === 0
}

export function hasFreshMarketQuote(quotes, value = new Date()) {
  const now = value.getTime()
  return Object.values(quotes || {}).some((quote) => {
    const marketTime = new Date(quote?.marketTime || '').getTime()
    const age = now - marketTime
    return Number.isFinite(marketTime) && age >= -2 * 60 * 1000 && age <= FRESH_QUOTE_MS
  })
}

function hasFreshExtendedQuote(quotes, timeField, value) {
  const now = value.getTime()
  return Object.values(quotes || {}).some((quote) => {
    const quoteTime = new Date(quote?.[timeField] || '').getTime()
    const age = now - quoteTime
    return Number.isFinite(quoteTime) && age >= -2 * 60 * 1000 && age <= EXTENDED_HOURS_FRESH_QUOTE_MS
  })
}

export function hasFreshAfterHoursQuote(quotes, value = new Date()) {
  return hasFreshExtendedQuote(quotes, 'postMarketTime', value)
}

export function hasFreshPreMarketQuote(quotes, value = new Date()) {
  return hasFreshExtendedQuote(quotes, 'preMarketTime', value)
}

export function groupPortfolioPositions(rows = []) {
  const users = new Map()
  for (const row of rows) {
    const uid = String(row?.uid || '').trim()
    const ticker = String(row?.ticker || '').trim().toUpperCase()
    const shares = Number(row?.shares)
    if (!uid || !/^[A-Z][A-Z0-9.-]{0,9}$/.test(ticker) || !Number.isFinite(shares) || shares <= 0) continue
    if (!users.has(uid)) users.set(uid, new Map())
    const holdings = users.get(uid)
    holdings.set(ticker, (holdings.get(ticker) || 0) + shares)
  }
  return Object.fromEntries([...users].map(([uid, holdings]) => [
    uid,
    [...holdings].map(([ticker, shares]) => ({ ticker, shares })),
  ]))
}

const EXTENDED_SESSIONS = {
  after_hours: { priceField: 'postMarketPrice', timeField: 'postMarketTime', source: 'scheduled_portfolio_price_refresh_after_hours' },
  pre_market: { priceField: 'preMarketPrice', timeField: 'preMarketTime', source: 'scheduled_portfolio_price_refresh_pre_market' },
}

// One unpriceable position (a fund whose provider doesn't serve intraday quotes, a symbol
// mid-outage) used to blank the whole snapshot for that user every five minutes. Every other
// held position still has a real quote most cycles, so this prices what it can and records the
// gap instead of throwing away a coverage's worth of otherwise-good data.
export function buildPortfolioSnapshot(positions, quotes, recordedAt, { session = 'regular' } = {}) {
  if (!positions?.length) return null
  const extended = EXTENDED_SESSIONS[session] || null
  const priced = positions.map((position) => {
    const quote = quotes?.[position.ticker]
    // A quote missing an actual extended-session print (thin coverage, no activity) falls
    // back to the regular-session price rather than dropping the position.
    const price = extended ? (quote?.[extended.priceField] ?? quote?.price) : quote?.price
    if (!Number.isFinite(price)) return null
    const value = Number(position.shares) * price
    return {
      ticker: position.ticker,
      shares: Number(position.shares),
      price,
      value,
      marketTime: (extended ? (quote[extended.timeField] ?? quote.marketTime) : quote.marketTime) || null,
    }
  })
  const pricedPositions = priced.filter(Boolean)
  if (!pricedPositions.length) return null

  const investedValue = pricedPositions.reduce((sum, position) => sum + position.value, 0)
  const unpricedTickers = positions
    .filter((_, index) => priced[index] == null)
    .map((position) => position.ticker)
  return {
    value: investedValue,
    investedValue,
    coveragePct: Math.round((pricedPositions.length / positions.length) * 100),
    source: extended ? extended.source : 'scheduled_portfolio_price_refresh',
    samplingIntervalMinutes: extended ? 30 : 5,
    recordedAt: recordedAt.toISOString(),
    marketDate: marketDate(recordedAt),
    positionCount: pricedPositions.length,
    totalPositionCount: positions.length,
    prices: pricedPositions,
    ...(unpricedTickers.length ? { unpricedTickers } : {}),
  }
}

function snapshotId(value) {
  return value.toISOString().slice(0, 16).replace(/[:.]/g, '-')
}

async function fetchQuoteUniverse(symbols, quoteFetcher) {
  const batches = []
  for (let index = 0; index < symbols.length; index += QUOTE_BATCH_SIZE) {
    batches.push(symbols.slice(index, index + QUOTE_BATCH_SIZE))
  }
  const results = await Promise.all(batches.map((batch) => quoteFetcher(batch)))
  return {
    quotes: Object.assign({}, ...results.map((result) => result.quotes)),
    failed: results.flatMap((result) => result.failed || []),
  }
}

async function commitSnapshots(db, writes) {
  let committed = 0
  for (let index = 0; index < writes.length; index += 200) {
    const batch = db.batch()
    for (const write of writes.slice(index, index + 200)) {
      batch.set(write.snapshotRef, write.payload, { merge: true })
      batch.set(write.stateRef, {
        lastScheduledSnapshotAt: write.payload.recordedAt,
        lastScheduledSnapshotCoveragePct: write.payload.coveragePct,
      }, { merge: true })
    }
    await batch.commit()
    committed += Math.min(200, writes.length - index)
  }
  return committed
}

export async function collectScheduledPortfolioSnapshots({
  db,
  quoteFetcher = fetchPortfolioQuotes,
  now = new Date(),
} = {}) {
  const regular = isRegularMarketWindow(now)
  const afterHours = !regular && isAfterHoursWindow(now)
  const preMarket = !regular && !afterHours && isPreMarketWindow(now)
  if (!regular && !afterHours && !preMarket) return { status: 'outside_market_hours', recorded: 0 }
  if ((afterHours || preMarket) && !isHalfHourMark(now)) return { status: 'extended_hours_off_tick', recorded: 0 }
  const session = regular ? 'regular' : afterHours ? 'after_hours' : 'pre_market'

  const positionsSnapshot = await db.collectionGroup('positions').get()
  const rows = positionsSnapshot.docs.map((item) => {
    const userRef = item.ref.parent.parent
    if (userRef?.parent?.id !== PORTFOLIO_COLLECTION) return null
    return { uid: userRef.id, ...item.data() }
  }).filter(Boolean)
  const portfolios = groupPortfolioPositions(rows)
  const userIds = Object.keys(portfolios)
  const symbols = [...new Set(userIds.flatMap((uid) => portfolios[uid].map((position) => position.ticker)))]
  if (!symbols.length) return { status: 'no_positions', recorded: 0 }

  const { quotes, failed } = await fetchQuoteUniverse(symbols, quoteFetcher)
  const fresh = session === 'regular' ? hasFreshMarketQuote(quotes, now)
    : session === 'after_hours' ? hasFreshAfterHoursQuote(quotes, now)
    : hasFreshPreMarketQuote(quotes, now)
  if (!fresh) {
    return { status: 'market_tape_stale', recorded: 0, requested: symbols.length, failed }
  }

  const roots = Object.fromEntries(userIds.map((uid) => [uid, db.collection(PORTFOLIO_COLLECTION).doc(uid)]))
  const id = snapshotId(now)
  const writes = []
  const skipped = []

  for (const uid of userIds) {
    const payload = buildPortfolioSnapshot(portfolios[uid], quotes, now, { session })
    if (!payload) {
      skipped.push(uid)
      continue
    }
    writes.push({
      snapshotRef: roots[uid].collection('intradaySnapshots').doc(id),
      stateRef: roots[uid].collection('tracking').doc('state'),
      payload,
    })
  }

  const recorded = await commitSnapshots(db, writes)
  return {
    status: 'complete',
    recorded,
    skipped: skipped.length,
    requested: symbols.length,
    failed,
    recordedAt: now.toISOString(),
  }
}

export default async () => {
  const result = await collectScheduledPortfolioSnapshots({ db: getFirestore(firebaseApp()) })
  console.log('Scheduled portfolio price snapshot:', result)
  return new Response(JSON.stringify(result), {
    status: 200,
    headers: { 'content-type': 'application/json; charset=utf-8' },
  })
}
