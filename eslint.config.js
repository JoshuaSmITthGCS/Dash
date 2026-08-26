import js from '@eslint/js'

const globals = Object.fromEntries([
  // browser
  'alert', 'Blob', 'caches', 'clients', 'confirm', 'console', 'crypto', 'document', 'fetch', 'FileReader', 'import.meta',
  'localStorage', 'MutationObserver', 'navigator', 'performance', 'requestAnimationFrame', 'Response', 'ResizeObserver',
  'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval',
  'Notification', 'TextEncoder', 'URL', 'URLSearchParams', 'window',
  // test runner
  'afterEach', 'beforeEach', 'describe', 'expect', 'it', 'vi',
].map((name) => [name, 'readonly']))

export default [
  // `.venv*` rather than `.venv`: a Python virtualenv ships vendored JavaScript (urllib3's
  // emscripten fetch worker, for one) written for a worker global scope, so ESLint flags it
  // as `'self' is not defined` and fails CI on code nobody here wrote. The exact-name ignore
  // missed a `.venv.py39.bak` backup directory and took the whole `site` job down with it.
  // `.claude/**`: installed agent skills vendor their own bundled JavaScript (UMD builds,
  // Playwright render scripts) written to other conventions. Linting third-party skill code
  // put 327 errors in front of the `site` job for code nobody here wrote.
  // `design/**`: Phase-0 direction mockups and their screenshot tooling — design artifacts,
  // not shipped source.
  { ignores: ['.venv*/**', 'dist/**', 'coverage/**', 'node_modules/**', '.claude/**', 'design/**'] },
  {
    files: ['**/*.{js,jsx}'],
    ...js.configs.recommended,
    languageOptions: {
      ...js.configs.recommended.languageOptions,
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals,
    },
  },
  {
    files: ['public/sw.js'],
    languageOptions: { globals: { self: 'readonly', clients: 'readonly' } },
  },
  {
    // Unimplemented connector stubs: the parameter names are the documented contract for
    // the eventual implementation, so they stay even though nothing reads them yet.
    files: ['src/lib/fidelityConnectorStub.js'],
    rules: { 'no-unused-vars': ['error', { args: 'none' }] },
  },
  {
    // The twelve-medium rebuild's 0f rule: `core/screens/*` compose exclusively from
    // `manifest.components` + `WallLabel` + the renderer + data hooks — never from the
    // pre-existing `src/pages/*` or top-level `src/components/*`. Classic (DESIGN.md §12) is
    // the sole, deliberate exception — it's the only medium permitted to reuse those existing
    // files, which is exactly why it's excluded here rather than the rule not existing at all.
    // The three-`../`-levels patterns match the literal relative-import depth every medium
    // subfolder (`components/`, `nav/`, `entry/`, `renderer/`) sits at from `src/`; a medium's
    // own local `./components/*` or `../components/*` import never matches this shape.
    files: ['src/mediums/**/*.{js,jsx}'],
    ignores: ['src/mediums/classic/**'],
    rules: {
      'no-restricted-imports': ['error', {
        patterns: [
          { group: ['../../../pages/*', '../../../../pages/*'], message: 'Only src/mediums/classic/** may import from src/pages/** (DESIGN.md §12 — the isolated Classic port).' },
          { group: ['../../../components/*', '../../../../components/*'], message: 'Only src/mediums/classic/** may import from the top-level src/components/** (DESIGN.md §12 — the isolated Classic port). A medium\'s own src/mediums/<id>/components/* is unaffected.' },
        ],
      }],
    },
  },
]
