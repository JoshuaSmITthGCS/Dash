import { useEffect, useRef, useState } from 'react'
import { useAuth } from './FirebaseAuthContext'
import { formatElapsed } from './useData'

const POLL_INTERVAL_MS = 20_000
const REFRESH_TIMEOUT_MS = 55 * 60_000
const ELAPSED_TICK_MS = 1_000

export function useAdvisorRefresh(generatedAt, reload, symbols = []) {
  const { currentUser } = useAuth()
  const [state, setState] = useState({ status: 'idle', message: '' })
  const [elapsedMs, setElapsedMs] = useState(0)
  const baseline = useRef(generatedAt)
  const startedAt = useRef(null)
  const runId = useRef(null)

  // There is no real progress signal from the GitHub Actions run - no step-by-step
  // percentage to show honestly. An elapsed-time counter is real, though, and it's what
  // actually answers "is this doing anything" while the run is in flight.
  useEffect(() => {
    if (state.status !== 'starting' && state.status !== 'pending') return undefined
    const tick = () => setElapsedMs(Date.now() - (startedAt.current || Date.now()))
    tick()
    const ticker = window.setInterval(tick, ELAPSED_TICK_MS)
    return () => window.clearInterval(ticker)
  }, [state.status])

  useEffect(() => {
    if (state.status !== 'pending') return undefined
    let checking = false

    const checkForUpdatedData = async () => {
      if (checking) return
      checking = true
      try {
        const idToken = await currentUser?.getIdToken()
        if (idToken) {
          const query = runId.current ? `?run_id=${runId.current}` : ''
          const progressResponse = await fetch(`/.netlify/functions/refresh-data${query}`, {
            headers: { Authorization: `Bearer ${idToken}` },
          })
          if (progressResponse.ok) {
            const progress = await progressResponse.json()
            if (progress.run_id) runId.current = progress.run_id
            if (progress.conclusion === 'failure') {
              setState({
                status: 'error',
                message: 'The data workflow failed before it could publish. Check GitHub Actions for the failed stage.',
                progress: progress.percent,
                stage: progress.stage,
              })
              return
            }
            if (progress.percent != null) {
              setState((current) => current.status === 'pending'
                ? { ...current, progress: progress.percent, stage: progress.stage }
                : current)
            }
          }
        }
        const latest = await reload()
        if (latest?.generated_at && latest.generated_at !== baseline.current) {
          setState({
            status: 'success',
            message: 'Market data updated. You are viewing the latest published refresh.',
          })
        }
      } catch {
        // A deployment can briefly return an old or unavailable asset; the next poll retries.
      } finally {
        checking = false
      }
    }

    const interval = window.setInterval(checkForUpdatedData, POLL_INTERVAL_MS)
    const timeout = window.setTimeout(() => {
      setState({
        status: 'error',
        message: 'The refresh is taking longer than expected. Try again or check the GitHub workflow.',
      })
    }, REFRESH_TIMEOUT_MS)
    return () => {
      window.clearInterval(interval)
      window.clearTimeout(timeout)
    }
  }, [currentUser, reload, state.status])

  const requestRefresh = async () => {
    if (!currentUser || state.status === 'pending') return
    baseline.current = generatedAt
    startedAt.current = Date.now()
    runId.current = null
    setElapsedMs(0)
    setState({ status: 'starting', message: 'Connecting to the refresh service…', progress: 0, stage: 'Starting refresh' })
    try {
      const idToken = await currentUser.getIdToken()
      const response = await fetch('/.netlify/functions/refresh-data', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${idToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symbols: [...new Set(
            symbols
              .map((symbol) => String(symbol || '').trim().toUpperCase())
              .filter(Boolean),
          )],
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (response.status === 503) {
        await reload()
        setState({
          status: 'error',
          message: 'No new Yahoo data was fetched: the refresh service is not configured on Netlify. Showing the latest previously published data.',
        })
        return
      }
      if (!response.ok && response.status !== 409) {
        throw new Error(payload.error || 'The refresh could not be started.')
      }
      setState({
        status: 'pending',
        message: response.status === 409
          ? 'A refresh is already running. This page will update automatically.'
          : 'Refresh started. This page will update automatically when new data is published.',
        progress: 0,
        stage: 'Waiting for a runner',
      })
    } catch (error) {
      setState({ status: 'error', message: error.message })
    }
  }

  const refreshing = state.status === 'starting' || state.status === 'pending'
  return {
    ...state,
    requestRefresh,
    refreshing,
    available: Boolean(currentUser),
    elapsedMs,
    elapsedLabel: refreshing ? formatElapsed(elapsedMs) : null,
  }
}
