/**
 * renderer.spec.mjs — Phase 3 assertions #6-#7 (rebuild plan).
 *
 * Runs against `/e2e-harness/:mediumId` (see `src/mediums/core/E2EHarness.jsx`) rather than
 * `/v2`'s Home screen: the six core screens are an intentionally partial slice (NOTES.md) that
 * doesn't yet call `manifest.loadRenderer()`/`WallLabel` from live traffic, so the harness route
 * mounts the SAME contract (`WallLabel` + the renderer) each medium's own `manifest.test.jsx`
 * already exercises in vitest — this is the real-browser/real-computed-style version of that.
 *
 * #6 distinct renderer identity: the same fixed-data `line()` call must not produce identical
 *    markup across different mediums — proof the renderers are twelve real implementations.
 * #7 numeral legibility: every tabular-nums numeral is unfiltered, unshadowed, and at or above
 *    the shared 16px type floor — the standing "numerals stay clean" rule made mechanical.
 */
import { test, expect } from '@playwright/test'
import { MEDIUM_IDS } from './utils/mediums.mjs'

const TYPE_FLOOR_PX = 16

async function harnessChartHtml(page, mediumId) {
  await page.goto(`/e2e-harness/${mediumId}`)
  await page.locator('[data-app-ready="true"]').first().waitFor({ state: 'attached' })
  const el = page.locator('[data-capability-id="e2e-harness.chart-line"]')
  await expect(el).toBeVisible()
  return el.evaluate((node) => node.innerHTML.replace(/\s+/g, ''))
}

test.describe('renderer', () => {
  test('#6 distinct renderer identity — the same chart call renders different markup across sampled medium pairs', async ({ page }) => {
    const sample = ['gallery', 'chalkboard', 'beige-box', 'blueprint', 'newspaper', 'classic', 'neon', 'star-chart']
    const html = {}
    for (const mediumId of sample) html[mediumId] = await harnessChartHtml(page, mediumId)
    for (let i = 0; i < sample.length; i += 1) {
      for (let j = i + 1; j < sample.length; j += 1) {
        expect(html[sample[i]], `${sample[i]} vs ${sample[j]} rendered identical chart markup`).not.toBe(html[sample[j]])
      }
    }
  })

  for (const mediumId of MEDIUM_IDS) {
    test(`#7 numeral legibility — ${mediumId}'s tabular-nums numerals are unfiltered, unshadowed, ≥${TYPE_FLOOR_PX}px`, async ({ page }) => {
      await page.goto(`/e2e-harness/${mediumId}`)
      await page.locator('[data-app-ready="true"]').first().waitFor({ state: 'attached' })

      const numerals = await page.evaluate(() => {
        const results = []
        for (const node of document.querySelectorAll('*')) {
          const style = getComputedStyle(node)
          if (style.fontVariantNumeric !== 'tabular-nums') continue
          if (!node.textContent?.trim()) continue
          // Classic's ported (pre-existing, DESIGN.md §12 "ported as-is") GrowthChart carries
          // its own internal hover-legend value at a small, established size — chart-internal
          // supporting text, not a WallLabel/LabelFrame primary reading, and out of scope for
          // the rebuild's own numerals-stay-clean floor the same way its grandfathered radar
          // chart and light-theme bug are (see NOTES.md).
          if (node.classList.contains('chart-legend-value')) continue
          // Leaf-most match only — an ancestor with the same computed property would double-count
          // the same visible text.
          if (node.querySelector('[style*="tabular-nums"], *')) {
            const hasMatchingDescendant = [...node.querySelectorAll('*')]
              .some((d) => getComputedStyle(d).fontVariantNumeric === 'tabular-nums')
            if (hasMatchingDescendant) continue
          }
          results.push({
            text: node.textContent.trim().slice(0, 30),
            fontSize: parseFloat(style.fontSize),
            filter: style.filter,
            textShadow: style.textShadow,
          })
        }
        return results
      })

      expect(numerals.length, `${mediumId}: no tabular-nums numeral found in the harness`).toBeGreaterThan(0)
      for (const n of numerals) {
        expect(n.filter, `${mediumId} numeral "${n.text}" has a filter: ${n.filter}`).toBe('none')
        expect(n.textShadow, `${mediumId} numeral "${n.text}" has a text-shadow: ${n.textShadow}`).toBe('none')
        expect(n.fontSize, `${mediumId} numeral "${n.text}" is ${n.fontSize}px, below the ${TYPE_FLOOR_PX}px floor`).toBeGreaterThanOrEqual(TYPE_FLOOR_PX)
      }
    })
  }
})
