import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { calculateAge, isValidBirthDate, RETIREMENT_AGES } from './age.js'
import modelSettings from '../../pipeline/config/settings.json'

export const PREFERENCES_KEY = 'valuesignal.ui-preferences.v1'

/**
 * Accent palette. `value` is the light-theme accent, `dark` the dark-theme one.
 *
 * `ink` and `inkDark` are the text color placed ON a filled accent surface, and
 * they differ per theme because the dark accents are light colors: white text on
 * any of them lands between 1.5:1 and 2.1:1, far below AA. Each `inkDark` clears
 * 8.9:1 against its own accent.
 *
 * Only --brand-primary is published per accent; --brand-secondary (the chart and
 * meter mark) is derived from it in variables.css so a new accent needs one
 * value per theme, not three.
 */
export const ACCENTS = {
  valuesignal: { label: 'ValueSignal Green', value: '#17513c', dark: '#7fe3b0', ink: '#ffffff', inkDark: '#07130d' },
  emerald: { label: 'Emerald', value: '#087f5b', dark: '#69dbb0', ink: '#ffffff', inkDark: '#04140e' },
  blue: { label: 'Blue', value: '#2463a6', dark: '#82b7ed', ink: '#ffffff', inkDark: '#08131f' },
  indigo: { label: 'Indigo', value: '#4b57a5', dark: '#aab3ff', ink: '#ffffff', inkDark: '#0d1024' },
  violet: { label: 'Violet', value: '#73509b', dark: '#c8a8e8', ink: '#ffffff', inkDark: '#170f21' },
  coral: { label: 'Coral', value: '#a94d45', dark: '#ffaaa2', ink: '#ffffff', inkDark: '#220b09' },
  amber: { label: 'Amber', value: '#8a6518', dark: '#e9c56b', ink: '#ffffff', inkDark: '#1d1503' },
  monochrome: { label: 'Monochrome', value: '#3f4942', dark: '#c7cec9', ink: '#ffffff', inkDark: '#10130f' },
}

export const DEFAULT_WIDGETS = [
  { id: 'portfolio-summary', label: 'Portfolio summary', visible: true, order: 0, size: 'full', locked: true },
  { id: 'performance-chart', label: 'Performance chart', visible: true, order: 1, size: 'full' },
  { id: 'metric-grid', label: 'Key metrics', visible: true, order: 2, size: 'full' },
  { id: 'top-signal', label: 'Top research signal', visible: true, order: 3, size: 'medium' },
  { id: 'action-needed', label: 'Action-needed summary', visible: true, order: 4, size: 'medium' },
  { id: 'allocation', label: 'Sector allocation', visible: true, order: 5, size: 'medium' },
  { id: 'watchlist-preview', label: 'Watchlist preview', visible: true, order: 6, size: 'medium' },
]

export const DEFAULT_PREFERENCES = {
  version: 5,
  theme: 'system',
  accentColor: 'valuesignal',
  surfaceStyle: 'outlined',
  cornerStyle: 'rounded',
  density: 'comfortable',
  numberFormat: 'automatic',
  privacyMode: false,
  chartStyle: 'area',
  chartLineWeight: 'standard',
  chartGrid: 'standard',
  defaultChartPeriod: '1M',
  defaultLandingPage: 'report',
  holdingSort: { key: 'allocation', direction: 'desc' },
  defaultBenchmark: 'SPY',
  defaultBenchmarks: ['SPY', 'QQQ', 'VTI'],
  suggestedActionsDefault: 'collapsed',
  mobileResearchView: 'visual',
  watchlistSizingMode: modelSettings.watchlist_setup.default_sizing_mode,
  forecast: { horizonYears: 5, recurringAnnual: 0, birthDate: '', currentAge: 30, retirementAge: 65 },
  chartAnimation: 'system',
  reducedMotion: 'system',
  higherContrast: false,
  largerChartLabels: false,
  widgets: DEFAULT_WIDGETS,
}

const PreferencesContext = createContext(null)

