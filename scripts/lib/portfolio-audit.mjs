// Pure audit checks over a portfolio's Firestore collections (positions, closedPositions,
// activity, intradaySnapshots, tracking/state). Every function here takes plain arrays/objects
// and returns a plain finding list -- no Firestore, no network -- so the whole audit is
// testable against fixtures and the CLI (audit-portfolio-ledger.mjs) is a thin read-and-print
// wrapper around it.
//
// This module exists because the LULU resurrection (2026-09) was found by the user, not the
// system: nothing checked that a closed position stayed closed, or that a sale's NAV step
// actually reconciled. Every check below answers one version of "did the ledger actually do
// what it claims to have done" -- run this before trusting a number on screen, and after any
// script here writes to Firestore.

import { portfolioReconciliationBridge, BASKET_FLOW_TYPES } from '../../src/lib/portfolioAnalytics.js'
import { planReferencePortfolioSync, seededTickersFromTrackingState } from '../../src/lib/referencePortfolio.js'

const normalizeTicker = (ticker) => String(ticker || '').trim().toUpperCase()
const finite = (value) => value !== null && value !== '' && Number.isFinite(Number(value))

/**
 * Check 1: a stored position whose ticker was closed (or whose current lot postdates a sale
 * of that same ticker) more recently than the position document itself was written. This is
 * the exact shape of the LULU bug: a sync re-created a position after a sale had already
 * closed it. `importedAt`/`syncedAt` on a position marks when a baseline sync last touched it;
 * a closedPositions doc or a later realized_gain/sale_proceeds activity row for the same
 * ticker, dated after that, means the position should not exist.
 */
export function findResurrectedPositions(positions = [], closedPositions = [], activities = []) {
  const closedByTicker = new Map(closedPositions.map((row) => [normalizeTicker(row.ticker || row.id), row]))
  const lastSaleByTicker = new Map()
  for (const row of activities) {
    if (!['realized_gain', 'sale_proceeds'].includes(row?.type)) continue
    const ticker = normalizeTicker(row.ticker || (row.note || '').match(/^([A-Z.]{1,10})\b/)?.[1])
    if (!ticker) continue
    const at = row.recordedAt || row.effectiveDate
    if (!lastSaleByTicker.has(ticker) || String(at) > String(lastSaleByTicker.get(ticker))) {
      lastSaleByTicker.set(ticker, at)
    }
  }
  const findings = []
  for (const position of positions) {
    const ticker = normalizeTicker(position.ticker)
    const closed = closedByTicker.get(ticker)
    const positionWrittenAt = position.importedAt || position.syncedAt || position.addedAt || position.updatedAt
    if (closed) {
      const closedAt = closed.closedAt || closed.saleDate
      if (!positionWrittenAt || String(positionWrittenAt) >= String(closedAt || '')) {
        findings.push({
          check: 'resurrected_position',
          severity: 'critical',
          ticker,
          positionId: position.id,
          detail: `${ticker} has a closedPositions record (closed ${closed.closedAt || closed.saleDate || 'unknown date'}) `
            + `but a position document was written ${positionWrittenAt ? `at ${positionWrittenAt}` : '(no timestamp) '} `
            + 'after that -- this is a sold position that came back.',
        })
      }
      continue
    }
    const lastSale = lastSaleByTicker.get(ticker)
    if (lastSale && (!positionWrittenAt || String(positionWrittenAt) < String(lastSale))) {
      findings.push({
        check: 'resurrected_position',
        severity: 'critical',
        ticker,
        positionId: position.id,
        detail: `${ticker} has a realized_gain/sale_proceeds activity dated ${lastSale} but the current position `
          + `document is older (${positionWrittenAt || 'no timestamp'}) -- a sale may have been undone.`,
      })
    }
  }
  return findings
}

/** Check 2: a ticker marked closed that is still (or again) held, with no re-buy on record. */
export function findClosedTickersStillHeld(positions = [], closedPositions = [], activities = []) {
  const held = new Set(positions.map((position) => normalizeTicker(position.ticker)))
  const findings = []
  for (const closed of closedPositions) {
    const ticker = normalizeTicker(closed.ticker || closed.id)
    if (!held.has(ticker)) continue
    const rebought = activities.some((row) => row?.type === 'stock_purchase'
      && normalizeTicker(row.ticker) === ticker
      && String(row.recordedAt || row.effectiveDate || '') > String(closed.closedAt || closed.saleDate || ''))
    if (!rebought) {
      findings.push({
        check: 'closed_ticker_still_held',
        severity: 'critical',
        ticker,
        detail: `${ticker} is marked closed (sold ${closed.saleDate || closed.closedAt || 'unknown date'}) `
          + 'but a position for it exists with no recorded re-buy since.',
      })
    }
  }
  return findings
}

