// Reading a holdings file into the stored portfolio.
//
// This is the general-purpose path the one-off Fidelity baseline in referencePortfolio.js is
// a special case of: the same reconciliation, driven by a file the user supplies rather than
// a constant compiled into the bundle, so a new brokerage export never needs a code change.
//
// Parsing is kept pure and separate from writing. A file is validated and planned in full
// before a single document is touched, so the UI can show exactly what an import would do --
// and so a malformed file is rejected outright rather than half-applied.

import { planReferencePortfolioSync } from './referencePortfolio.js'

export const IMPORT_SCHEMA_VERSION = 1

const TICKER_PATTERN = /^[A-Z][A-Z0-9.-]{0,9}$/
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

// Rejects null and '' rather than reading them as zero -- see the note in portfolioPosition.js.
const finite = (value) =>
  value !== null && value !== '' && typeof value !== 'boolean' && Number.isFinite(Number(value))
const round = (value) => Math.round(value * 100) / 100

/**
 * Accepts what people actually have: the app's own export, a hand-written file, or a bare
 * array of holdings. Cost may be stated per share or as a total, because brokerage exports
 * disagree about which they print -- both are carried through so neither has to be recomputed
 * from the other and rounded twice.
 */
function readPosition(raw, index) {
  const errors = []
  const at = `row ${index + 1}`
  const ticker = String(raw?.ticker ?? raw?.symbol ?? '').trim().toUpperCase()
  if (!ticker) errors.push(`${at}: no ticker`)
  else if (!TICKER_PATTERN.test(ticker)) errors.push(`${at}: "${ticker}" is not a ticker symbol`)

  const shares = Number(raw?.shares ?? raw?.quantity ?? raw?.qty)
  if (!finite(shares)) errors.push(`${at} (${ticker || '?'}): shares is missing or not a number`)
  else if (shares <= 0) errors.push(`${at} (${ticker || '?'}): shares must be greater than zero`)

  const hasTotal = finite(raw?.costBasisTotal ?? raw?.totalCost)
  const hasPerShare = finite(raw?.costBasis ?? raw?.costPerShare)
  const costBasisTotal = hasTotal ? Number(raw.costBasisTotal ?? raw.totalCost) : null
  const perShareInput = hasPerShare ? Number(raw.costBasis ?? raw.costPerShare) : null
  if (!hasTotal && !hasPerShare) {
    errors.push(`${at} (${ticker || '?'}): needs costBasisTotal or costBasis`)
  } else if ((hasTotal && costBasisTotal <= 0) || (!hasTotal && perShareInput <= 0)) {
    errors.push(`${at} (${ticker || '?'}): cost basis must be greater than zero`)
  }

  const purchaseDate = String(raw?.purchaseDate ?? raw?.bought ?? '').trim()
  if (purchaseDate && !DATE_PATTERN.test(purchaseDate)) {
    errors.push(`${at} (${ticker || '?'}): purchaseDate "${purchaseDate}" is not YYYY-MM-DD`)
  }

  const price = finite(raw?.price ?? raw?.snapshotPrice) ? Number(raw.price ?? raw.snapshotPrice) : null
  const value = finite(raw?.value ?? raw?.snapshotValue) ? Number(raw.value ?? raw.snapshotValue) : null

  if (errors.length) return { errors }

  const total = hasTotal ? costBasisTotal : perShareInput * shares
  return {
    errors: [],
    position: {
      ticker,
      shares,
      costBasis: total / shares,
      costBasisTotal: total,
      costBasisUnit: 'per_share',
      costBasisInputMode: hasTotal ? 'total' : 'share',
      purchaseDate,
      // Written explicitly even when absent. These are quantity-derived and a stale pair left
      // over from an earlier import would keep rendering the old dollar figure until a live
      // quote arrived, which reads as the import having failed to save.
      snapshotPrice: price,
      snapshotValue: value != null ? value : price != null ? round(price * shares) : null,
      snapshotPreviousClose: null,
    },
  }
}

