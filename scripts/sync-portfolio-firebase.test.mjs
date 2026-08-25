import { describe as group, expect, it } from 'vitest'
import { buildReport, describe, parseArguments, renderReportMarkdown, withTimeout } from './sync-portfolio-firebase.mjs'
import {
  planReferencePortfolioSync,
  referenceSyncDrift,
  verifyReferencePortfolio,
  referenceIntradaySnapshot,
  referenceSyncRecord,
  referenceTrackingState,
  summarizeReferenceSync,
  REFERENCE_PORTFOLIO,
  REFERENCE_PORTFOLIO_EXPECTED,
  REFERENCE_PORTFOLIO_RECORDED_AT,
  REFERENCE_PORTFOLIO_VERSION,
} from '../src/lib/referencePortfolio.js'

// Firestore as it would look holding a given baseline, for building report fixtures.
const storedAs = (reference) => reference.map((position) => ({
  id: `${position.ticker}-reference`,
  ticker: position.ticker,
  shares: position.shares,
  costBasis: position.costBasis,
  costBasisTotal: position.costBasisTotal,
  snapshotPrice: position.snapshotPrice,
  snapshotValue: position.snapshotValue,
  purchaseDate: position.purchaseDate || '',
}))

group('sync-portfolio-firebase arguments', () => {
  it('requires an account to be named', () => {
    expect(() => parseArguments([])).toThrow(/--email <address> or --uid/)
  })

  it('rejects naming the account twice', () => {
    expect(() => parseArguments(['--email', 'a@b.c', '--uid', 'x'])).toThrow(/not both/)
  })

  it('rejects an unknown flag rather than ignoring it', () => {
    expect(() => parseArguments(['--uid', 'x', '--dry-run'])).toThrow(/Unrecognized argument: --dry-run/)
  })

  it('requires a destination for --report', () => {
    expect(() => parseArguments(['--uid', 'x', '--report'])).toThrow(/--report needs a file path/)
    expect(parseArguments(['--uid', 'x', '--report', '-']).report).toBe('-')
  })

  // Dry run is the default because this import deletes holdings absent from the export.
  it('does not commit unless asked', () => {
    expect(parseArguments(['--uid', 'x'])).toMatchObject({ uid: 'x', commit: false })
    expect(parseArguments(['--uid', 'x', '--commit']).commit).toBe(true)
  })
})

group('sync-portfolio-firebase plan output', () => {
  it('marks each operation and carries the acquisition date', () => {
    const output = describe(planReferencePortfolioSync(
      [{ id: 'old', ticker: 'ZZZZ', shares: 1, costBasis: 5 }],
      [
        { ticker: 'AMZN', shares: 0.386, costBasis: 258.52, costBasisTotal: 99.79, purchaseDate: '2026-08-21' },
        { ticker: 'VOO', shares: 0.146, costBasis: 633.36, costBasisTotal: 92.47, purchaseDate: null },
      ],
    ))

    expect(output).toContain('+ AMZN')
    expect(output).toContain('2026-08-21')
    expect(output).toContain('$99.79')
    expect(output).toContain('undated') // VOO has no buy in the history
    expect(output).toContain('- ZZZZ   removed (not in the export)')
  })
})

