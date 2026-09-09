#!/usr/bin/env node
// Applies the Fidelity reference portfolio (src/lib/referencePortfolio.js) straight to
// Firestore, without waiting for the signed-in app to run its own sync.
//
// The app already reconciles on sign-in once per REFERENCE_PORTFOLIO_VERSION. This exists for
// the cases that cannot wait on a browser: seeding a fresh account, repairing one whose
// holdings drifted, or pushing a freshly exported baseline and confirming what it changed
// before it reaches the UI. Both paths share planReferencePortfolioSync and the record
// builders beside it, so they write byte-identical documents and cannot drift.
//
// Two ways to authenticate, picked automatically:
//
//   - SIGN-IN (default when no service account is configured). Signs in as the account with
//     its own app password, using the VITE_FIREBASE_* client config already in .env.local for
//     `npm run dev`. Nothing new to configure, and writes go through firestore.rules exactly
//     as the browser's would -- the rules grant a signed-in user their own portfolios/{uid}.
//     The password is prompted for, or read from PORTFOLIO_SYNC_PASSWORD; it is never taken
//     as a flag, which would leave it in shell history.
//   - ADMIN, when FIREBASE_SERVICE_ACCOUNT_JSON is set. Needs no password and can sync any
//     account by uid, but bypasses firestore.rules by design -- a server-side secret.
//
// Usage:
//   npm run portfolio:sync -- --email you@example.com
//   npm run portfolio:sync -- --email you@example.com --commit
//   npm run portfolio:sync -- --email you@example.com --report portfolio-check.md
//   npm run portfolio:sync -- --uid abc123 --commit          # admin credentials only
//
// Dry run is the DEFAULT and prints the full plan. Nothing is written until --commit, and a
// plain --commit only SEEDS: the export is a photograph of Aug 25 and the stored portfolio is
// the record, so it adds holdings the account has never been given and fills blank purchase
// dates, but never restates or deletes. --authoritative opts into the old behaviour, where a
// holding absent from the export is deleted.
//
// Requires FIREBASE_SERVICE_ACCOUNT_JSON (see .env.example) -- the same service-account
// credential netlify/functions/alert-push.mjs uses. It bypasses firestore.rules by design,
// so it is a server-side secret and must never be given a VITE_ prefix.

import { writeFile } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'
import {
  BATCH_LIMIT,
  connectPortfolioBackend,
  step,
  withTimeout,
} from './lib/portfolio-firestore-backend.mjs'

// Re-exported for scripts/sync-portfolio-firebase.test.mjs, which predates the shared backend
// module and tests this utility directly rather than through connectPortfolioBackend.
export { withTimeout }
import {
  planReferencePortfolioSync,
  referenceSyncMerges,
  seededTickersAfter,
  seededTickersFromTrackingState,
  referenceIntradaySnapshot,
  referenceSyncDrift,
  referenceSyncRecord,
  referenceTrackingState,
  summarizeReferenceSync,
  verifyReferencePortfolio,
  REFERENCE_PORTFOLIO,
  REFERENCE_PORTFOLIO_EXPECTED,
  REFERENCE_PORTFOLIO_RECORDED_AT,
  REFERENCE_PORTFOLIO_VERSION,
} from '../src/lib/referencePortfolio.js'

export function parseArguments(argv) {
  const options = { commit: false, authoritative: false, email: null, uid: null, report: null }
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index]
    if (argument === '--commit') options.commit = true
    else if (argument === '--authoritative') options.authoritative = true
    else if (argument === '--help' || argument === '-h') options.help = true
    else if (argument === '--email') options.email = argv[index += 1]
    else if (argument === '--uid') options.uid = argv[index += 1]
    else if (argument === '--report') options.report = argv[index += 1]
    else throw new Error(`Unrecognized argument: ${argument}`)
  }
  if (!options.help && !options.email && !options.uid) {
    throw new Error('Pass --email <address> or --uid <id> to name the account to sync.')
  }
  if (options.email && options.uid) {
    throw new Error('Pass either --email or --uid, not both.')
  }
  if (options.report === undefined || options.report === '') {
    throw new Error('--report needs a file path, or - for stdout.')
  }
  return options
}

const money = (value) => `$${value.toFixed(2)}`
const pad = (value, width) => String(value).padEnd(width)