/**
 * Check 3: the reconciliation bridge, run across every consecutive pair of daily snapshots
 * that carry an unrealizedGain figure -- not just the most recent pair, which is all the
 * live UI checks. A failure anywhere in history means some NAV step in that window has no
 * ledger row accounting for it (a trade made outside the app, a missed flow, or exactly the
 * LULU-class bug: a position changing with nothing recorded).
 */
export function auditReconciliationBridge(snapshots = [], activities = []) {
  const daily = new Map()
  for (const row of snapshots) {
    if (!finite(row?.value) || row.unrealizedGain == null) continue
    const date = row.marketDate || String(row.recordedAt || '').slice(0, 10)
    if (!date) continue
    const existing = daily.get(date)
    if (!existing || String(row.recordedAt || '') > String(existing.recordedAt || '')) daily.set(date, row)
  }
  const ordered = [...daily.entries()].sort(([left], [right]) => left.localeCompare(right))
  const findings = []
  for (let index = 1; index < ordered.length; index += 1) {
    const [startDate, startRow] = ordered[index - 1]
    const [endDate, endRow] = ordered[index]
    const bridge = portfolioReconciliationBridge([startRow, endRow], activities)
    if (!bridge.available) continue
    if (bridge.status === 'RECONCILIATION_FAILED') {
      const windowActivity = activities.filter((row) => {
        const date = row.effectiveDate || row.date
        return date && date > startDate && date <= endDate
      })
      findings.push({
        check: 'bridge_failed',
        severity: 'warning',
        startDate,
        endDate,
        residual: bridge.residual,
        detail: bridge.reason,
        activityInWindow: windowActivity.map((row) => ({ type: row.type, amount: row.amount, effectiveDate: row.effectiveDate || row.date, ticker: row.ticker || null })),
      })
    }
  }
  return findings
}

/**
 * Check 4: NAV steps with no ledger row explaining them. A `position_added` with no matching
 * `stock_purchase`, or a `realized_gain` with no matching `sale_proceeds`, means some measure
 * of return will read that step as unexplained gain or loss -- the exact class of bug fixed in
 * commit 8eae175 for the write paths going forward. A bare `position_removed` (source
 * manual_holding_removal) is reported informationally: it is documented as not a sale, but the
 * audit still names it so a real sale entered as a removal is visible.
 */
export function findOrphanFlows(activities = []) {
  const near = (a, b, toleranceMs = 120_000) => {
    const ta = Date.parse(a || ''); const tb = Date.parse(b || '')
    return Number.isFinite(ta) && Number.isFinite(tb) && Math.abs(ta - tb) <= toleranceMs
  }
  const findings = []
  const purchases = activities.filter((row) => row?.type === 'stock_purchase')
  const sales = activities.filter((row) => row?.type === 'sale_proceeds')

  for (const added of activities.filter((row) => row?.type === 'position_added')) {
    const matched = purchases.some((row) => normalizeTicker(row.ticker) === normalizeTicker(added.ticker)
      && near(row.recordedAt, added.recordedAt))
    if (!matched) {
      findings.push({
        check: 'orphan_purchase',
        severity: 'warning',
        ticker: added.ticker,
        detail: `${added.ticker}: a position_added row (${added.recordedAt}) has no matching stock_purchase -- `
          + 'this buy is invisible to every return measure taken off tracked NAV.',
      })
    }
  }
  for (const gain of activities.filter((row) => row?.type === 'realized_gain')) {
    const ticker = normalizeTicker(gain.ticker || (gain.note || '').match(/^([A-Z.]{1,10})\b/)?.[1])
    const matched = sales.some((row) => normalizeTicker(row.ticker) === ticker && near(row.recordedAt, gain.recordedAt))
    if (!matched) {
      findings.push({
        check: 'orphan_realized_gain',
        severity: 'warning',
        ticker: ticker || '(unknown)',
        detail: `A realized_gain row (${gain.recordedAt}, amount ${gain.amount}) has no matching sale_proceeds -- `
          + 'the shares left NAV with nothing recording where the money went.',
      })
    }
  }
  for (const removed of activities.filter((row) => row?.type === 'position_removed' && row?.source === 'manual_holding_removal')) {
    findings.push({
      check: 'bare_removal',
      severity: 'info',
      ticker: removed.ticker,
      detail: `${removed.ticker} was removed without a sale recorded (${removed.recordedAt}). `
        + 'If shares were actually sold, record the sale so the return measures reconcile.',
    })
  }
  return findings
}

/** Check 5 (informational): snapshots recorded before per-ticker prices were captured. */
export function findSnapshotsWithoutPrices(snapshots = []) {
  const missing = snapshots.filter((row) => finite(row?.value) && !(Array.isArray(row.prices) && row.prices.length))
  if (!missing.length) return []
  return [{
    check: 'snapshots_without_prices',
    severity: 'info',
    count: missing.length,
    detail: `${missing.length} of ${snapshots.length} recorded snapshots carry no per-ticker prices `
      + '(recorded before this was added) -- latestRecordedPrices() cannot use them as a price fallback.',
  }]
}

