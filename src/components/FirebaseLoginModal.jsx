import { useState } from 'react'
import { useAuth, FAMILY_THEMES } from '../lib/FirebaseAuthContext'
import Icon from './Icons'

const PROFILES = [
  { displayName: 'Josh', email: 'jbmsmusic05@gmail.com', theme: FAMILY_THEMES.default, label: 'Primary', isMain: true },
  { displayName: 'Dad', email: 'dad@valuesignal.family', theme: FAMILY_THEMES.Dad, label: 'Gold' },
  { displayName: 'Mom', email: 'mom@valuesignal.family', theme: FAMILY_THEMES.Mom, label: 'Crimson' },
  { displayName: 'Jay', email: 'jay@valuesignal.family', theme: FAMILY_THEMES.Jay, label: 'Red' },
]

export default function FirebaseLoginModal() {
  const { login, signup, currentUser } = useAuth()
  const [mode, setMode] = useState('select')
  const [selectedProfile, setSelectedProfile] = useState(null)
  const [formData, setFormData] = useState({ email: '', password: '', displayName: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  if (currentUser) return null

  const selectProfile = (profile) => {
    setSelectedProfile(profile)
    setFormData((current) => ({ ...current, email: profile.email, displayName: profile.displayName }))
    setMode('login')
  }

  const reset = () => {
    setMode('select'); setSelectedProfile(null)
    setFormData({ email: '', password: '', displayName: '' }); setError('')
  }

  const handleLogin = async (event) => {
    event.preventDefault(); setError(''); setLoading(true)
    const result = await login(formData.email, formData.password)
    if (!result.success) { setError(result.error); setLoading(false) }
  }

  const handleSignup = async (event) => {
    event.preventDefault(); setError(''); setLoading(true)
    const result = await signup(formData.email, formData.password, formData.displayName)
    if (!result.success) { setError(result.error); setLoading(false) }
  }

  return (
    <div className="modal-overlay auth-overlay" role="dialog" aria-modal="true" aria-labelledby="auth-title">
      <div className="modal login-modal">
        <div className="auth-brand">
          <span className="brand-mark">V</span>
          <span><span className="brand">Value<em>Signal</em></span><small>private research workspace</small></span>
        </div>

        {mode === 'select' && (
          <>
            <span className="eyebrow">Secure access</span>
            <h1 id="auth-title">Choose your profile</h1>
            <p className="auth-sub">Your holdings and settings stay separate for every profile.</p>
            <div className="profile-grid">
              {PROFILES.map((profile) => (
                <button key={profile.displayName} onClick={() => selectProfile(profile)}
                  className={`profile-card${profile.isMain ? ' main-profile-card' : ''}`}>
                  <span className="profile-initial" style={{ '--profile-accent': profile.theme.accent }}>
                    {profile.displayName.slice(0, 1)}
                  </span>
                  <span><strong>{profile.displayName}</strong><small>{profile.label} theme</small></span>
                  <Icon name="chevron" size={18} />
                </button>
              ))}
            </div>
            <button onClick={() => setMode('signup')} className="secondary-button auth-create">
              <Icon name="plus" size={18} /> Create new profile
            </button>
          </>
        )}

        {mode === 'login' && (
          <>
            <button onClick={reset} className="auth-back">← Back to profiles</button>
            <div className="auth-profile-heading">
              <span className="profile-initial">{selectedProfile?.displayName?.slice(0, 1)}</span>
              <div><span className="eyebrow">Welcome back</span><h1 id="auth-title">{selectedProfile?.displayName}</h1></div>
            </div>
            <form onSubmit={handleLogin} className="auth-form">
              <label><span>Password</span><input type="password" value={formData.password}
                onChange={(event) => setFormData({ ...formData, password: event.target.value })}
                autoComplete="current-password" autoFocus required /></label>
              {error && <div className="form-error" role="alert">{error}</div>}
              <button type="submit" className="primary-button" disabled={loading}>{loading ? 'Signing in…' : 'Sign in'}<Icon name="arrow" size={18} /></button>
            </form>
            <p className="auth-switch">First time here? <button onClick={() => setMode('signup')}>Create an account</button></p>
          </>
        )}

        {mode === 'signup' && (
          <>
            <button onClick={reset} className="auth-back">← Back to profiles</button>
            <span className="eyebrow">New workspace</span><h1 id="auth-title">Create your profile</h1>
            <p className="auth-sub">A separate, encrypted portfolio with its own theme and settings.</p>
            <form onSubmit={handleSignup} className="auth-form">
              <label><span>Display name</span><input type="text" value={formData.displayName}
                onChange={(event) => setFormData({ ...formData, displayName: event.target.value })}
                autoComplete="name" autoFocus required /></label>
              <label><span>Email address</span><input type="email" value={formData.email}
                onChange={(event) => setFormData({ ...formData, email: event.target.value })}
                autoComplete="email" required /></label>
              <label><span>Password</span><input type="password" value={formData.password}
                onChange={(event) => setFormData({ ...formData, password: event.target.value })}
                autoComplete="new-password" minLength={6} required /></label>
              {error && <div className="form-error" role="alert">{error}</div>}
              <button type="submit" className="primary-button" disabled={loading}>{loading ? 'Creating…' : 'Create profile'}<Icon name="arrow" size={18} /></button>
            </form>
          </>
        )}

        <div className="auth-security"><span aria-hidden="true">●</span> Encrypted cloud sync</div>
      </div>
    </div>
  )
}
