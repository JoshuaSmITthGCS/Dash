/**
 * rules.spec.mjs — Phase 3 assertions #10-#13 (rebuild plan), run against `/e2e-harness/:id`.
 *
 * #10 headline rule: Newspaper's accumulating fixture never reads as a declarative assertion.
 * #11 Chalkboard smudge: the prior-value mark renders behind the current value in DOM order, at
 *     a real, measurably lower luminance step — mechanically, not just visually.
 * #12 Neon glow exclusivity: any element carrying a glow (box-shadow/filter/text-shadow) is
 *     inside a breached container — never decorative, never on an established/accumulating row.
 * #13 Beige Box contrast: the disabled/unavailable state's text-on-window contrast clears
 *     WCAG AA (4.5:1), including against its own window background, not assumed.
 */
import { test, expect } from '@playwright/test'

async function gotoHarness(page, mediumId) {
  await page.goto(`/e2e-harness/${mediumId}`)
  await page.locator('[data-app-ready="true"]').first().waitFor({ state: 'attached' })
}

function relativeLuminance([r, g, b]) {
  const linear = (c) => { const s = c / 255; return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4 }
  const [rl, gl, bl] = [r, g, b].map(linear)
  return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl
}

function parseRgb(str) {
  const m = str.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)/)
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : [0, 0, 0]
}

function contrastRatio(a, b) {
  const [l1, l2] = [relativeLuminance(parseRgb(a)), relativeLuminance(parseRgb(b))].sort((x, y) => y - x)
  return (l1 + 0.05) / (l2 + 0.05)
}

test.describe('rules', () => {
  test('#10 headline rule — Newspaper never asserts what an accumulating metric cannot support', async ({ page }) => {
    await gotoHarness(page, 'newspaper')
    const headlines = await page.locator('h3').allTextContents()
    const accumulatingHeadline = headlines.find((h) => h.includes('17 of 24') || h.startsWith('Is '))
    expect(accumulatingHeadline, 'no interrogative headline found for the accumulating fixture').toBeTruthy()
    expect(accumulatingHeadline.startsWith('Is ')).toBe(true)

    const establishedHeadline = headlines.find((h) => h.includes('Deflated Sharpe adjusts'))
    expect(establishedHeadline, 'no declarative headline found for the established fixture').toBeTruthy()
    expect(establishedHeadline.startsWith('Is ')).toBe(false)

    // Standfirst flag: present for breached rows, absent for established/accumulating.
    const standfirstCount = await page.locator('[data-standfirst]').count()
    expect(standfirstCount).toBeGreaterThanOrEqual(2) // breached_metric + ic_bootstrap_ci fixtures
  })

  test('#11 Chalkboard erasure smudge — prior renders behind current in DOM order, at a lower opacity, mechanically checked', async ({ page }) => {
    await gotoHarness(page, 'chalkboard')
    const prior = page.locator('[data-state-mark="prior"]').first()
    const current = page.locator('[data-state-mark="current"]').first()
    await expect(prior).toBeVisible()
    await expect(current).toBeVisible()

    const order = await page.evaluate(() => {
      const p = document.querySelector('[data-state-mark="prior"]')
      const c = document.querySelector('[data-state-mark="current"]')
      return Boolean(p.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING)
    })
    expect(order, 'prior must precede current in DOM order (paints behind it)').toBe(true)

    const [priorOpacity, currentOpacity] = await Promise.all([
      prior.evaluate((el) => parseFloat(getComputedStyle(el).opacity)),
      current.evaluate((el) => parseFloat(getComputedStyle(el).opacity)),
    ])
    expect(priorOpacity, 'the smudge must be measurably dimmer than the current reading').toBeLessThan(currentOpacity - 0.1)
  })

  test('#12 Neon glow exclusivity — any glow effect belongs to a breached container, never a decorative or non-breached one', async ({ page }) => {
    await gotoHarness(page, 'neon')
    const violations = await page.evaluate(() => {
      const bad = []
      for (const node of document.querySelectorAll('*')) {
        const style = getComputedStyle(node)
        const hasGlow = (style.boxShadow && style.boxShadow !== 'none') || (style.filter && style.filter !== 'none') || (style.textShadow && style.textShadow !== 'none')
        if (!hasGlow) continue
        const breachedAncestor = node.closest('[data-breached="true"]')
        if (!breachedAncestor) bad.push({ tag: node.tagName, cls: node.className, boxShadow: style.boxShadow, filter: style.filter })
      }
      return bad
    })
    expect(violations, `glow found outside any breached container: ${JSON.stringify(violations)}`).toEqual([])

    // The positive case: the breached fixtures DO carry the glow — exclusivity, not absence.
    const glowingBreached = await page.evaluate(() => {
      return [...document.querySelectorAll('[data-breached="true"]')].some((node) => {
        const style = getComputedStyle(node)
        return style.boxShadow && style.boxShadow !== 'none'
      })
    })
    expect(glowingBreached, 'no breached container actually carries the glow — exclusivity is meaningless without a positive case').toBe(true)
  })

  test('#13 Beige Box contrast — the disabled/unavailable state clears WCAG AA (4.5:1) against its own window background', async ({ page }) => {
    await gotoHarness(page, 'beige-box')
    const disabled = page.locator('[data-beige-disabled="true"]').first()
    await expect(disabled).toBeVisible()

    const { textColor, bg } = await disabled.evaluate((el) => {
      const style = getComputedStyle(el)
      let bgNode = el
      let bg = getComputedStyle(bgNode).backgroundColor
      while ((bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent') && bgNode.parentElement) {
        bgNode = bgNode.parentElement
        bg = getComputedStyle(bgNode).backgroundColor
      }
      return { textColor: style.color, bg }
    })
    const ratioValue = contrastRatio(textColor, bg)
    expect(ratioValue, `disabled text ${textColor} on ${bg} is only ${ratioValue.toFixed(2)}:1, below WCAG AA's 4.5:1`).toBeGreaterThanOrEqual(4.5)
  })
})
