// Phase 3 harness (rebuild plan). Exact-pinned to `@playwright/test@1.62.1`, matching the
// existing `playwright-core` devDependency's version.
//
// Project shape: the plan calls for "projects = 12 mediums × {390, 430}" — that matrix exists
// here, but scoped to `visual.spec.mjs` only, since per-project baseline folders are what gives
// each medium×viewport its own screenshot directory. The other six spec files
// (parity/renderer/motion/rules/a11y/budget) don't need per-viewport pixel isolation, so they
// run once under a single default project and loop over `MEDIUM_IDS` internally — running every
// non-visual assertion 24 times over would be pure overhead, not more coverage.
import { defineConfig, devices } from '@playwright/test'
import { MEDIUM_IDS, VIEWPORTS } from './tests/e2e/utils/mediums.mjs'

const PORT = 5175
const CHROMIUM_EXECUTABLE = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined

const visualProjects = MEDIUM_IDS.flatMap((mediumId) =>
  VIEWPORTS.map((viewport) => ({
    name: `visual-${mediumId}-${viewport.name}`,
    testMatch: /visual\.spec\.mjs/,
    use: {
      ...devices['Desktop Chrome'],
      viewport: { width: viewport.width, height: viewport.height },
      reducedMotion: 'reduce',
      launchOptions: CHROMIUM_EXECUTABLE ? { executablePath: CHROMIUM_EXECUTABLE } : undefined,
    },
    metadata: { mediumId, viewport: viewport.name },
  }))
)

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  timeout: 30_000,
  expect: {
    timeout: 10_000,
    toHaveScreenshot: { maxDiffPixelRatio: 0.001, animations: 'disabled' },
  },
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: 'retain-on-failure',
  },
  webServer: {
    // `--mode e2e` picks up `.env.e2e`'s placeholder Firebase config — without it the built
    // bundle throws `auth/invalid-api-key` at module load and never renders anything (see
    // `.env.e2e`'s own comment; this was invisible until this harness first opened `dist/` in
    // a real browser).
    command: `npm run build:e2e && npx vite preview --port ${PORT} --strictPort`,
    port: PORT,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    ...visualProjects,
    {
      // reducedMotion defaults to 'reduce' here too; motion.spec.mjs's non-reduced-motion
      // assertion (#8) overrides it per-test via `page.emulateMedia()` rather than a second
      // project, so every other spec stays on the same reduced baseline by default.
      name: 'default',
      testIgnore: /visual\.spec\.mjs/,
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 390, height: 844 },
        reducedMotion: 'reduce',
        launchOptions: CHROMIUM_EXECUTABLE ? { executablePath: CHROMIUM_EXECUTABLE } : undefined,
      },
    },
  ],
})
