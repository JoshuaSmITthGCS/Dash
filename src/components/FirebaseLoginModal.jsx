import { useState } from 'react'
import { OWNER_EMAIL, useAuth } from '../lib/FirebaseAuthContext'
import Icon from './Icons'
import useBodyScrollLock from '../lib/useBodyScrollLock'

// Only appears when the device has no saved Firebase session (first visit or a cleared
// browser). One password unlocks Josh's workspace; the session then persists silently.
export default function FirebaseLoginModal() {
  const { login, currentUser } = useAuth()
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  useBodyScrollLock(!currentUser)
  if (currentUser) return null

  const handleLogin = async (event) => {
    event.preventDefault(); setError(''); setLoading(true)
    const result = await login(password)
    if (!result.success) { setError(result.error); setLoading(false) }
  }

  return (
    <div className="modal-overlay auth-overlay" role="dialog" aria-modal="true" aria-labelledby="auth-title">
      <div className="modal login-modal">
        <div className="auth-brand">
          <span className="brand-mark">V</span>
          <span><span className="brand">Value<em>Signal</em></span><small>private research workspace</small></span>
        </div>

        <div className="auth-profile-heading">
          <span className="profile-initial">J</span>
          <div><span className="eyebrow">Welcome back</span><h1 id="auth-title">Josh</h1></div>
        </div>
        <form onSubmit={handleLogin} className="auth-form">
          <input className="sr-only" type="email" name="username" value={OWNER_EMAIL}
            autoComplete="username" readOnly tabIndex="-1" aria-hidden="true" />
          <label><span>Password</span><input type="password" value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password" autoFocus required /></label>
          {error && <div className="form-error" role="alert">{error}</div>}
          <button type="submit" className="primary-button" disabled={loading}>{loading ? 'Signing in…' : 'Sign in'}<Icon name="arrow" size={18} /></button>
        </form>

        <div className="auth-security"><span aria-hidden="true">●</span> Encrypted cloud sync</div>
      </div>
    </div>
  )
}
