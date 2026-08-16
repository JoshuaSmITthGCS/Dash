import { chromium } from '/Users/eyerise/.npm/_npx/1ac161d228dd2210/node_modules/playwright/index.mjs'
const b = await chromium.launch()
const files = ['A-ledger','B-tape','C-studio','D-approved']
for (const f of files) {
  for (const theme of ['light','dark']) {
    const p = await b.newPage({ viewportSize:{width:1440,height:1000}, deviceScaleFactor:2 })
    const errs = []
    p.on('pageerror', e => errs.push(String(e)))
    p.on('console', m => { if (m.type()==='error') errs.push(m.text()) })
    await p.goto(`file://${process.cwd()}/${f}.html`)
    if (theme==='dark') await p.click('#themeBtn')
    await p.waitForTimeout(900)
    await p.screenshot({ path:`shots/${f}-${theme}.png`, fullPage:true })
    await p.setViewportSize({width:1440,height:1000})
    await p.screenshot({ path:`shots/${f}-${theme}-fold.png` })
    if (errs.length) console.log(`!! ${f}/${theme}`, errs.slice(0,4))
    else console.log(`ok ${f}/${theme}`)
    await p.close()
  }
}
await b.close()
