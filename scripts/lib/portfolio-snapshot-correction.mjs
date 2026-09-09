// Corrects a recorded daily account-value snapshot (Firestore `intradaySnapshots`) whose total
// was computed from the wrong set of holdings -- the exact damage the LULU resurrection and
// the never-recorded TSM buy did to every snapshot taken while the account was wrong.
//
// The guiding rule: correct only the specific, known error, using the most precise price data
// available for it, and never destroy the original recorded value.
//
//   - A ticker that was wrongly INCLUDED (held at record time by mistake, correctly not held)
//     is removed using the price the app itself recorded for it that day (snapshot.prices),
//     since that is the exact number the wrong total was built from -- no approximation needed.
//   - A ticker that was wrongly EXCLUDED (should have been held, is absent from the snapshot
//     entirely -- this is what happened to TSM, which was never entered into the app at all)
//     is added using the closest available historical closing price, since the app never
//     captured a live price for it that day. This is the one place an approximation is
//     unavoidable, and it is always labelled as one.
//   - A ticker present in both but at the wrong share count (a sale recorded a few hours after
//     that day's snapshot, say) is adjusted by the share difference at the app's own recorded
//     price for it.
//
// A snapshot recorded before per-ticker prices existed at all (no `prices` array) cannot be
// corrected this way -- there is nothing to distinguish "wrongly included" from "correctly
// included, just never itemized." Those get a full reconstruction from historical closes
// alone, clearly marked as a lower-precision estimate, or are left alone if the caller asks
// only for surgical corrections.

const normalizeTicker = (ticker) => String(ticker || '').trim().toUpperCase()
const finite = (value) => value !== null && value !== '' && Number.isFinite(Number(value))

/** The historical closing price for `ticker` on, or nearest before, `date`. Null if unknown. */
export function historicalCloseOn(priceHistoryByTicker, ticker, date) {
  const history = priceHistoryByTicker.get(normalizeTicker(ticker))
  if (!history?.dates?.length) return null
  let match = null
  for (let index = 0; index < history.dates.length; index += 1) {
    if (history.dates[index] > date) break
    if (finite(history.closes[index])) match = Number(history.closes[index])
  }
  return match
}

/**
 * Plans the correction for one snapshot. Returns `null` if the snapshot already matches the
 * correct holdings (nothing to do). Returns `{ blocked: true, blockers }` if a correction is
 * needed but the price data to make it precisely isn't available -- this is reported, never
 * guessed past. Otherwise returns the full correction: what changed per ticker, the corrected
 * total and unrealized gain, and the original values preserved alongside them.
 */
export function planSnapshotCorrection(snapshot, correctHoldings, priceHistoryByTicker) {
  if (!Array.isArray(snapshot.prices) || !snapshot.prices.length) {
    return { blocked: true, blockers: [`${snapshot.id || snapshot.marketDate}: no per-ticker prices recorded; needs full reconstruction, not a surgical correction`], mode: 'no_prices' }
  }

  const recordedByTicker = new Map(snapshot.prices.map((row) => [normalizeTicker(row.ticker), row]))
  const allTickers = new Set([...recordedByTicker.keys(), ...correctHoldings.keys()])
  const changes = []
  const blockers = []
  let delta = 0

  for (const ticker of allTickers) {
    const recorded = recordedByTicker.get(ticker)
    const correct = correctHoldings.get(ticker)
    const recordedShares = recorded ? Number(recorded.shares) || 0 : 0
    const correctShares = correct ? correct.shares : 0
    if (Math.abs(recordedShares - correctShares) < 1e-9) continue

    if (correctShares <= 1e-9) {
      if (!recorded || !finite(recorded.price)) { blockers.push(`${ticker}: recorded with no price, cannot remove it precisely`); continue }
      delta -= recordedShares * Number(recorded.price)
      changes.push({ ticker, action: 'remove', shares: recordedShares, price: Number(recorded.price) })
    } else if (recordedShares <= 1e-9) {
      const price = historicalCloseOn(priceHistoryByTicker, ticker, snapshot.marketDate || snapshot.recordedAt?.slice(0, 10))
      if (!finite(price)) { blockers.push(`${ticker}: missing from the snapshot entirely and no historical close is available to add it back`); continue }
      delta += correctShares * price
      changes.push({ ticker, action: 'add', shares: correctShares, price, estimated: true })
    } else {
      const price = finite(recorded.price) ? Number(recorded.price) : historicalCloseOn(priceHistoryByTicker, ticker, snapshot.marketDate)
      if (!finite(price)) { blockers.push(`${ticker}: share-count mismatch but no price available to value the difference`); continue }
      delta += (correctShares - recordedShares) * price
      changes.push({ ticker, action: 'adjust', from: recordedShares, to: correctShares, price })
    }
  }

  if (!changes.length && !blockers.length) return null
  if (blockers.length) return { blocked: true, blockers, changes, mode: 'surgical' }

  const correctedValue = Number(snapshot.value) + delta
  const correctCostBasisTotal = [...correctHoldings.values()].reduce((sum, holding) => sum + holding.costBasisTotal, 0)
  const correctedUnrealizedGain = correctedValue - correctCostBasisTotal

  return {
    blocked: false,
    mode: 'surgical',
    changes,
    delta,
    correctedValue,
    correctedUnrealizedGain,
    originalValue: Number(snapshot.value),
    originalUnrealizedGain: snapshot.unrealizedGain ?? null,
  }
}

/**
 * The lower-precision fallback for a snapshot with no `prices` array: values every correctly-
 * held ticker at its historical close and ignores the old recorded total entirely, since there
 * is no way to tell what it did or didn't include. Always labelled `estimated: true` in the
 * result; the caller decides whether to apply an estimate this coarse.
 */
export function planFullReconstruction(snapshot, correctHoldings, priceHistoryByTicker) {
  const date = snapshot.marketDate || String(snapshot.recordedAt || '').slice(0, 10)
  let total = 0
  const missing = []
  const priced = []
  for (const [ticker, holding] of correctHoldings) {
    if (holding.shares <= 1e-9) continue
    const price = historicalCloseOn(priceHistoryByTicker, ticker, date)
    if (!finite(price)) { missing.push(ticker); continue }
    total += holding.shares * price
    priced.push({ ticker, shares: holding.shares, price })
  }
  if (missing.length) {
    return { blocked: true, blockers: missing.map((ticker) => `${ticker}: no historical close available on or before ${date}`), mode: 'no_prices' }
  }
  const correctCostBasisTotal = [...correctHoldings.values()].reduce((sum, holding) => sum + holding.costBasisTotal, 0)
  return {
    blocked: false,
    mode: 'no_prices',
    estimated: true,
    changes: priced.map((row) => ({ ticker: row.ticker, action: 'reconstructed', shares: row.shares, price: row.price })),
    correctedValue: total,
    correctedUnrealizedGain: total - correctCostBasisTotal,
    originalValue: Number(snapshot.value),
    originalUnrealizedGain: snapshot.unrealizedGain ?? null,
  }
}
