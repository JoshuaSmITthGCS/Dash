import { lazy, Suspense, useEffect, useState, useCallback } from 'react'
import { Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import { DataStatus } from './components/DataStatus.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import Icon from './components/Icons.jsx'
import { MobileSheet } from './components/MobileSheet.jsx'
import { AuthProvider as FirebaseAuthProvider, useAuth } from './lib/FirebaseAuthContext.jsx'
import { usePreferences } from './lib/PreferencesContext.jsx'
import ModelVersionFooter from './components/ModelVersionFooter.jsx'
import AlertBadge from './components/AlertBadge.jsx'

// Dashboard is the landing route on a phone opening this cold on cellular, so it ships eager.
// Every other page loads on demand – keeps first paint off the weight of pages the visit may
// never touch (Finances, ETF comparisons, shadow portfolios, congress trades, etc).
const loadPicks = () => import('./pages/Picks.jsx')
const loadPortfolio = () => import('./pages/Portfolio.jsx')
const Picks = lazy(loadPicks)
const PolicyRadar = lazy(() => import('./pages/PolicyRadar.jsx'))
const Watchlist = lazy(() => import('./pages/Watchlist.jsx'))
const Methodology = lazy(() => import('./pages/Methodology.jsx'))
const Glossary = lazy(() => import('./pages/Glossary.jsx'))
const Portfolio = lazy(loadPortfolio)
const Finances = lazy(() => import('./pages/Finances.jsx'))
const Planning = lazy(() => import('./pages/Planning.jsx'))
const ResearchScreen = lazy(() => import('./pages/ResearchScreen.jsx'))
const SwingScreen = lazy(() => import('./pages/SwingScreen.jsx'))
const FastGrowthScreen = lazy(() => import('./pages/FastGrowthScreen.jsx'))
const OptionsScreen = lazy(() => import('./pages/OptionsScreen.jsx'))
const StrategyScreen = lazy(() => import('./pages/StrategyScreen.jsx'))
const ThemeExposureScreen = lazy(() => import('./pages/ThemeExposureScreen.jsx'))
const ShadowPortfolios = lazy(() => import('./pages/ShadowPortfolios.jsx'))
const BacktestComparison = lazy(() => import('./pages/BacktestComparison.jsx'))
const LiveValidation = lazy(() => import('./pages/LiveValidation.jsx'))
const EarlySessionResearch = lazy(() => import('./pages/EarlySessionResearch.jsx'))
const CongressTrades = lazy(() => import('./pages/CongressTrades.jsx'))
const InstitutionalActivity = lazy(() => import('./pages/InstitutionalActivity.jsx'))
const Settings = lazy(() => import('./pages/Settings.jsx'))
const Search = lazy(() => import('./pages/Search.jsx'))
const Diversification = lazy(() => import('./pages/Diversification.jsx'))
const Insights = lazy(() => import('./pages/Insights.jsx'))
const Alerts = lazy(() => import('./pages/Alerts.jsx'))
const Markets = lazy(() => import('./pages/Markets.jsx'))

// Flat strategy paths that predate the Options tab, kept alive as redirects into it.
const OPTIONS_STRATEGY_IDS = [
  'short-term-trades', 'covered-call', 'cash-secured-put', 'protective-put',
  'collar', 'vertical-spread', 'advanced-strategies',
]

const NAV_GROUPS = [
  {
    label: 'Research', icon: 'research',
    items: [
      { to: '/research', label: 'Research overview', icon: 'research' },
      { to: '/search', label: 'Stock search', icon: 'search' },
      { to: '/screens/swing', label: 'Swing screen', icon: 'market' },
      { to: '/screens/fast-growth', label: 'Growth screens', icon: 'market' },
      { to: '/screens/options', label: 'Options screens', icon: 'market' },
      { to: '/screens/themes', label: 'Theme exposure', icon: 'research' },
      { to: '/screens/politics', label: 'Congress trades', icon: 'method' },
      { to: '/screens/institutional', label: 'Institutional activity', icon: 'method' },
      { to: '/screens/early-session', label: 'Early session', icon: 'market' },
      { to: '/screens/shadow', label: 'Shadow portfolios', icon: 'market' },
    ],
  },
  {
    label: 'Figures', icon: 'market',
    items: [
      { to: '/portfolio/insights', label: 'Portfolio figures', icon: 'market' },
      { to: '/portfolio/diversification', label: 'Diversification', icon: 'portfolio' },
      { to: '/screens/backtests', label: 'Backtest comparison', icon: 'market' },
      { to: '/screens/validation', label: 'Live validation', icon: 'market' },
      { to: '/finances', label: 'Financial stats', icon: 'finances' },
      { to: '/planning', label: 'Planning figures', icon: 'finances' },
    ],
  },
]

const NAV_AFTER_GROUPS = [
  { to: '/markets', label: 'Markets', icon: 'market' },
  // /market is the news reader, not a second markets page. It had no nav entry and
  // was reachable only from one Dashboard link; the label says what it actually is.
  { to: '/market', label: 'News', icon: 'method' },
  { to: '/portfolio', label: 'Portfolio', icon: 'portfolio' },
  { to: '/watchlist', label: 'Watchlist', icon: 'watchlist' },
  { to: '/alerts', label: 'Alerts', icon: 'bell' },
  { to: '/methodology', label: 'Methodology', icon: 'method' },
  { to: '/glossary', label: 'Glossary', icon: 'glossary' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
]

const ROUTE_PRELOADERS = {
  '/research': loadPicks,
  '/portfolio': loadPortfolio,
}

function preloadRoute(path) {
  ROUTE_PRELOADERS[path]?.().catch(() => {
    // Navigation still owns recovery if a speculative preload loses its connection.
  })
}

function RouteLoading({ pathname }) {
  const label = pathname.startsWith('/portfolio')
    ? 'Opening your portfolio'
    : pathname.startsWith('/research') ? 'Opening research' : 'Opening page'
  return (
    <div className="route-loading" role="status" aria-live="polite">
      <span className="loading-mark" aria-hidden="true" />
      <strong>{label}…</strong>
      <span>Loading the latest saved view.</span>
    </div>
  )
}

function CloudDataUnavailable({ feature }) {
  const { authError, retryAuth } = useAuth()
  return <section className="report-empty-state">
    <span className="eyebrow">{feature}</span>
    <h1>Cloud data is offline</h1>
    <p>{authError || 'Firebase is still connecting to your solo workspace.'}</p>
    <button type="button" className="primary-button" onClick={retryAuth}>Reconnect Firebase</button>
  </section>
}

export const MOBILE_NAV = [
  { to: '/', label: 'Home', icon: 'overview', end: true },
  { to: '/portfolio', label: 'Portfolio', icon: 'portfolio' },
  { to: '/research', label: 'Research', icon: 'research' },
  { to: '/markets', label: 'Markets', icon: 'market' },
  { action: 'menu', label: 'More', icon: 'more' },
]

// Routes already one tap away on the mobile tab bar - left out of the "More" menu so it
// isn't just a second way to reach the same four screens.
const MOBILE_TAB_PATHS = new Set(MOBILE_NAV.filter((item) => item.to).map((item) => item.to))

function isMobileTabActive(pathname) {
  if (pathname === '/') return true
  return [...MOBILE_TAB_PATHS].some((to) => to !== '/' && (pathname === to || pathname.startsWith(`${to}/`)))
}

function MobileMoreMenu({ open, onClose }) {
  const moreGroups = [
    ...NAV_GROUPS.map((group) => ({ ...group, items: group.items.filter((item) => !MOBILE_TAB_PATHS.has(item.to)) })),
    { label: 'More', icon: 'more', items: NAV_AFTER_GROUPS.filter((item) => !MOBILE_TAB_PATHS.has(item.to)) },
  ]
  return (
    <MobileSheet open={open} title="More" onClose={onClose} className="mobile-more-sheet">
      <nav className="mobile-more-nav" aria-label="More screens">
        {moreGroups.map((group) => (
          <div className="mobile-more-group" key={group.label}>
            <span className="mobile-more-group-title"><Icon name={group.icon} size={14} />{group.label}</span>
            {group.items.map((item) => (
              <NavLink key={item.to} to={item.to} onClick={onClose}
                onPointerEnter={() => preloadRoute(item.to)} onFocus={() => preloadRoute(item.to)}
                className={({ isActive }) => `mobile-more-link${isActive ? ' active' : ''}`}>
                <Icon name={item.icon} size={16} /><span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </MobileSheet>
  )
}

function ProfilePanel() {
  const { currentUser, userProfile } = useAuth()
  if (!currentUser) return null

  return (
    <div className="profile-panel">
      <div className="avatar" aria-hidden="true">
        {(userProfile?.displayName || 'J').slice(0, 1).toUpperCase()}
      </div>
      <div className="profile-copy">
        <strong>{userProfile?.displayName || 'Josh'}</strong>
        <span>ValueSignal member</span>
      </div>
      <NavLink className="icon-button" to="/settings" aria-label="Interface settings"><Icon name="settings" /></NavLink>
    </div>
  )
}

function useSidebarCollapsed() {
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem('vs-sidebar-collapsed') === '1' } catch { return false }
  })
  const toggle = useCallback(() => {
    setCollapsed(prev => {
      const next = !prev
      try { localStorage.setItem('vs-sidebar-collapsed', next ? '1' : '0') } catch { /* storage unavailable */ }
      return next
    })
  }, [])
  return [collapsed, toggle]
}

function AppContent() {
  const { currentUser, loading, authError, retryAuth, userProfile } = useAuth()
  const { preferences, updatePreferences } = usePreferences()
  const { pathname, search } = useLocation()
  const [sidebarCollapsed, toggleSidebar] = useSidebarCollapsed()
  const [moreMenuOpen, setMoreMenuOpen] = useState(false)
  const portfolioPreview = import.meta.env.DEV && new URLSearchParams(search).get('portfolioPreview') === '1'

  useEffect(() => { setMoreMenuOpen(false) }, [pathname])

  useEffect(() => {
    const preload = () => {
      preloadRoute('/research')
      preloadRoute('/portfolio')
    }
    if ('requestIdleCallback' in window) {
      const id = window.requestIdleCallback(preload, { timeout: 2500 })
      return () => window.cancelIdleCallback(id)
    }
    const id = window.setTimeout(preload, 1200)
    return () => window.clearTimeout(id)
  }, [])

  const cloudPage = (feature, pathname, page) => loading
    ? <RouteLoading pathname={pathname} />
    : currentUser || (portfolioPreview && feature.startsWith('Portfolio')) ? page : <CloudDataUnavailable feature={feature} />

  return (
    <div className={`shell${sidebarCollapsed ? ' sidebar-collapsed' : ''}`} data-auth-resolving={loading ? 'true' : 'false'}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className="rail" aria-label="Primary navigation">
        <div className="rail-top">
          <NavLink to="/" className="brand-lockup" aria-label="ValueSignal overview">
            <span className="brand-mark">V</span>
            {!sidebarCollapsed && <span><span className="brand">Value<em>Signal</em></span></span>}
          </NavLink>
          <button className="sidebar-toggle" onClick={toggleSidebar} aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
            <Icon name="chevron" size={14} />
          </button>
        </div>
        <nav className="desktop-nav">
          <NavLink to="/" end className={({ isActive }) => `navlink${isActive ? ' active' : ''}`} title={sidebarCollapsed ? 'Home' : undefined}><Icon name="overview" size={18} />{!sidebarCollapsed && <span>Home</span>}</NavLink>
          {!sidebarCollapsed && NAV_GROUPS.map((group) => {
            const active = group.items.some((item) => pathname === item.to || pathname.startsWith(`${item.to}/`))
            return <details className={`nav-group${active ? ' active' : ''}`} key={group.label} open={active || undefined}>
              <summary><Icon name={group.icon} size={18} /><span>{group.label}</span><Icon name="chevron" size={13} className="nav-group-chevron" /></summary>
              <div>{group.items.map((item) => <NavLink key={item.to} to={item.to} onPointerEnter={() => preloadRoute(item.to)} onFocus={() => preloadRoute(item.to)} className={({ isActive }) => `nav-sublink${isActive ? ' active' : ''}`}><Icon name={item.icon} size={15} /><span>{item.label}</span></NavLink>)}</div>
            </details>
          })}
          {NAV_AFTER_GROUPS.map((item) => <NavLink key={item.to} to={item.to} onPointerEnter={() => preloadRoute(item.to)} onFocus={() => preloadRoute(item.to)} className={({ isActive }) => `navlink${isActive ? ' active' : ''}`} title={sidebarCollapsed ? item.label : undefined}><Icon name={item.icon} size={18} />{!sidebarCollapsed && <span>{item.label}</span>}</NavLink>)}
        </nav>
        {!sidebarCollapsed && <div className="rail-note">
          <span>Research framework</span>
          Fundamentals first. Evidence, not hype.
        </div>}
        {!sidebarCollapsed && <ProfilePanel />}
      </aside>

      <main id="main-content" className="content" tabIndex="-1">
        <header className="mobile-header">
          <NavLink to="/" className="brand-lockup" aria-label="ValueSignal overview">
            <span className="brand-mark">V</span>
            <span className="brand">Value<em>Signal</em></span>
          </NavLink>
          <div className="mobile-profile">
            {currentUser && <AlertBadge />}
            <button className="icon-button" onClick={() => updatePreferences({ privacyMode: !preferences.privacyMode })}
              aria-pressed={preferences.privacyMode} aria-label={preferences.privacyMode ? 'Show balances' : 'Hide balances'}>
              <Icon name={preferences.privacyMode ? 'eye-off' : 'eye'} />
            </button>
            <NavLink className="icon-button" to="/settings" aria-label="Settings"><Icon name="settings" /></NavLink>
            <div className="avatar" aria-label={`Profile: ${userProfile?.displayName || 'Investor'}`}>
              {(userProfile?.displayName || 'V').slice(0, 1).toUpperCase()}
            </div>
          </div>
        </header>
        {authError && <div className="cloud-session-error" role="alert">
          <span><strong>Cloud data is offline.</strong> Portfolio, finances, and alerts could not connect to Firebase.</span>
          <button type="button" className="text-button" onClick={retryAuth}>Try again</button>
        </div>}
        <DataStatus />
        <ErrorBoundary key={pathname} pageName={pathname.startsWith('/portfolio') ? 'Portfolio' : pathname.startsWith('/research') ? 'Research' : 'This page'}>
        <Suspense fallback={<RouteLoading pathname={pathname} />}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/research" element={<Picks />} />
          <Route path="/search" element={<Search />} />
          <Route path="/market" element={<PolicyRadar />} />
          <Route path="/markets" element={<Markets />} />
          <Route path="/portfolio" element={cloudPage('Portfolio', '/portfolio', <Portfolio view="summary" />)} />
          <Route path="/portfolio/performance" element={cloudPage('Portfolio performance', '/portfolio', <Portfolio view="performance" />)} />
          <Route path="/portfolio/data-overview" element={cloudPage('Portfolio data overview', '/portfolio', <Portfolio view="data" />)} />
          <Route path="/portfolio/diversification" element={cloudPage('Portfolio diversification', '/portfolio', <Diversification />)} />
          <Route path="/portfolio/insights" element={cloudPage('Portfolio insights', '/portfolio', <Insights />)} />
          <Route path="/finances" element={cloudPage('Finances', '/finances', <Finances />)} />
          <Route path="/planning" element={cloudPage('Planning', '/planning', <Planning />)} />
          <Route path="/screens/swing" element={<SwingScreen />} />
          <Route path="/screens/fast-growth" element={<FastGrowthScreen />} />
          <Route path="/screens/options" element={<OptionsScreen />} />
          <Route path="/screens/options/short-term-trades" element={<StrategyScreen id="short-term-trades" />} />
          <Route path="/screens/options/covered-call" element={<StrategyScreen id="covered-call" />} />
          <Route path="/screens/options/cash-secured-put" element={<StrategyScreen id="cash-secured-put" />} />
          <Route path="/screens/options/protective-put" element={<StrategyScreen id="protective-put" />} />
          <Route path="/screens/options/collar" element={<StrategyScreen id="collar" />} />
          <Route path="/screens/options/vertical-spread" element={<StrategyScreen id="vertical-spread" />} />
          <Route path="/screens/options/advanced-strategies" element={<StrategyScreen id="advanced-strategies" />} />
          {OPTIONS_STRATEGY_IDS.map((id) => (
            <Route key={id} path={`/screens/${id}`}
              element={<Navigate to={`/screens/options/${id}`} replace />} />
          ))}
          <Route path="/screens/momentum" element={<ResearchScreen file="screens/momentum.json" eyebrow="Monthly sleeve" title="Momentum" description="Exact month-end, skip-month price momentum with liquidity gates, hysteresis, and portfolio-level risk controls." />} />
          <Route path="/screens/quality-value" element={<ResearchScreen file="screens/quality-value.json" eyebrow="Quarterly screen" title="Quality at valuation lows" description="Cheapness versus applicable own-history multiples, peer value, business quality, distress, and forward-revision gates. The own-history window is only as deep as the collected point-in-time record, and every row publishes the window it was measured over." />} />
          <Route path="/screens/earnings" element={<ResearchScreen file="screens/earnings-timeliness.json" eyebrow="One-to-three-month horizon" title="Earnings timeliness" description="Point-in-time revisions, earnings information, price confirmation, industry breadth, and tradability–kept separate from structural quality." />} />
          <Route path="/screens/matrix" element={<ResearchScreen file="screens/structural-tactical.json" eyebrow="Two-axis research" title="Structural versus tactical matrix" description="Distinguishes durable business evidence from timely near-term information instead of blending their horizons." />} />
          <Route path="/screens/early-session" element={<EarlySessionResearch />} />
          <Route path="/screens/politics" element={<CongressTrades />} />
          <Route path="/screens/institutional" element={<InstitutionalActivity />} />
          <Route path="/screens/themes" element={<ThemeExposureScreen />} />
          <Route path="/screens/backtests" element={<BacktestComparison />} />
          <Route path="/screens/shadow" element={<ShadowPortfolios />} />
          <Route path="/screens/validation" element={<LiveValidation />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/methodology" element={<Methodology />} />
          <Route path="/glossary" element={<Glossary />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/alerts" element={cloudPage('Alerts', '/alerts', <Alerts />)} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
        </ErrorBoundary>
        <ModelVersionFooter />
      </main>

      <nav className="mobile-nav" aria-label="Mobile navigation">
        {MOBILE_NAV.map((item) => item.action === 'menu' ? (
            <button key="more" type="button"
              className={`mobile-nav-item${(moreMenuOpen || !isMobileTabActive(pathname)) ? ' active' : ''}`}
              aria-haspopup="dialog" aria-expanded={moreMenuOpen} onClick={() => setMoreMenuOpen(true)}>
              <span className="mobile-nav-icon"><Icon name={item.icon} size={18} /></span>
              <span>{item.label}</span>
            </button>
          ) : (
            <NavLink key={item.to} to={item.to} end={item.end}
              onPointerEnter={() => preloadRoute(item.to)} onFocus={() => preloadRoute(item.to)}
              className={({ isActive }) => `mobile-nav-item${isActive ? ' active' : ''}`}>
              <span className="mobile-nav-icon"><Icon name={item.icon} size={18} /></span>
              <span>{item.label}</span>
            </NavLink>
        ))}
      </nav>
      <MobileMoreMenu open={moreMenuOpen} onClose={() => setMoreMenuOpen(false)} />
    </div>
  )
}

export default function App() {
  return <FirebaseAuthProvider><AppContent /></FirebaseAuthProvider>
}
