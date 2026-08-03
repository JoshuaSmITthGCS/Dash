import { useMemo } from 'react'
import { useData } from '../lib/useData'
import { parseEtfComparison } from '../lib/etfComparison'
import { ETFComparisonChart } from './ETFComparisonChart'

export default function ETFComparisonPanel({ ticker }) {
  const { data, loading, error, reload } = useData(`etf/${ticker}.json`)
  const parsed = useMemo(() => {
    if (!data) return { value: null, error: null }
    try { return { value: parseEtfComparison(data), error: null } }
    catch (parseError) { return { value: null, error: parseError } }
  }, [data])
  if (loading) return <div className="card etf-state" role="status">Loading ETF and benchmark history…</div>
  if (error || parsed.error) return <div className="card etf-state" role="alert">
    <strong>ETF comparison could not be loaded</strong><span>{(error || parsed.error).message}</span>
    <button className="primary-button compact" onClick={() => reload().catch(() => {})}>Retry</button>
  </div>
  if (!parsed.value || parsed.value.status === 'unavailable') return <div className="card etf-state" role="status">
    <strong>Benchmark history unavailable</strong><span>Reason: {parsed.value?.reason_code || 'EMPTY_RESPONSE'}</span>
  </div>
  return <ETFComparisonChart data={parsed.value} />
}
