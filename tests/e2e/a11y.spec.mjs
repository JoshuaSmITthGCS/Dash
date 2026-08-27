/**
 * a11y.spec.mjs — Phase 3 assertions #14-#15 (rebuild plan), run against `/e2e-harness/:id`.
 *
 * #14 axe + landmarks + tab order + 44px targets + no horizontal overflow.
 * #15 chart-ink contrast (SVG stroke/fill colors against their background clear WCAG AA) + a
 *     glass-over-text check (the master's Liquid Glass scoping: backdrop-filter/blur may only
 *     ever sit on floating chrome, never over content text — the harness route renders no chrome
 *     at all, so this is a real, currently-passing regression guard, not a hopeful assumption).
 */
import AxeBuilder from '@axe-core/playwright'
import { test, expect } from '@playwright/test'
import { MEDIUM_IDS } from './utils/mediums.mjs'

async function gotoHarness(page, mediumId) {
  await page.goto(`/e2e-harness/${mediumId}`)
  await page.locator('[data-app-ready="true"]').first().waitFor({ state: 'attached' })
}

function relativeLuminance([r, g, b]) {
  const linear = (c) => { const s = c / 255; return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4 }
  const [rl, gl, bl] = [r, g, b].map(linear)
  return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl
}

function parseColor(str) {
  const m = str.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)/)
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null
}

function contrastRatio(a, b) {
  const [l1, l2] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x)
  return (l1 + 0.05) / (l2 + 0.05)
}

for (const mediumId of MEDIUM_IDS) {
  test(`#14 a11y — ${mediumId} passes axe with zero serious/critical violations`, async ({ page }) => {
    await gotoHarness(page, mediumId)
    const results = await new AxeBuilder({ page }).include('[data-e2e-harness]').analyze()
    const serious = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
    expect(serious, `${mediumId}: ${JSON.stringify(serious.map((v) => ({ id: v.id, nodes: v.nodes.length })))}`).toEqual([])
  })

  test(`#14 a11y — ${mediumId} has no horizontal overflow at 390px`, async ({ page }) => {
    await gotoHarness(page, mediumId)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow, `${mediumId}: page is ${overflow}px wider than its viewport`).toBeLessThanOrEqual(1)
  })

  test(`#14 a11y — ${mediumId}'s interactive elements meet the 44px touch-target minimum`, async ({ page }) => {
    await gotoHarness(page, mediumId)
    const undersized = await page.evaluate(() => {
      const bad = []
      for (const el of document.querySelectorAll('[data-e2e-harness] button, [data-e2e-harness] a, [data-e2e-harness] [role="button"]')) {
        const rect = el.getBoundingClientRect()
        if (rect.width === 0 && rect.height === 0) continue // not rendered/visible
        if (rect.width < 44 || rect.height < 44) bad.push({ text: el.textContent?.trim().slice(0, 20), width: rect.width, height: rect.height })
      }
      return bad
    })
    expect(undersized, `${mediumId}: undersized touch targets ${JSON.stringify(undersized)}`).toEqual([])
  })

  test(`#15 a11y — ${mediumId}'s chart ink clears WCAG AA contrast against its own background`, async ({ page }) => {
    await gotoHarness(page, mediumId)
    const chart = page.locator('[data-capability-id="e2e-harness.chart-line"] svg').first()
    await expect(chart).toBeVisible()
    const ratios = await chart.evaluate((svg) => {
      // Every medium sets its ground color via `[data-medium="x"] body { background: ... }`
      // (Classic is the one exception, via the shared legacy stylesheet) — [data-e2e-harness]
      // itself never carries its own background-color, so checking it directly always resolved
      // to transparent and silently compared chart ink against fake black instead of the
      // medium's real background.
      const bg = getComputedStyle(document.body).backgroundColor
      const results = []
      for (const shape of svg.querySelectorAll('path, line, circle, rect, polyline')) {
        const style = getComputedStyle(shape)
        const stroke = style.stroke !== 'none' ? style.stroke : null
        // <line> has no enclosed area — SVG never paints its `fill`, so a computed fill (often
        // the CSS-initial black, whether or not one was ever set) is inert, not real chart ink.
        const fill = shape.tagName !== 'line' && style.fill !== 'none' && style.fill !== 'rgba(0, 0, 0, 0)' ? style.fill : null
        if (stroke) results.push({ color: stroke, bg })
        if (fill) results.push({ color: fill, bg })
      }
      return results
    })
    const parsed = ratios.map((r) => ({ ...r, parsedColor: parseColor(r.color), parsedBg: parseColor(r.bg) })).filter((r) => r.parsedColor && r.parsedBg)
    expect(parsed.length, `${mediumId}: no resolvable chart ink color found (CSS variable never resolved — tokens.css not loaded?)`).toBeGreaterThan(0)
    for (const r of parsed) {
      const ratio = contrastRatio(r.parsedColor, r.parsedBg)
      // 3:1 is WCAG AA's own floor for graphical/UI-component contrast (1.4.11), not the 4.5:1
      // text floor — a chart stroke is a graphic, not body text.
      expect(ratio, `${mediumId}: chart ink ${r.color} on ${r.bg} is only ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(3)
    }
  })

  test(`#15 a11y — ${mediumId} never applies glass/blur over content text (Liquid Glass scoping: floating chrome only)`, async ({ page }) => {
    await gotoHarness(page, mediumId)
    const violations = await page.evaluate(() => {
      const bad = []
      for (const node of document.querySelectorAll('[data-e2e-harness] *')) {
        if (!node.textContent?.trim()) continue
        const style = getComputedStyle(node)
        const hasGlass = (style.backdropFilter && style.backdropFilter !== 'none') || (style.filter && style.filter.includes('blur') && !node.hasAttribute('aria-hidden'))
        if (hasGlass) bad.push({ tag: node.tagName, text: node.textContent.trim().slice(0, 20), backdropFilter: style.backdropFilter, filter: style.filter })
      }
      return bad
    })
    expect(violations, `${mediumId}: glass/blur found over content text: ${JSON.stringify(violations)}`).toEqual([])
  })
}
