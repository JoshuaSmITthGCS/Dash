import { createSoloSession, handler } from './solo-session.mjs'

describe('solo-session function', () => {
  it('creates a custom token for the existing owner UID', async () => {
    const authApi = {
      getUserByEmail: vi.fn().mockResolvedValue({ uid: 'owner-uid' }),
      createCustomToken: vi.fn().mockResolvedValue('custom-token'),
    }

    await expect(createSoloSession(authApi, 'owner@example.com')).resolves.toBe('custom-token')
    expect(authApi.getUserByEmail).toHaveBeenCalledWith('owner@example.com')
    expect(authApi.createCustomToken).toHaveBeenCalledWith('owner-uid', { soloWorkspace: true })
  })

  it('rejects methods other than POST before touching Firebase Admin', async () => {
    const response = await handler({ httpMethod: 'GET' })
    expect(response.statusCode).toBe(405)
  })
})
