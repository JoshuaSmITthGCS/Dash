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
    // v6 adds `medium` (the 12-medium rebuild) alongside the pre-existing fields below —
    // additive, not lossy: nothing a v5 blob held is dropped by the migration.
    expect(value.version).toBe(6)
    expect(value.medium).toBe('classic')
    expect(value.theme).toBe('system')
    expect(value.widgets).toHaveLength(DEFAULT_WIDGETS.length)
    expect(value.widgets.find((widget) => widget.id === 'portfolio-summary').visible).toBe(true)
    expect(value.widgets.some((widget) => widget.id === 'market-pulse')).toBe(false)
    expect(value.defaultLandingPage).toBe('report')
    expect(value.holdingSort).toEqual({ key: 'allocation', direction: 'desc' })
    expect(value.defaultBenchmarks).toEqual(['SPY', 'QQQ', 'VTI'])
    expect(value.watchlistSizingMode).toBe('capped')
  })

  it('accepts a valid medium and rejects an unknown one back to the default', () => {
    expect(validatePreferences({ medium: 'neon' }).medium).toBe('neon')
    expect(validatePreferences({ medium: 'not-a-medium' }).medium).toBe('classic')
  })

  it('only publishes the inline accent for a medium that accepts one (Classic today)', () => {
    installMatchMedia(false)
    render(<PreferencesProvider><Harness /></PreferencesProvider>)
    act(() => { fireEvent.click(screen.getByText('Update')) })
    expect(document.documentElement.style.getPropertyValue('--brand-primary')).not.toBe('')

    localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ ...JSON.parse(localStorage.getItem(PREFERENCES_KEY)), medium: 'neon' }))
    document.documentElement.style.removeProperty('--brand-primary')
    render(<PreferencesProvider><Harness /></PreferencesProvider>)
    expect(document.documentElement.style.getPropertyValue('--brand-primary')).toBe('')
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

  it('calculates age from birthdate and limits retirement age to supported options', () => {
    const value = validatePreferences({ forecast: { birthDate: '2000-01-01', currentAge: 72, retirementAge: 47 } })
    expect(value.forecast.currentAge).toBe(new Date().getFullYear() - 2000)
    expect(value.forecast.retirementAge).toBe(65)
  })

  it('keeps one to three unique supported benchmarks with the first as primary', () => {
    const value = validatePreferences({ defaultBenchmarks: ['QQQ', 'QQQ', 'NOPE', 'DIA', 'VTI', 'SPY'] })
    expect(value.defaultBenchmarks).toEqual(['QQQ', 'DIA', 'VTI'])
    expect(value.defaultBenchmark).toBe('QQQ')
  })

  it('keeps year-to-date as a supported home chart range', () => {
    expect(validatePreferences({ defaultChartPeriod: 'YTD' }).defaultChartPeriod).toBe('YTD')
  })

  it('keeps last hour as a supported chart range', () => {
    expect(validatePreferences({ defaultChartPeriod: '1H' }).defaultChartPeriod).toBe('1H')
  })
})
