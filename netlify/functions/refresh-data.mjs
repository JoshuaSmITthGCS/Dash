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

// The workflows this endpoint is allowed to start, as an allowlist keyed by the name the
// client sends. A client-supplied workflow *file name* would let any signed-in allowed user
// dispatch anything in .github/workflows; mapping through a fixed table means an unknown
// screen falls back to the advisor refresh rather than reaching a workflow nobody intended.
//
// The two screen collectors are here because they are on their own slow schedules - monthly
// for 13F, weekly for Congress - and are not touched by the main research refresh, so
// without this there is no way to re-run them from the app at all.
export const SCREEN_WORKFLOWS = {
  research: { workflow: 'refresh-advisor.yml', acceptsInputs: true, label: 'research refresh' },
  congress: { workflow: 'congress-trades.yml', acceptsInputs: false, label: 'Congressional disclosure collection' },
  institutional: { workflow: 'institutional-13f.yml', acceptsInputs: false, label: 'institutional 13F collection' },
  filings: { workflow: 'sec-filings.yml', acceptsInputs: false, label: '10-K/10-Q, DEF 14A, and 8-K filing collection' },
  'inside-information': { workflow: 'inside-information.yml', acceptsInputs: false, label: 'Inside Information merge' },
}

// Step weights per workflow, used to turn a job's completed steps into a percentage. The
// screen collectors are short and linear, so their steps are near-evenly weighted.
const SCREEN_PROGRESS_STEPS = [
  ['actions/checkout', 15],
  ['actions/setup-python', 10],
  ['pip install', 15],
  ['Collect', 45],
  ['Summarise what was collected', 5],
  ['Commit collected data with retry', 10],
]

