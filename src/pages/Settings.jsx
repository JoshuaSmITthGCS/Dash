import { useState } from 'react'
import { ACCENTS, DEFAULT_WIDGETS, usePreferences } from '../lib/PreferencesContext.jsx'
import Icon from '../components/Icons.jsx'
import { BENCHMARKS } from '../lib/portfolioAnalytics.js'
import { calculateAge, RETIREMENT_AGES } from '../lib/age.js'

const Choice = ({ active, children, onClick, preview }) => (
  <button type="button" className={`setting-choice${active ? ' active' : ''}`} aria-pressed={active} onClick={onClick}>
    {preview && <span className={`theme-preview ${preview}`} aria-hidden="true"><i /><i /><i /></span>}
    <span>{children}</span>
  </button>
)

function SelectRow({ id, label, description, value, onChange, children }) {
  return <div className="settings-row">
    <label htmlFor={id}><strong>{label}</strong>{description && <span>{description}</span>}</label>
    <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>{children}</select>
  </div>
}

function SwitchRow({ id, label, description, checked, onChange }) {
  return <div className="settings-row">
    <label htmlFor={id}><strong>{label}</strong>{description && <span>{description}</span>}</label>
    <label className="switch"><input id={id} type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /><span aria-hidden="true" /></label>
  </div>
}