// The CLI and the in-app sync write to the same collection, so they must produce identical
// documents. These builders are the single definition both call.
group('shared reference sync records', () => {
  it('stamps an add with importedAt and an update with syncedAt', () => {
    const at = '2026-08-25T12:00:00.000Z'
    const [add] = planReferencePortfolioSync([], [{ ticker: 'AMZN', shares: 1, costBasis: 2, purchaseDate: '2026-08-21' }])
    const [update] = planReferencePortfolioSync(
      [{ id: 'amzn-1', ticker: 'AMZN', shares: 9, costBasis: 9 }],
      [{ ticker: 'AMZN', shares: 1, costBasis: 2, purchaseDate: '2026-08-21' }],
    )

    expect(referenceSyncRecord(add, at)).toMatchObject({ id: 'AMZN-reference', importedAt: at, purchaseDate: '2026-08-21' })
    expect(referenceSyncRecord(add, at).syncedAt).toBeUndefined()
    expect(referenceSyncRecord(update, at)).toMatchObject({ syncedAt: at, shares: 1 })
  })

  it('builds an invested-only snapshot that matches the export totals', () => {
    const { id, document } = referenceIntradaySnapshot()

    expect(id).toBe('2026-08-25T11-55')
    expect(document.recordedAt).toBe(REFERENCE_PORTFOLIO_RECORDED_AT)
    expect(document.positionCount).toBe(REFERENCE_PORTFOLIO.length)
    expect(document.investedValue).toBeCloseTo(5668.16, 8)
    expect(document.prices).toHaveLength(REFERENCE_PORTFOLIO.length)
    expect(document.prices.some((row) => ['FZFXX', 'Pending activity'].includes(row.ticker))).toBe(false)
  })

  // Firestore rejects undefined, so an absent previous close has to reach it as null.
  it('carries a null previous close rather than an undefined one', () => {
    referenceIntradaySnapshot().document.prices.forEach((row) => {
      expect(row.previousClose).toBeNull()
    })
  })

  it('marks the account against the version that produced the write', () => {
    expect(referenceTrackingState('2026-08-25T12:00:00.000Z')).toEqual({
      referencePortfolioVersion: REFERENCE_PORTFOLIO_VERSION,
      referencePortfolioImportedAt: '2026-08-25T12:00:00.000Z',
    })
  })

  it('counts a plan the way both callers report it', () => {
    expect(summarizeReferenceSync(planReferencePortfolioSync(
      [{ id: 'gone', ticker: 'ZZZZ', shares: 1 }, { id: 'amzn', ticker: 'AMZN', shares: 1 }],
      [{ ticker: 'AMZN', shares: 2 }, { ticker: 'DELL', shares: 1 }],
    ))).toEqual({ added: 1, updated: 1, removed: 1 })
  })
})

group('baseline verification', () => {
  it('passes every check against the brokerage figures as shipped', () => {
    const failures = verifyReferencePortfolio().filter((check) => !check.ok)
    expect(failures.map((check) => `${check.name}: ${check.detail}`)).toEqual([])
  })

  // The point of holding the brokerage totals separately: a row edited without updating them
  // has to fail, or the baseline can silently stop matching the statement it claims to be.
  it('fails loudly when a holding no longer reconciles to those figures', () => {
    const tampered = REFERENCE_PORTFOLIO.map((position) => (position.ticker === 'MU'
      ? { ...position, shares: 5, snapshotValue: 4500 }
      : position))
    const failed = verifyReferencePortfolio(tampered).filter((check) => !check.ok).map((check) => check.name)

    expect(failed).toContain('Market value matches the account summary')
    expect(failed).toContain('Every price reproduces its exported value')
  })

  it('catches a purchase date taken from the export date', () => {
    const backdated = REFERENCE_PORTFOLIO.map((position) => (position.ticker === 'AMZN'
      ? { ...position, purchaseDate: REFERENCE_PORTFOLIO_RECORDED_AT.slice(0, 10) }
      : position))
    const failed = verifyReferencePortfolio(backdated).filter((check) => !check.ok).map((check) => check.name)

    expect(failed).toContain('No purchase date is taken from the export date')
  })
})

group('sync drift', () => {
  it('reports no drift for a holding the sync would rewrite identically', () => {
    const [operation] = planReferencePortfolioSync(
      [{ id: 'a', ticker: 'AAA', shares: 2, costBasis: 5, purchaseDate: '2026-01-01' }],
      [{ ticker: 'AAA', shares: 2, costBasis: 5, purchaseDate: '2026-01-01' }],
    )
    expect(referenceSyncDrift(operation)).toEqual([])
  })

  it('names each changed field with its before and after', () => {
    const [operation] = planReferencePortfolioSync(
      [{ id: 'a', ticker: 'AAA', shares: 9, costBasis: 5, purchaseDate: '' }],
      [{ ticker: 'AAA', shares: 2, costBasis: 5, purchaseDate: '2026-01-01' }],
    )
    expect(referenceSyncDrift(operation)).toEqual([
      { field: 'shares', from: 9, to: 2 },
      { field: 'purchaseDate', from: null, to: '2026-01-01' },
    ])
  })
})

