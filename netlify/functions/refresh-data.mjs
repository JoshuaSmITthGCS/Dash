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

const PROGRESS_STEPS = [
  ['Select the Eastern-time refresh window', 1],
  ['actions/checkout', 2],
  ['Restore the Yahoo/Alpha Vantage/SEC response cache', 3],
  ['actions/setup-python', 2],
  ['pip install', 2],
  ['Append point-in-time estimate snapshots', 3],
  ['Fetch and score stock research', 37],
  ['Fetch ETF growth screen', 15],
  ['Build ETF comparison', 20],
  ['Validate', 5],
  ['Commit refreshed data with retry', 10],
]

export function workflowProgress(jobs = []) {
  const steps = jobs.flatMap((job) => job.steps || [])
  let completed = 0
  let stage = 'Waiting for a runner'

  for (const [label, weight] of PROGRESS_STEPS) {
    const step = steps.find((candidate) => candidate.name?.includes(label))
    if (step?.status === 'completed' && step.conclusion === 'success') completed += weight
    if (step?.status === 'in_progress') stage = step.name
  }

  return { percent: Math.min(100, completed), stage }
}

async function refreshStatus(event, workflowUrl, headers) {
  const requestedRunId = event.queryStringParameters?.run_id
  let run

  if (requestedRunId && /^\d+$/.test(requestedRunId)) {
    const response = await fetch(`https://api.github.com/repos/${process.env.REFRESH_GITHUB_REPOSITORY}/actions/runs/${requestedRunId}`, { headers })
    if (!response.ok) throw new Error(`GitHub run lookup failed (${response.status})`)
    run = await response.json()
  } else {
    const response = await fetch(`${workflowUrl}/runs?branch=main&per_page=10`, { headers })
    if (!response.ok) throw new Error(`GitHub workflow lookup failed (${response.status})`)
    const runs = await response.json()
    run = runs.workflow_runs?.find((candidate) => ['queued', 'in_progress'].includes(candidate.status))
  }

  if (!run) return json(200, { active: false })
  const jobsResponse = await fetch(`https://api.github.com/repos/${process.env.REFRESH_GITHUB_REPOSITORY}/actions/runs/${run.id}/jobs?per_page=100`, { headers })
  if (!jobsResponse.ok) throw new Error(`GitHub jobs lookup failed (${jobsResponse.status})`)
  const jobs = await jobsResponse.json()
  const progress = workflowProgress(jobs.jobs)
  if (run.status === 'completed' && run.conclusion === 'success') {
    progress.percent = 100
    progress.stage = 'Publishing the website update'
  }
  return json(200, {
    active: ['queued', 'in_progress'].includes(run.status),
    run_id: run.id,
    status: run.status,
    conclusion: run.conclusion,
    ...progress,
  })
}

export async function handler(event) {
  if (!['GET', 'POST'].includes(event.httpMethod)) {
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
    if (event.httpMethod === 'GET') {
      return await refreshStatus(event, workflowUrl, headers)
    }
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
          // Manual refreshes are interactive: poll the prior top 100 plus every symbol
          // sent by the portfolio/watchlist, then carry the remaining rows forward from
          // the morning full sweep. Rebuilding ~900 names on every click made the button
          // take close to an hour without improving the user's own holdings.
          universe_scope: 'fast',
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
