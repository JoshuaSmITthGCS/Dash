import { useEffect, useRef, useState } from 'react'
import { useAuth } from './FirebaseAuthContext'
import { formatElapsed } from './useData'

// The two screen collectors run on their own slow schedules - monthly for the 13F sweep,
// weekly for Congressional disclosures - and the main research refresh does not touch
// either. Without this hook there is no way to re-run them from the app at all: the only
// options are waiting for the next cron or opening GitHub Actions.
//
// Deliberately separate from useAdvisorRefresh rather than another mode on it. That hook
// carries the research workflow's whole vocabulary - rescore vs. data, fast vs. full
// universe, portfolio symbols, a 95-minute ceiling - none of which a collector accepts, and
// folding a third mode in would mean every caller reasoning about combinations that cannot
// happen. A collector takes no inputs and either finishes in a few minutes or is stuck.
const POLL_INTERVAL_MS = 10_000
const COLLECTOR_TIMEOUT_MS = 20 * 60_000
const ELAPSED_TICK_MS = 1_000

export function useScreenRefresh(screen, reload) {
  const { currentUser } = useAuth()
  const [state, setState] = useState({ status: 'idle', message: '' })
  const [elapsedMs, setElapsedMs] = useState(0)
  const startedAt = useRef(null)
  const runId = useRef(null)

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

    const check = async () => {
      if (checking) return
      checking = true
      try {
        const idToken = await currentUser?.getIdToken()
        if (!idToken) return
        const query = new URLSearchParams({ screen, ...(runId.current ? { run_id: runId.current } : {}) })
        const response = await fetch(`/.netlify/functions/refresh-data?${query}`, {
          headers: { Authorization: `Bearer ${idToken}` },
        })
        if (!response.ok) return
        const progress = await response.json()
        if (progress.run_id) runId.current = progress.run_id
        if (progress.conclusion === 'failure') {
          setState({
            status: 'error',
            message: 'The collection workflow failed before it could publish. Check GitHub Actions for the failed stage.',
            progress: progress.percent,
            stage: progress.stage,
          })
          return
        }
        // A collector that finds nothing new publishes an unchanged file, so "the data
        // changed" is not a usable completion signal here the way it is for a research
        // refresh - the run's own conclusion is the only honest one.
        if (progress.conclusion === 'success') {
          await reload()
          setState({
            status: 'success',
            message: 'Collection finished. You are viewing the latest published data.',
            progress: 100,
          })
          return
        }
        setState((current) => ({ ...current, progress: progress.percent, stage: progress.stage }))
      } finally {
        checking = false
      }
    }

    const poll = window.setInterval(check, POLL_INTERVAL_MS)
    const timeout = window.setTimeout(() => {
      setState({
        status: 'error',
        message: 'The collection is taking longer than expected. Check GitHub Actions for the run.',
      })
    }, COLLECTOR_TIMEOUT_MS)
    check()
    return () => {
      window.clearInterval(poll)
      window.clearTimeout(timeout)
    }
  }, [currentUser, reload, screen, state.status])

  const requestRefresh = async () => {
    if (!currentUser || state.status === 'starting' || state.status === 'pending') return
    startedAt.current = Date.now()
    runId.current = null
    setElapsedMs(0)
    setState({ status: 'starting', message: 'Connecting to the collection service…', progress: 0 })
    try {
      const idToken = await currentUser.getIdToken()
      const response = await fetch('/.netlify/functions/refresh-data', {
        method: 'POST',
        headers: { Authorization: `Bearer ${idToken}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ screen }),
      })
      const payload = await response.json().catch(() => ({}))
      if (response.status === 503) {
        setState({
          status: 'error',
          message: 'Manual collection is not configured on Netlify. Showing the latest previously published data.',
        })
        return
      }
      if (!response.ok && response.status !== 409) {
        throw new Error(payload.error || 'The collection could not be started.')
      }
      if (payload.run_id) runId.current = payload.run_id
      setState({
        status: 'pending',
        message: response.status === 409
          ? 'A collection is already running. This page will update automatically.'
          : 'Collection started. This page will update automatically when it finishes.',
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
