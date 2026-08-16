import { useData } from '../lib/useData'
import DotPlot from './DotPlot.jsx'

function statsFor(data, key) {
  if (!data || data.status !== 'success') return null
  return key ? data.backtest?.[key] : data.backtest
}

/**
 * Every option strategy's simulated annualized return, on one shared scale, so a
 * reader comparing (say) covered calls to cash-secured puts doesn't have to hold
 * seven separately-expanded BacktestSummary panels in their head at once.
 *
 * Every options-strategy backtest file, in the order they appear in OPTIONS_NAV
 * (src/pages/ResearchScreen.jsx) plus the short-term-trades screen, which shares the
 * same envelope but lives outside the Options sub-nav — one useData call per file,
 * called unconditionally so hook order never depends on what the data contains.
 */
export default function CrossStrategyComparison() {
  const options = useData('screens/options-backtest.json')
  const shortTerm = useData('screens/short-term-trades-backtest.json')
  const coveredCall = useData('screens/covered-calls-backtest.json')
  const cashSecuredPut = useData('screens/cash-secured-puts-backtest.json')
  const protectivePut = useData('screens/protective-puts-backtest.json')
  const collar = useData('screens/collars-backtest.json')
  const verticalSpread = useData('screens/vertical-spreads-backtest.json')
  const advanced = useData('screens/advanced-strategies-backtest.json')

  const candidates = [
    { label: 'Multi-day options', stats: statsFor(options.data) },
    { label: 'Short-term trades', stats: statsFor(shortTerm.data) },
    { label: 'Covered call', stats: statsFor(coveredCall.data) },
    { label: 'Cash-secured put', stats: statsFor(cashSecuredPut.data) },
    { label: 'Protective put', stats: statsFor(protectivePut.data) },
    { label: 'Collar', stats: statsFor(collar.data) },
    { label: 'Vertical spread', stats: statsFor(verticalSpread.data) },
    { label: 'Iron condor', stats: statsFor(advanced.data, 'iron_condor') },
    { label: 'Straddle', stats: statsFor(advanced.data, 'straddle') },
  ]

  const rows = candidates
    .filter((row) => row.stats?.annualized_return != null)
    .map((row) => ({ id: row.label, label: row.label, value: row.stats.annualized_return * 100 }))

  if (rows.length < 2) return null
  return (
    <DotPlot
      rows={rows}
      xLabel="Annualized return (simulated)"
      xFormatter={(value) => `${value.toFixed(1)}%`}
      caption="Simulated annualized return across every options strategy backtest"
    />
  )
}
