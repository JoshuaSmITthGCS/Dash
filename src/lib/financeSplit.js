/** Totals a budget's income and expense line items into a monthly leftover. */
export function summarizeBudget(items = []) {
  const income = items.filter((item) => item.type === 'income')
    .reduce((sum, item) => sum + (Number(item.amount) || 0), 0)
  const expenses = items.filter((item) => item.type === 'expense')
    .reduce((sum, item) => sum + (Number(item.amount) || 0), 0)
  return { income, expenses, leftover: income - expenses }
}

/**
 * Divides a dollar amount across pools in proportion to each pool's percent,
 * normalizing against the pools' combined percent rather than assuming it sums to 100.
 */
export function splitAmount(amount, pools = []) {
  const totalPercent = pools.reduce((sum, pool) => sum + (Number(pool.percent) || 0), 0)
  if (!amount || totalPercent <= 0) return pools.map((pool) => ({ ...pool, share: 0 }))
  return pools.map((pool) => ({ ...pool, share: ((Number(pool.percent) || 0) / totalPercent) * amount }))
}
