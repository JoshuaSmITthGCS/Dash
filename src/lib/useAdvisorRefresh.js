import { useEffect, useRef, useState } from 'react'
import { useAuth } from './FirebaseAuthContext'
import { formatElapsed } from './useData'

const POLL_INTERVAL_MS = 20_000
const REFRESH_TIMEOUT_MS = 55 * 60_000
// A reanalysis never touches a data provider - it's a scoring pass over what's already
// published (see pipeline/rescore.py) - so a much shorter timeout is enough to say
// something is actually wrong rather than "still inside a normal 90-minute run".
const REANALYZE_TIMEOUT_MS = 10 * 60_000
const ELAPSED_TICK_MS = 1_000

export function useAdvisorRefresh(generatedAt, reload, symbols = []) {
  const { currentUser } = useAuth()
  const [state, setState] = useState({ status: 'idle', message: '' })
  const [elapsedMs, setElapsedMs] = useState(0)
  const baseline = useRef(generatedAt)
  const startedAt = useRef(null)
  const runId = useRef(null)
  const mode = useRef('data')

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
            // A completed, successful run is the authoritative "done" signal. A rescore
            // never moves generated_at - it re-scores the last-fetched data rather than
            // fetching anything new (see pipeline/rescore.py) - so waiting on that
            // timestamp alone left every rescore stuck "pending" until the timeout even
            // though the workflow itself finished in under a minute.
            if (progress.conclusion === 'success') {
              await reload()
              setState({
                status: 'success',
                message: mode.current === 'rescore'
                  ? 'Reanalysis complete. You are viewing the newly rescored data.'
                  : 'Market data updated. You are viewing the latest published refresh.',
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
        message: mode.current === 'rescore'
          ? 'The reanalysis is taking longer than expected. Try again or check the GitHub workflow.'
          : 'The refresh is taking longer than expected. Try again or check the GitHub workflow.',
      })
    }, mode.current === 'rescore' ? REANALYZE_TIMEOUT_MS : REFRESH_TIMEOUT_MS)
    return () => {
      window.clearInterval(interval)
      window.clearTimeout(timeout)
    }
  }, [currentUser, reload, state.status])

  const startRefresh = async (requestedMode) => {
    if (!currentUser || state.status === 'pending') return
    mode.current = requestedMode
    baseline.current = generatedAt
    startedAt.current = Date.now()
    runId.current = null
    setElapsedMs(0)
    setState({
      status: 'starting',
      message: requestedMode === 'rescore'
        ? 'Connecting to the reanalysis service…'
        : 'Connecting to the refresh service…',
      progress: 0,
      stage: requestedMode === 'rescore' ? 'Starting reanalysis' : 'Starting refresh'
    })
    try {
      const idToken = await currentUser.getIdToken()
      const response = await fetch('/.netlify/functions/refresh-data', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${idToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          mode: requestedMode,
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
          message: requestedMode === 'rescore'
            ? 'Reanalysis is not configured on Netlify. Showing the latest previously published data.'
            : 'No new Yahoo data was fetched: the refresh service is not configured on Netlify. Showing the latest previously published data.',
        })
        return
      }
      if (!response.ok && response.status !== 409) {
        throw new Error(payload.error || (requestedMode === 'rescore'
          ? 'The reanalysis could not be started.'
          : 'The refresh could not be started.'))
      }
      setState({
        status: 'pending',
        message: response.status === 409
          ? 'A refresh or reanalysis is already running. This page will update automatically.'
          : requestedMode === 'rescore'
            ? 'Reanalysis started. This page will update automatically in a couple of minutes.'
            : 'Refresh started. This page will update automatically when new data is published.',
        progress: 0,
        stage: requestedMode === 'rescore' ? 'Waiting for reanalysis' : 'Waiting for a runner',
      })
    } catch (error) {
      setState({ status: 'error', message: error.message })
    }
  }

  const requestRefresh = () => startRefresh('data')
  const requestReanalyze = () => startRefresh('rescore')

  const refreshing = state.status === 'starting' || state.status === 'pending'
  return {
    ...state,
    requestRefresh,
    requestReanalyze,
    refreshing,
    // Which of the two this run actually is, so a UI with separate refresh/reanalyze
    // buttons can label the one in flight instead of guessing from a shared "refreshing".
    activeMode: mode.current,
    available: Boolean(currentUser),
    elapsedMs,
    elapsedLabel: refreshing ? formatElapsed(elapsedMs) : null,
  }
}
