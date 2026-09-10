#!/usr/bin/env node
// Applies a dated list of real brokerage events (buys, sells, deposits, dividends) to an
// account's Firestore ledger, through the exact same primitives the app itself uses. This is
// WP2 of docs/PLAN-TRADE-LEDGER.md -- it exists because the account drifted from what Fidelity
// actually shows (a sale resurrected by a sync bug, real trades since the Aug 25 seed export
// never entered into Dash), and the fix is to replay what really happened, not to hand-edit
// documents.
//
// Money-market lines (FZFXX, SPAXX) are never events here -- tracked NAV is invested holdings
// only, matching the rule the Aug 25 export and the rest of this app already follow.
//
// Idempotent: every write carries a deterministic id, so re-running the same input file (or a
// superset of it) against an account that already has some of these events applied writes only
// what is actually missing. See scripts/lib/portfolio-reconciliation.mjs.
//
// Usage:
//   npm run portfolio:reconcile -- --email you@example.com --input scripts/fixtures/fidelity-activity-since-seed.json
//   npm run portfolio:reconcile -- --email you@example.com --input <file> --commit
//   npm run portfolio:reconcile -- --email you@example.com --input <file> --commit --verify scripts/fixtures/fidelity-positions-2026-09-09.json
//
// Dry run is the default. Nothing is written until --commit. --verify runs the read-only audit
// statement check (scripts/lib/portfolio-audit.mjs) against stored positions immediately after
// a commit, and exits 1 if they do not match -- so a reconciliation that silently missed
// something is never reported as a plain success.

import { readFile } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'
import { BATCH_LIMIT, connectPortfolioBackend, requireAccountSelection, step } from './lib/portfolio-firestore-backend.mjs'
import { eventActivityIds, planActivityReconciliation } from './lib/portfolio-reconciliation.mjs'
import { diffAgainstStatement } from './lib/portfolio-audit.mjs'

export function parseArguments(argv) {
  const options = { commit: false, email: null, uid: null, input: null, verify: null, help: false }
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index]
    if (argument === '--commit') options.commit = true
    else if (argument === '--email') options.email = argv[index += 1]
    else if (argument === '--uid') options.uid = argv[index += 1]
    else if (argument === '--input') options.input = argv[index += 1]
    else if (argument === '--verify') options.verify = argv[index += 1]
    else if (argument === '--help' || argument === '-h') options.help = true
    else throw new Error(`Unrecognized argument: ${argument}`)
  }
  if (!options.help) {
    requireAccountSelection(options)
    if (!options.input) throw new Error('Pass --input <events.json> naming the events to apply.')
  }
  return options
}

const money = (value) => `$${Number(value).toFixed(2)}`

export function printPlan({ writes, errors, skipped, summary }) {
  console.log(`\nPlan: ${summary.buy || 0} buy · ${summary.sell || 0} sell · ${summary.deposit || 0} deposit `
    + `· ${summary.withdrawal || 0} withdrawal · ${summary.dividend || 0} dividend · ${summary.skipped} already recorded (skipped)\n`)

  if (skipped.length) {
    console.log('Already recorded, left alone:')
    skipped.forEach(({ event }) => console.log(`  = ${event.date} ${event.kind} ${event.ticker || ''} ${event.amount ?? event.cost ?? event.proceeds ?? ''}`.trimEnd()))
    console.log('')
  }

  const byCollection = { positions: [], activity: [], closedPositions: [] }
  writes.forEach((write) => byCollection[write.collection]?.push(write))

  if (byCollection.positions.length) {
    console.log('Position changes:')
    byCollection.positions.forEach((write) => {
      if (write.op === 'delete') console.log(`  - ${write.id} removed`)
      // A depleted-but-not-closed lot from a sell writes only { shares: remaining } -- no
      // ticker field, since the position already exists. A new lot from a buy always carries
      // one, so presence of `ticker` is what actually distinguishes the two, not key count.
      else if (write.data.ticker) console.log(`  + ${write.id} ${write.data.ticker} ${write.data.shares} sh, cost ${money(write.data.shares * write.data.costBasis)}`)
      else console.log(`  ~ ${write.id} shares -> ${write.data.shares}`)
    })
    console.log('')
  }

  if (byCollection.closedPositions.length) {
    console.log('Closed positions:')
    byCollection.closedPositions.forEach((write) => {
      console.log(write.op === 'delete'
        ? `  - ${write.id} closed-marker cleared (re-bought)`
        : `  + ${write.id} closed ${write.data.saleDate}, realized ${money(write.data.realizedGain)}`)
    })
    console.log('')
  }

  if (byCollection.activity.length) {
    console.log('Activity rows:')
    byCollection.activity.forEach((write) => {
      const row = write.data
      console.log(`  + ${row.effectiveDate}  ${row.type.padEnd(16)} ${(row.ticker || '').padEnd(6)} ${money(row.amount)}`)
    })
    console.log('')
  }

  const realizedTotal = byCollection.activity
    .filter((write) => write.data.type === 'realized_gain')
    .reduce((sum, write) => sum + write.data.amount, 0)
  if (byCollection.activity.some((write) => write.data.type === 'realized_gain')) {
    console.log(`Total realized gain/loss in this plan: ${realizedTotal >= 0 ? '+' : '−'}${money(Math.abs(realizedTotal))}\n`)
  }

  if (errors.length) {
    console.log('ERRORS — these events were not planned and need attention before committing:')
    errors.forEach((error) => console.log(`  ✗ ${error}`))
    console.log('')
  }
}

