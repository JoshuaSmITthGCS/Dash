import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import {
  browserLocalPersistence,
  onAuthStateChanged,
  setPersistence,
  signInWithCustomToken,
} from 'firebase/auth'
import { auth } from './firebase'

const AuthContext = createContext(null)
const JOSH_PROFILE = { displayName: 'Josh', email: 'jbmsmusic05@gmail.com' }
const SOLO_SESSION_URL = '/.netlify/functions/solo-session'
const AUTH_REQUEST_TIMEOUT_MS = 15000

// Firebase still owns the session and every Firestore request. This solo workspace receives
// its owner token silently instead of asking for a password, then keeps it on the device.
const authPersistenceReady = setPersistence(auth, browserLocalPersistence).catch((error) => {
  console.warn('Persistent authentication is unavailable on this device:', error)
})

function withTimeout(promise, ms) {
  return Promise.race([
    promise,
    new Promise((_resolve, reject) => {
      window.setTimeout(() => reject(new Error('Cloud session timed out')), ms)
    }),
  ])
}

async function requestSoloSession() {
  const response = await withTimeout(fetch(SOLO_SESSION_URL, {
    method: 'POST',
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  }), AUTH_REQUEST_TIMEOUT_MS)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || !payload.token) throw new Error(payload.error || 'Cloud session was unavailable')
  return payload.token
}

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [authError, setAuthError] = useState('')
  const sessionRequest = useRef(null)

  const connectCloudData = useCallback(async () => {
    if (sessionRequest.current) return sessionRequest.current
    setLoading(true)
    setAuthError('')
    sessionRequest.current = (async () => {
      await authPersistenceReady
      const token = await requestSoloSession()
      const result = await withTimeout(signInWithCustomToken(auth, token), AUTH_REQUEST_TIMEOUT_MS)
      setCurrentUser(result.user)
      setLoading(false)
      return result.user
    })()

    try {
      return await sessionRequest.current
    } catch (error) {
      console.error('Cloud session error:', error)
      setAuthError('Cloud portfolio data is temporarily unavailable.')
      setLoading(false)
      return null
    } finally {
      sessionRequest.current = null
    }
  }, [])

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      setCurrentUser(user)
      if (user) {
        setAuthError('')
        setLoading(false)
      } else {
        connectCloudData()
      }
    })

    return unsubscribe
  }, [connectCloudData])

  const value = {
    currentUser,
    userProfile: JOSH_PROFILE,
    loading,
    authError,
    retryAuth: connectCloudData,
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