export default function Settings() {
  const { preferences, updatePreferences, resetAppearance, resetAll, setWidgets } = usePreferences()
  const [announcement, setAnnouncement] = useState('')
  const calculatedAge = calculateAge(preferences.forecast.birthDate)
  const today = new Date()
  const maxBirthDate = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  const toggleBenchmark = (symbol) => {
    const selected = preferences.defaultBenchmarks
    const next = selected.includes(symbol)
      ? selected.filter((item) => item !== symbol)
      : [...selected, symbol].slice(0, 3)
    if (!next.length) {
      setAnnouncement('Keep at least one comparison benchmark selected.')
      return
    }
    updatePreferences({ defaultBenchmarks: next, defaultBenchmark: next[0] })
    setAnnouncement(`${next.join(', ')} selected for performance comparisons.`)
  }

  const resetEverything = () => {
    if (!window.confirm('Reset all appearance, dashboard, chart, and data-display preferences?')) return
    resetAll()
    setAnnouncement('All preferences reset to defaults.')
  }

  const resetDashboard = () => {
    setWidgets(DEFAULT_WIDGETS)
    setAnnouncement('Financial Report reset to defaults.')
  }

  return <div className="settings-page">
    <header className="page-head compact-page-head">
      <div><span className="eyebrow">Personalize ValueSignal</span><h1 className="page-title">Settings</h1><p className="page-sub">Appearance and data presentation stay on this device.</p></div>
    </header>
    <p className="sr-only" aria-live="polite">{announcement}</p>

    <section className="settings-card" aria-labelledby="appearance-heading">
      <header><div><span className="settings-icon"><Icon name="sun" /></span><div><h2 id="appearance-heading">Appearance</h2><p>Theme, accent, surfaces, and spacing.</p></div></div></header>
      <div className="settings-block">
        <span className="settings-label">Theme mode</span>
        <div className="theme-options">
          {['system', 'light', 'dark'].map((theme) => <Choice key={theme} active={preferences.theme === theme} preview={theme} onClick={() => updatePreferences({ theme })}>{theme[0].toUpperCase() + theme.slice(1)}</Choice>)}
        </div>
      </div>
      <div className="settings-block">
        <span className="settings-label">Accent color</span>
        <div className="accent-options">
          {Object.entries(ACCENTS).map(([id, accent]) => <button key={id} type="button" className={preferences.accentColor === id ? 'active' : ''} aria-pressed={preferences.accentColor === id} onClick={() => updatePreferences({ accentColor: id })}><i style={{ background: accent.value }} />{accent.label}</button>)}
        </div>
      </div>
      <SelectRow id="surface-style" label="Surface style" description="Outlined is the default wireframe treatment." value={preferences.surfaceStyle} onChange={(surfaceStyle) => updatePreferences({ surfaceStyle })}><option value="outlined">Outlined</option><option value="soft">Soft</option><option value="elevated">Elevated</option></SelectRow>
      <SelectRow id="corner-style" label="Corner style" value={preferences.cornerStyle} onChange={(cornerStyle) => updatePreferences({ cornerStyle })}><option value="compact">Compact</option><option value="rounded">Rounded</option><option value="extra-rounded">Extra rounded</option></SelectRow>
      <SelectRow id="density" label="Interface density" description="Touch targets always remain at least 44px." value={preferences.density} onChange={(density) => updatePreferences({ density })}><option value="compact">Compact</option><option value="comfortable">Comfortable</option><option value="spacious">Spacious</option></SelectRow>
    </section>

    <section className="settings-card" aria-labelledby="dashboard-heading">
      <header><div><span className="settings-icon"><Icon name="overview" /></span><div><h2 id="dashboard-heading">Financial Report</h2><p>Report modules are managed here, away from the daily reading view.</p></div></div></header>
      <div className="settings-row"><div><strong>Visible report widgets</strong><span>{preferences.widgets.filter((widget) => widget.visible).length} of {preferences.widgets.length} shown</span></div><a className="secondary-button compact" href="/?customize=1">Customize report</a></div>
      <div className="settings-row"><div><strong>Default landing page</strong><span>Cold starts and invalid destinations return to the Financial Report.</span></div><b className="settings-value">Report</b></div>
      <div className="settings-row"><div><strong>Reset report layout</strong><span>Restore widget visibility, order, and sizes.</span></div><button className="ghost-button" type="button" onClick={resetDashboard}>Reset report</button></div>
      <fieldset className="settings-row benchmark-settings"><legend><strong>Default benchmarks</strong><span>Select up to three ETF proxies. The first selected benchmark is primary for portfolio scoring.</span></legend><div className="benchmark-choice-grid">{BENCHMARKS.map((item) => { const selected = preferences.defaultBenchmarks.includes(item.symbol); const primary = preferences.defaultBenchmarks[0] === item.symbol; const atLimit = preferences.defaultBenchmarks.length >= 3; return <label key={item.symbol} className={selected ? 'selected' : ''}><input type="checkbox" checked={selected} disabled={!selected && atLimit} onChange={() => toggleBenchmark(item.symbol)} /><span><b>{item.symbol}</b><small>{item.label}{primary ? ' · Primary' : ''}</small></span></label> })}</div></fieldset>
      <SelectRow id="holding-sort" label="Default holdings order" value={preferences.holdingSort.key} onChange={(key) => updatePreferences({ holdingSort: { key, direction: key === 'ticker' ? 'asc' : 'desc' } })}><option value="allocation">Allocation, largest first</option><option value="ticker">Ticker, A–Z</option><option value="value">Value, largest first</option><option value="gain">Dollar gain, largest first</option><option value="return">Percent gain, largest first</option></SelectRow>
      <SelectRow id="actions-default" label="Suggested actions" value={preferences.suggestedActionsDefault} onChange={(suggestedActionsDefault) => updatePreferences({ suggestedActionsDefault })}><option value="collapsed">Collapsed by default</option><option value="expanded">Expanded by default</option></SelectRow>
    </section>

    <section className="settings-card" aria-labelledby="charts-heading">
      <header><div><span className="settings-icon"><Icon name="market" /></span><div><h2 id="charts-heading">Charts</h2><p>Defaults for supported financial visualizations.</p></div></div></header>
      <SelectRow id="chart-period" label="Default period" value={preferences.defaultChartPeriod} onChange={(defaultChartPeriod) => updatePreferences({ defaultChartPeriod })}>{['1D', '1W', '1M', '3M', '6M', '1Y', 'All'].map((period) => <option key={period}>{period}</option>)}</SelectRow>
      <SelectRow id="chart-style" label="Chart style" value={preferences.chartStyle} onChange={(chartStyle) => updatePreferences({ chartStyle })}><option value="line">Line</option><option value="area">Line with area fill</option><option value="step">Stepped line</option></SelectRow>
      <SelectRow id="chart-weight" label="Line weight" value={preferences.chartLineWeight} onChange={(chartLineWeight) => updatePreferences({ chartLineWeight })}><option value="thin">Thin</option><option value="standard">Standard</option><option value="bold">Bold</option></SelectRow>
      <SelectRow id="chart-grid" label="Grid visibility" value={preferences.chartGrid} onChange={(chartGrid) => updatePreferences({ chartGrid })}><option value="minimal">Minimal</option><option value="standard">Standard</option><option value="hidden">Hidden</option></SelectRow>
      <SelectRow id="chart-animation" label="Animation" value={preferences.chartAnimation} onChange={(chartAnimation) => updatePreferences({ chartAnimation })}><option value="system">System</option><option value="on">On</option><option value="reduced">Reduced</option><option value="off">Off</option></SelectRow>
    </section>

    <section className="settings-card" aria-labelledby="planning-heading">
      <header><div><span className="settings-icon"><Icon name="finances" /></span><div><h2 id="planning-heading">Planning simulation</h2><p>Outcome ranges resample consecutive historical monthly returns from your portfolio or selected benchmark.</p></div></div></header>
      <div className="settings-row"><label htmlFor="recurring-annual"><strong>Annual contribution</strong><span>Added in equal monthly installments across every simulated path.</span></label><input id="recurring-annual" type="number" min="0" step="100" value={preferences.forecast.recurringAnnual} onChange={(event) => updatePreferences({ forecast: { ...preferences.forecast, recurringAnnual: Math.max(0, Number(event.target.value)) } })} /></div>
      <div className="settings-row"><label htmlFor="birth-date"><strong>Birthdate</strong><span>Your age is calculated automatically and used only for retirement planning.</span></label><input id="birth-date" type="date" max={maxBirthDate} value={preferences.forecast.birthDate} onChange={(event) => updatePreferences({ forecast: { ...preferences.forecast, birthDate: event.target.value } })} /></div>
      <div className="settings-row"><div><strong>Current age</strong><span>{calculatedAge === null ? 'Add your birthdate to calculate your age.' : 'Calculated from your birthdate.'}</span></div><b className="settings-value">{calculatedAge === null ? 'Not set' : calculatedAge}</b></div>
      <SelectRow id="retirement-age" label="Retirement age" description="The report shows a 10th through 90th percentile range at this age." value={preferences.forecast.retirementAge} onChange={(retirementAge) => updatePreferences({ forecast: { ...preferences.forecast, retirementAge: Number(retirementAge) } })}>{RETIREMENT_AGES.map((age) => <option key={age} value={age}>Age {age}</option>)}</SelectRow>
      <div className="settings-row"><div><strong>Projection model</strong><span>5,000 paths use a 12-month historical block bootstrap. Simulated outcomes are not predictions.</span></div><b className="settings-value">Automatic</b></div>
      <SelectRow id="mobile-research" label="Mobile research view" value={preferences.mobileResearchView} onChange={(mobileResearchView) => updatePreferences({ mobileResearchView })}><option value="visual">Visual summary</option><option value="detailed">Detailed cards</option></SelectRow>
      <SelectRow id="watchlist-sizing-mode" label="Watchlist sizing method" description="Capped uses one ceiling per eligible name. Equal risk lowers dollar size as published volatility rises." value={preferences.watchlistSizingMode} onChange={(watchlistSizingMode) => updatePreferences({ watchlistSizingMode })}><option value="capped">Capped maximum</option><option value="inverse-volatility">Equal risk by volatility</option></SelectRow>
    </section>

    <section className="settings-card" aria-labelledby="display-heading">
      <header><div><span className="settings-icon"><Icon name="finances" /></span><div><h2 id="display-heading">Data display</h2><p>Formatting preferences never alter source values.</p></div></div></header>
      <SelectRow id="number-format" label="Number format" value={preferences.numberFormat} onChange={(numberFormat) => updatePreferences({ numberFormat })}><option value="full">Full values</option><option value="compact">Compact values</option><option value="automatic">Automatic</option></SelectRow>
      <SwitchRow id="privacy" label="Hide balances" description="Masks portfolio balances and chart tooltips while keeping percentages visible." checked={preferences.privacyMode} onChange={(privacyMode) => updatePreferences({ privacyMode })} />
    </section>

    <section className="settings-card" aria-labelledby="accessibility-heading">
      <header><div><span className="settings-icon"><Icon name="accessibility" /></span><div><h2 id="accessibility-heading">Accessibility</h2><p>System preferences remain the default.</p></div></div></header>
      <SelectRow id="reduced-motion" label="Reduced motion" value={preferences.reducedMotion} onChange={(reducedMotion) => updatePreferences({ reducedMotion })}><option value="system">System</option><option value="on">On</option><option value="off">Off</option></SelectRow>
      <SwitchRow id="contrast" label="Higher contrast" checked={preferences.higherContrast} onChange={(higherContrast) => updatePreferences({ higherContrast })} />
      <SwitchRow id="chart-labels" label="Larger chart labels" checked={preferences.largerChartLabels} onChange={(largerChartLabels) => updatePreferences({ largerChartLabels })} />
    </section>

    <section className="settings-card reset-card" aria-labelledby="reset-heading">
      <header><div><span className="settings-icon"><Icon name="sync" /></span><div><h2 id="reset-heading">Reset and defaults</h2><p>Resetting all settings requires confirmation.</p></div></div></header>
      <div className="settings-row"><span>Theme, accent, surfaces, corners, and density</span><button className="secondary-button compact" type="button" onClick={() => { resetAppearance(); setAnnouncement('Appearance reset to defaults.') }}>Reset appearance</button></div>
      <div className="settings-row"><span>Every local interface preference</span><button className="destructive-button compact" type="button" onClick={resetEverything}>Reset all settings</button></div>
    </section>
  </div>
}