export function describe(operations) {
  const order = { add: 0, update: 1, remove: 2 }
  const symbol = { add: '+', update: '~', remove: '-' }
  return [...operations]
    .sort((left, right) => order[left.kind] - order[right.kind]
      || String(left.record.ticker).localeCompare(String(right.record.ticker)))
    .map((operation) => {
      const { ticker, shares, costBasisTotal, costBasis, purchaseDate } = operation.record
      const cost = Number.isFinite(costBasisTotal) ? costBasisTotal : Number(shares) * Number(costBasis)
      const dated = purchaseDate || 'undated'
      return operation.kind === 'remove'
        ? `  ${symbol.remove} ${pad(ticker, 6)} removed (not in the export)`
        : `  ${symbol[operation.kind]} ${pad(ticker, 6)} ${pad(shares, 8)} sh  ${pad(money(cost), 10)} ${dated}`
    })
    .join('\n')
}

const ACTIONS = { add: 'add', update: 'update', remove: 'remove' }

const shown = (value) => (value === null ? '(none)' : value)
const driftText = (drift) => drift
  .map((change) => `${change.field}: ${shown(change.from)} → ${shown(change.to)}`)
  .join('; ')

/**
 * The verification report. It answers two separate questions that are easy to conflate:
 * whether the shipped baseline is CORRECT (its rows still reconcile to the brokerage figures
 * they were transcribed from) and whether the account is UPDATED (Firestore already holds
 * that baseline, or what a sync would change). A row-by-row table plus the drift list makes
 * both checkable against a statement without reading any code.
 */
export function buildReport({ uid, email, operations, committed, generatedAt }) {
  const checks = verifyReferencePortfolio()
  const counts = summarizeReferenceSync(operations)
  const rows = operations
    .filter((operation) => operation.kind !== 'remove')
    .map((operation) => {
      const drift = referenceSyncDrift(operation)
      return {
        ticker: operation.record.ticker,
        shares: operation.record.shares,
        costBasisTotal: operation.record.costBasisTotal,
        snapshotPrice: operation.record.snapshotPrice,
        snapshotValue: operation.record.snapshotValue,
        purchaseDate: operation.record.purchaseDate || null,
        action: operation.kind === 'add' ? ACTIONS.add : drift.length ? ACTIONS.update : 'unchanged',
        drift,
      }
    })
    .sort((left, right) => left.ticker.localeCompare(right.ticker))
  const removals = operations.filter((operation) => operation.kind === 'remove')
  const changed = rows.filter((row) => row.action !== 'unchanged')
  return {
    generatedAt,
    account: { uid, email: email || null },
    baseline: {
      version: REFERENCE_PORTFOLIO_VERSION,
      pricesObservedAt: REFERENCE_PORTFOLIO_RECORDED_AT,
      holdings: REFERENCE_PORTFOLIO.length,
    },
    brokerage: REFERENCE_PORTFOLIO_EXPECTED,
    checks,
    correct: checks.every((check) => check.ok),
    inSync: changed.length === 0 && removals.length === 0,
    committed,
    counts,
    rows,
    removals: removals.map((operation) => ({ ticker: operation.record.ticker, id: operation.id })),
  }
}

