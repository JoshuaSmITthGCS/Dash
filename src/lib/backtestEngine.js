/**
 * Backtest Engine
 *
 * Simulates three portfolio strategies over time:
 * 1. Equal-weight: Fixed $500 into each stock on entry signal
 * 2. Rank-weighted: Scaled by rank (rank 1 = $1000, rank 20 = $100)
 * 3. SPY Benchmark: Same dollars, same dates, but buy SPY instead
 *
 * Entry signal: Stock enters top 20 or becomes "Attractive"/"Promising"
 * Exit signal: Stock exits top 20 or gets "SELL" recommendation
 */

/**
 * Signal types stored in Firestore
 */
export const SIGNAL_TYPES = {
  ENTRY: 'entry',
  EXIT: 'exit'
}

/**
 * Log entry/exit signal to Firestore
 *
 * @param {Object} signal - Signal data
 * @returns {Promise<Object>} Result with signal ID
 */
export async function logSignal(signal, db, currentUser) {
  if (!db || !currentUser) {
    console.error('Database or user not available')
    return { success: false, error: 'Not authenticated' }
  }

  try {
    const { collection, addDoc, serverTimestamp } = await import('firebase/firestore')

    const signalData = {
      ...signal,
      userId: currentUser.uid,
      timestamp: serverTimestamp(),
      createdAt: new Date().toISOString()
    }

    const docRef = await addDoc(collection(db, 'backtestSignals'), signalData)

    return { success: true, signalId: docRef.id }
  } catch (error) {
    console.error('Failed to log signal:', error)
    return { success: false, error: error.message }
  }
}

/**
 * Create entry signal object
 */
export function createEntrySignal(stock, rank) {
  return {
    type: SIGNAL_TYPES.ENTRY,
    ticker: stock.ticker,
    rank: rank,
    score: stock.score,
    stance: stock.stance,
    price: stock.price,
    marketCap: stock.market_cap,
    components: {
      fundamentals: stock.components?.fundamentals,
      technicals: stock.components?.market_behavior,
      sentiment: stock.components?.news_sentiment
    }
  }
}

/**
 * Create exit signal object
 */
export function createExitSignal(stock, reason) {
  return {
    type: SIGNAL_TYPES.EXIT,
    ticker: stock.ticker,
    price: stock.price,
    exitReason: reason, // 'dropped_out' or 'sell_signal'
    finalScore: stock.score,
    finalStance: stock.stance
  }
}

/**
 * Calculate position size for rank-weighted strategy
 * Rank 1 = $1000, sliding down to Rank 20 = $100
 */
export function calculateRankWeightedSize(rank) {
  if (rank < 1 || rank > 20) return 0

  // Linear interpolation: $1000 at rank 1, $100 at rank 20
  const maxSize = 1000
  const minSize = 100
  const step = (maxSize - minSize) / 19

  return maxSize - ((rank - 1) * step)
}

/**
 * Simulate equal-weight strategy
 *
 * @param {Array} signals - All entry/exit signals
 * @param {Object} priceData - Historical price data by ticker and date
 * @returns {Object} Strategy results
 */
export function simulateEqualWeight(signals, priceData) {
  const POSITION_SIZE = 500 // Fixed $500 per entry

  let cash = 0
  let positions = {} // ticker -> { shares, entryPrice, entryDate }
  const trades = []
  const portfolioValue = [] // { date, value }

  // Sort signals by timestamp
  const sortedSignals = [...signals].sort((a, b) =>
    new Date(a.timestamp || a.createdAt) - new Date(b.timestamp || b.createdAt)
  )

  for (const signal of sortedSignals) {
    const date = signal.timestamp || signal.createdAt

    if (signal.type === SIGNAL_TYPES.ENTRY) {
      // Buy signal
      if (!positions[signal.ticker]) {
        const shares = POSITION_SIZE / signal.price
        positions[signal.ticker] = {
          shares,
          entryPrice: signal.price,
          entryDate: date,
          rank: signal.rank
        }

        trades.push({
          ticker: signal.ticker,
          type: 'BUY',
          date,
          price: signal.price,
          shares,
          value: POSITION_SIZE,
          rank: signal.rank
        })
      }
    } else if (signal.type === SIGNAL_TYPES.EXIT) {
      // Sell signal
      if (positions[signal.ticker]) {
        const position = positions[signal.ticker]
        const saleValue = position.shares * signal.price
        const gain = saleValue - (position.shares * position.entryPrice)
        const gainPct = (gain / (position.shares * position.entryPrice)) * 100

        cash += saleValue

        trades.push({
          ticker: signal.ticker,
          type: 'SELL',
          date,
          price: signal.price,
          shares: position.shares,
          value: saleValue,
          gain,
          gainPct,
          exitReason: signal.exitReason,
          holdingPeriod: calculateHoldingPeriod(position.entryDate, date)
        })

        delete positions[signal.ticker]
      }
    }

    // Calculate portfolio value at this point
    const positionsValue = Object.keys(positions).reduce((sum, ticker) => {
      const currentPrice = signal.ticker === ticker ? signal.price :
        (priceData[ticker]?.[date] || positions[ticker].entryPrice)
      return sum + (positions[ticker].shares * currentPrice)
    }, 0)

    portfolioValue.push({
      date,
      value: cash + positionsValue,
      cash,
      positionsValue
    })
  }

  // Calculate final metrics
  const totalDeployed = trades.filter(t => t.type === 'BUY').reduce((sum, t) => sum + t.value, 0)
  const totalReturned = cash
  const totalReturn = totalReturned - totalDeployed
  const totalReturnPct = totalDeployed > 0 ? (totalReturn / totalDeployed) * 100 : 0

  const currentPositionsValue = Object.keys(positions).reduce((sum, ticker) => {
    const latestPrice = priceData[ticker]?.latest || positions[ticker].entryPrice
    return sum + (positions[ticker].shares * latestPrice)
  }, 0)

  const finalValue = cash + currentPositionsValue

  return {
    strategy: 'Equal-Weight',
    trades,
    portfolioValue,
    positions,
    metrics: {
      totalDeployed,
      totalReturned,
      totalReturn,
      totalReturnPct,
      currentPositionsValue,
      cash,
      finalValue,
      numTrades: trades.length,
      numWins: trades.filter(t => t.type === 'SELL' && t.gain > 0).length,
      numLosses: trades.filter(t => t.type === 'SELL' && t.gain < 0).length,
      avgGain: calculateAvgGain(trades),
      maxDrawdown: calculateMaxDrawdown(portfolioValue),
      sharpeRatio: calculateSharpeRatio(portfolioValue),
      turnover: calculateTurnover(trades, totalDeployed)
    }
  }
}

