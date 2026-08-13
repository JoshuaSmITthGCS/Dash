import { act, render, screen, waitFor } from '@testing-library/react'

const authMocks = vi.hoisted(() => ({
  observer: null,
  setPersistence: vi.fn(() => Promise.resolve()),
  signInWithCustomToken: vi.fn(),
  unsubscribe: vi.fn(),
}))

vi.mock('firebase/auth', () => ({
  browserLocalPersistence: { type: 'LOCAL' },
  setPersistence: authMocks.setPersistence,
  signInWithCustomToken: authMocks.signInWithCustomToken,
  onAuthStateChanged: vi.fn((_auth, observer) => {
    authMocks.observer = observer
    return authMocks.unsubscribe
  }),
}))
vi.mock('./firebase', () => ({ auth: {} }))

import { AuthProvider, useAuth } from './FirebaseAuthContext.jsx'

function AuthState() {
  const { currentUser, loading, authError } = useAuth()
  return <span>{loading ? 'Connecting Firebase' : currentUser ? 'Cloud connected' : authError}</span>
}

describe('solo workspace Firebase session', () => {
  beforeEach(() => {
    authMocks.observer = null
    authMocks.unsubscribe.mockClear()
    authMocks.signInWithCustomToken.mockReset()
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses an existing persistent Firebase session without requesting another token', () => {
    render(<AuthProvider><AuthState /></AuthProvider>)
    expect(screen.getByText('Connecting Firebase')).toBeVisible()

    act(() => authMocks.observer({ uid: 'owner-uid' }))

    expect(screen.getByText('Cloud connected')).toBeVisible()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('silently creates the owner session when the device has no saved session', async () => {
    fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ token: 'solo-custom-token' }),
    })
    authMocks.signInWithCustomToken.mockResolvedValue({ user: { uid: 'owner-uid' } })
    render(<AuthProvider><AuthState /></AuthProvider>)

    act(() => authMocks.observer(null))

    await waitFor(() => expect(authMocks.signInWithCustomToken).toHaveBeenCalledWith({}, 'solo-custom-token'))
    expect(fetch).toHaveBeenCalledWith('/.netlify/functions/solo-session', expect.objectContaining({ method: 'POST' }))
    expect(screen.getByText('Cloud connected')).toBeVisible()
  })

  it('shows a recoverable cloud error without opening a login form', async () => {
    fetch.mockResolvedValue({
      ok: false,
      json: async () => ({ error: 'Cloud data could not be connected.' }),
    })
    render(<AuthProvider><AuthState /></AuthProvider>)

    act(() => authMocks.observer(null))

    expect(await screen.findByText('Cloud portfolio data is temporarily unavailable.')).toBeVisible()
    expect(authMocks.signInWithCustomToken).not.toHaveBeenCalled()
  })
})