export function renderReportMarkdown(report) {
  const mark = (ok) => (ok ? '✅' : '❌')
  const dollars = (value) => (Number.isFinite(value) ? `$${value.toFixed(2)}` : '—')
  const lines = []

  lines.push('# Portfolio baseline verification', '')
  lines.push(`- **Generated** ${report.generatedAt}`)
  lines.push(`- **Account** \`${report.account.uid}\`${report.account.email ? ` (${report.account.email})` : ''}`)
  lines.push(`- **Baseline** \`${report.baseline.version}\``)
  lines.push(`- **Prices observed** ${report.baseline.pricesObservedAt} — this is when prices were read, not a purchase date`)
  lines.push(`- **Mode** ${report.committed ? 'committed — Firestore was written' : 'dry run — nothing written'}`)
  lines.push('')
  lines.push(`## ${mark(report.correct)} Baseline ${report.correct ? 'reconciles to the brokerage' : 'does NOT reconcile — see failures below'}`)
  lines.push('')
  lines.push('Each row of the baseline checked against the figures transcribed from the Fidelity account summary.', '')
  lines.push('| | Check | Detail |', '|---|---|---|')
  report.checks.forEach((check) => lines.push(`| ${mark(check.ok)} | ${check.name} | ${check.detail} |`))
  lines.push('')
  lines.push(`## ${mark(report.inSync)} Account ${report.inSync ? 'already matches this baseline' : 'is out of date'}`)
  lines.push('')
  lines.push(`${report.counts.added} to add · ${report.counts.updated} already stored · ${report.counts.removed} to remove`)
  lines.push('')

  if (report.inSync) {
    lines.push('Every stored holding already matches the baseline. A sync would change nothing.', '')
  } else {
    lines.push('### What a sync would change', '')
    lines.push('| Ticker | Action | Change |', '|---|---|---|')
    report.rows.filter((row) => row.action !== 'unchanged').forEach((row) => {
      lines.push(`| ${row.ticker} | ${row.action} | ${row.action === 'add' ? 'new holding' : driftText(row.drift)} |`)
    })
    report.removals.forEach((row) => lines.push(`| ${row.ticker} | remove | not present in the export |`))
    lines.push('')
  }

  lines.push('## Holdings', '')
  lines.push('| Ticker | Shares | Cost basis | Price | Value | Bought | State |', '|---|---:|---:|---:|---:|---|---|')
  report.rows.forEach((row) => {
    lines.push(`| ${row.ticker} | ${row.shares} | ${dollars(row.costBasisTotal)} | ${dollars(row.snapshotPrice)} `
      + `| ${dollars(row.snapshotValue)} | ${row.purchaseDate || '—'} | ${row.action} |`)
  })
  const cost = report.rows.reduce((sum, row) => sum + (row.costBasisTotal || 0), 0)
  const value = report.rows.reduce((sum, row) => sum + (row.snapshotValue || 0), 0)
  lines.push(`| **Total** | | **${dollars(cost)}** | | **${dollars(value)}** | | ${report.rows.length} holdings |`)
  lines.push('')
  lines.push(`Money market (FZFXX, not tracked): ${dollars(report.brokerage.moneyMarketValue)} · `
    + `account total per Fidelity: **${dollars(report.brokerage.accountTotal)}**`)
  lines.push('')
  const undated = report.rows.filter((row) => !row.purchaseDate)
  if (undated.length) {
    lines.push(`Undated holdings — no buy in the supplied transaction history, so since-purchase `
      + `measures stay unavailable for them: **${undated.map((row) => row.ticker).join(', ')}**`, '')
  }
  return lines.join('\n')
}

async function emitReport(options, { uid, operations, committed }) {
  if (!options.report) return
  const report = buildReport({
    uid,
    email: options.email,
    operations,
    committed,
    generatedAt: new Date().toISOString(),
  })
  const asJson = options.report !== '-' && options.report.endsWith('.json')
  const body = asJson ? `${JSON.stringify(report, null, 2)}\n` : `${renderReportMarkdown(report)}\n`
  if (options.report === '-') {
    console.log(`\n${body}`)
    return
  }
  await writeFile(options.report, body, 'utf8')
  console.log(`\nReport written to ${options.report}`
    + ` — baseline ${report.correct ? 'reconciles' : 'DOES NOT reconcile'},`
    + ` account ${report.inSync ? 'already matches' : 'out of date'}.`)
}

export async function main() {
  const options = parseArguments(process.argv.slice(2))
  if (options.help) {
    console.log(`sync-portfolio-firebase — apply the Fidelity reference portfolio to Firestore

  --email <address>   account to sync, resolved to a uid via Firebase Auth
  --uid <id>          account to sync, by uid
  --commit            actually write (default is a dry run that writes nothing)
  --authoritative     let the export overwrite and delete stored holdings. Off by default:
                      the export is a photograph of Aug 25 and Firestore is the record, so a
                      plain run only adds holdings the account has never been given. The
                      report always shows full drift either way.
  --report <path>     write a verification report (.md or .json; - for stdout)
  --help              this message

Credentials, picked automatically:
  sign-in   VITE_FIREBASE_* in .env.local (what \`npm run dev\` uses) plus the account
            password — prompted for, or read from PORTFOLIO_SYNC_PASSWORD
  admin     FIREBASE_SERVICE_ACCOUNT_JSON, if set; needed for --uid

Reference baseline: ${REFERENCE_PORTFOLIO_VERSION} (${REFERENCE_PORTFOLIO.length} holdings)`)
    return
  }

  step(`sync-portfolio-firebase · baseline ${REFERENCE_PORTFOLIO_VERSION} · ${REFERENCE_PORTFOLIO.length} holdings`)
  const backend = await connectPortfolioBackend(options)
  try {
    return await run(options, backend)
  } finally {
    await backend.close()
  }
}

