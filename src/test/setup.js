import '@testing-library/jest-dom/vitest'

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
