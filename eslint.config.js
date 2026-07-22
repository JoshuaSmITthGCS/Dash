import js from '@eslint/js'

const globals = Object.fromEntries([
  'console', 'document', 'fetch', 'import.meta', 'localStorage', 'setTimeout', 'window',
  'describe', 'expect', 'it', 'vi',
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
]
