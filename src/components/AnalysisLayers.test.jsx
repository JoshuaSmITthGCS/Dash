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
})
