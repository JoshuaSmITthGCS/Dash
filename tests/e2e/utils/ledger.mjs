/**
 * Parses `CAPABILITY-LEDGER.md`'s row table into the set of every capabilityId it declares —
 * the "known" side of parity.spec.mjs's both-direction diff (#1). Regex-based, same family as
 * `scripts/check-metric-preservation.mjs`, since the ledger is markdown, not JSON.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..')

export function readLedgerCapabilityIds() {
  const text = fs.readFileSync(path.join(ROOT, 'CAPABILITY-LEDGER.md'), 'utf8')
  const ids = new Set()
  // Row cells open with `| \`<capabilityId>\` |` — backtick-quoted, dot-separated kebab id.
  for (const match of text.matchAll(/^\|\s*`([a-z0-9.-]+)`\s*\|/gm)) {
    ids.add(match[1])
  }
  return ids
}
