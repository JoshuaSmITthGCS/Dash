// Turns "what the model would hold" into dollar trades against what the account actually
// holds. The model book is the backtest's own construction: the top `bookSize` published
// names, equal weight. Nothing here places an order; it is a worksheet.

import { modelRanks } from './modelAlignment.js'

export const REBALANCE_MODES = [
  { id: 'model_sleeve', label: 'Model sleeve only', blurb: 'Rebalance the capital already in model names; leave your own picks alone.' },
  { id: 'full_account', label: 'Whole account', blurb: 'Move the entire account onto the model book, selling everything else.' },
]

const finite = (value) => value != null && Number.isFinite(Number(value))
const upper = (value) => String(value || '').trim().toUpperCase()
const DAY_MS = 86400000
const SHORT_TERM_DAYS = 365

function holdingDays(purchaseDate, asOf) {
  const start = Date.parse(`${String(purchaseDate || '').slice(0, 10)}T00:00:00Z`)
  const end = Date.parse(`${asOf}T00:00:00Z`)
  return Number.isFinite(start) && Number.isFinite(end) ? Math.floor((end - start) / DAY_MS) : null
}

/** What selling `fraction` of a position would realize, and whether it is short-term. */
function taxOutcome(position, fraction, asOf) {
  const gain = finite(position.gain) ? Number(position.gain) * fraction : null
  const days = holdingDays(position.purchaseDate, asOf)
  const shortTerm = days != null && days < SHORT_TERM_DAYS
  let flag = null
  if (gain != null && gain > 0 && shortTerm) flag = 'short_term_gain'
  else if (gain != null && gain < 0) flag = 'realizes_loss'
  return { realizedGain: gain, holdingDays: days, shortTerm, flag }
}

/**
 * @param {object} options
 * @param {Array}  options.positions  enriched holdings (ticker, shares, currentValue, currentPrice, gain, purchaseDate)
 * @param {Array}  options.research   advisor.json research rows, in rank order
 * @param {string} options.mode       'model_sleeve' | 'full_account'
 * @param {number} options.bookSize   names in the model book (backtest default 20)
 * @param {number} options.costBps    one-way cost per trade, in basis points
 * @param {number} options.minTradeUsd trades smaller than this are left as drift
 * @param {string} options.asOf       YYYY-MM-DD for holding-period math
 */
