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
]
