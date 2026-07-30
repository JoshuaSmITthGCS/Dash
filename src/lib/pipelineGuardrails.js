/**
 * Pipeline Guardrails
 *
 * Data quality validation and exclusion logic.
 * Rejects stocks with:
 * - Mismatched fiscal periods
 * - Incomplete fundamental data
 * - Stale price data
 * - Missing required metrics
 *
 * Provides transparent "why excluded" explanations for debugging
 */

/**
 * Fiscal period validation
 * Ensures all quarterly data is from the same fiscal period
 */
export function validateFiscalPeriods(stock) {
  const issues = []

  // Check if we have quarterly data
  if (!stock.financials?.quarterly || stock.financials.quarterly.length === 0) {
    issues.push({
      severity: 'critical',
      category: 'missing_data',
      message: 'No quarterly financial data available',
      field: 'financials.quarterly'
    })
    return { valid: false, issues }
  }

  const quarters = stock.financials.quarterly

  // Check for fiscal period mismatches
  const fiscalYears = quarters.map(q => q.fiscalYear).filter(Boolean)
  const fiscalQuarters = quarters.map(q => q.fiscalQuarter).filter(Boolean)

  if (fiscalYears.length === 0 || fiscalQuarters.length === 0) {
    issues.push({
      severity: 'critical',
      category: 'missing_fiscal_info',
      message: 'Missing fiscal year or quarter information',
      field: 'fiscalYear/fiscalQuarter',
      details: { fiscalYears, fiscalQuarters }
    })
    return { valid: false, issues }
  }

  // Check for sequential quarters (should be Q4→Q1, Q1→Q2, etc.)
  for (let i = 0; i < quarters.length - 1; i++) {
    const current = quarters[i]
    const next = quarters[i + 1]

    if (!current.fiscalQuarter || !next.fiscalQuarter) continue

    const currentQ = parseInt(current.fiscalQuarter.replace('Q', ''))
    const nextQ = parseInt(next.fiscalQuarter.replace('Q', ''))
    const currentYear = current.fiscalYear
    const nextYear = next.fiscalYear

    // Expected: quarters should be consecutive (allowing year rollover)
    const isSequential =
      (currentQ === nextQ + 1 && currentYear === nextYear) || // Same year, prev quarter
      (currentQ === 1 && nextQ === 4 && currentYear === nextYear + 1) // Year rollover

    if (!isSequential) {
      issues.push({
        severity: 'warning',
        category: 'non_sequential_quarters',
        message: `Non-sequential fiscal periods: ${current.fiscalYear} ${current.fiscalQuarter} → ${next.fiscalYear} ${next.fiscalQuarter}`,
        field: 'fiscalQuarter',
        details: { currentQuarter: `${current.fiscalYear} ${current.fiscalQuarter}`, nextQuarter: `${next.fiscalYear} ${next.fiscalQuarter}` }
      })
    }
  }

  // Check for duplicate fiscal periods
  const periodKeys = quarters.map(q => `${q.fiscalYear}-${q.fiscalQuarter}`).filter(Boolean)
  const duplicates = periodKeys.filter((key, index) => periodKeys.indexOf(key) !== index)

  if (duplicates.length > 0) {
    issues.push({
      severity: 'critical',
      category: 'duplicate_periods',
      message: `Duplicate fiscal periods found: ${[...new Set(duplicates)].join(', ')}`,
      field: 'fiscalQuarter',
      details: { duplicates: [...new Set(duplicates)] }
    })
    return { valid: false, issues }
  }

  return { valid: issues.filter(i => i.severity === 'critical').length === 0, issues }
}

/**
 * Data completeness validation
 * Ensures critical metrics are present and non-null
 */
export function validateDataCompleteness(stock) {
  const issues = []

  // Required fundamental metrics
  const requiredMetrics = [
    { path: 'price', label: 'Current Price' },
    { path: 'market_cap', label: 'Market Cap' },
    { path: 'financials.revenue', label: 'Revenue' },
    { path: 'financials.earnings', label: 'Earnings' },
    { path: 'ratios.pe', label: 'P/E Ratio' },
    { path: 'ratios.debt_to_equity', label: 'Debt/Equity' }
  ]

  requiredMetrics.forEach(metric => {
    const value = getNestedValue(stock, metric.path)

    if (value === null || value === undefined || value === '') {
      issues.push({
        severity: 'warning',
        category: 'missing_metric',
        message: `Missing ${metric.label}`,
        field: metric.path
      })
    }

    // Check for obviously invalid values
    if (typeof value === 'number') {
      if (isNaN(value) || !isFinite(value)) {
        issues.push({
          severity: 'critical',
          category: 'invalid_value',
          message: `Invalid ${metric.label}: ${value}`,
          field: metric.path
        })
      }

      // Negative market cap or price = data error
      if ((metric.path === 'price' || metric.path === 'market_cap') && value < 0) {
        issues.push({
          severity: 'critical',
          category: 'invalid_value',
          message: `Negative ${metric.label}: ${value}`,
          field: metric.path
        })
      }
    }
  })

  // Count missing metrics
  const missingCount = issues.filter(i => i.category === 'missing_metric').length
  const criticalCount = issues.filter(i => i.severity === 'critical').length

  // Reject if >50% of required metrics are missing or any critical issues
  const valid = missingCount <= requiredMetrics.length / 2 && criticalCount === 0

  return { valid, issues, stats: { missingCount, criticalCount, totalRequired: requiredMetrics.length } }
}

