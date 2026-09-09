#!/usr/bin/env node
// Corrects the daily account-value snapshots (Firestore `intradaySnapshots`) that were saved
// while the account held the wrong things -- LULU wrongly present after it was sold, TSM
// wrongly absent because it was never entered into the app at all. This is what makes
// historical performance measures (Sharpe, the reconciliation bridge, money- and time-weighted
// return) agree with reality for date ranges spanning the bug, not just the account's current
// state.
//
// It never rewrites a snapshot blindly. For each one it asks two questions in order:
//
//   1. What SHOULD this account have held on this date? Answered by replaying a full
//      chronological event history (--history) on top of a starting baseline, entirely
//      independent of what the buggy snapshot itself says.
//   2. Does the snapshot already agree? If yes, it is left untouched. If not, the correction
//      is made using the most precise price available: the app's OWN recorded price for a
//      ticker that was wrongly included (scripts/lib/portfolio-snapshot-correction.mjs), and a
//      historical closing price (from public/data/report.json) only for a ticker that was
//      wrongly excluded and so was never priced by the app at all -- always labelled as an
//      estimate where that happens.
//
// A snapshot with no per-ticker prices at all (recorded before that was captured) cannot be
// surgically corrected -- there is nothing to tell "wrongly included" apart from "correctly
// included, just not itemized." Those are reported and skipped unless --allow-estimates is
// passed, which reconstructs the total from historical closes alone for every held ticker: a
// real but lower-precision number, always marked `estimated: true` in what gets written.
//
// The original value is never discarded: every corrected document keeps `originalValue` and
// `originalUnrealizedGain` alongside the corrected ones, plus the exact per-ticker changes that
// produced the correction, so this is auditable after the fact -- see `npm run portfolio:audit`.
// Idempotent: a snapshot already carrying `correctedAt` is skipped on a later run unless
// --force is passed.
//
// Usage:
//   npm run portfolio:rebuild-snapshots -- --email you@example.com --history scripts/fixtures/fidelity-activity-since-seed.json
//   npm run portfolio:rebuild-snapshots -- --email you@example.com --history <file> --commit
//   npm run portfolio:rebuild-snapshots -- --email you@example.com --history <file> --commit --allow-estimates
//
// Dry run is the default.

import { readFile } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'
import { BATCH_LIMIT, connectPortfolioBackend, requireAccountSelection, step } from './lib/portfolio-firestore-backend.mjs'
import { holdingsAsOf, positionTimeline } from './lib/portfolio-timeline.mjs'
import { planFullReconstruction, planSnapshotCorrection } from './lib/portfolio-snapshot-correction.mjs'
import { buildPortfolioPriceData } from '../src/lib/portfolioPosition.js'
import { REFERENCE_PORTFOLIO, REFERENCE_PORTFOLIO_RECORDED_AT } from '../src/lib/referencePortfolio.js'

const REPORT_PATH = 'public/data/report.json'

// The bug this script exists for -- a wrongly-resurrected position, a real buy never entered
// into the app -- could only ever corrupt a snapshot dated on or after the Aug 25 export,
// since that export (and the sync it drives) is the earliest thing that could have caused it.
// So the baseline is REFERENCE_PORTFOLIO itself: exact, known share counts as of that date,
// not a reconstruction from Fidelity's activity log, which gives dollar amounts per fill but
// not always share counts -- fine for validating cost-basis totals (already done, see
// docs/PLAN-TRADE-LEDGER.md) but not precise enough to replay share-by-share before Aug 25.
// `--history` is therefore the events *since* that date -- see
// scripts/fixtures/fidelity-activity-since-seed.json -- not the full multi-year trading
// history. A snapshot dated before Aug 25 is left alone entirely; there is nothing this bug
// could have done to it.
const BASELINE_CUTOFF = REFERENCE_PORTFOLIO_RECORDED_AT.slice(0, 10)

export function parseArguments(argv) {
  const options = { commit: false, allowEstimates: false, force: false, email: null, uid: null, history: null, report: null, help: false }
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index]
    if (argument === '--commit') options.commit = true
    else if (argument === '--allow-estimates') options.allowEstimates = true
    else if (argument === '--force') options.force = true
    else if (argument === '--email') options.email = argv[index += 1]
    else if (argument === '--uid') options.uid = argv[index += 1]
    else if (argument === '--history') options.history = argv[index += 1]
    else if (argument === '--report-path') options.report = argv[index += 1]
    else if (argument === '--help' || argument === '-h') options.help = true
    else throw new Error(`Unrecognized argument: ${argument}`)
  }
  if (!options.help) {
    requireAccountSelection(options)
    if (!options.history) throw new Error('Pass --history <file> naming the buy/sell events since the Aug 25 export to replay.')
  }
  return options
}

