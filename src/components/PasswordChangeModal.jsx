import { useState } from 'react'
import { useAuth } from '../lib/FirebaseAuthContext'

export default function PasswordChangeModal({ onClose }) {
  const { changePassword } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess(false)

    // Validation
    if (newPassword.length < 6) {
      setError('New password must be at least 6 characters')
      return
    }

    if (newPassword !== confirmPassword) {
      setError('New passwords do not match')
      return
    }

    if (currentPassword === newPassword) {
      setError('New password must be different from current password')
      return
    }

    setLoading(true)

    const result = await changePassword(currentPassword, newPassword)

    if (result.success) {
      setSuccess(true)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')

      // Auto-close after 2 seconds
      setTimeout(() => {
        onClose()
      }, 2000)
    } else {
      setError(result.error)
    }

    setLoading(false)
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 420 }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ margin: 0 }}>Change Password</h2>
          <button className="chip button-chip" onClick={onClose}>✕ Close</button>
        </div>

        {success ? (
          <div style={{ textAlign: 'center', padding: '40px 20px' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>✅</div>
            <h3 style={{ color: 'var(--pos)', marginBottom: 8 }}>Password Updated!</h3>
            <p style={{ opacity: 0.7 }}>Your password has been changed successfully.</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', marginBottom: 6, fontSize: 13, fontWeight: 600 }}>
                Current Password
              </label>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                style={{ width: '100%' }}
                placeholder="Enter your current password"
                required
                autoFocus
              />
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', marginBottom: 6, fontSize: 13, fontWeight: 600 }}>
                New Password
              </label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                style={{ width: '100%' }}
                placeholder="Enter new password (min 6 characters)"
                required
                minLength={6}
              />
            </div>

            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', marginBottom: 6, fontSize: 13, fontWeight: 600 }}>
                Confirm New Password
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                style={{ width: '100%' }}
                placeholder="Confirm new password"
                required
                minLength={6}
              />
            </div>

            {error && (
              <div style={{
                color: 'var(--neg)',
                marginBottom: 16,
                fontSize: 14,
                padding: 12,
                background: 'color-mix(in srgb, var(--neg) 10%, transparent)',
                borderRadius: 8,
                border: '1px solid var(--neg)'
              }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              className="tab active"
              style={{ width: '100%' }}
              disabled={loading}
            >
              {loading ? 'Updating...' : 'Update Password'}
            </button>
          </form>
        )}

        <div style={{ marginTop: 20, padding: 12, background: 'var(--bg-elev)', borderRadius: 8, fontSize: 12, opacity: 0.7 }}>
          <strong>Password Requirements:</strong>
          <ul style={{ marginTop: 8, paddingLeft: 20, marginBottom: 0 }}>
            <li>Minimum 6 characters</li>
            <li>Must be different from current password</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
