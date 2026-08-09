import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import AnalysisLayers from './AnalysisLayers'

describe('AnalysisLayers', () => {
  it('explains coverage and confidence independently', () => {
    render(<AnalysisLayers analysis={{
      structural: { raw_score: 80, effective_score: 62, coverage: 0.8, confidence: 0.39, classification: 'insufficient_evidence' },
      timeliness: { raw_score: 35, effective_score: 44, coverage: 0.5, confidence: 0.45, classification: 'weakening' },
    }} />)
    expect(screen.getByText('80%')).toBeInTheDocument()
    expect(screen.getByText('39%')).toBeInTheDocument()
    expect(screen.getByText(/cannot issue prescriptive company guidance/i)).toBeInTheDocument()
    expect(screen.getByText('weakening')).toBeInTheDocument()
  })

  it('renders an unresolved layer as unmeasured rather than as a score', () => {
    // The exact defect: timeliness published effective_score 50 with 0% coverage for every
    // company in the universe, and the UI rendered it as evidence.
    render(<AnalysisLayers analysis={{
      structural: { raw_score: 91, effective_score: 68, coverage: 0.59, confidence: 0.42, classification: 'quality_watch' },
      timeliness: {
        raw_score: null, effective_score: null, coverage: 0, confidence: 0,
        classification: 'unavailable', unavailable_reason: 'No free forward-estimate provider',
      },
    }} />)
    expect(screen.getByText('not measured')).toBeInTheDocument()
    expect(screen.getByText(/No free forward-estimate provider/)).toBeInTheDocument()
    expect(screen.queryByText('50')).not.toBeInTheDocument()
  })

  it('never labels a completeness ratio as confidence', () => {
    render(<AnalysisLayers analysis={{
      structural: { raw_score: 80, effective_score: 62, coverage: 0.8, confidence: 0.7, classification: 'quality_watch' },
    }} />)
    expect(screen.queryByText(/evidence confidence/i)).not.toBeInTheDocument()
    expect(screen.getByText('Data coverage')).toBeInTheDocument()
  })
})
