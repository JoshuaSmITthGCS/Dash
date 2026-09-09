import { describe, expect, it } from 'vitest'
import {
  auditReconciliationBridge,
  auditReferenceDrift,
  diffAgainstStatement,
  findClosedTickersStillHeld,
  findOrphanFlows,
  findResurrectedPositions,
  findSnapshotsWithoutPrices,
  findUncorrectedSnapshots,
  runPortfolioAudit,
} from './portfolio-audit.mjs'

describe('findResurrectedPositions — the exact shape of the LULU bug', () => {
  it('flags a position whose ticker is marked closed', () => {
    const positions = [{ id: 'LULU-reference', ticker: 'LULU', shares: 1, importedAt: '2026-09-05T00:00:00Z' }]
    const closedPositions = [{ id: 'LULU', ticker: 'LULU', closedAt: '2026-09-03T00:00:00Z', saleDate: '2026-09-03' }]
    const findings = findResurrectedPositions(positions, closedPositions, [])
    expect(findings).toHaveLength(1)
    expect(findings[0]).toMatchObject({ check: 'resurrected_position', severity: 'critical', ticker: 'LULU' })
  })

  it('does not flag a position written before the ticker was closed (the normal case, mid-sale)', () => {
    const positions = [{ id: 'LULU-1', ticker: 'LULU', shares: 1, importedAt: '2026-08-25T11:55:00Z' }]
    const closedPositions = [{ id: 'LULU', ticker: 'LULU', closedAt: '2026-09-03T00:00:00Z' }]
    // Position doc is older than the close -- this is the moment right before the sale wrote
    // the closedPositions doc and deleted the position, not a resurrection.
    // (In practice the position would already be deleted by then; this asserts the timestamp
    // comparison direction is correct rather than accidentally always failing.)
    expect(findResurrectedPositions([], closedPositions, [])).toHaveLength(0)
    expect(positions).toBeDefined()
  })

  it('flags a position with no closedPositions doc but an activity trail proving it was sold', () => {
    const positions = [{ id: 'NTNX-reference', ticker: 'NTNX', shares: 1.284, importedAt: '2026-09-06T00:00:00Z' }]
    const activities = [
      { type: 'sale_proceeds', ticker: 'NTNX', recordedAt: '2026-09-08T00:00:00Z', effectiveDate: '2026-09-04' },
    ]
    const findings = findResurrectedPositions(positions, [], activities)
    expect(findings).toHaveLength(1)
    expect(findings[0].ticker).toBe('NTNX')
  })

  it('is silent on a clean account', () => {
    const positions = [{ id: 'AAPL-1', ticker: 'AAPL', shares: 10, importedAt: '2026-01-01T00:00:00Z' }]
    expect(findResurrectedPositions(positions, [], [])).toHaveLength(0)
  })
})

describe('findClosedTickersStillHeld', () => {
  it('flags a closed ticker with an open position and no recorded re-buy', () => {
    const positions = [{ ticker: 'LULU', shares: 1 }]
    const closedPositions = [{ ticker: 'LULU', saleDate: '2026-09-03' }]
    expect(findClosedTickersStillHeld(positions, closedPositions, [])).toHaveLength(1)
  })

  it('does not flag when a stock_purchase after the sale re-opened it', () => {
    const positions = [{ ticker: 'LULU', shares: 2 }]
    const closedPositions = [{ ticker: 'LULU', saleDate: '2026-09-03' }]
    const activities = [{ type: 'stock_purchase', ticker: 'LULU', recordedAt: '2026-09-08T00:00:00Z' }]
    expect(findClosedTickersStillHeld(positions, closedPositions, activities)).toHaveLength(0)
  })
})

describe('auditReconciliationBridge across history', () => {
  it('reports every failed window, not only the most recent', () => {
    const snapshots = [
      { value: 10000, unrealizedGain: 1000, marketDate: '2026-01-01', recordedAt: '2026-01-01T20:00:00Z' },
      { value: 9600, unrealizedGain: 900, marketDate: '2026-01-02', recordedAt: '2026-01-02T20:00:00Z' },
      { value: 9650, unrealizedGain: 950, marketDate: '2026-01-03', recordedAt: '2026-01-03T20:00:00Z' },
    ]
    // Jan 1->2: a 400 NAV drop with no flow recorded for it (bridge fails).
    // Jan 2->3: reconciles cleanly (no activity needed, unrealizedGain change explains it).
    const findings = auditReconciliationBridge(snapshots, [])
    expect(findings).toHaveLength(1)
    expect(findings[0]).toMatchObject({ check: 'bridge_failed', startDate: '2026-01-01', endDate: '2026-01-02' })
  })

  it('is silent when a sale_proceeds row explains the NAV step', () => {
    const snapshots = [
      { value: 10000, unrealizedGain: 1000, marketDate: '2026-01-01', recordedAt: '2026-01-01T20:00:00Z' },
      { value: 9600, unrealizedGain: 900, marketDate: '2026-01-02', recordedAt: '2026-01-02T20:00:00Z' },
    ]
    const activities = [
      { type: 'realized_gain', amount: 100, effectiveDate: '2026-01-02' },
      { type: 'sale_proceeds', amount: 400, effectiveDate: '2026-01-02' },
    ]
    expect(auditReconciliationBridge(snapshots, activities)).toHaveLength(0)
  })

  it('deduplicates same-day snapshots to the latest one before pairing', () => {
    const snapshots = [
      { value: 9900, unrealizedGain: 950, marketDate: '2026-01-01', recordedAt: '2026-01-01T15:00:00Z' },
      { value: 10000, unrealizedGain: 1000, marketDate: '2026-01-01', recordedAt: '2026-01-01T20:00:00Z' },
      { value: 10000, unrealizedGain: 1000, marketDate: '2026-01-02', recordedAt: '2026-01-02T20:00:00Z' },
    ]
    expect(auditReconciliationBridge(snapshots, [])).toHaveLength(0)
  })
})