export function suggestModelTrades({
  positions = [],
  research = [],
  mode = 'model_sleeve',
  bookSize = 20,
  costBps = 10,
  minTradeUsd = 5,
  asOf = new Date().toISOString().slice(0, 10),
} = {}) {
  const ranks = modelRanks(research)
  const book = research
    .filter((row) => row?.ticker && !row.is_etf && finite(row.price) && Number(row.price) > 0)
    .slice(0, bookSize)
    .map((row) => ({ ticker: upper(row.ticker), price: Number(row.price), rank: ranks.get(upper(row.ticker)), name: row.name || null }))
  if (!book.length) return { available: false, reason: 'The model has no priced names in this refresh.' }

  const held = new Map()
  positions.forEach((position) => {
    const ticker = upper(position.ticker)
    if (!ticker || !finite(position.shares) || !(Number(position.shares) > 0) || !finite(position.currentValue)) return
    // Several lots of one ticker collapse into one line: trades are per ticker.
    const prior = held.get(ticker)
    const lot = { ...position, ticker }
    held.set(ticker, prior ? {
      ...prior,
      shares: Number(prior.shares) + Number(lot.shares),
      currentValue: Number(prior.currentValue) + Number(lot.currentValue),
      gain: (Number(prior.gain) || 0) + (Number(lot.gain) || 0),
      // The newest lot decides short-term status: selling the whole line includes it.
      purchaseDate: String(lot.purchaseDate || '') > String(prior.purchaseDate || '') ? lot.purchaseDate : prior.purchaseDate,
    } : lot)
  })

  const inScope = [...held.values()].filter((position) => mode === 'full_account' || ranks.has(position.ticker))
  const capital = inScope.reduce((sum, position) => sum + Number(position.currentValue), 0)
  if (!(capital > 0)) {
    return {
      available: false,
      reason: mode === 'model_sleeve'
        ? 'None of your holdings are in the model’s ranked list, so there is no model sleeve to rebalance. Switch to Whole account to see a full move.'
        : 'No priced holdings to rebalance.',
    }
  }

  const target = capital / book.length
  const bookTickers = new Set(book.map((row) => row.ticker))
  const trades = []

  inScope.filter((position) => !bookTickers.has(position.ticker)).forEach((position) => {
    const amount = Number(position.currentValue)
    const rank = ranks.get(position.ticker) ?? null
    trades.push({
      ticker: position.ticker,
      action: 'SELL',
      amount,
      shares: Number(position.shares),
      currentValue: amount,
      targetValue: 0,
      rank,
      reason: rank ? `Ranked #${rank}, outside the ${book.length}-name book` : 'Not in the model’s ranked list',
      ...taxOutcome(position, 1, asOf),
    })
  })

  book.forEach((row) => {
    const position = held.get(row.ticker)
    const current = position ? Number(position.currentValue) : 0
    const delta = target - current
    if (Math.abs(delta) < minTradeUsd) return
    const price = position && finite(position.currentPrice) ? Number(position.currentPrice) : row.price
    if (delta > 0) {
      trades.push({
        ticker: row.ticker,
        action: position ? 'ADD' : 'BUY',
        amount: delta,
        shares: delta / price,
        currentValue: current,
        targetValue: target,
        rank: row.rank,
        reason: `Ranked #${row.rank}, ${position ? 'under' : 'not yet at'} its equal weight`,
        realizedGain: null,
        holdingDays: null,
        shortTerm: false,
        flag: null,
      })
    } else {
      const fraction = current > 0 ? -delta / current : 0
      trades.push({
        ticker: row.ticker,
        action: 'TRIM',
        amount: -delta,
        shares: Number(position.shares) * fraction,
        currentValue: current,
        targetValue: target,
        rank: row.rank,
        reason: `Ranked #${row.rank}, above its equal weight`,
        ...taxOutcome(position, fraction, asOf),
      })
    }
  })

  const order = { SELL: 0, TRIM: 1, ADD: 2, BUY: 3 }
  trades.sort((a, b) => order[a.action] - order[b.action] || b.amount - a.amount)
  const sold = trades.filter((trade) => trade.action === 'SELL' || trade.action === 'TRIM')
  const bought = trades.filter((trade) => trade.action === 'ADD' || trade.action === 'BUY')
  const sum = (rows, key) => rows.reduce((total, row) => total + (finite(row[key]) ? Number(row[key]) : 0), 0)
  const traded = sum(trades, 'amount')
  const shortTermGains = sum(sold.filter((trade) => trade.flag === 'short_term_gain'), 'realizedGain')

  return {
    available: true,
    mode,
    bookSize: book.length,
    capital,
    targetPerName: target,
    costBps,
    minTradeUsd,
    trades,
    totals: {
      sells: sum(sold, 'amount'),
      buys: sum(bought, 'amount'),
      turnoverPct: traded / 2 / capital * 100,
      estimatedCost: traded * costBps / 10000,
      shortTermGains,
      realizedLosses: sum(sold.filter((trade) => trade.flag === 'realizes_loss'), 'realizedGain'),
      shortTermCount: sold.filter((trade) => trade.flag === 'short_term_gain').length,
    },
    methodology: `Target is the model’s top ${book.length} published names at equal weight (the backtest’s own `
      + `construction), sized to ${mode === 'full_account' ? 'the whole account' : 'the capital already in model names'}. `
      + `Cost uses the backtest’s flat ${costBps} bps one way. Trades under $${minTradeUsd} are left as drift. `
      + 'Short-term means held under a year from the newest lot’s purchase date; gains are estimates from '
      + 'your recorded cost basis, not tax advice.',
  }
}
