import { useEffect, useRef } from 'react'
import { useAuth } from './FirebaseAuthContext'
import { db } from './firebase'
import { logSignal, createEntrySignal, createExitSignal } from './backtestEngine'

/**
 * Signal Tracking Hook
 *
 * Automatically logs entry/exit signals when:
 * - Entry: Stock enters top 20 OR becomes "Attractive"/"Promising"
 * - Exit: Stock exits top 20 OR gets "SELL" recommendation
 *
 * Usage: Add to Dashboard.jsx or Picks.jsx to track signals in real-time
 */
export function useSignalTracking(currentStocks, previousStocks) {
  const { currentUser } = useAuth()
  const previousStocksRef = useRef(previousStocks)

  useEffect(() => {
    if (!currentUser || !db || !currentStocks || !previousStocks) return

    // Track stocks that have changed
    const previousMap = new Map(previousStocks.map(s => [s.ticker, s]))
    const currentMap = new Map(currentStocks.map(s => [s.ticker, s]))

    // Get current top 20 by rank
    const currentTop20 = currentStocks.slice(0, 20).map(s => s.ticker)
    const previousTop20 = previousStocks.slice(0, 20).map(s => s.ticker)

    const signals = []

    // Check each stock in current universe
    currentStocks.forEach((currentStock, index) => {
      const previousStock = previousMap.get(currentStock.ticker)
      const rank = index + 1

      // Entry Signal Conditions:
      // 1. Stock enters top 20 (wasn't in previous top 20)
      // 2. Stock becomes "Attractive" or "Promising" (stance change)
      const wasInTop20 = previousTop20.includes(currentStock.ticker)
      const isNowInTop20 = currentTop20.includes(currentStock.ticker)

      const wasAttractivePreviously = previousStock?.stance === 'Attractive' || previousStock?.stance === 'Promising'
      const isAttractiveNow = currentStock.stance === 'Attractive' || currentStock.stance === 'Promising'

      // Entry signal: enters top 20 OR becomes attractive
      if ((!wasInTop20 && isNowInTop20) || (!wasAttractivePreviously && isAttractiveNow)) {
        signals.push({
          type: 'entry',
          signal: createEntrySignal(currentStock, rank),
          reason: !wasInTop20 && isNowInTop20 ? 'entered_top_20' : 'stance_upgrade'
        })
      }
    })

    // Check for exit signals
    previousStocks.forEach(previousStock => {
      const currentStock = currentMap.get(previousStock.ticker)

      const wasInTop20 = previousTop20.includes(previousStock.ticker)
      const isStillInTop20 = currentTop20.includes(previousStock.ticker)

      const wasSellPreviously = previousStock.stance === 'SELL'
      const isSellNow = currentStock?.stance === 'SELL'

      // Exit signal: drops out of top 20 OR becomes SELL
      if ((wasInTop20 && !isStillInTop20) || (!wasSellPreviously && isSellNow)) {
        const exitStock = currentStock || previousStock
        signals.push({
          type: 'exit',
          signal: createExitSignal(exitStock, wasInTop20 && !isStillInTop20 ? 'dropped_out' : 'sell_signal'),
          reason: wasInTop20 && !isStillInTop20 ? 'dropped_out_top_20' : 'sell_signal'
        })
      }
    })

    // Log all signals to Firestore
    signals.forEach(async ({ signal, reason }) => {
      const result = await logSignal(signal, db, currentUser)
      if (result.success) {
        console.log(`✓ Logged ${signal.type} signal for ${signal.ticker}:`, reason)
      } else {
        console.error(`✗ Failed to log signal for ${signal.ticker}:`, result.error)
      }
    })

    // Update ref for next comparison
    previousStocksRef.current = currentStocks

  }, [currentStocks, previousStocks, currentUser])
}

/**
 * Manual signal logging function
 * Use this to manually log a signal (e.g., from a button click)
 */
export async function manualLogSignal(stock, type, rank, db, currentUser) {
  if (!db || !currentUser) {
    console.error('Database or user not available')
    return { success: false, error: 'Not authenticated' }
  }

  const signal = type === 'entry'
    ? createEntrySignal(stock, rank)
    : createExitSignal(stock, 'manual')

  return await logSignal(signal, db, currentUser)
}
