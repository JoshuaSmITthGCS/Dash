import { cert, getApps, initializeApp } from 'firebase-admin/app'
import { getFirestore } from 'firebase-admin/firestore'
import { fetchPortfolioQuotes } from './portfolio-prices.mjs'

const QUOTE_BATCH_SIZE = 50
const FRESH_QUOTE_MS = 15 * 60 * 1000
const PORTFOLIO_COLLECTION = 'portfolios'

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

export function hasFreshMarketQuote(quotes, value = new Date()) {
  const now = value.getTime()
  return Object.values(quotes || {}).some((quote) => {
    const marketTime = new Date(quote?.marketTime || '').getTime()
    const age = now - marketTime
    return Number.isFinite(marketTime) && age >= -2 * 60 * 1000 && age <= FRESH_QUOTE_MS
  })
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

export function buildPortfolioSnapshot(positions, quotes, cashBalance, recordedAt) {
  if (!positions?.length) return null
  const priced = positions.map((position) => {
    const quote = quotes?.[position.ticker]
    if (!Number.isFinite(quote?.price)) return null
    const value = Number(position.shares) * quote.price
    return {
      ticker: position.ticker,
      shares: Number(position.shares),
      price: quote.price,
      value,
      marketTime: quote.marketTime || null,
    }
  })
  if (priced.some((position) => position == null)) return null

  const investedValue = priced.reduce((sum, position) => sum + position.value, 0)
  const cashValue = Number.isFinite(Number(cashBalance)) ? Number(cashBalance) : 0
  return {
    value: investedValue + cashValue,
    investedValue,
    cashValue,
    coveragePct: 100,
    source: 'scheduled_portfolio_price_refresh',
    samplingIntervalMinutes: 5,
    recordedAt: recordedAt.toISOString(),
    marketDate: marketDate(recordedAt),
    positionCount: priced.length,
    prices: priced,
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
  if (!isRegularMarketWindow(now)) return { status: 'outside_market_hours', recorded: 0 }

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
  if (!hasFreshMarketQuote(quotes, now)) {
    return { status: 'market_tape_stale', recorded: 0, requested: symbols.length, failed }
  }

  const roots = Object.fromEntries(userIds.map((uid) => [uid, db.collection(PORTFOLIO_COLLECTION).doc(uid)]))
  const stateRefs = userIds.map((uid) => roots[uid].collection('tracking').doc('state'))
  const stateDocuments = await db.getAll(...stateRefs)
  const cashByUser = Object.fromEntries(stateDocuments.map((item, index) => [
    userIds[index],
    item.exists && item.data()?.cashTrackingEnabled ? Number(item.data()?.cashBalance || 0) : 0,
  ]))
  const id = snapshotId(now)
  const writes = []
  const skipped = []

  for (const uid of userIds) {
    const payload = buildPortfolioSnapshot(portfolios[uid], quotes, cashByUser[uid], now)
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