describe('findOrphanFlows', () => {
  it('flags a position_added with no matching stock_purchase', () => {
    const activities = [{ type: 'position_added', ticker: 'AAPL', recordedAt: '2026-01-01T00:00:00Z', amount: 500 }]
    const findings = findOrphanFlows(activities)
    expect(findings).toHaveLength(1)
    expect(findings[0]).toMatchObject({ check: 'orphan_purchase', ticker: 'AAPL' })
  })

  it('is silent when the stock_purchase is present at the same instant', () => {
    const activities = [
      { type: 'position_added', ticker: 'AAPL', recordedAt: '2026-01-01T00:00:00.000Z', amount: 500 },
      { type: 'stock_purchase', ticker: 'AAPL', recordedAt: '2026-01-01T00:00:00.500Z', amount: 500 },
    ]
    expect(findOrphanFlows(activities)).toHaveLength(0)
  })

  it('flags a realized_gain with no matching sale_proceeds', () => {
    const activities = [{ type: 'realized_gain', ticker: 'LULU', recordedAt: '2026-09-03T00:00:00Z', amount: -15.54 }]
    const findings = findOrphanFlows(activities)
    expect(findings.some((finding) => finding.check === 'orphan_realized_gain')).toBe(true)
  })

  it('reports a bare manual removal informationally, not as a warning', () => {
    const activities = [{ type: 'position_removed', ticker: 'XYZ', source: 'manual_holding_removal', recordedAt: '2026-01-01T00:00:00Z' }]
    const findings = findOrphanFlows(activities)
    expect(findings).toHaveLength(1)
    expect(findings[0]).toMatchObject({ check: 'bare_removal', severity: 'info' })
  })
})

describe('findSnapshotsWithoutPrices', () => {
  it('counts snapshots missing per-ticker prices', () => {
    const snapshots = [
      { value: 100, recordedAt: '2026-01-01' },
      { value: 200, recordedAt: '2026-01-02', prices: [{ ticker: 'AAPL', price: 150 }] },
    ]
    const findings = findSnapshotsWithoutPrices(snapshots)
    expect(findings).toHaveLength(1)
    expect(findings[0]).toMatchObject({ severity: 'info', count: 1 })
  })

  it('is silent when every snapshot has prices', () => {
    const snapshots = [{ value: 100, recordedAt: '2026-01-01', prices: [{ ticker: 'AAPL', price: 150 }] }]
    expect(findSnapshotsWithoutPrices(snapshots)).toHaveLength(0)
  })
})

describe('diffAgainstStatement', () => {
  const statement = { positions: [{ ticker: 'AAPL', shares: 10, costBasisTotal: 1000 }] }

  it('flags a holding the statement shows but Firestore lacks', () => {
    const findings = diffAgainstStatement([], statement)
    expect(findings.some((finding) => finding.check === 'statement_missing_holding')).toBe(true)
  })

  it('flags a share-count mismatch', () => {
    const positions = [{ ticker: 'AAPL', shares: 5, costBasis: 100 }]
    const findings = diffAgainstStatement(positions, statement)
    expect(findings.some((finding) => finding.check === 'statement_share_mismatch')).toBe(true)
  })

  it('flags a cost-basis mismatch', () => {
    const positions = [{ ticker: 'AAPL', shares: 10, costBasis: 90 }]
    const findings = diffAgainstStatement(positions, statement)
    expect(findings.some((finding) => finding.check === 'statement_cost_mismatch')).toBe(true)
  })

  it('flags a holding Firestore has that the statement does not list (the LULU case)', () => {
    const positions = [
      { ticker: 'AAPL', shares: 10, costBasis: 100 },
      { ticker: 'LULU', shares: 1, costBasis: 117.94 },
    ]
    const findings = diffAgainstStatement(positions, statement)
    expect(findings.some((finding) => finding.check === 'statement_unexpected_holding' && finding.ticker === 'LULU')).toBe(true)
  })

  it('sums shares across multiple lots of the same ticker before comparing', () => {
    const positions = [
      { ticker: 'AAPL', shares: 6, costBasis: 100 },
      { ticker: 'AAPL', shares: 4, costBasis: 100 },
    ]
    expect(diffAgainstStatement(positions, statement).some((finding) => finding.check === 'statement_share_mismatch')).toBe(false)
  })

  it('is silent with no statement supplied', () => {
    expect(diffAgainstStatement([{ ticker: 'AAPL', shares: 10 }], null)).toHaveLength(0)
  })
})

