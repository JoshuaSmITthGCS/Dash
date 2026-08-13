import { createContext, useContext, useState, useEffect } from 'react'
import {
  browserLocalPersistence,
  onAuthStateChanged,
  setPersistence,
  signInWithEmailAndPassword,
} from 'firebase/auth'
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

// Make the intended remembered-device behavior explicit instead of depending on Firebase's
// environment-selected default. If storage is unavailable (for example, a locked-down private
// window), auth still works for the current tab and the sign-in form explains the next failure.
const authPersistenceReady = setPersistence(auth, browserLocalPersistence).catch((error) => {
  console.warn('Persistent authentication is unavailable on this device:', error)
})

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
      await authPersistenceReady
      const result = await withTimeout(signInWithEmailAndPassword(auth, OWNER_EMAIL, password), AUTH_REQUEST_TIMEOUT_MS)
      return { success: true, user: result.user }
    } catch (error) {
      console.error('Login error:', error)
      return { success: false, error: describeAuthError(error) }
    }
  }

  useEffect(() => {
    // Keep the login surface hidden until Firebase has definitively restored (or rejected)
    // the saved browser session. A timer here used to show the password modal after 1.2s even
    // when a remembered session was still resolving on a slower desktop connection.
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      setCurrentUser(user)
      setLoading(false)
    })

    return unsubscribe
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