/**
 * Data freshness validation
 * Ensures price and financial data aren't stale
 */
export function validateDataFreshness(stock, options = {}) {
  const issues = []
  const now = new Date()

  const maxPriceAgeDays = options.maxPriceAgeDays || 7 // Price data older than 7 days is stale
  const maxFinancialsAgeDays = options.maxFinancialsAgeDays || 120 // Financial data older than 120 days (1 quarter) is stale

  // Check price freshness
  if (stock.priceUpdatedAt) {
    const priceAge = (now - new Date(stock.priceUpdatedAt)) / (1000 * 60 * 60 * 24)
    if (priceAge > maxPriceAgeDays) {
      issues.push({
        severity: 'warning',
        category: 'stale_price',
        message: `Price data is ${Math.floor(priceAge)} days old (threshold: ${maxPriceAgeDays} days)`,
        field: 'priceUpdatedAt',
        details: { ageDays: Math.floor(priceAge), threshold: maxPriceAgeDays }
      })
    }
  }

  // Check financial data freshness
  if (stock.financials?.quarterly && stock.financials.quarterly.length > 0) {
    const latestQuarter = stock.financials.quarterly[0]
    if (latestQuarter.reportDate) {
      const financialsAge = (now - new Date(latestQuarter.reportDate)) / (1000 * 60 * 60 * 24)
      if (financialsAge > maxFinancialsAgeDays) {
        issues.push({
          severity: 'warning',
          category: 'stale_financials',
          message: `Latest financials are ${Math.floor(financialsAge)} days old (threshold: ${maxFinancialsAgeDays} days)`,
          field: 'financials.quarterly[0].reportDate',
          details: { ageDays: Math.floor(financialsAge), threshold: maxFinancialsAgeDays }
        })
      }
    }
  }

  return { valid: issues.filter(i => i.severity === 'critical').length === 0, issues }
}

/**
 * Comprehensive validation pipeline
 * Runs all validation checks and returns overall verdict
 */
export function validateStock(stock, options = {}) {
  const results = {
    ticker: stock.ticker,
    valid: true,
    excluded: false,
    issues: [],
    categories: {
      fiscal_periods: null,
      data_completeness: null,
      data_freshness: null
    }
  }

  // Run all validations
  const fiscalCheck = validateFiscalPeriods(stock)
  const completenessCheck = validateDataCompleteness(stock)
  const freshnessCheck = validateDataFreshness(stock, options)

  results.categories.fiscal_periods = fiscalCheck
  results.categories.data_completeness = completenessCheck
  results.categories.data_freshness = freshnessCheck

  // Aggregate issues
  results.issues = [
    ...fiscalCheck.issues,
    ...completenessCheck.issues,
    ...freshnessCheck.issues
  ]

  // Determine if stock should be excluded
  const hasCriticalIssues = results.issues.some(i => i.severity === 'critical')
  const tooManyWarnings = results.issues.filter(i => i.severity === 'warning').length > 5

  results.valid = !hasCriticalIssues && !tooManyWarnings
  results.excluded = !results.valid

  // Add exclusion summary
  if (results.excluded) {
    const criticalIssues = results.issues.filter(i => i.severity === 'critical')
    results.exclusionReason = criticalIssues.length > 0
      ? criticalIssues.map(i => i.message).join('; ')
      : 'Too many data quality warnings'
  }

  return results
}

/**
 * Batch validate stocks
 * Returns {passed: [], excluded: []}
 */
export function validateStockBatch(stocks, options = {}) {
  const results = {
    passed: [],
    excluded: [],
    summary: {
      total: stocks.length,
      passed: 0,
      excluded: 0,
      exclusionReasons: {}
    }
  }

  stocks.forEach(stock => {
    const validation = validateStock(stock, options)

    if (validation.valid) {
      results.passed.push(stock)
      results.summary.passed++
    } else {
      results.excluded.push({
        stock,
        validation
      })
      results.summary.excluded++

      // Track exclusion reasons
      validation.issues
        .filter(i => i.severity === 'critical')
        .forEach(issue => {
          if (!results.summary.exclusionReasons[issue.category]) {
            results.summary.exclusionReasons[issue.category] = 0
          }
          results.summary.exclusionReasons[issue.category]++
        })
    }
  })

  return results
}

/**
 * Helper: Get nested object value by path
 */
function getNestedValue(obj, path) {
  return path.split('.').reduce((current, key) => current?.[key], obj)
}

/**
 * Format validation results for display
 */
export function formatValidationReport(validation) {
  const lines = []

  lines.push(`Stock: ${validation.ticker}`)
  lines.push(`Status: ${validation.excluded ? '❌ EXCLUDED' : '✅ PASSED'}`)

  if (validation.exclusionReason) {
    lines.push(`Reason: ${validation.exclusionReason}`)
  }

  if (validation.issues.length > 0) {
    lines.push('\nIssues:')
    validation.issues.forEach(issue => {
      const icon = issue.severity === 'critical' ? '🔴' : '⚠️'
      lines.push(`  ${icon} [${issue.category}] ${issue.message}`)
      if (issue.details) {
        lines.push(`     Details: ${JSON.stringify(issue.details)}`)
      }
    })
  }

  return lines.join('\n')
}
