// User-provided Fidelity cash history. Stable IDs make repeated cloud syncs idempotent.
export const FIDELITY_CASH_FLOWS = [
  { id: 'fidelity-deposit-2025-07-28-20', type: 'deposit', amount: 20, effectiveDate: '2025-07-28', note: 'Electronic Funds Transfer Received (Cash)' },
  { id: 'fidelity-deposit-2025-08-04-60', type: 'deposit', amount: 60, effectiveDate: '2025-08-04', note: 'Electronic Funds Transfer Received (Cash)' },
  { id: 'fidelity-deposit-2026-02-13-200', type: 'deposit', amount: 200, effectiveDate: '2026-02-13', note: 'Electronic Funds Transfer Received (Cash)' },
  { id: 'fidelity-deposit-2026-03-06-200', type: 'deposit', amount: 200, effectiveDate: '2026-03-06', note: 'Electronic Funds Transfer Received (Cash)' },
  { id: 'fidelity-withdrawal-2026-03-30-200', type: 'withdrawal', amount: 200, effectiveDate: '2026-03-30', note: 'Electronic Funds Transfer Paid (Cash)' },
  { id: 'fidelity-deposit-2026-07-23-1700', type: 'deposit', amount: 1700, effectiveDate: '2026-07-23', note: 'Electronic Funds Transfer Received (Cash)' },
  { id: 'fidelity-deposit-2026-07-30-200', type: 'deposit', amount: 200, effectiveDate: '2026-07-30', note: 'Electronic Funds Transfer Received (Cash)' },
  { id: 'fidelity-deposit-2026-08-03-400', type: 'deposit', amount: 400, effectiveDate: '2026-08-03', note: 'Electronic Funds Transfer Received (Cash)' },
  { id: 'fidelity-deposit-2026-08-04-100', type: 'deposit', amount: 100, effectiveDate: '2026-08-04', note: 'Electronic Funds Transfer Received (Cash)', status: 'processing' },
]

export const FIDELITY_REFERENCE_SNAPSHOT = {
  asOf: '2026-08-04T14:01:23-04:00',
  totalAccountValue: 2818.41,
  investments: 2817.99,
  cash: 0.42,
  dayChange: 132.32,
  periodReturns: { '1D': 2.67, '1M': 3.01, YTD: 13.02, '1Y': 32.20 },
}

export function summarizeCashFlows(rows = FIDELITY_CASH_FLOWS) {
  const settled = rows.filter((row) => !['pending', 'processing'].includes(row.status))
  const pending = rows.filter((row) => ['pending', 'processing'].includes(row.status))
  const deposits = settled.filter((row) => row.type === 'deposit').reduce((sum, row) => sum + Number(row.amount || 0), 0)
  const withdrawals = settled.filter((row) => row.type === 'withdrawal').reduce((sum, row) => sum + Number(row.amount || 0), 0)
  const pendingDeposits = pending.filter((row) => row.type === 'deposit').reduce((sum, row) => sum + Number(row.amount || 0), 0)
  return { deposits, withdrawals, netContributions: deposits - withdrawals, pendingDeposits }
}