/**
 * Every ticker's `{ dates, closes }` history, merged the same way the app itself resolves a
 * price (research > portfolio_coverage > screen_universe, later entries winning on conflict).
 */
export function buildPriceHistoryMap(reportJson) {
  const merged = buildPortfolioPriceData(
    reportJson?.screen_universe || [], reportJson?.portfolio_coverage || [], reportJson?.research || [],
  )
  const map = new Map()
  for (const [ticker, row] of Object.entries(merged)) {
    if (row?.history?.dates?.length) map.set(ticker, { dates: row.history.dates, closes: row.history.closes })
  }
  return map
}

/** The account's exact holdings as of the Aug 25 export -- see BASELINE_CUTOFF above. */
export function buildBaseline() {
  return REFERENCE_PORTFOLIO.map((position, index) => ({
    id: `${position.ticker}-reference-${index}`,
    ticker: position.ticker,
    shares: position.shares,
    costBasis: position.costBasis,
  }))
}

/**
 * Applies a correction's per-ticker changes onto a snapshot's own `prices` array, so the
 * corrected document is internally consistent -- a wrongly-included ticker is removed from it,
 * not just netted out of the total; a wrongly-excluded one is added with the price used.
 */
export function correctedPricesArray(originalPrices, changes, marketTime) {
  const byTicker = new Map((originalPrices || []).map((row) => [String(row.ticker).toUpperCase(), { ...row }]))
  for (const change of changes) {
    if (change.action === 'remove') byTicker.delete(change.ticker)
    else if (change.action === 'add' || change.action === 'reconstructed') {
      byTicker.set(change.ticker, { ticker: change.ticker, shares: change.shares, price: change.price, value: change.shares * change.price, previousClose: null, marketTime, estimated: true })
    } else if (change.action === 'adjust') {
      const existing = byTicker.get(change.ticker) || { ticker: change.ticker, price: change.price }
      byTicker.set(change.ticker, { ...existing, shares: change.to, value: change.to * change.price })
    }
  }
  return [...byTicker.values()]
}

const money = (value) => `${Number(value) < 0 ? '−' : ''}$${Math.abs(Number(value)).toFixed(2)}`

function printCorrection(snapshot, result) {
  const date = snapshot.marketDate || String(snapshot.recordedAt || '').slice(0, 10)
  console.log(`\n${date}  (${snapshot.id})  ${result.estimated ? '[ESTIMATED — no per-ticker prices recorded]' : ''}`)
  result.changes.forEach((change) => {
    if (change.action === 'remove') console.log(`  - ${change.ticker}: remove ${change.shares} sh @ ${money(change.price)} (was wrongly held)`)
    else if (change.action === 'add') console.log(`  + ${change.ticker}: add ${change.shares} sh @ ${money(change.price)} [historical close] (was wrongly missing)`)
    else if (change.action === 'reconstructed') console.log(`  = ${change.ticker}: ${change.shares} sh @ ${money(change.price)} [historical close]`)
    else console.log(`  ~ ${change.ticker}: ${change.from} → ${change.to} sh @ ${money(change.price)}`)
  })
  console.log(`  Total: ${money(result.originalValue)} → ${money(result.correctedValue)}  (${result.delta != null ? (result.delta >= 0 ? '+' : '') + money(result.delta) : 'reconstructed'})`)
}

