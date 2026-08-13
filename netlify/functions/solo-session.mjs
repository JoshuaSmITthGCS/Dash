import { cert, getApps, initializeApp } from 'firebase-admin/app'
import { getAuth } from 'firebase-admin/auth'

const DEFAULT_OWNER_EMAIL = 'jbmsmusic05@gmail.com'

const json = (statusCode, body) => ({
  statusCode,
  headers: {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
  },
  body: JSON.stringify(body),
})

function firebaseApp() {
  if (getApps().length) return getApps()[0]
  const raw = process.env.FIREBASE_SERVICE_ACCOUNT_JSON
  if (!raw) throw new Error('FIREBASE_SERVICE_ACCOUNT_JSON is not configured')
  return initializeApp({ credential: cert(JSON.parse(raw)) })
}

export async function createSoloSession(authApi, ownerEmail) {
  const owner = await authApi.getUserByEmail(ownerEmail)
  return authApi.createCustomToken(owner.uid, { soloWorkspace: true })
}

export async function handler(event) {
  if (event.httpMethod !== 'POST') return json(405, { error: 'Method not allowed.' })

  try {
    const ownerEmail = (process.env.SOLO_FIREBASE_EMAIL || DEFAULT_OWNER_EMAIL).trim().toLowerCase()
    const token = await createSoloSession(getAuth(firebaseApp()), ownerEmail)
    return json(200, { token })
  } catch (error) {
    console.error('Solo Firebase session failed:', error)
    return json(500, { error: 'Cloud data could not be connected.' })
  }
}