/**
 * Simulate rank-weighted strategy
 */
export function simulateRankWeighted(signals, priceData) {
  let cash = 0
  let positions = {}
  const trades = []
  const portfolioValue = []

  const sortedSignals = [...signals].sort((a, b) =>
    new Date(a.timestamp || a.createdAt) - new Date(b.timestamp || b.createdAt)
  )

  for (const signal of sortedSignals) {
    const date = signal.timestamp || signal.createdAt

    if (signal.type === SIGNAL_TYPES.ENTRY) {
      if (!positions[signal.ticker]) {
        const positionSize = calculateRankWeightedSize(signal.rank)
        const shares = positionSize / signal.price

        positions[signal.ticker] = {
          shares,
          entryPrice: signal.price,
          entryDate: date,
          rank: signal.rank,
          positionSize
        }

        trades.push({
          ticker: signal.ticker,
          type: 'BUY',
          date,
          price: signal.price,
          shares,
          value: positionSize,
          rank: signal.rank
        })
      }
    } else if (signal.type === SIGNAL_TYPES.EXIT) {
      if (positions[signal.ticker]) {
        const position = positions[signal.ticker]
        const saleValue = position.shares * signal.price
        const gain = saleValue - (position.shares * position.entryPrice)
        const gainPct = (gain / (position.shares * position.entryPrice)) * 100

        cash += saleValue

        trades.push({
          ticker: signal.ticker,
          type: 'SELL',
          date,
          price: signal.price,
          shares: position.shares,
          value: saleValue,
          gain,
          gainPct,
          exitReason: signal.exitReason,
          holdingPeriod: calculateHoldingPeriod(position.entryDate, date)
        })

        delete positions[signal.ticker]
      }
    }

    const positionsValue = Object.keys(positions).reduce((sum, ticker) => {
      const currentPrice = signal.ticker === ticker ? signal.price :
        (priceData[ticker]?.[date] || positions[ticker].entryPrice)
      return sum + (positions[ticker].shares * currentPrice)
    }, 0)

    portfolioValue.push({
      date,
      value: cash + positionsValue,
      cash,
      positionsValue
    })
  }

  const totalDeployed = trades.filter(t => t.type === 'BUY').reduce((sum, t) => sum + t.value, 0)
  const totalReturned = cash
  const totalReturn = totalReturned - totalDeployed
  const totalReturnPct = totalDeployed > 0 ? (totalReturn / totalDeployed) * 100 : 0

  const currentPositionsValue = Object.keys(positions).reduce((sum, ticker) => {
    const latestPrice = priceData[ticker]?.latest || positions[ticker].entryPrice
    return sum + (positions[ticker].shares * latestPrice)
  }, 0)

  const finalValue = cash + currentPositionsValue

  return {
    strategy: 'Rank-Weighted',
    trades,
    portfolioValue,
    positions,
    metrics: {
      totalDeployed,
      totalReturned,
      totalReturn,
      totalReturnPct,
      currentPositionsValue,
      cash,
      finalValue,
      numTrades: trades.length,
      numWins: trades.filter(t => t.type === 'SELL' && t.gain > 0).length,
      numLosses: trades.filter(t => t.type === 'SELL' && t.gain < 0).length,
      avgGain: calculateAvgGain(trades),
      maxDrawdown: calculateMaxDrawdown(portfolioValue),
      sharpeRatio: calculateSharpeRatio(portfolioValue),
      turnover: calculateTurnover(trades, totalDeployed)
    }
  }
}

