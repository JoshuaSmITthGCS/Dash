import { NavLink, Route, Routes } from 'react-router-dom'
import Dashboard from './pages/Dashboard.jsx'
import Picks from './pages/Picks.jsx'
import PolicyRadar from './pages/PolicyRadar.jsx'
import Watchlist from './pages/Watchlist.jsx'
import Methodology from './pages/Methodology.jsx'
import { DataStatus } from './components/DataStatus.jsx'

const NAV = [
  { to: '/', label: 'Overview', end: true },
  { to: '/research', label: 'Research' },
  { to: '/market', label: 'Market Pulse' },
  { to: '/watchlist', label: 'Watchlist' },
  { to: '/methodology', label: 'Methodology' },
]

export default function App() {
  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand">Value<em>Signal</em></div>
        <div className="brand-sub">research advisor</div>
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end}
            className={({ isActive }) => `navlink${isActive ? ' active' : ''}`}>
            <span className="dot" />{n.label}
          </NavLink>
        ))}
        <div className="rail-foot">
          fundamentals first<br />
          evidence, not hype<br />
          general research only
        </div>
      </aside>
      <main className="content">
        <DataStatus />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/research" element={<Picks />} />
          <Route path="/market" element={<PolicyRadar />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/methodology" element={<Methodology />} />
        </Routes>
      </main>
    </div>
  )
}
