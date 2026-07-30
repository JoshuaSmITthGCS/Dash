import js from '@eslint/js'

const globals = Object.fromEntries([
  // browser
  'alert', 'Blob', 'confirm', 'console', 'document', 'fetch', 'FileReader', 'import.meta',
  'localStorage', 'navigator', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval',
  'URL', 'window',
  // test runner
  'afterEach', 'beforeEach', 'describe', 'expect', 'it', 'vi',
].map((name) => [name, 'readonly']))

export default [
  { ignores: ['.venv/**', 'dist/**', 'coverage/**', 'node_modules/**'] },
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
    // Unimplemented connector stubs: the parameter names are the documented contract for
    // the eventual implementation, so they stay even though nothing reads them yet.
    files: ['src/lib/fidelityConnectorStub.js'],
    rules: { 'no-unused-vars': ['error', { args: 'none' }] },
  },
]
