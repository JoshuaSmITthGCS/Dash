import { useState } from 'react'
import { useAuth } from '../lib/AuthContext'

export default function LoginModal() {
  const { login, user } = useAuth()
  const [password, setPassword] = useState('')
  const [username, setUsername] = useState('')
  const [error, setError] = useState('')

  if (user) return null

  const handleSubmit = (e) => {
    e.preventDefault()
    setError('')
    if (!username.trim()) {
      setError('Please enter your name')
      return
    }
    const success = login(password, username.trim())
    if (!success) {
      setError('Incorrect password')
      setPassword('')
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal login-modal">
        <div className="brand" style={{ marginBottom: 12 }}>Value<em>Signal</em></div>
        <h2 style={{ marginBottom: 8 }}>Family Portfolio Tracker</h2>
        <p style={{ marginBottom: 24, opacity: 0.7 }}>Enter the family password to access your portfolio</p>

        <form onSubmit={handleSubmit}>
          <input
            type="text"
            placeholder="Your name"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            style={{ marginBottom: 12 }}
            autoFocus
          />
          <input
            type="password"
            placeholder="Family password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ marginBottom: 12 }}
          />
          {error && <div style={{ color: 'var(--neg)', marginBottom: 12, fontSize: 14 }}>{error}</div>}
          <button type="submit" className="tab active" style={{ width: '100%' }}>
            Login
          </button>
        </form>

        <p style={{ marginTop: 24, fontSize: 13, opacity: 0.6 }}>
          Your portfolio is stored locally in your browser
        </p>
      </div>
    </div>
  )
}
