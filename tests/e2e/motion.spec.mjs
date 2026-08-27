/**
 * motion.spec.mjs — Phase 3 assertions #8-#9 (rebuild plan).
 *
 * Eleven of the twelve mediums' own DESIGN.md "Motion + reduced-motion" sections claim
 * "None — trivially compliant" (the two governed exceptions the master permits — an index
 * ticker, Ticker's flip-and-reorder — are labeled in `manifest.motion.profile` but have no
 * implemented animated behavior yet; see NOTES.md). Classic is the one exception: its own
 * section (DESIGN.md, "Existing motion profile, already state-driven...") explicitly keeps its
 * pre-existing, correctly-gated hover transitions rather than claiming zero motion — 0f forbids
 * reopening that shared styling for this rebuild, so the "applies no motion" assertion below
 * excludes it (NO_MOTION_CLAIM_EXEMPT). The "reduced motion never hides content" assertion
 * still applies universally — Classic's grandfathered motion doesn't grandfather that.
 */
import { test, expect } from '@playwright/test'
import { MEDIUM_IDS } from './utils/mediums.mjs'

const NO_MOTION_CLAIM_EXEMPT = new Set(['classic'])

async function gotoHarness(page, mediumId) {
  await page.goto(`/e2e-harness/${mediumId}`)
  await page.locator('[data-app-ready="true"]').first().waitFor({ state: 'attached' })
}

for (const mediumId of MEDIUM_IDS.filter((id) => !NO_MOTION_CLAIM_EXEMPT.has(id))) {
  test(`#8/#9 motion — ${mediumId} applies no real CSS transition/animation anywhere`, async ({ page }) => {
    await gotoHarness(page, mediumId)
    const animated = await page.evaluate(() => {
      const found = []
      for (const node of document.querySelectorAll('*')) {
        const style = getComputedStyle(node)
        if (style.animationName && style.animationName !== 'none') found.push({ tag: node.tagName, kind: 'animation', value: style.animationName })
        if (style.transitionDuration && style.transitionDuration !== '0s' && style.transitionProperty !== 'none') {
          found.push({ tag: node.tagName, kind: 'transition', value: `${style.transitionProperty} ${style.transitionDuration}` })
        }
      }
      return found
    })
    expect(animated, `${mediumId} applies motion where its own DESIGN.md section claims none: ${JSON.stringify(animated)}`).toEqual([])
  })
}

// "Reduced motion never hides content" applies to every medium, Classic included — its
// grandfathered motion (see header comment) doesn't grandfather hiding content from that check.
for (const mediumId of MEDIUM_IDS) {
  test(`#8/#9 motion — ${mediumId} renders identical content whether or not reduced motion is requested`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await gotoHarness(page, mediumId)
    const reduced = await page.locator('[data-e2e-harness]').innerHTML()

    await page.emulateMedia({ reducedMotion: 'no-preference' })
    await page.reload()
    await page.locator('[data-app-ready="true"]').first().waitFor({ state: 'attached' })
    const full = await page.locator('[data-e2e-harness]').innerHTML()

    expect(reduced, `${mediumId}: reduced motion must never hide content the non-reduced state shows`).toBe(full)
  })
}
