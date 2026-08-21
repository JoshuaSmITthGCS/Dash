import { useEffect, useRef, useState } from 'react'
import { useAuth } from './FirebaseAuthContext'
import { formatElapsed } from './useData'

const POLL_INTERVAL_MS = 20_000
const REFRESH_TIMEOUT_MS = 55 * 60_000
// A complete sweep can legitimately use most of the workflow's 90-minute allowance.
// Keep polling slightly beyond that limit so the UI does not report a false timeout while
// GitHub still considers a full-universe run healthy.
const FULL_REFRESH_TIMEOUT_MS = 95 * 60_000
// A reanalysis touches no data provider, but it is no longer "under a minute": the rescore
// path re-runs every disk-only screen build, the shadow-portfolio append, the validation
// artifact suite, and the commit step, on top of a full-history checkout and cache restore.
// This deadline is therefore a SOFT one: it only fires when the status endpoint has no
// live run to report (dispatch never landed, polling unauthorized). While GitHub confirms
// the run is queued or in progress the UI keeps waiting - the workflow's own 90-minute
// kill switch is the backstop for a genuinely hung run, and the poll reports its
// failure/cancellation the moment that happens.
const REANALYZE_TIMEOUT_MS = 5 * 60_000
// Absolute ceiling on polling regardless of what the status endpoint claims. GitHub
// terminates the job at 90 minutes, so a run still reported active past this point is a
// monitoring failure, not a working run.
const POLL_HARD_CAP_MS = 95 * 60_000
// How long a "the run is alive" observation stays fresh enough to suppress the soft
// deadline - a couple of missed polls (transient API hiccups) shouldn't flip a working
// run into a timeout error.
const ACTIVE_SIGNAL_GRACE_MS = 2 * 60_000
const ELAPSED_TICK_MS = 1_000

