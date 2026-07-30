import { useState } from 'react'
import { useAuth, FAMILY_THEMES } from '../lib/FirebaseAuthContext'

export default function FirebaseLoginModal() {
  const { login, signup, currentUser } = useAuth()
  const [mode, setMode] = useState('select') // 'select', 'login', 'signup'
  const [selectedProfile, setSelectedProfile] = useState(null)
  const [formData, setFormData] = useState({ email: '', password: '', displayName: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (currentUser) return null

  // Family profile presets - YOUR profile is the default/main one
  const mainProfile = {
    displayName: 'Me',
    email: 'me@valuesignal.family',
    theme: FAMILY_THEMES['default'],
    icon: '✨',
    isMain: true
  }

  const familyProfiles = [
    {
      displayName: 'Dad',
      email: 'dad@valuesignal.family',
      theme: FAMILY_THEMES['Dad'],
      icon: '👨'
    },
    {
      displayName: 'Mom',
      email: 'mom@valuesignal.family',
      theme: FAMILY_THEMES['Mom'],
      icon: '👩'
    },
    {
      displayName: 'Jay',
      email: 'jay@valuesignal.family',
      theme: FAMILY_THEMES['Jay'],
      icon: '🧑'
    }
  ]

  const handleProfileSelect = (profile) => {
    setSelectedProfile(profile)
    setFormData({ ...formData, email: profile.email, displayName: profile.displayName })
    setMode('login')
  }

  const handleLogin = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    const result = await login(formData.email, formData.password)

    if (!result.success) {
      setError(result.error)
      setLoading(false)
    }
  }

  const handleSignup = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    if (!formData.displayName) {
      setError('Please enter a display name')
      setLoading(false)
      return
    }

    const result = await signup(formData.email, formData.password, formData.displayName)

    if (!result.success) {
      setError(result.error)
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal login-modal" onClick={(e) => e.stopPropagation()}>
        <div className="brand" style={{ marginBottom: 12 }}>Value<em>Signal</em></div>

        {/* Profile Selection Mode */}
        {mode === 'select' && (
          <>
            <h2 style={{ marginBottom: 8 }}>Who's checking in?</h2>
            <p style={{ marginBottom: 24, opacity: 0.7 }}>Select your profile to continue</p>

            {/* Main Profile (You) - Bigger */}
            <button
              onClick={() => handleProfileSelect(mainProfile)}
              className="profile-card main-profile-card"
              style={{
                background: `linear-gradient(135deg, ${mainProfile.theme.primary}30, ${mainProfile.theme.accent}30)`,
                border: `3px solid ${mainProfile.theme.accent}`,
                borderRadius: 16,
                padding: 32,
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                textAlign: 'center',
                marginBottom: 20,
                width: '100%'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = mainProfile.theme.accent
                e.currentTarget.style.transform = 'translateY(-4px)'
                e.currentTarget.style.boxShadow = `0 8px 24px ${mainProfile.theme.accent}40`
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = mainProfile.theme.accent
                e.currentTarget.style.transform = 'translateY(0)'
                e.currentTarget.style.boxShadow = 'none'
              }}
            >
              <div style={{ fontSize: 60, marginBottom: 12 }}>{mainProfile.icon}</div>
              <div style={{ fontWeight: 700, fontSize: 24, marginBottom: 6 }}>My Portfolio</div>
              <div style={{ fontSize: 13, opacity: 0.8, fontFamily: 'var(--font-mono)' }}>
                {mainProfile.theme.name}
              </div>
            </button>

            {/* Family Members - Smaller Grid */}
            <div style={{ marginBottom: 8, fontSize: 12, opacity: 0.6, textAlign: 'center' }}>
              or login as:
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 20 }}>
              {familyProfiles.map((profile) => (
                <button
                  key={profile.displayName}
                  onClick={() => handleProfileSelect(profile)}
                  className="profile-card"
                  style={{
                    background: `linear-gradient(135deg, ${profile.theme.primary}20, ${profile.theme.accent}20)`,
                    border: `2px solid ${profile.theme.primary}40`,
                    borderRadius: 10,
                    padding: 16,
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    textAlign: 'center'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = profile.theme.accent
                    e.currentTarget.style.transform = 'translateY(-2px)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = `${profile.theme.primary}40`
                    e.currentTarget.style.transform = 'translateY(0)'
                  }}
                >
                  <div style={{ fontSize: 32, marginBottom: 6 }}>{profile.icon}</div>
                  <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 3 }}>{profile.displayName}</div>
                  <div style={{ fontSize: 9, opacity: 0.6, fontFamily: 'var(--font-mono)' }}>
                    {profile.theme.name.split(' &')[0]}
                  </div>
                </button>
              ))}
            </div>

            <button
              onClick={() => setMode('signup')}
              className="tab"
              style={{ width: '100%', marginTop: 12 }}
            >
              + Create New Profile
            </button>
          </>
        )}

        {/* Login Mode */}
        {mode === 'login' && (
          <>
            <button
              onClick={() => {
                setMode('select')
                setSelectedProfile(null)
                setFormData({ email: '', password: '', displayName: '' })
                setError('')
              }}
              style={{ marginBottom: 16, background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 13 }}
            >
              ← Back to profiles
            </button>

            <div style={{ textAlign: 'center', marginBottom: 20 }}>
              <div style={{ fontSize: selectedProfile?.isMain ? 56 : 48, marginBottom: 8 }}>{selectedProfile?.icon}</div>
              <h2 style={{ marginBottom: 4 }}>Welcome back{selectedProfile?.isMain ? '' : `, ${selectedProfile?.displayName}`}!</h2>
              <p style={{ fontSize: 13, opacity: 0.7 }}>
                <span style={{ color: selectedProfile?.theme.primary }}>●</span> {selectedProfile?.theme.name}
              </p>
            </div>

            <form onSubmit={handleLogin}>
              <input
                type="password"
                placeholder="Enter your password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                style={{ marginBottom: 12, width: '100%' }}
                autoFocus
                required
              />

              {error && (
                <div style={{ color: 'var(--neg)', marginBottom: 12, fontSize: 14 }}>
                  {error}
                </div>
              )}

              <button
                type="submit"
                className="tab active"
                style={{ width: '100%' }}
                disabled={loading}
              >
                {loading ? 'Logging in...' : 'Login'}
              </button>
            </form>

            <p style={{ marginTop: 16, fontSize: 13, opacity: 0.6, textAlign: 'center' }}>
              First time? <button onClick={() => setMode('signup')} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', textDecoration: 'underline' }}>Create account</button>
            </p>
          </>
        )}

        {/* Signup Mode */}
        {mode === 'signup' && (
          <>
            <button
              onClick={() => {
                setMode('select')
                setFormData({ email: '', password: '', displayName: '' })
                setError('')
              }}
              style={{ marginBottom: 16, background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 13 }}
            >
              ← Back to profiles
            </button>

            <h2 style={{ marginBottom: 8 }}>Create New Profile</h2>
            <p style={{ marginBottom: 24, opacity: 0.7 }}>Join the family portfolio tracker</p>

            <form onSubmit={handleSignup}>
              <input
                type="text"
                placeholder="Display name (e.g., Dad, Mom, Jay, or your name)"
                value={formData.displayName}
                onChange={(e) => setFormData({ ...formData, displayName: e.target.value })}
                style={{ marginBottom: 12, width: '100%' }}
                autoFocus
                required
              />

              <input
                type="email"
                placeholder="Email address"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                style={{ marginBottom: 12, width: '100%' }}
                required
              />

              <input
                type="password"
                placeholder="Create a password (min 6 characters)"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                style={{ marginBottom: 12, width: '100%' }}
                required
                minLength={6}
              />

              {error && (
                <div style={{ color: 'var(--neg)', marginBottom: 12, fontSize: 14 }}>
                  {error}
                </div>
              )}

              <div style={{ background: 'var(--bg-elev)', padding: 12, borderRadius: 8, marginBottom: 16, fontSize: 13 }}>
                <strong>Your theme will be:</strong>
                <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
                  {(() => {
                    const theme = FAMILY_THEMES[formData.displayName] || FAMILY_THEMES['default']
                    return (
                      <>
                        <div style={{ width: 24, height: 24, borderRadius: 4, background: theme.primary, border: '2px solid var(--border)' }}></div>
                        <div style={{ width: 24, height: 24, borderRadius: 4, background: theme.accent, border: '2px solid var(--border)' }}></div>
                        <span style={{ opacity: 0.8 }}>{theme.name}</span>
                      </>
                    )
                  })()}
                </div>
              </div>

              <button
                type="submit"
                className="tab active"
                style={{ width: '100%' }}
                disabled={loading}
              >
                {loading ? 'Creating account...' : 'Create Account'}
              </button>
            </form>

            <p style={{ marginTop: 16, fontSize: 13, opacity: 0.6, textAlign: 'center' }}>
              Already have an account? <button onClick={() => setMode('login')} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', textDecoration: 'underline' }}>Login</button>
            </p>
          </>
        )}

        <p style={{ marginTop: 24, fontSize: 11, opacity: 0.5, textAlign: 'center' }}>
          🔒 Your data is encrypted and synced to the cloud
        </p>
      </div>
    </div>
  )
}
