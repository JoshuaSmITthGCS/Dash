import { lazy, Suspense, useState } from 'react'
import { Navigate, NavLink, Route, Routes } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import { DataStatus } from './components/DataStatus.jsx'
import Icon from './components/Icons.jsx'
import { AuthProvider as FirebaseAuthProvider, useAuth } from './lib/FirebaseAuthContext.jsx'
import FirebaseLoginModal from './components/FirebaseLoginModal.jsx'
import PasswordChangeModal from './components/PasswordChangeModal.jsx'
import { usePreferences } from './lib/PreferencesContext.jsx'
import ModelVersionFooter from './components/ModelVersionFooter.jsx'
import AlertBadge from './components/AlertBadge.jsx'

// Dashboard is the landing route on a phone opening this cold on cellular, so it ships eager.
// Every other page loads on demand — keeps first paint off the weight of pages the visit may
// never touch (Finances, ETF comparisons, shadow portfolios, congress trades, etc).
const Picks = lazy(() => import('./pages/Picks.jsx'))
const PolicyRadar = lazy(() => import('./pages/PolicyRadar.jsx'))
const Watchlist = lazy(() => import('./pages/Watchlist.jsx'))
const Methodology = lazy(() => import('./pages/Methodology.jsx'))
const Glossary = lazy(() => import('./pages/Glossary.jsx'))
const Portfolio = lazy(() => import('./pages/Portfolio.jsx'))
const Finances = lazy(() => import('./pages/Finances.jsx'))
const ResearchScreen = lazy(() => import('./pages/ResearchScreen.jsx'))
const ShadowPortfolios = lazy(() => import('./pages/ShadowPortfolios.jsx'))
const LiveValidation = lazy(() => import('./pages/LiveValidation.jsx'))
const EarlySessionResearch = lazy(() => import('./pages/EarlySessionResearch.jsx'))
const CongressTrades = lazy(() => import('./pages/CongressTrades.jsx'))
const Settings = lazy(() => import('./pages/Settings.jsx'))
const Search = lazy(() => import('./pages/Search.jsx'))
const Diversification = lazy(() => import('./pages/Diversification.jsx'))
const Insights = lazy(() => import('./pages/Insights.jsx'))
const Alerts = lazy(() => import('./pages/Alerts.jsx'))

