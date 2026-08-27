/**
 * Determinism helpers shared by every e2e spec (DESIGN.md / the rebuild plan's Phase 3 section):
 * frozen data fixtures served via `page.route`, a frozen `Date`, and seeded preferences/entry
 * state — so a screenshot of the same medium never churns between runs and never depends on
 * live pipeline output. `networkidle`/`waitForTimeout` are banned in this directory (enforced by
 * eslint.config.js); every spec instead waits on `[data-app-ready="true"]`.
 */
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const FIXTURES_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'fixtures', 'data')

// The frozen "now" every spec runs against — chosen to postdate every fixture's own
// `generated_at` so nothing reads as "from the future."
export const FROZEN_NOW = '2026-08-26T12:00:00.000Z'

export const PREFERENCES_KEY = 'valuesignal.ui-preferences.v1'

/** Routes every `/data/**` request to the matching trimmed, committed fixture file. */
export async function mockDataRoutes(page) {
  await page.route('**/data/**', async (route) => {
    const url = new URL(route.request().url())
    const relative = url.pathname.replace(/^.*\/data\//, '')
    const filePath = path.join(FIXTURES_DIR, relative)
    try {
      await route.fulfill({ path: filePath, contentType: 'application/json' })
    } catch {
      await route.fulfill({ status: 404, body: '{}', contentType: 'application/json' })
    }
  })
}

/** Freezes `Date`/`Date.now` before any page script runs — screenshots never show a moving clock. */
export async function freezeClock(page, iso = FROZEN_NOW) {
  await page.addInitScript((frozenIso) => {
    const FrozenDate = class extends Date {
      constructor(...args) { super(...(args.length ? args : [frozenIso])) }
      static now() { return new Date(frozenIso).getTime() }
    }
    Date = FrozenDate
  }, iso)
}

/**
 * Seeds `localStorage`'s preferences blob and, when `entrySkip` is true, the medium's own
 * `sessionStorage` entry-seen key — both before any app script runs, via `addInitScript` (never
 * a post-navigation `page.evaluate`, which would race the app's own first paint).
 */
export async function seedPreferences(page, { medium, entrySkip = true, extra = {} } = {}) {
  await page.addInitScript(({ key, medium: mediumId, skip, extraPrefs }) => {
    const blob = { version: 6, medium: mediumId, entrySkip: skip ? { [mediumId]: true } : {}, ...extraPrefs }
    window.localStorage.setItem(key, JSON.stringify(blob))
    if (skip) window.sessionStorage.setItem(`valuesignal.entry-seen.${mediumId}`, '1')
  }, { key: PREFERENCES_KEY, medium, skip: entrySkip, extraPrefs: extra })
}

/** The one call every spec makes before `page.goto` — mocks data, freezes time, seeds prefs. */
export async function primeDeterministicPage(page, { medium, entrySkip = true, extra = {} } = {}) {
  await mockDataRoutes(page)
  await freezeClock(page)
  await seedPreferences(page, { medium, entrySkip, extra })
}

/** Waits for MediumShell's own readiness flag — never networkidle, never waitForTimeout. */
export async function waitForAppReady(page) {
  await page.locator('[data-app-ready="true"]').first().waitFor({ state: 'attached' })
}