export async function main() {
  const options = parseArguments(process.argv.slice(2))
  if (options.help) {
    console.log(`reconcile-portfolio-activity — apply real brokerage events to Firestore

  --email <address>   account to reconcile, resolved to a uid via Firebase Auth
  --uid <id>           account to reconcile, by uid
  --input <path>       JSON file of events: [{ kind: 'buy'|'sell'|'deposit'|'withdrawal'|'dividend', date, ... }]
  --commit             actually write (default is a dry run that writes nothing)
  --verify <path>      after a commit, diff stored positions against this fidelity-positions
                       fixture and exit 1 if they do not match exactly
  --help               this message

Idempotent: re-running the same input file writes only what is not already recorded.`)
    return
  }

  step('reconcile-portfolio-activity')
  const raw = await readFile(options.input, 'utf8')
  const parsed = JSON.parse(raw)
  const events = Array.isArray(parsed) ? parsed : parsed.events
  if (!Array.isArray(events)) throw new Error(`${options.input}: expected a JSON array of events, or an object with an "events" array.`)
  console.log(`Loaded ${events.length} event(s) from ${options.input}`)

  const backend = await connectPortfolioBackend(options)
  try {
    console.log(`Account: ${backend.uid}${options.email ? ` (${options.email})` : ''} · ${backend.mode} credentials\n`)

    step('Reading stored positions, closed tickers, and activity…')
    const [positions, closedTickers, activity] = await Promise.all([
      backend.readPositions(),
      backend.readClosedTickers ? backend.readClosedTickers() : [],
      backend.readActivity ? backend.readActivity() : [],
    ])
    console.log(`Currently stored: ${positions.length} position(s), ${closedTickers.length} closed ticker(s), ${activity.length} activity row(s)`)

    const existingActivityIds = new Set(activity.map((row) => row.id))
    const plan = planActivityReconciliation(positions, events, {
      existingActivityIds, closedTickers: new Set(closedTickers),
    })

    printPlan(plan)

    if (plan.errors.length) {
      console.log('Refusing to write anything while errors are present. Fix the input file and re-run.')
      process.exitCode = 1
      return
    }

    if (plan.writes.length > BATCH_LIMIT) {
      throw new Error(`Plan needs ${plan.writes.length} writes, over Firestore's ${BATCH_LIMIT}-write batch limit. Split the input file.`)
    }

    if (!options.commit) {
      console.log(plan.writes.length ? 'Dry run — nothing written. Re-run with --commit to apply.' : 'Nothing to do — every event is already recorded.')
      return
    }

    if (!plan.writes.length) {
      console.log('Nothing to do — every event is already recorded. No write performed.')
      return
    }

    step(`Committing ${plan.writes.length} writes…`)
    await backend.commit((batch) => {
      const docFor = { positions: batch.positionDoc, activity: batch.activityDoc, closedPositions: batch.closedPositionDoc }
      plan.writes.forEach((write) => {
        const ref = docFor[write.collection](write.id)
        if (write.op === 'delete') batch.delete(ref)
        else batch.set(ref, write.data, false)
      })
    })
    console.log(`\nCommitted ${plan.writes.length} writes.`)

    if (options.verify) {
      step(`Verifying against ${options.verify}…`)
      const statement = JSON.parse(await readFile(options.verify, 'utf8'))
      const finalPositions = await backend.readPositions()
      const findings = diffAgainstStatement(finalPositions, statement)
      if (findings.length) {
        console.log(`\n❌ Verification FAILED — stored positions do not match ${options.verify}:`)
        findings.forEach((finding) => console.log(`  ${finding.detail}`))
        process.exitCode = 1
      } else {
        console.log(`\n✅ Verified: stored positions match ${options.verify} exactly.`)
      }
    }
  } finally {
    await backend.close()
  }
}

const invokedDirectly = process.argv[1]
  && import.meta.url === pathToFileURL(process.argv[1]).href
if (invokedDirectly) {
  main()
    .catch((error) => {
      console.error(`\nreconcile-portfolio-activity failed: ${error.message}`)
      process.exitCode = 1
    })
    .finally(() => {
      const exit = setTimeout(() => process.exit(process.exitCode ?? 0), 2000)
      exit.unref?.()
    })
}