async function run(options, backend) {
  const { uid } = backend

  console.log(`Account: ${uid}${options.email ? ` (${options.email})` : ''} · ${backend.mode} credentials\n`)

  step('Reading stored positions from Firestore…')
  const existing = await backend.readPositions()
  console.log(`Currently stored: ${existing.length} position${existing.length === 1 ? '' : 's'}`)

  // Tickers the account has sold out of since the export was taken. The export still lists
  // them -- it is a photograph of Aug 25 -- and re-adding them here would undo a recorded
  // sale, the same way the in-app sync used to. Same ledger the app writes.
  const closedTickers = (await backend.readClosedTickers?.()) || []
  if (closedTickers.length) {
    console.log(`Sold since the export, left alone: ${closedTickers.join(', ')}`)
  }

  // Two plans, on purpose. `drift` answers "how does this account differ from the Aug 25
  // statement", which is the report's whole job and stays worth seeing. `operations` is what
  // would actually be written, and unless --authoritative is passed that is seeding only:
  // additions the account has never been given, plus purchase-date backfills. Firestore is
  // the record; the statement is history.
  const seededTickers = seededTickersFromTrackingState(await backend.readTrackingState?.())
  const drift = planReferencePortfolioSync(existing, undefined, { closedTickers })
  const operations = options.authoritative
    ? drift
    : planReferencePortfolioSync(existing, undefined, { closedTickers, seededTickers, mode: 'seed' })
  const counts = summarizeReferenceSync(operations)
  const snapshot = referenceIntradaySnapshot()
  const writes = operations.length + 2

  console.log(options.authoritative
    ? `Plan (--authoritative): ${counts.added} added · ${counts.updated} updated · ${counts.removed} removed\n`
    : `Plan (seed only): ${counts.added} added · ${counts.updated} purchase date(s) filled · nothing overwritten or removed\n`)
  console.log(describe(operations))
  if (!options.authoritative) {
    const suppressed = drift.filter((operation) => operation.kind !== 'add'
      && (operation.kind === 'remove' || referenceSyncDrift(operation).length))
    if (suppressed.length) {
      console.log(`\n${suppressed.length} difference(s) from the statement left alone, because `
        + 'the stored portfolio is the record. Pass --authoritative to overwrite them:')
      console.log(describe(suppressed))
    }
  }

  const closedSet = new Set(closedTickers.map((ticker) => String(ticker).trim().toUpperCase()))
  const applied = REFERENCE_PORTFOLIO.filter((position) => !closedSet.has(position.ticker))
  const invested = applied.reduce((sum, position) => sum + position.snapshotValue, 0)
  const cost = applied.reduce((sum, position) => sum + position.costBasisTotal, 0)
  const undated = applied.filter((position) => !position.purchaseDate)
  console.log(`\nAfter this sync: ${applied.length} holdings · ${money(cost)} cost · ${money(invested)} value`)
  if (undated.length) {
    console.log(`Undated holdings (no buy in the transaction history): ${undated.map((position) => position.ticker).join(', ')}`)
  }

  if (writes > BATCH_LIMIT) {
    throw new Error(`Plan needs ${writes} writes, over Firestore's ${BATCH_LIMIT}-write batch limit.`)
  }

  if (!options.commit) {
    await emitReport(options, { uid, operations, committed: false })
    console.log('\nDry run — nothing written. Re-run with --commit to apply.')
    if (counts.removed) {
      console.log(`Note: --commit --authoritative deletes ${counts.removed} stored holding${counts.removed === 1 ? '' : 's'} absent from the export.`)
    }
    return
  }

  const importedAt = new Date().toISOString()
  step(`Committing ${writes} writes…`)
  await backend.commit((batch) => {
    operations.forEach((operation) => {
      const positionRef = batch.positionDoc(operation.id)
      if (operation.kind === 'remove') {
        batch.delete(positionRef)
        return
      }
      batch.set(positionRef, referenceSyncRecord(operation, importedAt), referenceSyncMerges(operation))
    })
    batch.set(batch.snapshotDoc(snapshot.id), snapshot.document, true)
    batch.set(batch.trackingDoc(), referenceTrackingState(importedAt, seededTickersAfter(operations, seededTickers)), true)
  })

  console.log(`\nCommitted ${writes} writes at ${importedAt}.`)
  console.log(`Account marked as reconciled to ${REFERENCE_PORTFOLIO_VERSION}; the app will not re-run its own sync for this version.`)
  // Reported against the pre-commit plan, so the drift section says what this run changed.
  await emitReport(options, { uid, operations, committed: true })
}

// Guarded so the module can be imported for testing without running a sync.
const invokedDirectly = process.argv[1]
  && import.meta.url === pathToFileURL(process.argv[1]).href
if (invokedDirectly) {
  main()
    .catch((error) => {
      console.error(`\nsync-portfolio-firebase failed: ${error.message}`)
      process.exitCode = 1
    })
    .finally(() => {
      // Backstop: if a stray handle still holds the loop open, leave with the status we set
      // rather than appearing to hang after the work is visibly finished.
      const exit = setTimeout(() => process.exit(process.exitCode ?? 0), 2000)
      exit.unref?.()
    })
}
