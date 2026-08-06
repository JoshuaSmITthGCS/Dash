import { defineConfig } from 'vite'
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
  },
})
