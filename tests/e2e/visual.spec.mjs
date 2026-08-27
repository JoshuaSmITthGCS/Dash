/**
 * visual.spec.mjs — Phase 3 assertion #5 (rebuild plan): the screenshot matrix + greyscale pass.
 * Only these `visual-<medium>-<viewport>` projects run this file (see playwright.config.mjs) —
 * one project per medium×viewport gives each its own baseline directory.
 *
 * Matrix, per medium: Home (`/v2`), Research (`/v2/research`), Screens with the richest
 * disclosure set (`/v2/screens?recipe=swing`), Evidence's 64-metric report
 * (`/v2/evidence?section=validation`), and the entry page where the medium has one. The plan's
 * fuller matrix also names a StockDetailModal shot on a fixed ticker — not included here since
 * the six core screens are still an intentionally partial slice (NOTES.md) that doesn't open a
 * stock detail sheet from live traffic yet; adding it here would either screenshot nothing or
 * silently pass on absence, neither of which is a real assertion.
 */
import { test, expect } from '@playwright/test'
import { primeDeterministicPage, waitForAppReady } from './utils/mockData.mjs'
import { MEDIUMS_WITH_ENTRY } from './utils/mediums.mjs'

const DESTINATIONS = [
  { name: 'home', path: '/v2' },
  { name: 'research', path: '/v2/research' },
  { name: 'screens-swing', path: '/v2/screens?recipe=swing' },
  { name: 'evidence-validation', path: '/v2/evidence?section=validation' },
]

function currentMedium(testInfo) {
  const meta = testInfo.project.metadata
  if (!meta?.mediumId) throw new Error(`project "${testInfo.project.name}" has no mediumId metadata — visual.spec.mjs only runs under the visual-<medium>-<viewport> projects`)
  return meta
}

test.describe('visual', () => {
  for (const dest of DESTINATIONS) {
    test(`${dest.name} — screenshot matrix`, async ({ page }, testInfo) => {
      const { mediumId } = currentMedium(testInfo)
      await primeDeterministicPage(page, { medium: mediumId, entrySkip: true })
      await page.goto(dest.path)
      await waitForAppReady(page)
      // [data-volatile] would mask live timestamps/prices if any screen rendered them directly
      // outside the frozen fixtures — none currently do, but the mask is here so a future screen
      // that does add one doesn't silently reintroduce baseline churn.
      // Research's screenshot (Phase 4b) runs long and tall enough (a full ranked pool, dozens of
      // richly-disclosed cards) that the default 10s stability window can catch a heavier medium
      // (e.g. neon's per-card glow effects) still mid-layout — bumped to 20s here rather than
      // globally, since every other destination settles well inside the default.
      await expect(page).toHaveScreenshot(`${dest.name}.png`, { fullPage: true, mask: [page.locator('[data-volatile]')], timeout: 20_000 })
    })

    test(`${dest.name} — greyscale (color-independent legibility)`, async ({ page }, testInfo) => {
      const { mediumId } = currentMedium(testInfo)
      await primeDeterministicPage(page, { medium: mediumId, entrySkip: true })
      await page.goto(dest.path)
      await waitForAppReady(page)
      await page.addStyleTag({ content: 'html { filter: grayscale(1) !important; }' })
      await expect(page).toHaveScreenshot(`${dest.name}-greyscale.png`, { fullPage: true, mask: [page.locator('[data-volatile]')], timeout: 20_000 })
    })
  }

  test('entry page — screenshot', async ({ page }, testInfo) => {
    const { mediumId } = currentMedium(testInfo)
    if (!MEDIUMS_WITH_ENTRY.includes(mediumId)) test.skip(true, `${mediumId} has no entry page (entry: null)`)
    await primeDeterministicPage(page, { medium: mediumId, entrySkip: false })
    await page.goto('/v2')
    await waitForAppReady(page)
    await expect(page).toHaveScreenshot('entry.png', { fullPage: true })
  })
})
