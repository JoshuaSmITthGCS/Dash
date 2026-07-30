import { createContext, useContext, useState, useEffect } from 'react'

const AuthContext = createContext(null)

const MASTER_PASSWORD = 'ufb9*r23nQebi'
const AUTH_KEY = 'valuesignal.auth'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Check if user is already logged in
    try {
      const stored = localStorage.getItem(AUTH_KEY)
      if (stored) {
        const auth = JSON.parse(stored)
        // Check if session is still valid (24 hours)
        if (auth.expiresAt > Date.now()) {
          setUser(auth.user)
        } else {
          localStorage.removeItem(AUTH_KEY)
        }
      }
    } catch (e) {
      console.error('Auth restoration failed:', e)
    }
    setLoading(false)
  }, [])

  const login = (password, username = 'Family Member') => {
    if (password === MASTER_PASSWORD) {
      const auth = {
        user: {
          id: `user-${Date.now()}`,
          name: username,
          loginAt: Date.now()
        },
        expiresAt: Date.now() + (24 * 60 * 60 * 1000) // 24 hours
      }
      localStorage.setItem(AUTH_KEY, JSON.stringify(auth))
      setUser(auth.user)
      return true
    }
    return false
  }

  const logout = () => {
    localStorage.removeItem(AUTH_KEY)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
