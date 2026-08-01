const MONTHS_PER_YEAR = 12

/**
 * Projects a savings balance to retirement using monthly compounding.
 * Returns a yearly series plus nominal and inflation-adjusted final balances.
 */
export function projectRetirement({
  currentSavings = 0,
  monthlyContribution = 0,
  annualReturnPct = 7,
  inflationPct = 2.5,
  years = 30,
} = {}) {
  const monthlyRate = annualReturnPct / 100 / MONTHS_PER_YEAR
  const totalMonths = Math.max(0, Math.round(years * MONTHS_PER_YEAR))

  const series = []
  let balance = currentSavings
  for (let month = 0; month <= totalMonths; month++) {
    if (month > 0) balance = balance * (1 + monthlyRate) + monthlyContribution
    if (month % MONTHS_PER_YEAR === 0) {
      const year = month / MONTHS_PER_YEAR
      const real = balance / Math.pow(1 + inflationPct / 100, year)
      series.push({ year, nominal: balance, real })
    }
  }

  const final = series[series.length - 1] || { nominal: currentSavings, real: currentSavings }
  const totalContributed = currentSavings + monthlyContribution * totalMonths

  return {
    series,
    nominalFinal: final.nominal,
    realFinal: final.real,
    totalContributed,
    totalGrowth: final.nominal - totalContributed,
  }
}
