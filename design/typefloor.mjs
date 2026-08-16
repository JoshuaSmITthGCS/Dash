// Type-floor sweep. DESIGN.md: "No text below 11px, anywhere, including SVG labels."
//
// Why this exists separately from a plain getComputedStyle sweep: an SVG with a fixed
// viewBox and width="100%" scales its contents. A <text fontSize="11"> inside
// viewBox="0 0 1080 360" rendered into a 900px container paints at 9.2px. A CSS-only
// sweep reads the *specified* 11 and passes it. This measures the rendered size by
// multiplying the specified size by the element's screen CTM scale.
//
//   node design/typefloor.mjs                       # default routes, three widths
//   ROUTES='[["/","home"]]' WIDTHS='1440' node design/typefloor.mjs
//
// Exits non-zero when anything renders below the floor, so CI can gate on it.

import { chromium } from '/Users/eyerise/.npm/_npx/1ac161d228dd2210/node_modules/playwright/index.mjs'

const BASE = process.env.BASE || 'http://localhost:5175'
const FLOOR = Number(process.env.FLOOR || 11)
const WIDTHS = (process.env.WIDTHS || '1440,1100,820').split(',').map(Number)
const ROUTES = JSON.parse(process.env.ROUTES || `[
  ["/?portfolioPreview=1", "home"],
  ["/portfolio?portfolioPreview=1", "portfolio"],
  ["/portfolio/performance?portfolioPreview=1", "portfolio-performance"],
  ["/research", "research"],
  ["/markets", "markets"]
]`)

const browser = await chromium.launch()
const findings = []

for (const [route, name] of ROUTES) {
  for (const width of WIDTHS) {
    const page = await browser.newPage({ viewport: { width, height: 1000 } })
    await page.goto(BASE + route, { waitUntil: 'networkidle' }).catch(() => {})
    await page.waitForTimeout(2200)
    // Audit collapsed sections in the state a reader actually sees them in. A closed
    // <details> still lays out a box, so measuring it shut reports the scale of content
    // nobody is looking at — and misses whatever it looks like once opened.
    await page.evaluate(() => document.querySelectorAll('details').forEach((el) => { el.open = true }))
    await page.waitForTimeout(700)
    const rows = await page.evaluate((floor) => {
      const out = []
      // `className` on an SVG element is an SVGAnimatedString, not a string, so read the
      // attribute directly and fall back to the nearest HTML ancestor that carries a class.
      const classOf = (el) => (el.ownerSVGElement || el.tagName === 'svg'
        ? el.getAttribute('class')
        : el.className?.toString()) || ''
      const ownerOf = (el) => {
        for (let node = el; node; node = node.parentElement) {
          const first = classOf(node).split(' ').filter(Boolean)[0]
          if (first) return first
        }
        return el.tagName
      }
      const push = (el, specified, rendered, kind) => {
        if (rendered >= floor - 0.05) return
        out.push({ kind, owner: ownerOf(el), specified, rendered: +rendered.toFixed(1), text: el.textContent.trim().slice(0, 24) })
      }
      document.querySelectorAll('body *').forEach((el) => {
        if (!el.textContent?.trim() || el.children.length) return
        if (el.ownerSVGElement) return
        push(el, parseFloat(getComputedStyle(el).fontSize), parseFloat(getComputedStyle(el).fontSize), 'dom')
      })
      document.querySelectorAll('svg text, svg tspan').forEach((el) => {
        if (!el.textContent?.trim()) return
        const specified = parseFloat(getComputedStyle(el).fontSize)
        const m = el.getScreenCTM()
        push(el, specified, specified * (m ? Math.hypot(m.b, m.d) : 1), 'svg')
      })
      return out
    }, FLOOR)
    await page.close()

    const grouped = new Map()
    for (const row of rows) {
      const key = `${row.kind}:${row.owner}`
      const seen = grouped.get(key)
      grouped.set(key, { ...row, count: (seen?.count || 0) + 1, rendered: Math.min(seen?.rendered ?? 99, row.rendered) })
    }
    const label = `${name} @ ${width}px`
    if (!grouped.size) { console.log(`ok   ${label}`); continue }
    console.log(`FAIL ${label}`)
    for (const row of grouped.values()) {
      console.log(`       ${row.kind.padEnd(4)} ${row.owner.padEnd(24)} x${String(row.count).padEnd(3)} specified ${row.specified}px -> renders ${row.rendered}px  "${row.text}"`)
      findings.push({ route: name, width, ...row })
    }
  }
}

await browser.close()
console.log(`\n${findings.length} violation group(s) below ${FLOOR}px.`)
process.exit(findings.length ? 1 : 0)