export async function main() {
  const options = parseArguments(process.argv.slice(2))
  if (options.help) {
    console.log(`rebuild-portfolio-snapshots — correct daily account-value snapshots recorded while the account was wrong

  --email <address>    account to correct, resolved to a uid via Firebase Auth
  --uid <id>            account to correct, by uid
  --history <path>      JSON file of buy/sell events *since* the Aug 25 export -- e.g.
                        scripts/fixtures/fidelity-activity-since-seed.json. Only snapshots
                        dated on or after that export are ever corrected.
  --commit              actually write (default is a dry run that writes nothing)
  --allow-estimates      also correct snapshots with no per-ticker prices at all, using a full
                        reconstruction from historical closes (lower precision, always marked
                        estimated: true)
  --force                re-correct a snapshot that already carries a previous correction
  --help                 this message

Never destroys the original value: every corrected document keeps originalValue and
originalUnrealizedGain alongside the corrected numbers.`)
    return
  }

  step('rebuild-portfolio-snapshots')
  const reportJson = JSON.parse(await readFile(REPORT_PATH, 'utf8'))
  const priceHistory = buildPriceHistoryMap(reportJson)
  console.log(`Loaded price history for ${priceHistory.size} tickers from ${REPORT_PATH}`)

  const historyFile = JSON.parse(await readFile(options.history, 'utf8'))
  const events = Array.isArray(historyFile) ? historyFile : historyFile.events || []
  const baseline = buildBaseline()
  const timeline = positionTimeline(baseline, events)
  console.log(`Replaying ${events.length} event(s) since the ${BASELINE_CUTOFF} export on its exact ${baseline.length}-position baseline`)

  const backend = await connectPortfolioBackend(options)
  try {
    console.log(`Account: ${backend.uid}${options.email ? ` (${options.email})` : ''} · ${backend.mode} credentials\n`)

    step('Reading recorded snapshots…')
    const snapshots = (await backend.readSnapshots()).sort((left, right) => String(left.recordedAt || '').localeCompare(String(right.recordedAt || '')))
    console.log(`${snapshots.length} recorded snapshot(s)`)

    let corrected = 0
    let clean = 0
    let alreadyCorrected = 0
    let blocked = 0
    const writes = []

    let beforeCutoff = 0
    for (const snapshot of snapshots) {
      const date = snapshot.marketDate || String(snapshot.recordedAt || '').slice(0, 10)
      // Nothing before the export could have been touched by this bug -- see BASELINE_CUTOFF.
      if (date < BASELINE_CUTOFF) { beforeCutoff += 1; continue }
      if (snapshot.correctedAt && !options.force) { alreadyCorrected += 1; continue }
      const correctHoldings = holdingsAsOf(timeline, date)

      let result = planSnapshotCorrection(snapshot, correctHoldings, priceHistory)
      if (result === null) { clean += 1; continue }
      if (result.blocked && result.mode === 'no_prices' && options.allowEstimates) {
        result = planFullReconstruction(snapshot, correctHoldings, priceHistory)
      }
      if (result.blocked) {
        blocked += 1
        console.log(`\n${date} (${snapshot.id}): BLOCKED`)
        result.blockers.forEach((blocker) => console.log(`  ✗ ${blocker}`))
        continue
      }

      corrected += 1
      printCorrection(snapshot, result)
      writes.push({
        id: snapshot.id,
        data: {
          value: result.correctedValue,
          unrealizedGain: result.correctedUnrealizedGain,
          originalValue: result.originalValue,
          originalUnrealizedGain: result.originalUnrealizedGain,
          prices: correctedPricesArray(snapshot.prices, result.changes, snapshot.recordedAt),
          correctedAt: new Date().toISOString(),
          correctionMode: result.mode,
          correctionChanges: result.changes,
        },
      })
    }

    console.log(`\n${'='.repeat(60)}`)
    console.log(`${corrected} corrected · ${clean} already correct · ${alreadyCorrected} previously corrected (skipped) `
      + `· ${blocked} blocked · ${beforeCutoff} before ${BASELINE_CUTOFF} (not in scope)`)

    if (!writes.length) {
      console.log(corrected === 0 && blocked === 0 ? '\nNothing to correct.' : '\nNo writes to make.')
      return
    }
    if (writes.length > BATCH_LIMIT) {
      throw new Error(`${writes.length} corrections exceed Firestore's ${BATCH_LIMIT}-write batch limit. Run in smaller date ranges.`)
    }
    if (!options.commit) {
      console.log('\nDry run — nothing written. Re-run with --commit to apply.')
      return
    }

    step(`Committing ${writes.length} corrections…`)
    await backend.commit((batch) => {
      writes.forEach((write) => batch.set(batch.snapshotDoc(write.id), write.data, true))
    })
    console.log(`\nCommitted ${writes.length} corrections.`)
  } finally {
    await backend.close()
  }
}

const invokedDirectly = process.argv[1]
  && import.meta.url === pathToFileURL(process.argv[1]).href
if (invokedDirectly) {
  main()
    .catch((error) => {
      console.error(`\nrebuild-portfolio-snapshots failed: ${error.message}`)
      process.exitCode = 1
    })
    .finally(() => {
      const exit = setTimeout(() => process.exit(process.exitCode ?? 0), 2000)
      exit.unref?.()
    })
}
