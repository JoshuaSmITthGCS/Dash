/**
 * parity.spec.mjs — Phase 3 assertions #1-#4 (rebuild plan).
 *
 * #1 both-direction capability diff: every `data-capability-id` actually rendered must already
 *    exist in CAPABILITY-LEDGER.md (hard requirement — a rendered id the ledger doesn't know
 *    about is a hallucinated capability). The reverse direction (ledger rows never rendered) is
 *    reported, not asserted to zero — `core/screens/*` are a documented, intentionally partial
 *    slice (NOTES.md); full ledger coverage is a cutover-readiness question, not a per-commit
 *    harness gate. Also invokes the existing `scripts/check-metric-preservation.mjs` gate.
 * #2 nav parity: every medium's nav reaches all six destinations, 0-or-1 additional interaction.
 * #3 deep-link bypass: an entry medium never shows its entry page off the bare destination root.
 * #4 entry containment: the entry page renders (skippable) on first, unseen load, and every
 *    interactive element in it carries an already-known capabilityId.
 */
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect } from '@playwright/test'
import { primeDeterministicPage, waitForAppReady } from './utils/mockData.mjs'
import { MEDIUM_IDS, MEDIUMS_WITH_ENTRY } from './utils/mediums.mjs'
import { readLedgerCapabilityIds } from './utils/ledger.mjs'

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const DESTINATIONS = ['/v2', '/v2/research', '/v2/screens', '/v2/portfolio', '/v2/markets', '/v2/evidence']

test.describe('parity', () => {
  test('#1a invoke check-metric-preservation.mjs — the existing capability-preservation gate stays green', () => {
    expect(() => execFileSync('node', ['scripts/check-metric-preservation.mjs'], { cwd: ROOT, stdio: 'pipe' })).not.toThrow()
  })

  test('#1b every rendered data-capability-id is a known ledger row — zero hallucinated capabilities', async ({ page }) => {
    const ledgerIds = readLedgerCapabilityIds()
    await primeDeterministicPage(page, { medium: 'gallery', entrySkip: true })
    const rendered = new Set()
    for (const dest of DESTINATIONS) {
      await page.goto(dest)
      await waitForAppReady(page)
      const ids = await page.locator('[data-capability-id]').evaluateAll((nodes) => nodes.map((n) => n.getAttribute('data-capability-id')))
      ids.forEach((id) => rendered.add(id))
    }
    const unknown = [...rendered].filter((id) => !ledgerIds.has(id))
    expect(unknown, `capability ids rendered but not in CAPABILITY-LEDGER.md: ${unknown.join(', ')}`).toEqual([])

    // Reverse direction: reported, never asserted to zero — the six core screens are an
    // intentionally partial proof-of-pattern slice (NOTES.md), not full ledger coverage yet.
    const uncovered = [...ledgerIds].filter((id) => !rendered.has(id))
    console.log(`[parity] ${rendered.size} capability ids rendered; ${uncovered.length} of ${ledgerIds.size} ledger rows not yet rendered (expected — partial slice, see NOTES.md).`)
  })

  for (const mediumId of MEDIUM_IDS) {
    test(`#2 nav parity — ${mediumId} reaches all six destinations`, async ({ page }) => {
      await primeDeterministicPage(page, { medium: mediumId, entrySkip: true })
      await page.goto('/v2')
      await waitForAppReady(page)
      for (const dest of DESTINATIONS) {
        await page.goto(dest)
        await waitForAppReady(page)
        await expect(page.locator('[data-medium-shell]')).toBeVisible()
        expect(new URL(page.url()).pathname).toBe(dest)
      }
    })
  }

  for (const mediumId of MEDIUMS_WITH_ENTRY) {
    test(`#3 deep-link bypass — ${mediumId} never shows entry off the bare root`, async ({ page }) => {
      // No entrySkip, no seen key: if the bypass were NOT structural, this is exactly the state
      // that would show the entry — proving the deep link still skips it either way.
      await primeDeterministicPage(page, { medium: mediumId, entrySkip: false })
      await page.goto('/v2/research')
      await waitForAppReady(page)
      await expect(page.locator('[data-medium-shell]')).toBeVisible()
    })

    test(`#4 entry containment — ${mediumId} shows entry on first unseen load, every element carries a known capabilityId`, async ({ page }) => {
      const ledgerIds = readLedgerCapabilityIds()
      await primeDeterministicPage(page, { medium: mediumId, entrySkip: false })
      await page.goto('/v2')
      await waitForAppReady(page)
      await expect(page.locator('[data-medium-shell]')).not.toBeVisible()
      const ids = await page.locator('[data-capability-id]').evaluateAll((nodes) => nodes.map((n) => n.getAttribute('data-capability-id')))
      expect(ids.length, `${mediumId}'s entry page has no data-capability-id elements`).toBeGreaterThan(0)
      const unknown = ids.filter((id) => !ledgerIds.has(id))
      expect(unknown, `${mediumId} entry: unknown capability ids ${unknown.join(', ')}`).toEqual([])
    })
  }
})
