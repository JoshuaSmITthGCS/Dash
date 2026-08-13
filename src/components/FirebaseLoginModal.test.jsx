import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const authMocks = vi.hoisted(() => ({
  login: vi.fn(),
}))

vi.mock('../lib/FirebaseAuthContext', () => ({
  OWNER_EMAIL: 'owner@example.com',
  useAuth: () => ({ currentUser: null, login: authMocks.login }),
}))
vi.mock('../lib/useBodyScrollLock', () => ({ default: vi.fn() }))
vi.mock('./Icons', () => ({ default: () => null }))

import FirebaseLoginModal from './FirebaseLoginModal.jsx'

describe('FirebaseLoginModal', () => {
  beforeEach(() => {
    authMocks.login.mockReset()
    authMocks.login.mockResolvedValue({ success: true })
  })

  it('submits a password populated directly by a desktop password manager', async () => {
    render(<FirebaseLoginModal />)
    const passwordField = screen.getByLabelText('Password')

    // Password managers can update the DOM without dispatching the React change event.
    passwordField.value = 'saved-desktop-password'
    fireEvent.submit(passwordField.form)

    await waitFor(() => {
      expect(authMocks.login).toHaveBeenCalledWith('saved-desktop-password')
    })
  })

  it('submits a password entered normally', async () => {
    render(<FirebaseLoginModal />)
    const passwordField = screen.getByLabelText('Password')

    fireEvent.change(passwordField, { target: { value: 'typed-password' } })
    fireEvent.submit(passwordField.form)

    await waitFor(() => {
      expect(authMocks.login).toHaveBeenCalledWith('typed-password')
    })
  })
})
