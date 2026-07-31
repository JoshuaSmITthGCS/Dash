import { useEffect } from 'react'
import { useAuth } from './FirebaseAuthContext'
import { db } from './firebase'
import { logSignal, createEntrySignal, createExitSignal } from './backtestEngine'
import { getRecommendation } from './recommendation'

const SNAPSHOT_KEY = 'valuesignal.signalSnapshot'
const ATTRACTIVE_STANCES = new Set(['ATTRACTIVE', 'PROMISING'])

function readSnapshot() {
  try { return JSON.parse(localStorage.getItem(SNAPSHOT_KEY)) || null }
  catch { return null }
}

function writeSnapshot(generatedAt, stocks) {
  const snapshot = {
    generatedAt,
    stocks: stocks.map((stock, index) => ({
      ticker: stock.ticker,
      rank: index + 1,
      stance: stock.stance,
      action: getRecommendation(stock)?.action,
    })),
  }
  try { localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(snapshot)) } catch { /* storage unavailable */ }
}

/**
 * Signal Tracking Hook
 *
 * Diffs each newly published refresh against the last refresh this browser saw
 * (tracked in localStorage, so it survives reloads without needing a server round trip)
 * and logs entry/exit signals to Firestore so /backtest has something real to replay:
 * - Entry: stock enters the top 20 OR its stance becomes ATTRACTIVE/PROMISING
 * - Exit: stock drops out of the top 20 OR its guidance action becomes SELL
 *
 * Stance values from the pipeline are uppercase ("ATTRACTIVE"/"PROMISING"/"MIXED"/"CAUTION"),
 * and SELL/TRIM/WATCH/HOLD live on the guidance action (getRecommendation), not on stance —
 * they are two different fields.
 *
 * Call once per page with the full ranked research array and the payload's generated_at.
 */
export function useSignalTracking(currentStocks, generatedAt) {
  const { currentUser } = useAuth()

  useEffect(() => {
    if (!currentUser || !db || !generatedAt || !currentStocks?.length) return

    const snapshot = readSnapshot()
    if (snapshot?.generatedAt === generatedAt) return // already processed this refresh

    const previousStocks = snapshot?.stocks || []
    const previousMap = new Map(previousStocks.map((stock) => [stock.ticker, stock]))
    const currentMap = new Map(currentStocks.map((stock) => [stock.ticker, stock]))
    const currentTop20 = new Set(currentStocks.slice(0, 20).map((stock) => stock.ticker))
    const previousTop20 = new Set(previousStocks.slice(0, 20).map((stock) => stock.ticker))
    const isFirstSnapshot = previousStocks.length === 0

    const signals = []

    currentStocks.forEach((stock, index) => {
      const rank = index + 1
      const previous = previousMap.get(stock.ticker)
      const wasInTop20 = previousTop20.has(stock.ticker)
      const isNowInTop20 = currentTop20.has(stock.ticker)
      const wasAttractive = ATTRACTIVE_STANCES.has(previous?.stance)
      const isAttractive = ATTRACTIVE_STANCES.has(stock.stance)

      const enteredTop20 = !wasInTop20 && isNowInTop20
      const upgraded = !wasAttractive && isAttractive
      if (isFirstSnapshot ? isNowInTop20 : (enteredTop20 || upgraded)) {
        signals.push({
          signal: createEntrySignal(stock, rank),
          reason: isFirstSnapshot ? 'initial_snapshot' : enteredTop20 ? 'entered_top_20' : 'stance_upgrade',
        })
      }
    })

    if (!isFirstSnapshot) {
      previousStocks.forEach((previous) => {
        const current = currentMap.get(previous.ticker)
        const wasInTop20 = previousTop20.has(previous.ticker)
        const isStillInTop20 = currentTop20.has(previous.ticker)
        const isSellNow = current ? getRecommendation(current)?.action === 'SELL' : false

        const droppedOut = wasInTop20 && !isStillInTop20
        const newSell = previous.action !== 'SELL' && isSellNow
        if (droppedOut || newSell) {
          signals.push({
            signal: createExitSignal(current || previous, droppedOut ? 'dropped_out' : 'sell_signal'),
            reason: droppedOut ? 'dropped_out_top_20' : 'sell_signal',
          })
        }
      })
    }

    signals.forEach(async ({ signal, reason }) => {
      const result = await logSignal(signal, db, currentUser)
      if (!result.success) console.error(`Failed to log ${signal.type} signal for ${signal.ticker} (${reason}):`, result.error)
    })

    writeSnapshot(generatedAt, currentStocks)
  }, [currentStocks, generatedAt, currentUser])
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
