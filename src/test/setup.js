import '@testing-library/jest-dom/vitest'

// jsdom implements neither ResizeObserver nor real layout (getBoundingClientRect always
// returns zeros), so @tanstack/react-virtual's dynamic measureElement has nothing to observe
// and falls back to repeatedly treating every rendered row as 0-height, which makes its
// windowing math pick nonsensical indices instead of settling near scrollY. A no-op observer
// is the standard fix: the virtualizer then relies on estimateSize alone, which is exactly
// what it does in a real browser until the first ResizeObserver callback fires anyway.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

// Node 22 may expose an unusable experimental localStorage getter unless a backing file is
// configured. Tests need deterministic browser-style storage and enumerable keys.
const localStorageMock = {}
Object.defineProperties(localStorageMock, {
  length: { get() { return Object.keys(localStorageMock).length } },
  key: { value(index) { return Object.keys(localStorageMock)[index] ?? null } },
  getItem: { value(key) { return Object.prototype.hasOwnProperty.call(localStorageMock, key) ? localStorageMock[key] : null } },
  setItem: { value(key, value) { localStorageMock[String(key)] = String(value) } },
  removeItem: { value(key) { delete localStorageMock[key] } },
  clear: { value() { Object.keys(localStorageMock).forEach((key) => delete localStorageMock[key]) } },
})

Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, configurable: true })
Object.defineProperty(window, 'localStorage', { value: localStorageMock, configurable: true })

// Firebase initializes at module load: `src/lib/firebase.js` calls getAuth() as a side effect
// of being imported, and getAuth throws `auth/invalid-api-key` when VITE_FIREBASE_API_KEY is
// undefined. Any test that transitively imports `App.jsx` therefore fails in a checkout with
// no `.env.local` -- which is every CI run, and every fresh clone.
//
// These are placeholder values, never real credentials. They only need to be syntactically
// well-formed enough for initializeApp/getAuth to construct without throwing; no test makes a
// network call, and anything exercising real auth behaviour mocks the module outright. A real
// `.env.local` still wins, because Vite resolves those before this file runs.
for (const [key, value] of Object.entries({
  VITE_FIREBASE_API_KEY: 'test-api-key',
  VITE_FIREBASE_AUTH_DOMAIN: 'test.firebaseapp.com',
  VITE_FIREBASE_PROJECT_ID: 'test-project',
  VITE_FIREBASE_STORAGE_BUCKET: 'test-project.appspot.com',
  VITE_FIREBASE_MESSAGING_SENDER_ID: '1234567890',
  VITE_FIREBASE_APP_ID: '1:1234567890:web:testappid',
})) {
  if (!import.meta.env[key]) import.meta.env[key] = value
}
