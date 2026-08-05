/* global Worker */
import { useEffect, useRef, useState } from 'react'
import { simulateProjection } from './projectionEngine.js'

let nextRequestId = 0

export function useProjectionSimulation(input) {
  const [state, setState] = useState({ result: null, loading: Boolean(input), error: null })
  const inputRef = useRef(input)
  inputRef.current = input
  const inputKey = JSON.stringify(input)

  useEffect(() => {
    const requestInput = inputRef.current
    if (!requestInput) {
      setState({ result: null, loading: false, error: null })
      return undefined
    }

    const id = ++nextRequestId
    let cancelled = false
    let worker = null
    let fallbackTimer = null
    setState((current) => ({ ...current, loading: true, error: null }))

    const finish = (result, error = null) => {
      if (!cancelled) setState({ result, loading: false, error })
    }

    if (typeof Worker === 'function') {
      try {
        worker = new Worker(new URL('../workers/projectionWorker.js', import.meta.url), { type: 'module' })
        worker.onmessage = (event) => {
          if (event.data.id !== id) return
          finish(event.data.result || null, event.data.error || null)
          worker?.terminate()
        }
        worker.onerror = () => {
          finish(null, 'The projection worker could not complete this simulation.')
          worker?.terminate()
        }
        worker.postMessage({ id, input: requestInput })
      } catch {
        worker = null
      }
    }

    if (!worker) {
      fallbackTimer = setTimeout(() => {
        try {
          const startedAt = globalThis.performance.now()
          finish({ ...simulateProjection(requestInput), runtimeMs: globalThis.performance.now() - startedAt })
        } catch (error) {
          finish(null, error instanceof Error ? error.message : 'Projection failed.')
        }
      }, 0)
    }

    return () => {
      cancelled = true
      worker?.terminate()
      if (fallbackTimer != null) clearTimeout(fallbackTimer)
    }
  }, [inputKey])

  return state
}