/**
 * Simulate SPY benchmark
 */
export function simulateSPYBenchmark(signals, spyPriceData) {
  let shares = 0
  let totalInvested = 0
  const trades = []
  const portfolioValue = []

  // For each entry signal in the stock strategy, buy SPY instead
  const entrySignals = signals.filter(s => s.type === SIGNAL_TYPES.ENTRY)
    .sort((a, b) => new Date(a.timestamp || a.createdAt) - new Date(b.timestamp || b.createdAt))

  for (const signal of entrySignals) {
    const date = signal.timestamp || signal.createdAt
    const spyPrice = spyPriceData[date]

    if (spyPrice) {
      // Use same dollar amount that would have been invested in stock
      const investAmount = 500 // Equal to equal-weight strategy
      const sharesToBuy = investAmount / spyPrice

      shares += sharesToBuy
      totalInvested += investAmount

      trades.push({
        ticker: 'SPY',
        type: 'BUY',
        date,
        price: spyPrice,
        shares: sharesToBuy,
        value: investAmount
      })

      const currentValue = shares * spyPrice
      portfolioValue.push({
        date,
        value: currentValue
      })
    }
  }

  // Final value using latest SPY price
  const latestSPYPrice = spyPriceData.latest
  const finalValue = shares * latestSPYPrice
  const totalReturn = finalValue - totalInvested
  const totalReturnPct = totalInvested > 0 ? (totalReturn / totalInvested) * 100 : 0

  return {
    strategy: 'SPY Benchmark',
    trades,
    portfolioValue,
    shares,
    metrics: {
      totalDeployed: totalInvested,
      finalValue,
      totalReturn,
      totalReturnPct,
      numTrades: trades.length,
      avgSPYPrice: totalInvested / shares,
      latestSPYPrice,
      maxDrawdown: calculateMaxDrawdown(portfolioValue),
      sharpeRatio: calculateSharpeRatio(portfolioValue)
    }
  }
}

/**
 * Helper: Calculate holding period in days
 */
function calculateHoldingPeriod(entryDate, exitDate) {
  const entry = new Date(entryDate)
  const exit = new Date(exitDate)
  return Math.floor((exit - entry) / (1000 * 60 * 60 * 24))
}

/**
 * Helper: Calculate average gain from closed trades
 */
function calculateAvgGain(trades) {
  const closedTrades = trades.filter(t => t.type === 'SELL')
  if (closedTrades.length === 0) return 0

  const totalGain = closedTrades.reduce((sum, t) => sum + (t.gainPct || 0), 0)
  return totalGain / closedTrades.length
}

/**
 * Helper: Calculate maximum drawdown
 */
function calculateMaxDrawdown(portfolioValue) {
  if (portfolioValue.length < 2) return 0

  let maxDrawdown = 0
  let peak = portfolioValue[0].value

  for (const point of portfolioValue) {
    if (point.value > peak) {
      peak = point.value
    }

    const drawdown = ((peak - point.value) / peak) * 100
    if (drawdown > maxDrawdown) {
      maxDrawdown = drawdown
    }
  }

  return maxDrawdown
}

/**
 * Helper: Calculate Sharpe ratio (simplified)
 */
function calculateSharpeRatio(portfolioValue) {
  if (portfolioValue.length < 2) return 0

  // Calculate returns between points
  const returns = []
  for (let i = 1; i < portfolioValue.length; i++) {
    const ret = (portfolioValue[i].value - portfolioValue[i-1].value) / portfolioValue[i-1].value
    returns.push(ret)
  }

  if (returns.length === 0) return 0

  // Mean return
  const meanReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length

  // Standard deviation
  const variance = returns.reduce((sum, r) => sum + Math.pow(r - meanReturn, 2), 0) / returns.length
  const stdDev = Math.sqrt(variance)

  if (stdDev === 0) return 0

  // Sharpe = (mean return - risk-free rate) / std dev
  // Assuming risk-free rate = 0 for simplicity
  return meanReturn / stdDev
}

/**
 * Helper: Calculate turnover (trades / total deployed)
 */
function calculateTurnover(trades, totalDeployed) {
  if (totalDeployed === 0) return 0

  const totalTraded = trades.reduce((sum, t) => sum + t.value, 0)
  return totalTraded / totalDeployed
}

/**
 * Calculate CAGR (Compound Annual Growth Rate)
 */
export function calculateCAGR(startValue, endValue, years) {
  if (startValue === 0 || years === 0) return 0
  return (Math.pow(endValue / startValue, 1 / years) - 1) * 100
}

/**
 * Format metric for display
 */
export function formatMetric(value, type = 'number') {
  if (value == null || isNaN(value)) return '—'

  switch (type) {
    case 'percent':
      return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
    case 'currency':
      return `$${value.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
    case 'number':
      return value.toFixed(2)
    default:
      return value.toString()
  }
}
