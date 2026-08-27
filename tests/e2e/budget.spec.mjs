/**
 * budget.spec.mjs — Phase 3 assertion #16 (rebuild plan): "entry bundle < 500 kB with any theme
 * active." Measures real network transfer for a cold load of `/v2` with each medium active —
 * every JS/CSS/font/texture byte the browser actually downloads to render that medium, not a
 * static guess at chunk boundaries. Runs from 2b onward per the plan, not only at cutover.
 */
import { test, expect } from '@playwright/test'
import { primeDeterministicPage, waitForAppReady } from './utils/mockData.mjs'
import { MEDIUM_IDS } from './utils/mediums.mjs'

const BUDGET_BYTES = 500_000

for (const mediumId of MEDIUM_IDS) {
  test(`#16 budget — ${mediumId}'s cold /v2 load stays under the 500 kB entry budget`, async ({ page }) => {
    await primeDeterministicPage(page, { medium: mediumId, entrySkip: true })
    let totalBytes = 0
    const byUrl = []
    page.on('response', async (response) => {
      const url = response.url()
      if (!/\.(js|css|woff2?|ttf|otf|png|jpe?g|svg)(\?|$)/i.test(url)) return
      if (url.includes('/data/')) return // published data payloads aren't part of the UI budget
      try {
        const headers = response.headers()
        const size = Number(headers['content-length']) || (await response.body()).length
        totalBytes += size
        byUrl.push({ url: url.replace(/^.*\/assets\//, ''), size })
      } catch {
        // navigation raced the response body (redirect/aborted) — not part of the real payload
      }
    })
    await page.goto('/v2')
    await waitForAppReady(page)
    expect(totalBytes, `${mediumId}: ${totalBytes} bytes over budget — ${JSON.stringify(byUrl.sort((a, b) => b.size - a.size).slice(0, 8))}`).toBeLessThan(BUDGET_BYTES)
  })
}
