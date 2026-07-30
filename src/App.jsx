import { useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import Picks from './pages/Picks.jsx'
import PolicyRadar from './pages/PolicyRadar.jsx'
import Watchlist from './pages/Watchlist.jsx'
import Methodology from './pages/Methodology.jsx'
import Portfolio from './pages/Portfolio.jsx'
import { DataStatus } from './components/DataStatus.jsx'
import { AuthProvider as FirebaseAuthProvider, useAuth } from './lib/FirebaseAuthContext.jsx'
import FirebaseLoginModal from './components/FirebaseLoginModal.jsx'
import PasswordChangeModal from './components/PasswordChangeModal.jsx'

const NAV = [
  { to: '/', label: 'Overview', end: true },
  { to: '/research', label: 'Research' },
  { to: '/market', label: 'Market Pulse' },
  { to: '/portfolio', label: 'My Portfolio', requireAuth: true },
  { to: '/watchlist', label: 'Watchlist' },
  { to: '/methodology', label: 'Methodology' },
]

function ProfileSwitcher() {
  const { currentUser, userProfile, logout, toggleDarkMode } = useAuth()
  const [showPasswordChange, setShowPasswordChange] = useState(false)

  if (!currentUser) return null

  const theme = userProfile?.colorTheme

  return (
    <>
      <div style={{
        padding: '12px 14px',
        marginTop: 'auto',
        marginBottom: 12,
        border: '1px solid var(--border)',
        borderRadius: 8,
        background: 'var(--bg-elev)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <div style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: theme?.accent || 'var(--accent)'
          }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{userProfile?.displayName}</div>
            <div style={{ fontSize: 10, opacity: 0.6, fontFamily: 'var(--font-mono)' }}>
              {theme?.name}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 4, flexDirection: 'column' }}>
          <div style={{ display: 'flex', gap: 4 }}>
            <button
              onClick={toggleDarkMode}
              className="chip button-chip"
              style={{ fontSize: 10, padding: '4px 8px', flex: 1 }}
              title="Toggle dark/light mode"
            >
              {userProfile?.darkMode ? '☀️' : '🌙'}
            </button>
            <button
              onClick={() => setShowPasswordChange(true)}
              className="chip button-chip"
              style={{ fontSize: 10, padding: '4px 8px', flex: 1 }}
              title="Change password"
            >
              🔐
            </button>
            <button
              onClick={logout}
              className="chip button-chip"
              style={{ fontSize: 10, padding: '4px 8px', flex: 1 }}
              title="Switch profile"
            >
              ↻
            </button>
          </div>
        </div>
      </div>
      {showPasswordChange && (
        <PasswordChangeModal onClose={() => setShowPasswordChange(false)} />
      )}
    </>
  )
}

function AppContent() {
  const { currentUser, loading } = useAuth()

  if (loading) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', minHeight: '100vh' }}>
        <div>Loading...</div>
      </div>
    )
  }

  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand">Value<em>Signal</em></div>
        <div className="brand-sub">research advisor</div>
        {NAV.map((n) => {
          if (n.requireAuth && !currentUser) return null
          return (
            <NavLink key={n.to} to={n.to} end={n.end}
              className={({ isActive }) => `navlink${isActive ? ' active' : ''}`}>
              <span className="dot" />{n.label}
            </NavLink>
          )
        })}
        <div className="rail-foot" style={{ marginTop: 'auto', marginBottom: 8 }}>
          fundamentals first<br />
          evidence, not hype<br />
          general research only
        </div>
        <ProfileSwitcher />
      </aside>
      <main className="content">
        <DataStatus />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/research" element={<Picks />} />
          <Route path="/market" element={<PolicyRadar />} />
          <Route path="/portfolio" element={currentUser ? <Portfolio /> : <Dashboard />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/methodology" element={<Methodology />} />
        </Routes>
      </main>
      {!currentUser && <FirebaseLoginModal />}
    </div>
  )
}

export default function App() {
  return (
    <FirebaseAuthProvider>
      <AppContent />
    </FirebaseAuthProvider>
  )
}
