/* global self */
import { simulateProjection } from '../lib/projectionEngine.js'

self.onmessage = (event) => {
  const startedAt = globalThis.performance.now()
  try {
    const result = simulateProjection(event.data.input)
    self.postMessage({ id: event.data.id, result: { ...result, runtimeMs: globalThis.performance.now() - startedAt } })
  } catch (error) {
    self.postMessage({ id: event.data.id, error: error instanceof Error ? error.message : 'Projection failed.' })
  }
}