/**
 * Validates a holdings file without touching anything. Returns every problem at once rather
 * than the first, so a file can be fixed in one pass instead of one error per attempt.
 */
export function parsePortfolioImport(text) {
  let raw
  try {
    raw = JSON.parse(text)
  } catch (error) {
    return { ok: false, errors: [`Not valid JSON: ${error.message}`], positions: [], meta: {} }
  }

  const rows = Array.isArray(raw) ? raw : raw?.positions
  if (!Array.isArray(rows)) {
    return {
      ok: false,
      positions: [],
      meta: {},
      errors: ['No holdings found. Expected a JSON array, or an object with a "positions" array.'],
    }
  }
  if (!rows.length) {
    return { ok: false, positions: [], meta: {}, errors: ['The file contains no holdings.'] }
  }

  const errors = []
  const positions = []
  rows.forEach((row, index) => {
    const parsed = readPosition(row, index)
    errors.push(...parsed.errors)
    if (parsed.position) positions.push(parsed.position)
  })

  // A duplicated ticker cannot be reconciled: the two rows disagree about one holding, and
  // silently keeping either would import a portfolio the file does not describe.
  const seen = new Map()
  positions.forEach((position) => {
    seen.set(position.ticker, (seen.get(position.ticker) || 0) + 1)
  })
  const duplicates = [...seen].filter(([, count]) => count > 1).map(([ticker]) => ticker)
  if (duplicates.length) {
    errors.push(`Repeated ticker${duplicates.length === 1 ? '' : 's'}: ${duplicates.join(', ')}. `
      + 'Combine each holding into one row.')
  }

  const undated = positions.filter((position) => !position.purchaseDate).map((row) => row.ticker)
  const warnings = undated.length
    ? [`No purchase date on ${undated.join(', ')} — since-purchase measures stay unavailable for `
      + `${undated.length === 1 ? 'it' : 'them'} until one is set.`]
    : []

  return {
    ok: errors.length === 0,
    errors,
    warnings,
    positions,
    meta: {
      source: typeof raw?.source === 'string' ? raw.source : null,
      recordedAt: typeof raw?.recordedAt === 'string' ? raw.recordedAt : null,
      schemaVersion: Number(raw?.schemaVersion) || null,
      count: positions.length,
      costBasisTotal: round(positions.reduce((sum, row) => sum + row.costBasisTotal, 0)),
      marketValue: positions.every((row) => row.snapshotValue != null)
        ? round(positions.reduce((sum, row) => sum + row.snapshotValue, 0))
        : null,
    },
  }
}

/**
 * What importing these holdings would do to the stored portfolio.
 *
 * `replace` treats the file as the whole portfolio, exactly as the brokerage baseline import
 * does: holdings absent from it are removed. `merge` only adds and updates, which is the
 * right mode for a file covering part of an account. The distinction matters enough that the
 * UI asks rather than assuming, since one of them deletes.
 */
export function planPortfolioImport(existing = [], parsed, mode = 'replace') {
  if (!parsed?.ok) return []
  const operations = planReferencePortfolioSync(existing, parsed.positions)
  return mode === 'merge' ? operations.filter((operation) => operation.kind !== 'remove') : operations
}

/** The file this app writes, and the shape `parsePortfolioImport` is happiest reading back. */
export function buildPortfolioExport(positions = [], meta = {}) {
  return {
    schemaVersion: IMPORT_SCHEMA_VERSION,
    source: meta.source || 'ValueSignal portfolio export',
    recordedAt: meta.recordedAt || new Date().toISOString(),
    positions: positions.map((position) => ({
      ticker: position.ticker,
      shares: position.shares,
      costBasisTotal: finite(position.costBasisTotal)
        ? Number(position.costBasisTotal)
        : round(Number(position.shares) * Number(position.costBasis)),
      purchaseDate: position.purchaseDate || '',
      ...(finite(position.snapshotPrice) ? { price: Number(position.snapshotPrice) } : {}),
      ...(finite(position.snapshotValue) ? { value: Number(position.snapshotValue) } : {}),
    })),
  }
}
