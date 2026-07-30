import { useState } from 'react'
import { formatValidationReport } from '../lib/pipelineGuardrails'

/**
 * Data Quality Debug View
 *
 * Shows which stocks were excluded from rankings and why.
 * Helps users understand data quality issues and pipeline decisions.
 */
export default function DataQualityDebugView({ validationResults }) {
  const [expanded, setExpanded] = useState(false)
  const [selectedStock, setSelectedStock] = useState(null)

  if (!validationResults || validationResults.summary.excluded === 0) {
    return null
  }

  const { summary, excluded } = validationResults

  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 12,
      padding: 16,
      marginBottom: 20
    }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          cursor: 'pointer'
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <div>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>
            ⚠️ Data Quality Report
          </h3>
          <p style={{ margin: '4px 0 0', fontSize: 12, opacity: 0.7 }}>
            {summary.excluded} stock{summary.excluded === 1 ? '' : 's'} excluded due to data quality issues
          </p>
        </div>
        <button className="chip button-chip" style={{ fontSize: 11, padding: '4px 10px' }}>
          {expanded ? 'Hide' : 'Show'} Details
        </button>
      </div>

      {expanded && (
        <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
          {/* Exclusion Summary */}
          <div style={{
            background: 'var(--bg-elev)',
            borderRadius: 8,
            padding: 12,
            marginBottom: 16
          }}>
            <h4 style={{ margin: '0 0 8px', fontSize: 13, fontWeight: 600 }}>
              Exclusion Breakdown
            </h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, fontSize: 12 }}>
              <div>
                <div style={{ opacity: 0.7 }}>Total Evaluated</div>
                <div style={{ fontSize: 18, fontWeight: 600 }}>{summary.total}</div>
              </div>
              <div>
                <div style={{ opacity: 0.7 }}>Passed ✅</div>
                <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--pos)' }}>{summary.passed}</div>
              </div>
              <div>
                <div style={{ opacity: 0.7 }}>Excluded ❌</div>
                <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--neg)' }}>{summary.excluded}</div>
              </div>
              <div>
                <div style={{ opacity: 0.7 }}>Pass Rate</div>
                <div style={{ fontSize: 18, fontWeight: 600 }}>
                  {((summary.passed / summary.total) * 100).toFixed(1)}%
                </div>
              </div>
            </div>

            {Object.keys(summary.exclusionReasons).length > 0 && (
              <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
                  Common Issues:
                </div>
                {Object.entries(summary.exclusionReasons).map(([reason, count]) => (
                  <div key={reason} style={{ fontSize: 12, opacity: 0.8, marginBottom: 4 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                      {count}×
                    </span>{' '}
                    {reason.replace(/_/g, ' ')}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Excluded Stocks List */}
          <h4 style={{ margin: '0 0 12px', fontSize: 13, fontWeight: 600 }}>
            Excluded Stocks
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {excluded.map(({ stock, validation }) => {
              const isSelected = selectedStock === stock.ticker
              const criticalIssues = validation.issues.filter(i => i.severity === 'critical')
              const warningIssues = validation.issues.filter(i => i.severity === 'warning')

              return (
                <div
                  key={stock.ticker}
                  style={{
                    background: isSelected ? 'var(--bg-elev)' : 'transparent',
                    border: `1px solid ${isSelected ? 'var(--accent)' : 'var(--border)'}`,
                    borderRadius: 8,
                    padding: 12,
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                  }}
                  onClick={() => setSelectedStock(isSelected ? null : stock.ticker)}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontWeight: 600, fontFamily: 'var(--font-mono)', fontSize: 14 }}>
                        {stock.ticker}
                      </div>
                      <div style={{ fontSize: 11, opacity: 0.7, marginTop: 2 }}>
                        {validation.exclusionReason}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, fontSize: 11 }}>
                      {criticalIssues.length > 0 && (
                        <span className="chip" style={{
                          background: 'var(--neg)',
                          color: 'white',
                          padding: '3px 8px'
                        }}>
                          🔴 {criticalIssues.length} critical
                        </span>
                      )}
                      {warningIssues.length > 0 && (
                        <span className="chip" style={{
                          background: 'orange',
                          color: 'white',
                          padding: '3px 8px'
                        }}>
                          ⚠️ {warningIssues.length} warning{warningIssues.length === 1 ? '' : 's'}
                        </span>
                      )}
                    </div>
                  </div>

                  {isSelected && (
                    <div style={{
                      marginTop: 12,
                      paddingTop: 12,
                      borderTop: '1px solid var(--border)',
                      fontSize: 12
                    }}>
                      <div style={{ fontWeight: 600, marginBottom: 8 }}>Issue Details:</div>
                      {validation.issues.map((issue, i) => (
                        <div
                          key={i}
                          style={{
                            marginBottom: 8,
                            paddingLeft: 12,
                            borderLeft: `3px solid ${issue.severity === 'critical' ? 'var(--neg)' : 'orange'}`
                          }}
                        >
                          <div style={{ fontWeight: 600, marginBottom: 2 }}>
                            {issue.severity === 'critical' ? '🔴' : '⚠️'} {issue.category.replace(/_/g, ' ')}
                          </div>
                          <div style={{ opacity: 0.8 }}>{issue.message}</div>
                          {issue.field && (
                            <div style={{
                              fontSize: 10,
                              opacity: 0.6,
                              fontFamily: 'var(--font-mono)',
                              marginTop: 2
                            }}>
                              Field: {issue.field}
                            </div>
                          )}
                          {issue.details && (
                            <div style={{
                              fontSize: 10,
                              opacity: 0.6,
                              fontFamily: 'var(--font-mono)',
                              marginTop: 2,
                              background: 'var(--bg-card)',
                              padding: 4,
                              borderRadius: 4,
                              marginTop: 4
                            }}>
                              {JSON.stringify(issue.details, null, 2)}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* Explanation */}
          <div style={{
            marginTop: 16,
            padding: 12,
            background: 'var(--bg-elev)',
            borderRadius: 8,
            fontSize: 12,
            opacity: 0.7
          }}>
            <strong>Why stocks get excluded:</strong> We reject stocks with critical data quality issues like
            mismatched fiscal periods, duplicate quarters, negative market caps, or too many missing metrics.
            This ensures rankings are based on reliable, complete data.
          </div>
        </div>
      )}
    </div>
  )
}
