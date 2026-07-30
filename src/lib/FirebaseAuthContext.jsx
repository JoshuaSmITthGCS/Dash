import { createContext, useContext, useState, useEffect } from 'react'
import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signOut,
  onAuthStateChanged,
  updateProfile,
  updatePassword as firebaseUpdatePassword,
  reauthenticateWithCredential,
  EmailAuthProvider
} from 'firebase/auth'
import { doc, setDoc, getDoc, updateDoc } from 'firebase/firestore'
import { auth, db } from './firebase'

const AuthContext = createContext(null)

// Family color themes (auto-assigned by display name)
export const FAMILY_THEMES = {
  'Dad': {
    name: 'Black & Gold',
    primary: '#000000',
    accent: '#FFD700',
    bg: '#0a0a0a',
    bgCard: '#1a1a1a'
  },
  'Jay': {
    name: 'Black & Red',
    primary: '#000000',
    accent: '#FF0000',
    bg: '#0a0000',
    bgCard: '#1a0000'
  },
  'Mom': {
    name: 'Crimson & Cream',
    primary: '#DC143C',
    accent: '#FFFDD0',
    bg: '#1a0505',
    bgCard: '#2a0808'
  },
  'default': {
    name: 'Forest Green & Cream',
    primary: '#228B22',
    accent: '#FFFDD0',
    bg: '#051a05',
    bgCard: '#082a08'
  }
}

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null)
  const [userProfile, setUserProfile] = useState(null)
  const [loading, setLoading] = useState(true)

  // Get theme for a user based on display name
  const getThemeForUser = (displayName) => {
    return FAMILY_THEMES[displayName] || FAMILY_THEMES['default']
  }

  // Create user profile in Firestore
  const createUserProfile = async (user, displayName) => {
    const theme = getThemeForUser(displayName)
    const profileData = {
      uid: user.uid,
      email: user.email,
      displayName,
      colorTheme: theme,
      darkMode: true, // Default to dark mode
      createdAt: new Date().toISOString(),
      lastLogin: new Date().toISOString()
    }

    await setDoc(doc(db, 'users', user.uid), profileData)
    return profileData
  }

  // Load user profile from Firestore
  const loadUserProfile = async (user) => {
    const docRef = doc(db, 'users', user.uid)
    const docSnap = await getDoc(docRef)

    if (docSnap.exists()) {
      const profile = docSnap.data()
      // Update last login
      await updateDoc(docRef, {
        lastLogin: new Date().toISOString()
      })
      return profile
    }

    return null
  }

  // Switch palettes by flipping one attribute. The full light and dark token sets live in
  // variables.css, so a theme change can never leave light text sitting on a white card.
  const applyTheme = (theme, darkMode = true) => {
    const root = document.documentElement
    root.setAttribute('data-theme', darkMode ? 'dark' : 'light')

    // A personal accent is the only per-user override, and only where it stays readable:
    // the family accents are bright hues built for dark surfaces.
    root.style.setProperty('--primary', theme.primary)
    if (darkMode && theme.accent) {
      root.style.setProperty('--accent', theme.accent)
      root.style.setProperty('--accent-dim', theme.accent)
      root.style.setProperty('--accent-glow', `${theme.accent}22`)
      root.style.setProperty('--tier-high', theme.accent)
      root.style.setProperty('--series-stock', theme.accent)
    } else {
      for (const token of ['--accent', '--accent-dim', '--accent-glow', '--tier-high', '--series-stock']) {
        root.style.removeProperty(token)
      }
    }
  }

  // Sign up new user
  const signup = async (email, password, displayName) => {
    try {
      const result = await createUserWithEmailAndPassword(auth, email, password)
      await updateProfile(result.user, { displayName })
      const profile = await createUserProfile(result.user, displayName)
      setUserProfile(profile)
      applyTheme(profile.colorTheme, profile.darkMode)
      return { success: true, user: result.user }
    } catch (error) {
      console.error('Signup error:', error)
      return { success: false, error: error.message }
    }
  }

  // Sign in existing user
  const login = async (email, password) => {
    try {
      const result = await signInWithEmailAndPassword(auth, email, password)
      const profile = await loadUserProfile(result.user)
      if (profile) {
        setUserProfile(profile)
        applyTheme(profile.colorTheme, profile.darkMode)
      }
      return { success: true, user: result.user }
    } catch (error) {
      console.error('Login error:', error)
      return { success: false, error: error.message }
    }
  }

  // Log out
  const logout = async () => {
    try {
      await signOut(auth)
      setUserProfile(null)
      // Reset to default theme
      applyTheme(FAMILY_THEMES['default'], true)
      return { success: true }
    } catch (error) {
      console.error('Logout error:', error)
      return { success: false, error: error.message }
    }
  }

  // Update user theme
  const updateTheme = async (newTheme, darkMode) => {
    if (!currentUser) return

    try {
      const docRef = doc(db, 'users', currentUser.uid)
      await updateDoc(docRef, {
        colorTheme: newTheme,
        darkMode
      })

      setUserProfile(prev => ({
        ...prev,
        colorTheme: newTheme,
        darkMode
      }))

      applyTheme(newTheme, darkMode)
      return { success: true }
    } catch (error) {
      console.error('Theme update error:', error)
      return { success: false, error: error.message }
    }
  }

  // Toggle dark/light mode
  const toggleDarkMode = async () => {
    if (!currentUser || !userProfile) return

    const newDarkMode = !userProfile.darkMode
    await updateTheme(userProfile.colorTheme, newDarkMode)
  }

  // Change password
  const changePassword = async (currentPassword, newPassword) => {
    if (!currentUser || !currentUser.email) {
      return { success: false, error: 'No user logged in' }
    }

    try {
      // Re-authenticate first (required by Firebase for password change)
      const credential = EmailAuthProvider.credential(
        currentUser.email,
        currentPassword
      )
      await reauthenticateWithCredential(currentUser, credential)

      // Update password
      await firebaseUpdatePassword(currentUser, newPassword)

      return { success: true, message: 'Password updated successfully!' }
    } catch (error) {
      console.error('Password change error:', error)
      let errorMessage = 'Failed to change password'

      if (error.code === 'auth/wrong-password') {
        errorMessage = 'Current password is incorrect'
      } else if (error.code === 'auth/weak-password') {
        errorMessage = 'New password is too weak (min 6 characters)'
      }

      return { success: false, error: errorMessage }
    }
  }

  // Listen for auth state changes
  useEffect(() => {
    // Auth should never hold the research UI hostage when Firebase is slow or offline.
    // The observer can still populate the session later; after four seconds we render the
    // signed-out state with a recoverable login surface.
    const fallback = window.setTimeout(() => setLoading(false), 4000)
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      setCurrentUser(user)

      if (user) {
        const profile = await loadUserProfile(user)
        if (profile) {
          setUserProfile(profile)
          applyTheme(profile.colorTheme, profile.darkMode)
        }
      } else {
        setUserProfile(null)
      }

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
    userProfile,
    loading,
    signup,
    login,
    logout,
    updateTheme,
    toggleDarkMode,
    changePassword,
    FAMILY_THEMES
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