// `symbols` are the caller's holdings/watchlist, dispatched as portfolio tickers.
// `focusSymbols` is a different request: re-poll and re-rank exactly these companies and
// nothing else. Kept as its own argument rather than a flag on `symbols` because the two
// mean different things downstream - a focus name is not something the user owns, and
// sending it as one would tag it as a holding everywhere the pipeline reads that list.
export function useAdvisorRefresh(generatedAt, reload, symbols = [], focusSymbols = []) {
  const { currentUser } = useAuth()
  const [state, setState] = useState({ status: 'idle', message: '' })
  const [elapsedMs, setElapsedMs] = useState(0)
  const baseline = useRef(generatedAt)
  const startedAt = useRef(null)
  const runId = useRef(null)
  const mode = useRef('data')
  const scope = useRef('fast')
  const focused = useRef(false)

  const refreshCompleteMessage = () => scope.current === 'full'
    ? 'Full universe updated. You are viewing the latest published refresh.'
    : 'Market data updated. You are viewing the latest published refresh.'

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
    // When the status endpoint last confirmed the run was queued or in progress. The soft
    // per-mode deadline below only fires while this is stale: a run GitHub says is still
    // working is never a timeout, however long its mode "should" take - the rescore path
    // outgrew its old 5-minute estimate exactly this way, and the fixed timer turned every
    // healthy reanalysis into a spurious "taking longer than expected" error.
    let lastSeenActiveAt = 0

    const timedOutMessage = () => mode.current === 'rescore'
      ? 'The reanalysis is taking longer than expected. Try again or check the GitHub workflow.'
      : scope.current === 'full'
        ? 'The full-universe refresh is taking longer than expected. Try again or check the GitHub workflow.'
        : 'The refresh is taking longer than expected. Try again or check the GitHub workflow.'
    const softTimeoutMs = mode.current === 'rescore'
      ? REANALYZE_TIMEOUT_MS
      : scope.current === 'full' ? FULL_REFRESH_TIMEOUT_MS : REFRESH_TIMEOUT_MS

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
            // Any completed-but-not-successful conclusion ends the wait: failure,
            // cancelled, timed_out, ... A cancelled run used to fall through here and
            // leave the UI polling until the timeout for a run that was already gone.
            if (progress.status === 'completed' && progress.conclusion && progress.conclusion !== 'success') {
              setState({
                status: 'error',
                message: progress.conclusion === 'cancelled'
                  ? 'The data workflow was cancelled before it could publish.'
                  : 'The data workflow failed before it could publish. Check GitHub Actions for the failed stage.',
                progress: progress.percent,
                stage: progress.stage,
              })
              return
            }
            // A completed, successful run is the authoritative "done" signal. A rescore
            // never moves generated_at - it re-scores the last-fetched data rather than
            // fetching anything new (see pipeline/rescore.py) - so waiting on that
            // timestamp alone left every rescore stuck "pending" until the timeout even
            // though the workflow itself had finished.
            if (progress.conclusion === 'success') {
              await reload()
              setState({
                status: 'success',
                message: mode.current === 'rescore'
                  ? 'Reanalysis complete. You are viewing the newly rescored data.'
                  : refreshCompleteMessage(),
              })
              return
            }
            if (progress.active || ['queued', 'in_progress'].includes(progress.status)) {
              lastSeenActiveAt = Date.now()
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
            message: refreshCompleteMessage(),
          })
          return
        }
        const elapsed = Date.now() - (startedAt.current || Date.now())
        const recentlyActive = Date.now() - lastSeenActiveAt < ACTIVE_SIGNAL_GRACE_MS
        if (elapsed > softTimeoutMs && !recentlyActive) {
          setState({ status: 'error', message: timedOutMessage() })
        }
      } catch {
        // A deployment can briefly return an old or unavailable asset; the next poll retries.
      } finally {
        checking = false
      }
    }

    const interval = window.setInterval(checkForUpdatedData, POLL_INTERVAL_MS)
    const hardCap = window.setTimeout(() => {
      setState({ status: 'error', message: timedOutMessage() })
    }, POLL_HARD_CAP_MS)
    return () => {
      window.clearInterval(interval)
      window.clearTimeout(hardCap)
    }
  }, [currentUser, reload, state.status])

  const startRefresh = async (requestedMode, requestedScope = 'fast', { focus = false } = {}) => {
    if (!currentUser || state.status === 'pending') return
    focused.current = focus
    mode.current = requestedMode
    scope.current = requestedMode === 'data' && requestedScope === 'full' ? 'full' : 'fast'
    baseline.current = generatedAt
    startedAt.current = Date.now()
    runId.current = null
    setElapsedMs(0)
    setState({
      status: 'starting',
      message: requestedMode === 'rescore'
        ? 'Connecting to the reanalysis service…'
        : scope.current === 'full'
          ? 'Connecting to the full-universe refresh service…'
          : 'Connecting to the refresh service…',
      progress: 0,
      stage: requestedMode === 'rescore'
        ? 'Starting reanalysis'
        : scope.current === 'full' ? 'Starting full-universe refresh' : 'Starting refresh'
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
          universe_scope: scope.current,
          symbols: [...new Set(
            symbols
              .map((symbol) => String(symbol || '').trim().toUpperCase())
              .filter(Boolean),
          )],
          focus_symbols: focus
            ? [...new Set(
              focusSymbols
                .map((symbol) => String(symbol || '').trim().toUpperCase())
                .filter(Boolean),
            )]
            : [],
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (response.status === 503) {
        await reload()
        setState({
          status: 'error',
          message: requestedMode === 'rescore'
            ? 'Reanalysis is not configured on Netlify. Showing the latest previously published data.'
            : scope.current === 'full'
              ? 'No full-universe data was fetched: the refresh service is not configured on Netlify. Showing the latest previously published data.'
              : 'No new Yahoo data was fetched: the refresh service is not configured on Netlify. Showing the latest previously published data.',
        })
        return
      }
      if (!response.ok && response.status !== 409) {
        throw new Error(payload.error || (requestedMode === 'rescore'
          ? 'The reanalysis could not be started.'
          : 'The refresh could not be started.'))
      }
      // Locking onto the run's own ID (returned by the dispatch or the 409 conflict) up
      // front means every later status poll targets that exact run instead of scanning
      // for one still "queued/in_progress" - a run that finishes inside one poll interval
      // would otherwise vanish from that scan before it's ever seen as complete.
      if (payload.run_id) runId.current = payload.run_id
      setState({
        status: 'pending',
        message: response.status === 409
          ? 'A refresh or reanalysis is already running. This page will update automatically.'
          : requestedMode === 'rescore'
            ? 'Reanalysis started. This page will update automatically in a couple of minutes.'
            : scope.current === 'full'
              ? 'Full-universe refresh started. This page will update automatically when all names are published.'
              : 'Refresh started. This page will update automatically when new data is published.',
        progress: 0,
        stage: requestedMode === 'rescore'
          ? 'Waiting for reanalysis'
          : scope.current === 'full' ? 'Waiting for a full-universe runner' : 'Waiting for a runner',
      })
    } catch (error) {
      setState({ status: 'error', message: error.message })
    }
  }

  const requestRefresh = () => startRefresh('data')
  const requestFullRefresh = () => startRefresh('data', 'full')
  const requestReanalyze = () => startRefresh('rescore')
  // Re-poll and re-rank only the names the caller named. Everything else keeps its last
  // published row, which is what makes this cheap enough to be a button.
  const requestFocusedRefresh = () => startRefresh('data', 'fast', { focus: true })

  const refreshing = state.status === 'starting' || state.status === 'pending'
  return {
    ...state,
    requestRefresh,
    requestFullRefresh,
    requestReanalyze,
    requestFocusedRefresh,
    refreshing,
    // Which of the two this run actually is, so a UI with separate refresh/reanalyze
    // buttons can label the one in flight instead of guessing from a shared "refreshing".
    activeMode: mode.current,
    activeScope: scope.current,
    activeFocused: focused.current,
    available: Boolean(currentUser),
    elapsedMs,
    elapsedLabel: refreshing ? formatElapsed(elapsedMs) : null,
  }
}