export function validatePreferences(raw) {
  if (!raw || typeof raw !== 'object') return DEFAULT_PREFERENCES
  const pick = (value, allowed, fallback) => allowed.includes(value) ? value : fallback
  const storedWidgets = Array.isArray(raw.widgets) ? raw.widgets : []
  const widgets = DEFAULT_WIDGETS.map((fallback, index) => {
    const stored = storedWidgets.find((item) => item?.id === fallback.id) || {}
    return {
      ...fallback,
      visible: fallback.locked ? true : stored.visible !== false,
      order: Number.isInteger(stored.order) ? stored.order : index,
      size: pick(stored.size, ['small', 'medium', 'large', 'full'], fallback.size),
    }
  }).sort((a, b) => a.order - b.order).map((item, order) => ({ ...item, order }))
  const birthDate = isValidBirthDate(raw.forecast?.birthDate) ? raw.forecast.birthDate : ''
  const calculatedAge = calculateAge(birthDate)
  const currentAge = calculatedAge ?? Math.max(0, Math.min(120, Number(raw.forecast?.currentAge) || 30))
  const retirementAge = pick(Number(raw.forecast?.retirementAge), RETIREMENT_AGES, 65)
  const allowedBenchmarks = ['SPY', 'QQQ', 'DIA', 'IWM', 'VTI', 'VEA', 'VWO', 'VXUS']
  const legacyBenchmark = pick(raw.defaultBenchmark, allowedBenchmarks, 'SPY')
  const storedBenchmarks = Array.isArray(raw.defaultBenchmarks)
    ? raw.defaultBenchmarks
    : [legacyBenchmark, 'QQQ', 'VTI']
  const defaultBenchmarks = [...new Set(storedBenchmarks.filter((symbol) => allowedBenchmarks.includes(symbol)))].slice(0, 3)
  if (!defaultBenchmarks.length) defaultBenchmarks.push('SPY')

  return {
    ...DEFAULT_PREFERENCES,
    ...raw,
    version: 5,
    theme: pick(raw.theme, ['system', 'light', 'dark'], 'system'),
    accentColor: ACCENTS[raw.accentColor] ? raw.accentColor : 'valuesignal',
    surfaceStyle: pick(raw.surfaceStyle, ['outlined', 'soft', 'elevated'], 'outlined'),
    cornerStyle: pick(raw.cornerStyle, ['compact', 'rounded', 'extra-rounded'], 'rounded'),
    density: pick(raw.density, ['compact', 'comfortable', 'spacious'], 'comfortable'),
    numberFormat: pick(raw.numberFormat, ['full', 'compact', 'automatic'], 'automatic'),
    chartStyle: pick(raw.chartStyle, ['line', 'area', 'step'], 'area'),
    chartLineWeight: pick(raw.chartLineWeight, ['thin', 'standard', 'bold'], 'standard'),
    chartGrid: pick(raw.chartGrid, ['minimal', 'standard', 'hidden'], 'standard'),
    defaultChartPeriod: pick(raw.defaultChartPeriod, ['1H', '1D', '1W', '1M', '3M', '6M', 'YTD', '1Y', 'All'], '1M'),
    defaultLandingPage: pick(raw.defaultLandingPage, ['report'], 'report'),
    holdingSort: {
      key: pick(raw.holdingSort?.key === 'gainPct' ? 'return' : raw.holdingSort?.key, ['allocation', 'ticker', 'company', 'signal', 'value', 'gain', 'return', 'score', 'rating', 'trend', 'shares', 'cost', 'price', 'purchaseDate'], 'allocation'),
      direction: pick(raw.holdingSort?.direction, ['asc', 'desc'], 'desc'),
    },
    defaultBenchmark: defaultBenchmarks[0],
    defaultBenchmarks,
    suggestedActionsDefault: pick(raw.suggestedActionsDefault, ['collapsed', 'expanded'], 'collapsed'),
    mobileResearchView: pick(raw.mobileResearchView, ['visual', 'detailed'], 'visual'),
    watchlistSizingMode: pick(raw.watchlistSizingMode, ['capped', 'inverse-volatility'], modelSettings.watchlist_setup.default_sizing_mode),
    forecast: {
      horizonYears: pick(Number(raw.forecast?.horizonYears), [1, 3, 5, 10, 15, 20, 25, 30], 5),
      recurringAnnual: Math.max(0, Number(raw.forecast?.recurringAnnual) || 0),
      birthDate,
      currentAge,
      retirementAge,
    },
    chartAnimation: pick(raw.chartAnimation, ['system', 'on', 'reduced', 'off'], 'system'),
    reducedMotion: pick(raw.reducedMotion, ['system', 'on', 'off'], 'system'),
    privacyMode: Boolean(raw.privacyMode),
    higherContrast: Boolean(raw.higherContrast),
    largerChartLabels: Boolean(raw.largerChartLabels),
    widgets,
  }
}

