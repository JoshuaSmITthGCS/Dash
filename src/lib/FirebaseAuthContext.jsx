import { createContext, useContext, useState, useEffect } from 'react'
import { signInWithEmailAndPassword, onAuthStateChanged } from 'firebase/auth'
import { auth } from './firebase'

const AuthContext = createContext(null)

// Single-user workspace: this is Josh's personal dashboard. The Firebase session is kept
// only because Firestore's security rules key every document to the account's UID — once
// the device holds a session it is never surfaced in the UI again.
export const OWNER_EMAIL = 'jbmsmusic05@gmail.com'
const JOSH_PROFILE = { displayName: 'Josh', email: OWNER_EMAIL }

// Interactive sign-in must not spin forever on a flaky or offline connection - the same
// principle already applied to the passive auth-state check below (see its comment).
const AUTH_REQUEST_TIMEOUT_MS = 15000

const AUTH_ERROR_MESSAGES = {
  'auth/wrong-password': 'That password is incorrect.',
  'auth/invalid-credential': 'That password is incorrect.',
  'auth/user-not-found': "We couldn't find that account.",
  'auth/too-many-requests': 'Too many attempts. Wait a few minutes and try again.',
  'auth/network-request-failed': 'Check your connection and try again.',
}

function describeAuthError(error) {
  return AUTH_ERROR_MESSAGES[error?.code] || 'Something went wrong. Try again.'
}

function withTimeout(promise, ms) {
  return Promise.race([
    promise,
    new Promise((_resolve, reject) => {
      window.setTimeout(() => reject({ code: 'auth/network-request-failed' }), ms)
    }),
  ])
}

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const login = async (password) => {
    try {
      const result = await withTimeout(signInWithEmailAndPassword(auth, OWNER_EMAIL, password), AUTH_REQUEST_TIMEOUT_MS)
      return { success: true, user: result.user }
    } catch (error) {
      console.error('Login error:', error)
      return { success: false, error: describeAuthError(error) }
    }
  }

  useEffect(() => {
    // Auth should never hold the research UI hostage when Firebase is slow or offline.
    // The observer can still populate the session later; after a short fallback we render
    // the signed-out state with a recoverable login surface.
    const fallback = window.setTimeout(() => setLoading(false), 1200)
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      setCurrentUser(user)
      setLoading(false)
      window.clearTimeout(fallback)
    })

    return () => {
      window.clearTimeout(fallback)
      unsubscribe()
    }
  }, [])

  const value = {
    currentUser,
    userProfile: JOSH_PROFILE,
    loading,
    login,
  }

  return (
    <AuthContext.Provider value={value}>
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
