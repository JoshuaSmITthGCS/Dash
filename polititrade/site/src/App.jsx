import { NavLink, Route, Routes } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import Picks from './pages/Picks.jsx'
import Trades from './pages/Trades.jsx'
import Politicians from './pages/Politicians.jsx'
import PolicyRadar from './pages/PolicyRadar.jsx'
import Watchlist from './pages/Watchlist.jsx'
import { DataStatus } from './components/DataStatus.jsx'

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/picks', label: 'Best Picks' },
  { to: '/trades', label: 'Trade Feed' },
  { to: '/politicians', label: 'Leaderboard' },
  { to: '/radar', label: 'Policy Radar' },
  { to: '/watchlist', label: 'Watchlist' },
]

export default function App() {
  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand">Politi<em>Trade</em></div>
        <div className="brand-sub">signal terminal</div>
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end}
            className={({ isActive }) => `navlink${isActive ? ' active' : ''}`}>
            <span className="dot" />{n.label}
          </NavLink>
        ))}
        <div className="rail-foot">
          v1.0 · static · $0/mo<br />
          data lags 30–45d<br />
          not financial advice
        </div>
      </aside>
      <main className="content">
        <DataStatus />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/picks" element={<Picks />} />
          <Route path="/trades" element={<Trades />} />
          <Route path="/politicians" element={<Politicians />} />
          <Route path="/radar" element={<PolicyRadar />} />
          <Route path="/watchlist" element={<Watchlist />} />
        </Routes>
      </main>
    </div>
  )
}