function readPreferences() {
  try { return validatePreferences(JSON.parse(localStorage.getItem(PREFERENCES_KEY))) }
  catch { return DEFAULT_PREFERENCES }
}

export function PreferencesProvider({ children }) {
  const [preferences, setPreferences] = useState(readPreferences)
  const [systemDark, setSystemDark] = useState(() => window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false)

  useEffect(() => {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!media) return undefined
    const update = (event) => setSystemDark(event.matches)
    media.addEventListener?.('change', update)
    return () => media.removeEventListener?.('change', update)
  }, [])

  const resolvedTheme = preferences.theme === 'system' ? (systemDark ? 'dark' : 'light') : preferences.theme

  useEffect(() => {
    const root = document.documentElement
    const accent = ACCENTS[preferences.accentColor]
    root.dataset.theme = resolvedTheme
    root.dataset.surface = preferences.surfaceStyle
    root.dataset.corners = preferences.cornerStyle
    root.dataset.density = preferences.density
    root.dataset.contrast = preferences.higherContrast ? 'high' : 'standard'
    root.dataset.motion = preferences.reducedMotion
    root.dataset.chartGrid = preferences.chartGrid
    root.dataset.chartWeight = preferences.chartLineWeight
    root.dataset.chartStyle = preferences.chartStyle
    root.dataset.chartAnimation = preferences.chartAnimation
    root.dataset.chartLabels = preferences.largerChartLabels ? 'large' : 'standard'
    const isDark = resolvedTheme === 'dark'
    // Only the primary is published. --brand-secondary, --accent-dim and
    // --series-stock derive from it in variables.css, so they stay in step with
    // whichever accent is active without three more inline writes.
    root.style.setProperty('--brand-primary', isDark ? accent.dark : accent.value)
    root.style.setProperty('--accent', isDark ? accent.dark : accent.value)
    root.style.setProperty('--accent-ink', isDark ? accent.inkDark : accent.ink)
    const themeMeta = document.getElementById('theme-color-meta')
    themeMeta?.setAttribute('content', isDark ? '#0b100e' : '#eceff0')
    try { localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences)) } catch { /* storage can be unavailable */ }
  }, [preferences, resolvedTheme])

  const value = useMemo(() => ({
    preferences,
    resolvedTheme,
    updatePreferences: (patch) => setPreferences((current) => validatePreferences({ ...current, ...patch })),
    setWidgets: (widgets) => setPreferences((current) => validatePreferences({ ...current, widgets })),
    resetAppearance: () => setPreferences((current) => validatePreferences({
      ...current,
      theme: DEFAULT_PREFERENCES.theme,
      accentColor: DEFAULT_PREFERENCES.accentColor,
      surfaceStyle: DEFAULT_PREFERENCES.surfaceStyle,
      cornerStyle: DEFAULT_PREFERENCES.cornerStyle,
      density: DEFAULT_PREFERENCES.density,
    })),
    resetAll: () => setPreferences(DEFAULT_PREFERENCES),
  }), [preferences, resolvedTheme])

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>
}

export function usePreferences() {
  const value = useContext(PreferencesContext)
  if (!value) throw new Error('usePreferences must be used within PreferencesProvider')
  return value
}

export function formatPreferenceMoney(value, mode = 'automatic') {
  if (!Number.isFinite(Number(value))) return '–'
  const number = Number(value)
  const compact = mode === 'compact' || (mode === 'automatic' && Math.abs(number) >= 100_000)
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD', notation: compact ? 'compact' : 'standard',
    minimumFractionDigits: compact ? 1 : 2, maximumFractionDigits: compact ? 1 : 2,
  }).format(number)
}