export function parseRequestBody(body) {
  let payload = {}
  try {
    payload = JSON.parse(body || '{}')
  } catch {
    payload = {}
  }
  const screen = Object.hasOwn(SCREEN_WORKFLOWS, payload.screen) ? payload.screen : 'research'
  const tickerList = (values, limit) => (Array.isArray(values)
    ? [...new Set(
        values
          .map((symbol) => String(symbol || '').trim().toUpperCase())
          .filter((symbol) => /^[A-Z][A-Z0-9.-]{0,9}$/.test(symbol))
      )].slice(0, limit)
    : [])
  const symbols = tickerList(payload.symbols, 50)
  // A re-ranking request for one named set, kept apart from `symbols` because that list is
  // dispatched as the user's holdings and would relabel every re-ranked name as one. The cap
  // is higher because the caller is a whole screen rather than a portfolio: the theme screen
  // scores a few hundred companies, and truncating it would silently re-rank a slice of the
  // list while presenting it as the list.
  const focusSymbols = tickerList(payload.focus_symbols, 400)
  // "rescore" re-scores the last published data with no new provider requests at all - see
  // pipeline/rescore.py. Anything else falls back to a real data refresh.
  const mode = payload.mode === 'rescore' ? 'rescore' : 'data'
  const universeScope = payload.universe_scope === 'full' ? 'full' : 'fast'
  return { symbols, focusSymbols, mode, universeScope, screen }
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

export function workflowProgress(jobs = [], screen = 'research') {
  const steps = jobs.flatMap((job) => job.steps || [])
  let completed = 0
  let stage = 'Waiting for a runner'

  for (const [label, weight] of (screen === 'research' ? PROGRESS_STEPS : SCREEN_PROGRESS_STEPS)) {
    const step = steps.find((candidate) => candidate.name?.includes(label))
    if (step?.status === 'completed' && step.conclusion === 'success') completed += weight
    if (step?.status === 'in_progress') stage = step.name
  }

  return { percent: Math.min(100, completed), stage }
}

// Polls for the one workflow run that appears after a dispatch and wasn't in the
// pre-dispatch run list, since GitHub's dispatch endpoint itself returns no run ID.
// Correlating by "not previously seen" rather than by timestamp sidesteps any clock-skew
// ambiguity between this function and GitHub's servers.
export async function locateDispatchedRun(workflowUrl, headers, priorRunIds, {
  attempts = 5,
  delayMs = 700,
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
} = {}) {
  for (let attempt = 0; attempt < attempts; attempt++) {
    if (attempt > 0) await sleep(delayMs)
    const pollResponse = await fetch(`${workflowUrl}/runs?branch=main&event=workflow_dispatch&per_page=5`, { headers })
    if (!pollResponse.ok) continue
    const polled = await pollResponse.json()
    const created = polled.workflow_runs?.find((run) => !priorRunIds.has(run.id))
    if (created) return created.id
  }
  return null
}

async function refreshStatus(event, workflowUrl, headers, screen) {
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
  const progress = workflowProgress(jobs.jobs, screen)
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
  if (!idToken) return json(401, { error: 'A Firebase cloud session is required to request a refresh.' })

  try {
    const user = await getAuth(firebaseApp()).verifyIdToken(idToken, true)
    if (!user.email || !allowedEmails.has(user.email.toLowerCase())) {
      return json(403, { error: 'Your account is not allowed to start data refreshes.' })
    }
    const { symbols, focusSymbols, mode, universeScope, screen } = parseRequestBody(event.body)
    const refreshMode = mode === 'rescore' ? 'rescore-only' : 'data-only'

    // A GET carries no body, so the screen it is asking about rides in the query string.
    // Without it every status poll would be scored against the research workflow's step
    // list and a collector run would sit at 0% until it finished.
    const statusScreen = Object.hasOwn(SCREEN_WORKFLOWS, event.queryStringParameters?.screen)
      ? event.queryStringParameters.screen
      : screen
    const selected = SCREEN_WORKFLOWS[event.httpMethod === 'GET' ? statusScreen : screen]

    const workflowUrl = `https://api.github.com/repos/${repository}/actions/workflows/${selected.workflow}`
    const headers = githubHeaders(githubToken)
    if (event.httpMethod === 'GET') {
      return await refreshStatus(event, workflowUrl, headers, statusScreen)
    }
    const runsResponse = await fetch(`${workflowUrl}/runs?branch=main&per_page=10`, { headers })
    if (!runsResponse.ok) {
      throw new Error(`GitHub workflow lookup failed (${runsResponse.status})`)
    }
    const runs = await runsResponse.json()
    const active = runs.workflow_runs?.find((run) => ['queued', 'in_progress'].includes(run.status))
    if (active) {
      return json(409, { error: `A ${selected.label} is already running. Please wait for it to finish.`, run_id: active.id })
    }
    const priorRunIds = new Set((runs.workflow_runs || []).map((run) => run.id))

    const dispatchResponse = await fetch(`${workflowUrl}/dispatches`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        ref: 'main',
        // The collectors declare `workflow_dispatch: {}` and accept no inputs; GitHub
        // rejects a dispatch that supplies any, so the research workflow's inputs are only
        // sent to the workflow that actually declares them.
        ...(selected.acceptsInputs ? {
          inputs: {
            refresh_mode: refreshMode,
            // Portfolio and watchlist controls use the fast prior-top-100 sweep. The home
            // control may explicitly request a complete ~900-name rebuild. Rescoring skips
            // provider requests, so the scope is harmless for that mode.
            universe_scope: universeScope,
            portfolio_symbols: symbols.join(','),
            focus_symbols: focusSymbols.join(','),
          },
        } : {}),
      }),
    })
    if (!dispatchResponse.ok) {
      throw new Error(`GitHub workflow dispatch failed (${dispatchResponse.status})`)
    }
    // GitHub's dispatch endpoint returns no run ID (204, no body), and a rescore run can
    // complete in under a minute - faster than the client's own poll interval. Without
    // pinning the exact run ID down here, the client's first status check can find the
    // "queued/in_progress" list already empty (the run finished and dropped out of it)
    // and never learn what happened, waiting out the full timeout for a run that's long
    // since succeeded. A short poll for the one new run ID that appears after dispatch
    // removes that race entirely: every later status check targets that exact run by ID,
    // which works whether it's still running or already done.
    const runId = await locateDispatchedRun(workflowUrl, headers, priorRunIds)
    return json(202, { ok: true, mode: refreshMode, universe_scope: universeScope, symbols, focus_symbols: focusSymbols, screen, run_id: runId })
  } catch (error) {
    console.error('Manual refresh failed:', error)
    return json(500, { error: 'The refresh could not be started. Check the server configuration.' })
  }
}
