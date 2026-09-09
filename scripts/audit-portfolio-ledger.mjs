#!/usr/bin/env node
// Read-only audit of one account's portfolio ledger against the invariants the app relies on.
// This is the tool that would have caught the LULU resurrection: it checks that a closed
// position stays closed, that every NAV step has a ledger row explaining it, and that the
// reconciliation bridge holds across the account's whole recorded history, not just the most
// recent pair of snapshots.
//
// Never writes anything. Exits 1 if any critical or warning finding is present, 0 otherwise
// (informational findings never fail the run).
//
// Usage:
//   npm run portfolio:audit -- --email you@example.com
//   npm run portfolio:audit -- --email you@example.com --statement scripts/fixtures/fidelity-positions-2026-09-09.json
//   npm run portfolio:audit -- --uid abc123                      # admin credentials only
//   npm run portfolio:audit -- --json
//
// Requires the same credentials as sync-portfolio-firebase.mjs (see that file's header).

import { readFile, readdir } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { connectPortfolioBackend, requireAccountSelection, step } from './lib/portfolio-firestore-backend.mjs'
import { runPortfolioAudit } from './lib/portfolio-audit.mjs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const FIXTURES_DIR = path.join(__dirname, 'fixtures')

export function parseArguments(argv) {
  const options = { email: null, uid: null, statement: null, json: false, help: false }
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index]
    if (argument === '--email') options.email = argv[index += 1]
    else if (argument === '--uid') options.uid = argv[index += 1]
    else if (argument === '--statement') options.statement = argv[index += 1]
    else if (argument === '--json') options.json = true
    else if (argument === '--help' || argument === '-h') options.help = true
    else throw new Error(`Unrecognized argument: ${argument}`)
  }
  if (!options.help) requireAccountSelection(options)
  return options
}

/** The newest `fidelity-positions-*.json` fixture in scripts/fixtures/, or null if none exist. */
async function newestPositionsFixture() {
  let names
  try { names = await readdir(FIXTURES_DIR) } catch { return null }
  const candidates = names.filter((name) => /^fidelity-positions-.*\.json$/.test(name)).sort()
  if (!candidates.length) return null
  return path.join(FIXTURES_DIR, candidates.at(-1))
}

async function loadStatement(explicitPath) {
  const target = explicitPath || await newestPositionsFixture()
  if (!target) return null
  const raw = await readFile(target, 'utf8')
  return { path: target, ...JSON.parse(raw) }
}

function severityIcon(severity) {
  return { critical: '🛑', warning: '⚠️ ', info: 'ℹ️ ' }[severity] || '• '
}

export function printReport(report, statementPath) {
  console.log(`\n${'='.repeat(72)}`)
  console.log('PORTFOLIO LEDGER AUDIT')
  console.log('='.repeat(72))
  if (statementPath) console.log(`Statement checked against: ${statementPath}`)
  console.log(`Critical: ${report.critical.length} · Warnings: ${report.warnings.length} · Informational: ${report.info.length}\n`)

  for (const severity of ['critical', 'warnings', 'info']) {
    const findings = report[severity]
    if (!findings.length) continue
    console.log(`--- ${severity.toUpperCase()} ---`)
    for (const finding of findings) {
      console.log(`${severityIcon(finding.severity)}[${finding.check}] ${finding.detail}`)
      if (finding.activityInWindow?.length) {
        finding.activityInWindow.forEach((row) => console.log(`     - ${row.effectiveDate} ${row.type} ${row.ticker || ''} ${row.amount}`))
      }
      if (finding.operations?.length) {
        finding.operations.forEach((op) => console.log(`     - ${op.kind} ${op.ticker}`))
      }
    }
    console.log('')
  }

  console.log(report.ok
    ? '✅ No critical or warning findings.'
    : '❌ Findings above need attention before this account\'s figures can be trusted.')
}

export async function main() {
  const options = parseArguments(process.argv.slice(2))
  if (options.help) {
    console.log(`audit-portfolio-ledger — read-only checks against a portfolio's Firestore ledger

  --email <address>     account to audit, resolved to a uid via Firebase Auth
  --uid <id>             account to audit, by uid
  --statement <path>     a fidelity-positions-*.json fixture to diff stored positions against
                         (defaults to the newest one in scripts/fixtures/, if any)
  --json                 print the full report as JSON instead of formatted text
  --help                 this message

Never writes. Exits 1 if any critical or warning finding is present.`)
    return
  }

  step(`audit-portfolio-ledger`)
  const backend = await connectPortfolioBackend(options)
  try {
    console.log(`Account: ${backend.uid}${options.email ? ` (${options.email})` : ''} · ${backend.mode} credentials\n`)
    step('Reading positions, closed positions, activity, and snapshots…')
    const [positions, closedPositions, activities, snapshots, trackingState] = await Promise.all([
      backend.readPositions(),
      backend.readClosedPositions ? backend.readClosedPositions() : [],
      backend.readActivity ? backend.readActivity() : [],
      backend.readSnapshots ? backend.readSnapshots() : [],
      backend.readTrackingState ? backend.readTrackingState() : null,
    ])
    const statement = await loadStatement(options.statement)

    const report = runPortfolioAudit({ positions, closedPositions, activities, snapshots, trackingState, statement })

    if (options.json) {
      console.log(JSON.stringify(report, null, 2))
    } else {
      printReport(report, statement?.path || null)
    }
    process.exitCode = report.ok ? 0 : 1
  } finally {
    await backend.close()
  }
}

const invokedDirectly = process.argv[1]
  && import.meta.url === pathToFileURL(process.argv[1]).href
if (invokedDirectly) {
  main()
    .catch((error) => {
      console.error(`\naudit-portfolio-ledger failed: ${error.message}`)
      process.exitCode = 1
    })
    .finally(() => {
      const exit = setTimeout(() => process.exit(process.exitCode ?? 0), 2000)
      exit.unref?.()
    })
}
