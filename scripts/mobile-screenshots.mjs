import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright-core'

const chrome = process.env.CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const baseUrl = process.env.MOBILE_SCREENSHOT_URL || 'http://127.0.0.1:5173/research?preview=1'
const outputDirectory = new URL('../docs/mobile-screenshots/', import.meta.url)
const cases = [
  { width: 390, height: 844, theme: 'light' },
  { width: 390, height: 844, theme: 'dark' },
  { width: 430, height: 932, theme: 'light' },
  { width: 430, height: 932, theme: 'dark' },
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
  })
  await context.addInitScript(({ theme }) => {
    localStorage.setItem('valuesignal.ui-preferences.v1', JSON.stringify({ theme }))
  }, { theme: entry.theme })
  const page = await context.newPage()
  await page.goto(baseUrl, { waitUntil: 'load' })
  await page.locator('.research-mobile-card').first().waitFor({ state: 'visible' })
  const validation = await page.evaluate(() => {
    const nav = document.querySelector('.mobile-nav')?.getBoundingClientRect()
    const toolbar = document.querySelector('.research-toolbar')?.getBoundingClientRect()
    const firstFilter = document.querySelector('.research-toolbar select')?.getBoundingClientRect()
    return {
      innerWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      noHorizontalOverflow: document.documentElement.scrollWidth <= window.innerWidth,
      mobileNavInsideViewport: Boolean(nav && nav.left >= 0 && nav.right <= window.innerWidth),
      filterUsesFullRow: Boolean(toolbar && firstFilter && firstFilter.width >= toolbar.width - 1),
    }
  })
  const name = `research-${entry.width}-${entry.theme}.png`
  await page.screenshot({ path: new URL(name, outputDirectory).pathname })
  results.push({ ...entry, file: name, ...validation })
  await context.close()
}
await browser.close()

if (results.some((entry) => !entry.noHorizontalOverflow || !entry.mobileNavInsideViewport || !entry.filterUsesFullRow || entry.innerWidth !== entry.width)) {
  console.error(JSON.stringify(results, null, 2))
  process.exitCode = 1
} else {
  console.log(JSON.stringify(results, null, 2))
}
