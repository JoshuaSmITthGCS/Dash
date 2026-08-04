import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  DEFAULT_WIDGETS,
  PREFERENCES_KEY,
  PreferencesProvider,
  usePreferences,
  validatePreferences,
} from './PreferencesContext.jsx'

function Harness() {
  const { preferences, resolvedTheme, updatePreferences, setWidgets } = usePreferences()
  return <div>
    <span data-testid="theme">{resolvedTheme}</span>
    <span data-testid="accent">{preferences.accentColor}</span>
    <span data-testid="visible">{preferences.widgets.filter((widget) => widget.visible).length}</span>
    <button onClick={() => updatePreferences({ theme: 'dark', accentColor: 'blue', privacyMode: true })}>Update</button>
    <button onClick={() => setWidgets(preferences.widgets.map((widget) => widget.id === 'top-signal' ? { ...widget, visible: false } : widget).reverse())}>Widgets</button>
  </div>
}

function installMatchMedia(initial = false) {
  let dark = initial
  const listeners = new Set()
  window.matchMedia = vi.fn(() => ({
    get matches() { return dark },
    addEventListener: (_name, listener) => listeners.add(listener),
    removeEventListener: (_name, listener) => listeners.delete(listener),
  }))
  return (matches) => { dark = matches; listeners.forEach((listener) => listener({ matches })) }
}

afterEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  vi.restoreAllMocks()
})

describe('interface preferences', () => {
  it('migrates malformed settings and preserves the required summary widget', () => {
    const value = validatePreferences({
      version: 0,
      theme: 'sepia',
      widgets: [{ id: 'portfolio-summary', visible: false }, { id: 'market-pulse', visible: false, order: 0, size: 'huge' }],
    })
    expect(value.version).toBe(2)
    expect(value.theme).toBe('system')
    expect(value.widgets).toHaveLength(DEFAULT_WIDGETS.length)
    expect(value.widgets.find((widget) => widget.id === 'portfolio-summary').visible).toBe(true)
    expect(value.widgets.some((widget) => widget.id === 'market-pulse')).toBe(false)
    expect(value.defaultLandingPage).toBe('report')
    expect(value.holdingSort).toEqual({ key: 'allocation', direction: 'desc' })
    expect(value.defaultBenchmarks).toEqual(['SPY', 'QQQ', 'VTI'])
  })

  it('follows live system-theme changes until the user selects an override', () => {
    const changeSystemTheme = installMatchMedia(false)
    render(<PreferencesProvider><Harness /></PreferencesProvider>)
    expect(screen.getByTestId('theme')).toHaveTextContent('light')
    act(() => changeSystemTheme(true))
    expect(screen.getByTestId('theme')).toHaveTextContent('dark')
    fireEvent.click(screen.getByRole('button', { name: 'Update' }))
    act(() => changeSystemTheme(false))
    expect(screen.getByTestId('theme')).toHaveTextContent('dark')
    expect(screen.getByTestId('accent')).toHaveTextContent('blue')
    expect(JSON.parse(localStorage.getItem(PREFERENCES_KEY)).privacyMode).toBe(true)
  })

  it('persists widget visibility and ordering', () => {
    installMatchMedia(false)
    render(<PreferencesProvider><Harness /></PreferencesProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'Widgets' }))
    const stored = JSON.parse(localStorage.getItem(PREFERENCES_KEY))
    expect(stored.widgets.find((widget) => widget.id === 'top-signal').visible).toBe(false)
    expect(stored.widgets.map((widget) => widget.order)).toEqual(stored.widgets.map((_, index) => index))
  })

  it('never accepts a retirement age earlier than the current age', () => {
    const value = validatePreferences({ forecast: { currentAge: 72, retirementAge: 60 } })
    expect(value.forecast.retirementAge).toBe(72)
  })

  it('keeps one to three unique supported benchmarks with the first as primary', () => {
    const value = validatePreferences({ defaultBenchmarks: ['QQQ', 'QQQ', 'NOPE', 'DIA', 'VTI', 'SPY'] })
    expect(value.defaultBenchmarks).toEqual(['QQQ', 'DIA', 'VTI'])
    expect(value.defaultBenchmark).toBe('QQQ')
  })
})
