import { useEffect, useRef, useState } from 'react'
import { useAuth } from './FirebaseAuthContext'

const POLL_INTERVAL_MS = 20_000
const REFRESH_TIMEOUT_MS = 55 * 60_000

export function useAdvisorRefresh(generatedAt, reload) {
  const { currentUser } = useAuth()
  const [state, setState] = useState({ status: 'idle', message: '' })
  const baseline = useRef(generatedAt)

  useEffect(() => {
    if (state.status !== 'pending') return undefined
    let checking = false

    const checkForUpdatedData = async () => {
      if (checking) return
      checking = true
      try {
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
  }, [reload, state.status])

  const requestRefresh = async () => {
    if (!currentUser || state.status === 'pending') return
    baseline.current = generatedAt
    setState({ status: 'starting', message: 'Connecting to the refresh service…' })
    try {
      const idToken = await currentUser.getIdToken()
      const response = await fetch('/.netlify/functions/refresh-data', {
        method: 'POST',
        headers: { Authorization: `Bearer ${idToken}` },
      })
      const payload = await response.json().catch(() => ({}))
      if (response.status === 503) {
        await reload()
        setState({
          status: 'success',
          message: 'Latest published data reloaded. Automatic market refresh is not configured on Netlify yet.',
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
      })
    } catch (error) {
      setState({ status: 'error', message: error.message })
    }
  }

  return {
    ...state,
    requestRefresh,
    refreshing: state.status === 'starting' || state.status === 'pending',
    available: Boolean(currentUser),
  }
}
