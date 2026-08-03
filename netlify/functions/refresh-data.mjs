import { cert, getApps, initializeApp } from 'firebase-admin/app'
import { getAuth } from 'firebase-admin/auth'

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

function githubHeaders(token) {
  return {
    Accept: 'application/vnd.github+json',
    Authorization: `Bearer ${token}`,
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'ValueSignal-refresh-control',
  }
}

function portfolioSymbols(body) {
  let payload = {}
  try {
    payload = JSON.parse(body || '{}')
  } catch {
    return []
  }
  if (!Array.isArray(payload.symbols)) return []

  return [...new Set(
    payload.symbols
      .map((symbol) => String(symbol || '').trim().toUpperCase())
      .filter((symbol) => /^[A-Z][A-Z0-9.-]{0,9}$/.test(symbol))
  )].slice(0, 50)
}

export async function handler(event) {
  if (event.httpMethod !== 'POST') {
    return json(405, { error: 'Method not allowed.' })
  }

  const githubToken = process.env.GITHUB_REFRESH_TOKEN
  const repository = process.env.REFRESH_GITHUB_REPOSITORY
  const allowedEmails = new Set(
    (process.env.REFRESH_ALLOWED_EMAILS || '')
      .split(',')
      .map((email) => email.trim().toLowerCase())
      .filter(Boolean)
  )
  if (!githubToken || !repository || !allowedEmails.size) {
    return json(503, { error: 'Manual refresh is not configured on the server.' })
  }
  if (!/^[^/]+\/[^/]+$/.test(repository)) {
    return json(503, { error: 'The configured GitHub repository is invalid.' })
  }

  const authorization = event.headers.authorization || event.headers.Authorization || ''
  const idToken = authorization.startsWith('Bearer ') ? authorization.slice(7) : ''
  if (!idToken) return json(401, { error: 'Sign in before requesting a refresh.' })

  try {
    const user = await getAuth(firebaseApp()).verifyIdToken(idToken, true)
    if (!user.email || !allowedEmails.has(user.email.toLowerCase())) {
      return json(403, { error: 'Your account is not allowed to start data refreshes.' })
    }
    const symbols = portfolioSymbols(event.body)

    const workflowUrl = `https://api.github.com/repos/${repository}/actions/workflows/refresh-advisor.yml`
    const headers = githubHeaders(githubToken)
    const runsResponse = await fetch(`${workflowUrl}/runs?branch=main&per_page=10`, { headers })
    if (!runsResponse.ok) {
      throw new Error(`GitHub workflow lookup failed (${runsResponse.status})`)
    }
    const runs = await runsResponse.json()
    const active = runs.workflow_runs?.find((run) => ['queued', 'in_progress'].includes(run.status))
    if (active) {
      return json(409, { error: 'A data refresh is already running. Please wait for it to finish.' })
    }

    const dispatchResponse = await fetch(`${workflowUrl}/dispatches`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        ref: 'main',
        inputs: {
          refresh_mode: 'data-only',
          // A person clicking "refresh" wants everything current, not just the prior
          // top 100 - always request the full sweep regardless of what the scheduled
          // intraday runs default to.
          universe_scope: 'full',
          portfolio_symbols: symbols.join(','),
        },
      }),
    })
    if (!dispatchResponse.ok) {
      throw new Error(`GitHub workflow dispatch failed (${dispatchResponse.status})`)
    }
    return json(202, { ok: true, mode: 'data-only', symbols })
  } catch (error) {
    console.error('Manual refresh failed:', error)
    return json(500, { error: 'The refresh could not be started. Check the server configuration.' })
  }
}
