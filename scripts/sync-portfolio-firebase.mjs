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
// Usage:
//   node --env-file=.env.local scripts/sync-portfolio-firebase.mjs --email you@example.com
//   node --env-file=.env.local scripts/sync-portfolio-firebase.mjs --uid abc123 --commit
//
// Dry run is the DEFAULT and prints the full plan. Nothing is written until --commit,
// because this import is authoritative: a holding absent from the export is deleted.
//
// Requires FIREBASE_SERVICE_ACCOUNT_JSON (see .env.example) -- the same service-account
// credential netlify/functions/alert-push.mjs uses. It bypasses firestore.rules by design,
// so it is a server-side secret and must never be given a VITE_ prefix.

import { pathToFileURL } from 'node:url'
import { cert, getApps, initializeApp } from 'firebase-admin/app'
import { getAuth } from 'firebase-admin/auth'
import { getFirestore } from 'firebase-admin/firestore'
import {
  planReferencePortfolioSync,
  referenceIntradaySnapshot,
  referenceSyncRecord,
  referenceTrackingState,
  summarizeReferenceSync,
  REFERENCE_PORTFOLIO,
  REFERENCE_PORTFOLIO_VERSION,
} from '../src/lib/referencePortfolio.js'

// Firestore caps a batch at 500 writes. 46 holdings plus the snapshot and tracking documents
// is far below it, but a plan is only bounded by what the account already holds.
const BATCH_LIMIT = 500

export function parseArguments(argv) {
  const options = { commit: false, email: null, uid: null }
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index]
    if (argument === '--commit') options.commit = true
    else if (argument === '--help' || argument === '-h') options.help = true
    else if (argument === '--email') options.email = argv[index += 1]
    else if (argument === '--uid') options.uid = argv[index += 1]
    else throw new Error(`Unrecognized argument: ${argument}`)
  }
  if (!options.help && !options.email && !options.uid) {
    throw new Error('Pass --email <address> or --uid <id> to name the account to sync.')
  }
  if (options.email && options.uid) {
    throw new Error('Pass either --email or --uid, not both.')
  }
  return options
}

function firebaseApp() {
  if (getApps().length) return getApps()[0]
  const raw = process.env.FIREBASE_SERVICE_ACCOUNT_JSON
  if (!raw) {
    throw new Error(
      'FIREBASE_SERVICE_ACCOUNT_JSON is not set. Load it with '
      + '`node --env-file=.env.local scripts/sync-portfolio-firebase.mjs ...`',
    )
  }
  let credential
  try { credential = JSON.parse(raw) } catch { throw new Error('FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON.') }
  return initializeApp({ credential: cert(credential) })
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

export async function main() {
  const options = parseArguments(process.argv.slice(2))
  if (options.help) {
    console.log(`sync-portfolio-firebase — apply the Fidelity reference portfolio to Firestore

  --email <address>   account to sync, resolved to a uid via Firebase Auth
  --uid <id>          account to sync, by uid
  --commit            actually write (default is a dry run that writes nothing)
  --help              this message

Reference baseline: ${REFERENCE_PORTFOLIO_VERSION} (${REFERENCE_PORTFOLIO.length} holdings)`)
    return
  }

  const app = firebaseApp()
  const db = getFirestore(app)

  const uid = options.uid || (await getAuth(app).getUserByEmail(options.email)).uid
  console.log(`Account: ${uid}${options.email ? ` (${options.email})` : ''}`)
  console.log(`Baseline: ${REFERENCE_PORTFOLIO_VERSION} · ${REFERENCE_PORTFOLIO.length} holdings\n`)

  const positionsRef = db.collection('portfolios').doc(uid).collection('positions')
  const existing = (await positionsRef.get()).docs.map((item) => ({ id: item.id, ...item.data() }))
  console.log(`Currently stored: ${existing.length} position${existing.length === 1 ? '' : 's'}`)

  const operations = planReferencePortfolioSync(existing)
  const counts = summarizeReferenceSync(operations)
  const snapshot = referenceIntradaySnapshot()
  const writes = operations.length + 2

  console.log(`Plan: ${counts.added} added · ${counts.updated} updated · ${counts.removed} removed\n`)
  console.log(describe(operations))

  const invested = REFERENCE_PORTFOLIO.reduce((sum, position) => sum + position.snapshotValue, 0)
  const cost = REFERENCE_PORTFOLIO.reduce((sum, position) => sum + position.costBasisTotal, 0)
  const undated = REFERENCE_PORTFOLIO.filter((position) => !position.purchaseDate)
  console.log(`\nAfter this sync: ${REFERENCE_PORTFOLIO.length} holdings · ${money(cost)} cost · ${money(invested)} value`)
  if (undated.length) {
    console.log(`Undated holdings (no buy in the transaction history): ${undated.map((position) => position.ticker).join(', ')}`)
  }

  if (writes > BATCH_LIMIT) {
    throw new Error(`Plan needs ${writes} writes, over Firestore's ${BATCH_LIMIT}-write batch limit.`)
  }

  if (!options.commit) {
    console.log('\nDry run — nothing written. Re-run with --commit to apply.')
    if (counts.removed) {
      console.log(`Note: --commit deletes ${counts.removed} stored holding${counts.removed === 1 ? '' : 's'} absent from the export.`)
    }
    return
  }

  const importedAt = new Date().toISOString()
  const batch = db.batch()
  operations.forEach((operation) => {
    const positionRef = positionsRef.doc(operation.id)
    if (operation.kind === 'remove') {
      batch.delete(positionRef)
      return
    }
    batch.set(positionRef, referenceSyncRecord(operation, importedAt), {
      merge: operation.kind === 'update',
    })
  })
  batch.set(
    db.collection('portfolios').doc(uid).collection('intradaySnapshots').doc(snapshot.id),
    snapshot.document,
    { merge: true },
  )
  batch.set(
    db.collection('portfolios').doc(uid).collection('tracking').doc('state'),
    referenceTrackingState(importedAt),
    { merge: true },
  )
  await batch.commit()

  console.log(`\nCommitted ${writes} writes at ${importedAt}.`)
  console.log(`Account marked as reconciled to ${REFERENCE_PORTFOLIO_VERSION}; the app will not re-run its own sync for this version.`)
}

// Guarded so the module can be imported for testing without running a sync.
const invokedDirectly = process.argv[1]
  && import.meta.url === pathToFileURL(process.argv[1]).href
if (invokedDirectly) {
  main().catch((error) => {
    console.error(`\nsync-portfolio-firebase failed: ${error.message}`)
    process.exitCode = 1
  })
}