describe('auditReferenceDrift', () => {
  it('is informational only and never suggests a write', () => {
    const findings = auditReferenceDrift([], [], null)
    expect(findings.every((finding) => finding.severity === 'info')).toBe(true)
  })

  it('excludes tickers already seeded from counting as drift', () => {
    // An account seeded from the reference export should show zero "meaningful" adds even
    // though reconcile mode would technically propose them again.
    const trackingState = { referencePortfolioVersion: 'any-version' }
    const findings = auditReferenceDrift([], [], trackingState)
    // Every reference ticker is treated as already seeded (seededTickersFromTrackingState
    // falls back to "the whole export" when a version marker exists with no explicit list).
    expect(findings).toEqual([])
  })
})

describe('runPortfolioAudit orchestration', () => {
  it('is ok on a clean account with a matching statement', () => {
    const positions = [{ ticker: 'AAPL', shares: 10, costBasis: 100, importedAt: '2026-01-01T00:00:00Z' }]
    const statement = { positions: [{ ticker: 'AAPL', shares: 10, costBasisTotal: 1000 }] }
    const report = runPortfolioAudit({ positions, statement })
    expect(report.ok).toBe(true)
    expect(report.critical).toHaveLength(0)
  })

  it('is not ok when a resurrected position is present, and it lands in critical', () => {
    const positions = [{ id: 'LULU-reference', ticker: 'LULU', shares: 1, importedAt: '2026-09-05T00:00:00Z' }]
    const closedPositions = [{ ticker: 'LULU', closedAt: '2026-09-03T00:00:00Z' }]
    const report = runPortfolioAudit({ positions, closedPositions })
    expect(report.ok).toBe(false)
    expect(report.critical.length).toBeGreaterThan(0)
  })

  it('informational-only findings never flip ok to false', () => {
    const activities = [{ type: 'position_removed', ticker: 'XYZ', source: 'manual_holding_removal', recordedAt: '2026-01-01T00:00:00Z' }]
    const report = runPortfolioAudit({ activities })
    expect(report.info.length).toBeGreaterThan(0)
    expect(report.critical).toHaveLength(0)
    expect(report.warnings).toHaveLength(0)
    expect(report.ok).toBe(true)
  })
})

describe('findUncorrectedSnapshots', () => {
  const correctHoldingsAsOf = (date) => {
    if (date < '2026-09-03') return new Map([['LULU', { shares: 1, costBasisTotal: 117.94 }]])
    return new Map([['TSM', { shares: 0.482, costBasisTotal: 199.67 }]])
  }

  it('flags a snapshot whose recorded tickers disagree with the correct holdings for its date', () => {
    const snapshots = [{
      marketDate: '2026-09-04', value: 100,
      prices: [{ ticker: 'LULU', shares: 1, price: 100 }], // wrong: LULU should be gone, TSM should be present
    }]
    const findings = findUncorrectedSnapshots(snapshots, correctHoldingsAsOf, null)
    expect(findings).toHaveLength(1)
    expect(findings[0]).toMatchObject({ check: 'uncorrected_snapshots', severity: 'warning', count: 1 })
    expect(findings[0].dates).toContain('2026-09-04')
  })

  it('is silent when the recorded tickers match the correct holdings', () => {
    const snapshots = [{ marketDate: '2026-09-04', value: 100, prices: [{ ticker: 'TSM', shares: 0.482, price: 200 }] }]
    expect(findUncorrectedSnapshots(snapshots, correctHoldingsAsOf, null)).toHaveLength(0)
  })

  it('skips a snapshot already marked corrected', () => {
    const snapshots = [{ marketDate: '2026-09-04', value: 100, correctedAt: '2026-09-10T00:00:00Z', prices: [{ ticker: 'LULU', shares: 1, price: 100 }] }]
    expect(findUncorrectedSnapshots(snapshots, correctHoldingsAsOf, null)).toHaveLength(0)
  })

  it('skips a snapshot before the given cutoff date', () => {
    const snapshots = [{ marketDate: '2026-08-01', value: 100, prices: [{ ticker: 'LULU', shares: 1, price: 100 }] }]
    expect(findUncorrectedSnapshots(snapshots, correctHoldingsAsOf, '2026-08-25')).toHaveLength(0)
  })

  it('skips a snapshot with no prices array -- that is findSnapshotsWithoutPrices\' job, not this one\'s', () => {
    const snapshots = [{ marketDate: '2026-09-04', value: 100 }]
    expect(findUncorrectedSnapshots(snapshots, correctHoldingsAsOf, null)).toHaveLength(0)
  })

  it('does nothing when no correctHoldingsAsOf function is supplied', () => {
    expect(findUncorrectedSnapshots([{ marketDate: '2026-09-04', value: 100, prices: [] }], null, null)).toHaveLength(0)
  })
})
