import { chromium } from '/Users/eyerise/.npm/_npx/1ac161d228dd2210/node_modules/playwright/index.mjs'
const BASE = process.env.BASE || 'http://localhost:5175'
const routes = JSON.parse(process.env.ROUTES || '[["/","dashboard"]]')
const themes = (process.env.THEMES || 'light,dark').split(',')
const tag = process.env.TAG || ''
const b = await chromium.launch()
for (const [route, name] of routes) {
  for (const theme of themes) {
    const p = await b.newPage({ viewportSize: { width: 1440, height: 1000 }, deviceScaleFactor: 1 })
    const errs = []
    p.on('pageerror', e => errs.push(String(e).slice(0, 200)))
    p.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)) })
    await p.addInitScript(t => {
      localStorage.setItem('valuesignal.ui-preferences.v1', JSON.stringify({ version: 5, theme: t }))
    }, theme)
    await p.goto(BASE + route, { waitUntil: 'networkidle' }).catch(() => {})
    await p.waitForTimeout(1800)
    await p.screenshot({ path: `design/shots/${tag}${name}-${theme}.png`, fullPage: false })
    console.log(`${errs.length ? 'ERR ' : 'ok  '}${name}/${theme}${errs.length ? ' :: ' + errs.slice(0, 3).join(' | ') : ''}`)
    await p.close()
  }
}
await b.close()
