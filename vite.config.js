import { defineConfig } from 'vite'
import { configDefaults } from 'vitest/config'
import react from '@vitejs/plugin-react'
import settings from './pipeline/config/settings.json' with { type: 'json' }

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: 'firebase-firestore',
              test: /node_modules[\\/]@firebase[\\/]firestore[\\/]/,
              maxSize: settings.build.firebase_chunk_max_bytes,
            },
            {
              name: 'firebase-webchannel',
              test: /node_modules[\\/]@firebase[\\/]webchannel-wrapper[\\/]/,
            },
            {
              name: 'firebase-auth',
              test: /node_modules[\\/]@firebase[\\/]auth[\\/]/,
            },
            {
              name: 'firebase',
              test: /node_modules[\\/](@firebase|firebase)[\\/]/,
            },
            {
              name: 'vendor',
              test: /node_modules[\\/]/,
            },
          ],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    // tests/e2e/** are @playwright/test specs, not vitest — Playwright and vitest both default
    // to matching `*.spec.*` files, so without this exclusion `npm test` would try (and fail)
    // to run the e2e specs under vitest's jsdom/globals runtime.
    exclude: [...configDefaults.exclude, 'tests/e2e/**'],
  },
})
