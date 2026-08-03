import { useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import Picks from './pages/Picks.jsx'
import PolicyRadar from './pages/PolicyRadar.jsx'
import Watchlist from './pages/Watchlist.jsx'
import Methodology from './pages/Methodology.jsx'
import Glossary from './pages/Glossary.jsx'
import Portfolio from './pages/Portfolio.jsx'
import Finances from './pages/Finances.jsx'
import ResearchScreen from './pages/ResearchScreen.jsx'
import ShadowPortfolios from './pages/ShadowPortfolios.jsx'
<<<<<<< HEAD
import LiveValidation from './pages/LiveValidation.jsx'
=======
>>>>>>> dfd30bf31be272164cd860f3eec5e2b7e300d26b
import { DataStatus } from './components/DataStatus.jsx'
import Icon from './components/Icons.jsx'
import { AuthProvider as FirebaseAuthProvider, useAuth } from './lib/FirebaseAuthContext.jsx'
import FirebaseLoginModal from './components/FirebaseLoginModal.jsx'
import PasswordChangeModal from './components/PasswordChangeModal.jsx'

const NAV = [
  { to: '/', label: 'Overview', icon: 'overview', end: true, mobile: true },
  { to: '/research', label: 'Research', icon: 'research', mobile: true },
  { to: '/portfolio', label: 'Portfolio', icon: 'portfolio', requireAuth: true, mobile: true },
  { to: '/watchlist', label: 'Watchlist', icon: 'watchlist', mobile: true },
  { to: '/market', label: 'Market Pulse', icon: 'market' },
  { to: '/finances', label: 'Finances', icon: 'finances', requireAuth: true },
  { to: '/screens/momentum', label: 'Screens', icon: 'research' },
  { to: '/methodology', label: 'Methodology', icon: 'method' },
  { to: '/glossary', label: 'Glossary', icon: 'glossary' },
]

function ProfilePanel() {
  const { currentUser, userProfile, logout, toggleDarkMode } = useAuth()
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
        <button className="icon-button" onClick={toggleDarkMode}
          aria-label={userProfile?.darkMode ? 'Use light theme' : 'Use dark theme'}>
          <Icon name={userProfile?.darkMode ? 'sun' : 'moon'} />
        </button>
        <button className="icon-button" onClick={() => setShowPasswordChange(true)}
          aria-label="Account settings"><Icon name="user" /></button>
        <button className="icon-button" onClick={logout} aria-label="Sign out"><Icon name="logout" /></button>
      </div>
      {showPasswordChange && <PasswordChangeModal onClose={() => setShowPasswordChange(false)} />}
    </>
  )
}

function MoreLink() {
  return (
    <NavLink to="/market" className={({ isActive }) => `mobile-nav-item${isActive ? ' active' : ''}`}>
      <span className="mobile-nav-icon"><Icon name="more" size={19} /></span>
      <span>More</span>
    </NavLink>
  )
}

function AppContent() {
  const { currentUser, loading, userProfile } = useAuth()
  const previewMode = import.meta.env.DEV && new window.URLSearchParams(window.location.search).has('preview')

  if (loading) {
    return <div className="app-loading" role="status"><span className="loading-mark" />Loading ValueSignal</div>
  }

  return (
    <div className="shell">
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
            <button className="icon-button" aria-label="Notifications"><Icon name="bell" /></button>
            <div className="avatar" aria-label={`Profile: ${userProfile?.displayName || 'Investor'}`}>
              {(userProfile?.displayName || 'V').slice(0, 1).toUpperCase()}
            </div>
          </div>
        </header>
        <DataStatus />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/research" element={<Picks />} />
          <Route path="/market" element={<PolicyRadar />} />
          <Route path="/portfolio" element={currentUser ? <Portfolio /> : <Dashboard />} />
          <Route path="/finances" element={currentUser ? <Finances /> : <Dashboard />} />
          <Route path="/screens/momentum" element={<ResearchScreen file="screens/momentum.json" eyebrow="Monthly sleeve" title="Momentum" description="Exact month-end, skip-month price momentum with liquidity gates, hysteresis, and portfolio-level risk controls." />} />
          <Route path="/screens/quality-value" element={<ResearchScreen file="screens/quality-value.json" eyebrow="Quarterly screen" title="Quality at multi-year valuation lows" description="Cheapness versus applicable own-history multiples, peer value, business quality, distress, and forward-revision gates." />} />
          <Route path="/screens/earnings" element={<ResearchScreen file="screens/earnings-timeliness.json" eyebrow="One-to-three-month horizon" title="Earnings timeliness" description="Point-in-time revisions, earnings information, price confirmation, industry breadth, and tradability—kept separate from structural quality." />} />
          <Route path="/screens/matrix" element={<ResearchScreen file="screens/structural-tactical.json" eyebrow="Two-axis research" title="Structural versus tactical matrix" description="Distinguishes durable business evidence from timely near-term information instead of blending their horizons." />} />
          <Route path="/screens/shadow" element={<ShadowPortfolios />} />
<<<<<<< HEAD
          <Route path="/screens/validation" element={<LiveValidation />} />
=======

>>>>>>> dfd30bf31be272164cd860f3eec5e2b7e300d26b
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/methodology" element={<Methodology />} />
          <Route path="/glossary" element={<Glossary />} />
        </Routes>
      </main>

      <nav className="mobile-nav" aria-label="Mobile navigation">
        {NAV.filter((item) => item.mobile).map((item) => {
          if (item.requireAuth && !currentUser) return null
          return (
            <NavLink key={item.to} to={item.to} end={item.end}
              className={({ isActive }) => `mobile-nav-item${isActive ? ' active' : ''}`}>
              <span className="mobile-nav-icon"><Icon name={item.icon} size={19} /></span>
              <span>{item.label}</span>
            </NavLink>
          )
        })}
        <MoreLink />
      </nav>
      {!currentUser && !previewMode && <FirebaseLoginModal />}
    </div>
  )
}

export default function App() {
  return <FirebaseAuthProvider><AppContent /></FirebaseAuthProvider>
}