const NAV = [
  { to: '/', label: 'Financial Report', icon: 'overview', end: true },
  { to: '/research', label: 'Research', icon: 'research' },
  { to: '/search', label: 'Search', icon: 'search' },
  { to: '/portfolio', label: 'Portfolio', icon: 'portfolio', requireAuth: true },
  { to: '/watchlist', label: 'Watchlist', icon: 'watchlist' },
  { to: '/finances', label: 'Finances', icon: 'finances', requireAuth: true },
  { to: '/screens/momentum', label: 'Screens', icon: 'research' },
  { to: '/methodology', label: 'Methodology', icon: 'method' },
  { to: '/glossary', label: 'Glossary', icon: 'glossary' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
  { to: '/alerts', label: 'Alerts', icon: 'bell', requireAuth: true },
]

export const MOBILE_NAV = [
  { to: '/research', label: 'Research', icon: 'research' },
  { to: '/search', label: 'Search', icon: 'search' },
  { to: '/', label: 'Report', icon: 'overview', end: true, primary: true },
  { to: '/portfolio', label: 'Portfolio', icon: 'portfolio' },
  { to: '/watchlist', label: 'Watchlist', icon: 'watchlist' },
]

function ProfilePanel() {
  const { currentUser, userProfile, logout } = useAuth()
  const [showPasswordChange, setShowPasswordChange] = useState(false)
  if (!currentUser) return null

  return (
    <>
      <div className="profile-panel">
        <div className="avatar" aria-hidden="true">
          {(userProfile?.displayName || currentUser.email || 'V').slice(0, 1).toUpperCase()}
        </div>
        <div className="profile-copy">
          <strong>{userProfile?.displayName || 'Investor'}</strong>
          <span>{userProfile?.colorTheme?.name || 'ValueSignal member'}</span>
        </div>
        <NavLink className="icon-button" to="/settings" aria-label="Interface settings"><Icon name="settings" /></NavLink>
        <button className="icon-button" onClick={() => setShowPasswordChange(true)}
          aria-label="Account settings"><Icon name="user" /></button>
        <button className="icon-button" onClick={logout} aria-label="Sign out"><Icon name="logout" /></button>
      </div>
      {showPasswordChange && <PasswordChangeModal onClose={() => setShowPasswordChange(false)} />}
    </>
  )
}

function AppContent() {
  const { currentUser, loading, userProfile } = useAuth()
  const { preferences, updatePreferences } = usePreferences()
  const previewMode = import.meta.env.DEV && new window.URLSearchParams(window.location.search).has('preview')

  return (
    <div className="shell" data-auth-resolving={loading ? 'true' : 'false'}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className="rail" aria-label="Primary navigation">
        <NavLink to="/" className="brand-lockup" aria-label="ValueSignal overview">
          <span className="brand-mark">V</span>
          <span><span className="brand">Value<em>Signal</em></span><span className="brand-sub">research intelligence</span></span>
        </NavLink>
        <nav className="desktop-nav">
          {NAV.map((item) => {
            if (item.requireAuth && !currentUser) return null
            return (
              <NavLink key={item.to} to={item.to} end={item.end}
                className={({ isActive }) => `navlink${isActive ? ' active' : ''}`}>
                <Icon name={item.icon} size={19} /><span>{item.label}</span>
              </NavLink>
            )
          })}
        </nav>
        <div className="rail-note">
          <span>Research framework</span>
          Fundamentals first. Evidence, not hype. General research only.
        </div>
        <ProfilePanel />
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
        <DataStatus />
        <Suspense fallback={<div className="route-loading" role="status"><span className="loading-mark" /></div>}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/research" element={<Picks />} />
          <Route path="/search" element={<Search />} />
          <Route path="/market" element={<PolicyRadar />} />
          <Route path="/portfolio" element={currentUser ? <Portfolio /> : <Dashboard />} />
          <Route path="/portfolio/diversification" element={currentUser ? <Diversification /> : <Dashboard />} />
          <Route path="/portfolio/insights" element={currentUser ? <Insights /> : <Dashboard />} />
          <Route path="/finances" element={currentUser ? <Finances /> : <Dashboard />} />
          <Route path="/screens/momentum" element={<ResearchScreen file="screens/momentum.json" eyebrow="Monthly sleeve" title="Momentum" description="Exact month-end, skip-month price momentum with liquidity gates, hysteresis, and portfolio-level risk controls." />} />
          <Route path="/screens/quality-value" element={<ResearchScreen file="screens/quality-value.json" eyebrow="Quarterly screen" title="Quality at multi-year valuation lows" description="Cheapness versus applicable own-history multiples, peer value, business quality, distress, and forward-revision gates." />} />
          <Route path="/screens/earnings" element={<ResearchScreen file="screens/earnings-timeliness.json" eyebrow="One-to-three-month horizon" title="Earnings timeliness" description="Point-in-time revisions, earnings information, price confirmation, industry breadth, and tradability—kept separate from structural quality." />} />
          <Route path="/screens/matrix" element={<ResearchScreen file="screens/structural-tactical.json" eyebrow="Two-axis research" title="Structural versus tactical matrix" description="Distinguishes durable business evidence from timely near-term information instead of blending their horizons." />} />
          <Route path="/screens/early-session" element={<EarlySessionResearch />} />
          <Route path="/screens/politics" element={<CongressTrades />} />
          <Route path="/screens/shadow" element={<ShadowPortfolios />} />
          <Route path="/screens/validation" element={<LiveValidation />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/methodology" element={<Methodology />} />
          <Route path="/glossary" element={<Glossary />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/alerts" element={currentUser ? <Alerts /> : <Dashboard />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
        <ModelVersionFooter />
      </main>

      <nav className="mobile-nav" aria-label="Mobile navigation">
        {MOBILE_NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}
              className={({ isActive }) => `mobile-nav-item${item.primary ? ' mobile-nav-report' : ''}${isActive ? ' active' : ''}`}>
              <span className="mobile-nav-icon"><Icon name={item.icon} size={19} /></span>
              <span>{item.label}</span>
            </NavLink>
        ))}
      </nav>
      {!loading && !currentUser && !previewMode && <FirebaseLoginModal />}
    </div>
  )
}

export default function App() {
  return <FirebaseAuthProvider><AppContent /></FirebaseAuthProvider>
}
