import { mkdir, writeFile } from 'node:fs/promises'
import { chromium } from 'playwright-core'
import settings from '../pipeline/config/settings.json' with { type: 'json' }

const chrome = process.env.CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const origin = process.env.MOBILE_SCREENSHOT_ORIGIN || 'http://127.0.0.1:5173'
const outputDirectory = new URL('../docs/mobile-screenshots/', import.meta.url)
const heights = { 390: 844, 430: 932 }
const cases = settings.interface.mobile_acceptance_widths.flatMap((width) => [
  { width, height: heights[width], theme: 'light' },
  { width, height: heights[width], theme: 'dark' },
])
const pages = [
  {
    name: 'home',
    path: '/?preview=1&portfolioPreview=1',
    ready: '.report-hero-grid',
    async settle(page) {
      await page.waitForFunction(() => !document.querySelector('.home-fact-link strong')?.textContent?.includes('Calculating'))
    },
  },
  {
    name: 'planning',
    path: '/planning?preview=1&portfolioPreview=1',
    ready: '.planning-verdict',
    async settle(page) {
      await page.waitForFunction(() => document.querySelector('.success-gauge strong')?.textContent?.trim() !== '…')
    },
  },
  { name: 'research', path: '/research?preview=1', ready: '.research-mobile-card' },
  {
    name: 'stock-detail',
    path: '/research?preview=1',
    ready: '.stock-concept-hero',
    async prepare(page) {
      const card = page.locator('.research-mobile-card').first()
      await card.locator('.expand-button').click()
      await card.locator('.research-expanded .primary-button').click()
    },
  },
]

await mkdir(outputDirectory, { recursive: true })
const browser = await chromium.launch({ executablePath: chrome, headless: true })
const results = []
for (const entry of cases) {
  const context = await browser.newContext({
    viewport: { width: entry.width, height: entry.height },
    screen: { width: entry.width, height: entry.height },
    deviceScaleFactor: 1,
    isMobile: true,
    hasTouch: true,
    colorScheme: entry.theme,
    reducedMotion: 'reduce',
  })
  await context.addInitScript(({ theme }) => {
    localStorage.setItem('valuesignal.ui-preferences.v1', JSON.stringify({ theme }))
  }, { theme: entry.theme })
  for (const target of pages) {
    const page = await context.newPage()
    await page.goto(`${origin}${target.path}`, { waitUntil: 'load' })
    if (target.prepare) await target.prepare(page)
    await page.locator(target.ready).first().waitFor({ state: 'visible' })
    if (target.settle) await target.settle(page)
    const validation = await page.evaluate((minimumTarget) => {
      const nav = document.querySelector('.mobile-nav')?.getBoundingClientRect()
      const interactive = [...document.querySelectorAll('button, input, select, [role="button"]')]
        .filter((element) => {
          const style = getComputedStyle(element)
          const rect = element.getBoundingClientRect()
          return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
        })
      const undersizedTargets = interactive.map((element) => {
        const rect = element.getBoundingClientRect()
        return { label: element.getAttribute('aria-label') || element.textContent?.trim().slice(0, 50) || element.tagName, width: rect.width, height: rect.height }
      }).filter((target) => target.width < minimumTarget || target.height < minimumTarget)
      const animated = [...document.querySelectorAll('*')].filter((element) => {
        const style = getComputedStyle(element)
        return style.animationName !== 'none' && parseFloat(style.animationDuration) > 0.001
      }).length
      return {
        innerWidth: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        noHorizontalOverflow: document.documentElement.scrollWidth <= window.innerWidth,
        mobileNavInsideViewport: Boolean(nav && nav.left >= 0 && nav.right <= window.innerWidth),
        undersizedTargets,
        reducedMotionStatic: animated === 0,
      }
    }, settings.interface.minimum_touch_target_px)
    const name = `${target.name}-${entry.width}-${entry.theme}.png`
    await page.screenshot({ path: new URL(name, outputDirectory).pathname })
    results.push({ ...entry, page: target.name, file: name, ...validation })
    await page.close()
  }
  await context.close()
}
await browser.close()

const failed = results.some((entry) => !entry.noHorizontalOverflow
  || !entry.mobileNavInsideViewport
  || entry.innerWidth !== entry.width
  || entry.undersizedTargets.length
  || !entry.reducedMotionStatic)
const report = {
  generated_at: new Date().toISOString(),
  result: failed ? 'fail' : 'pass',
  minimum_touch_target_px: settings.interface.minimum_touch_target_px,
  cases: results,
}
await writeFile(new URL('../pipeline/reports/mobile_visual_check.json', import.meta.url), `${JSON.stringify(report, null, 2)}\n`)
process.stdout.write(`${JSON.stringify(results, null, 2)}\n`)
if (failed) process.exitCode = 1