group('verification report', () => {
  const report = (stored) => buildReport({
    uid: 'u1', email: 'you@example.com', committed: false, generatedAt: '2026-08-25T13:00:00.000Z',
    operations: planReferencePortfolioSync(stored),
  })

  it('calls an account holding the full baseline in sync', () => {
    const result = report(storedAs(REFERENCE_PORTFOLIO))

    expect(result.correct).toBe(true)
    expect(result.inSync).toBe(true)
    expect(result.rows.every((row) => row.action === 'unchanged')).toBe(true)
    expect(renderReportMarkdown(result)).toContain('Account already matches this baseline')
  })

  // The account as it stood on the Aug 14 baseline: the seven Aug-21 buys not yet stored.
  it('calls an account missing the Aug 21 buys out of date and names them', () => {
    const result = report(storedAs(REFERENCE_PORTFOLIO.filter((p) => p.purchaseDate !== '2026-08-21')))

    expect(result.inSync).toBe(false)
    expect(result.counts.added).toBe(7)
    expect(result.rows.filter((row) => row.action === 'add').map((row) => row.ticker))
      .toEqual(['AMP', 'AMZN', 'DELL', 'ETN', 'MPC', 'THC', 'TWLO'])
    expect(renderReportMarkdown(result)).toContain('Account is out of date')
  })

  it('shows a stale share count and a missing date as drift', () => {
    const stored = storedAs(REFERENCE_PORTFOLIO)
    stored.find((row) => row.ticker === 'MU').shares = 0.5
    stored.find((row) => row.ticker === 'HIG').purchaseDate = ''
    const markdown = renderReportMarkdown(report(stored))

    expect(markdown).toContain('| MU | update | shares: 0.5 → 0.101 |')
    expect(markdown).toContain('| HIG | update | purchaseDate: (none) → 2026-08-07 |')
  })

  it('lists a stored holding the export no longer carries as a removal', () => {
    const stored = [...storedAs(REFERENCE_PORTFOLIO), { id: 'TTM-old', ticker: 'TTM', shares: 3 }]
    const result = report(stored)

    expect(result.inSync).toBe(false)
    expect(result.removals).toEqual([{ ticker: 'TTM', id: 'TTM-old' }])
    expect(renderReportMarkdown(result)).toContain('| TTM | remove | not present in the export |')
  })

  it('totals the holdings table to the brokerage account total', () => {
    const markdown = renderReportMarkdown(report(storedAs(REFERENCE_PORTFOLIO)))
    const { costBasisTotal, marketValue, accountTotal, moneyMarketValue } = REFERENCE_PORTFOLIO_EXPECTED

    expect(markdown).toContain(`**$${costBasisTotal.toFixed(2)}**`)
    expect(markdown).toContain(`**$${marketValue.toFixed(2)}**`)
    expect(markdown).toContain(`$${moneyMarketValue.toFixed(2)} · account total per Fidelity: **$${accountTotal.toFixed(2)}**`)
    expect(markdown).toContain('BSX, VOO')
  })

  it('states plainly whether anything was written', () => {
    const stored = storedAs(REFERENCE_PORTFOLIO)
    expect(renderReportMarkdown(report(stored))).toContain('dry run — nothing written')
    expect(renderReportMarkdown(buildReport({
      uid: 'u1', committed: true, generatedAt: 'now',
      operations: planReferencePortfolioSync(stored),
    }))).toContain('committed — Firestore was written')
  })
})

// firebase-admin retries a blocked connection with long backoff and prints nothing while it
// does, so an unreachable Google endpoint used to look like the script had frozen. Every
// network call is now bounded and announced before it starts.
group('network timeouts', () => {
  it('passes a result through untouched when it arrives in time', async () => {
    await expect(withTimeout(Promise.resolve('ok'), 'Firestore read', 50)).resolves.toBe('ok')
  })

  it('surfaces the underlying failure rather than masking it as a timeout', async () => {
    await expect(withTimeout(Promise.reject(new Error('permission denied')), 'Firestore read', 50))
      .rejects.toThrow('permission denied')
  })

  it('names the step and says nothing was written when it stalls', async () => {
    const stalled = new Promise(() => {})
    await expect(withTimeout(stalled, 'Firebase Auth', 10)).rejects.toThrow(
      /Firebase Auth did not respond within 0\.01s[\s\S]*nothing has been written/,
    )
  })

  // A leaked timer would keep the process alive after the work finished — the exact class of
  // hang this whole change is about.
  it('clears its timer once the call resolves', async () => {
    const before = process._getActiveHandles?.().length ?? 0
    await withTimeout(Promise.resolve(1), 'Firestore read', 60_000)
    expect((process._getActiveHandles?.().length ?? 0)).toBeLessThanOrEqual(before)
  })
})
