import { act, render, screen } from '@testing-library/react'

const authMocks = vi.hoisted(() => ({
  observer: null,
  setPersistence: vi.fn(() => Promise.resolve()),
  signIn: vi.fn(),
  unsubscribe: vi.fn(),
}))

vi.mock('firebase/auth', () => ({
  browserLocalPersistence: { type: 'LOCAL' },
  setPersistence: authMocks.setPersistence,
  signInWithEmailAndPassword: authMocks.signIn,
  onAuthStateChanged: vi.fn((_auth, observer) => {
    authMocks.observer = observer
    return authMocks.unsubscribe
  }),
}))
vi.mock('./firebase', () => ({ auth: {} }))

import { AuthProvider, useAuth } from './FirebaseAuthContext.jsx'

function AuthState() {
  const { currentUser, loading } = useAuth()
  return <span>{loading ? 'Restoring session' : currentUser ? 'Signed in' : 'Signed out'}</span>
}

describe('remembered-device authentication', () => {
  beforeEach(() => {
    authMocks.observer = null
    authMocks.unsubscribe.mockClear()
  })

  it('keeps auth resolving until Firebase restores the saved user', () => {
    render(<AuthProvider><AuthState /></AuthProvider>)
    expect(screen.getByText('Restoring session')).toBeVisible()

    act(() => authMocks.observer({ uid: 'saved-user' }))

    expect(screen.getByText('Signed in')).toBeVisible()
  })

  it('does not turn a slow saved-session check into a signed-out state on a timer', () => {
    vi.useFakeTimers()
    render(<AuthProvider><AuthState /></AuthProvider>)

    act(() => vi.advanceTimersByTime(10_000))
    expect(screen.getByText('Restoring session')).toBeVisible()

    act(() => authMocks.observer(null))
    expect(screen.getByText('Signed out')).toBeVisible()
    vi.useRealTimers()
  })
})
