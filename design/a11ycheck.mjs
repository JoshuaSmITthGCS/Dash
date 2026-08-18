import { chromium } from 'playwright-core'
const BASE = 'http://localhost:5175'
const b = await chromium.launch()
const p = await b.newPage({ viewport: { width: 1440, height: 1000 } })
await p.addInitScript(() => localStorage.setItem('valuesignal.ui-preferences.v1', JSON.stringify({ version: 5, theme: 'light' })))

// 1. skip link is the first stop
await p.goto(`${BASE}/`, { waitUntil: 'networkidle' }).catch(() => {})
await p.waitForTimeout(1500)
await p.keyboard.press('Tab')
console.log('first tab stop     :', await p.evaluate(() => document.activeElement?.textContent?.trim().slice(0, 40)))

// 2. walk the Picks page and open the first row's modal by keyboard
await p.goto(`${BASE}/screens/fast-growth`, { waitUntil: 'networkidle' }).catch(() => {})
await p.waitForTimeout(2000)
const opened = await p.evaluate(async () => {
  const btn = [...document.querySelectorAll('button')].find(b => /Open .* research/.test(b.getAttribute('aria-label') || ''))
  if (!btn) return 'no research button found'
  btn.focus(); btn.click()
  await new Promise(r => setTimeout(r, 600))
  const dialog = document.querySelector('[role="dialog"]')
  if (!dialog) return 'modal has no role=dialog'
  return {
    role: dialog.getAttribute('role'),
    ariaModal: dialog.getAttribute('aria-modal'),
    labelledby: !!dialog.getAttribute('aria-labelledby'),
    labelText: document.getElementById(dialog.getAttribute('aria-labelledby'))?.textContent,
    focusInside: dialog.contains(document.activeElement),
  }
})
console.log('modal semantics    :', JSON.stringify(opened))

// 3. Tab 40 times; focus must never escape the dialog
const escaped = await p.evaluate(async () => {
  const dialog = document.querySelector('[role="dialog"]')
  if (!dialog) return 'no dialog'
  for (let i = 0; i < 40; i++) {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    if (!dialog.contains(document.activeElement)) return `escaped at tab ${i + 1}`
  }
  return 'trapped for 40 tabs'
})
console.log('focus trap         :', escaped)

// 4. Escape closes and focus returns
const restored = await p.evaluate(async () => {
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  await new Promise(r => setTimeout(r, 400))
  return {
    closed: !document.querySelector('[role="dialog"]'),
    focusReturnedTo: document.activeElement?.getAttribute('aria-label') || document.activeElement?.tagName,
  }
})
console.log('escape + restore   :', JSON.stringify(restored))

// 5. any control with no accessible name, anywhere on this page
const unnamed = await p.evaluate(() => {
  const nodes = [...document.querySelectorAll('button, a[href], input, select, textarea')]
  return nodes.filter(n => {
    if (n.type === 'hidden') return false
    const text = (n.textContent || '').trim()
    const label = n.getAttribute('aria-label') || n.getAttribute('title')
    const byId = n.id && document.querySelector(`label[for="${CSS.escape(n.id)}"]`)
    const wrapped = n.closest('label')
    const labelledby = n.getAttribute('aria-labelledby')
    return !text && !label && !byId && !wrapped && !labelledby
  }).map(n => `${n.tagName}.${n.className || ''}`.slice(0, 60))
})
console.log('unnamed controls   :', unnamed.length, unnamed.slice(0, 5))
await b.close()