/**
 * Check 6: diff stored positions against an external statement (a Fidelity Positions export,
 * transcribed into the fixture shape used by scripts/fixtures/fidelity-positions-*.json).
 * Read-only -- it never suggests a write. This answers "does Firestore equal what Fidelity
 * actually shows right now", independent of anything this app's own sync logic believes.
 */
export function diffAgainstStatement(positions = [], statement) {
  if (!statement?.positions) return []
  const stored = new Map(positions.map((position) => [normalizeTicker(position.ticker), position]))
  const statementTickers = new Set(statement.positions.map((row) => normalizeTicker(row.ticker)))
  const findings = []
  for (const row of statement.positions) {
    const ticker = normalizeTicker(row.ticker)
    const held = stored.get(ticker)
    if (!held) {
      findings.push({
        check: 'statement_missing_holding', severity: 'critical', ticker,
        detail: `${ticker}: the statement shows ${row.shares} shares held; Firestore has no position for it.`,
      })
      continue
    }
    const totalShares = positions
      .filter((position) => normalizeTicker(position.ticker) === ticker)
      .reduce((sum, position) => sum + (Number(position.shares) || 0), 0)
    if (Math.abs(totalShares - row.shares) > 1e-6) {
      findings.push({
        check: 'statement_share_mismatch', severity: 'critical', ticker,
        detail: `${ticker}: statement shows ${row.shares} shares, Firestore holds ${totalShares}.`,
      })
    }
    const totalCost = positions
      .filter((position) => normalizeTicker(position.ticker) === ticker)
      .reduce((sum, position) => sum + (Number(position.shares) || 0) * (Number(position.costBasis) || 0), 0)
    if (finite(row.costBasisTotal) && Math.abs(totalCost - row.costBasisTotal) > 0.01) {
      findings.push({
        check: 'statement_cost_mismatch', severity: 'warning', ticker,
        detail: `${ticker}: statement cost basis $${row.costBasisTotal.toFixed(2)}, Firestore $${totalCost.toFixed(2)}.`,
      })
    }
  }
  for (const [ticker] of stored) {
    if (!statementTickers.has(ticker)) {
      findings.push({
        check: 'statement_unexpected_holding', severity: 'critical', ticker,
        detail: `${ticker}: Firestore holds a position for it, but the statement does not list it -- `
          + 'sold since the statement, or resurrected by mistake.',
      })
    }
  }
  return findings
}

/**
 * Check 7 (informational): how the account differs from the in-code REFERENCE_PORTFOLIO under
 * `mode: 'reconcile'`. This is never applied -- the app only ever seeds -- but it is useful
 * context: it says "the export and your record disagree here", most of which is simply normal
 * trading since the export was taken.
 */
export function auditReferenceDrift(positions = [], closedTickers = [], trackingState = null) {
  const seededTickers = seededTickersFromTrackingState(trackingState)
  const operations = planReferencePortfolioSync(positions, undefined, { closedTickers, mode: 'reconcile' })
  const meaningful = operations.filter((operation) => {
    if (operation.kind === 'add') return !seededTickers.includes(normalizeTicker(operation.record.ticker))
    return true
  })
  if (!meaningful.length) return []
  return [{
    check: 'reference_drift',
    severity: 'info',
    count: meaningful.length,
    detail: `${meaningful.length} difference(s) between the account and the in-code REFERENCE_PORTFOLIO `
      + '(reconcile mode, not applied) -- expected after any trading since the export was taken.',
    operations: meaningful.map((operation) => ({ kind: operation.kind, ticker: operation.record.ticker })),
  }]
}

/** Runs every check and returns one flat, ordered finding list plus a pass/fail summary. */
export function runPortfolioAudit({
  positions = [], closedPositions = [], activities = [], snapshots = [], trackingState = null, statement = null,
}) {
  const findings = [
    ...findResurrectedPositions(positions, closedPositions, activities),
    ...findClosedTickersStillHeld(positions, closedPositions, activities),
    ...auditReconciliationBridge(snapshots, activities),
    ...findOrphanFlows(activities),
    ...findSnapshotsWithoutPrices(snapshots),
    ...diffAgainstStatement(positions, statement),
    ...auditReferenceDrift(positions, closedPositions.map((row) => row.ticker || row.id), trackingState),
  ]
  const critical = findings.filter((finding) => finding.severity === 'critical')
  const warnings = findings.filter((finding) => finding.severity === 'warning')
  const info = findings.filter((finding) => finding.severity === 'info')
  return {
    ok: critical.length === 0 && warnings.length === 0,
    critical, warnings, info,
    findings,
  }
}

// Referenced for callers that want the flow vocabulary without importing portfolioAnalytics
// directly (kept here so this module documents its own dependency on it).
export { BASKET_FLOW_TYPES }
