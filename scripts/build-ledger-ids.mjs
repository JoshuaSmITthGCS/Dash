// Parses every `data-capability-id`-shaped id out of CAPABILITY-LEDGER.md's tables and writes
// them to scripts/ledger-ids.json, consumed by src/mediums/core/capability.js in dev builds to
// warn on any capabilityId that isn't a real ledger row. Mirrors the parsing convention
// scripts/check-metric-preservation.mjs already uses against docs/METRIC_INVENTORY.md.
import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const ledger = fs.readFileSync(path.join(root, 'CAPABILITY-LEDGER.md'), 'utf8')

// Every ledger row's first cell is the id, wrapped in backticks: | `class.scope.slug` | ...
const ids = [...ledger.matchAll(/^\| `([a-z0-9.-]+)` \|/gm)].map((match) => match[1])
const unique = [...new Set(ids)]

fs.writeFileSync(path.join(root, 'scripts', 'ledger-ids.json'), `${JSON.stringify(unique, null, 2)}\n`)
process.stdout.write(`Wrote ${unique.length} capability ids to scripts/ledger-ids.json\n`)
