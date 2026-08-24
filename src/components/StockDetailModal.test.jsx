import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import {
  CoverageScoreDial, InsideInformationView, mergeResearchStock, themeExposureName,
  themeExposureScore,
} from './StockDetailModal.jsx'

describe('CoverageScoreDial', () => {
  it('reports the measured coverage', () => {
    render(<CoverageScoreDial score={71} dataCoverage={0.82} />)

    expect(screen.getByText('82% data coverage')).toBeInTheDocument()
  })

  it('says coverage was not measured rather than showing zero', () => {
    // The lightweight universe projection published no coverage for ~840 of 879 rows, and
    // the `?? 0` this replaces turned that silence into a confident "0% data coverage"
    // beside the faintest, most broken arc the dial can draw. Absent is not zero.
    render(<CoverageScoreDial score={67} dataCoverage={null} />)

    expect(screen.getByText('data coverage not measured')).toBeInTheDocument()
    expect(screen.queryByText('0% data coverage')).not.toBeInTheDocument()
  })

  it('still shows a genuinely measured zero as zero', () => {
    render(<CoverageScoreDial score={12} dataCoverage={0} />)

    expect(screen.getByText('0% data coverage')).toBeInTheDocument()
  })

  it('describes an unmeasured row to screen readers without asserting a percentage', () => {
    render(<CoverageScoreDial score={67} dataCoverage={undefined} />)

    expect(screen.getByRole('img')).toHaveAccessibleName(
      'Research score 67, data coverage not measured for this row')
  })
})

describe('theme exposure entries', () => {
  const published = {
    theme_id: 'ai_infrastructure', display_name: 'AI Infrastructure Buildout',
    theme_exposure_score: 74, opportunity_score: 71, eligible: true,
  }

  it('reads the name and score the pipeline publishes', () => {
    expect(themeExposureName(published)).toBe('AI Infrastructure Buildout')
    expect(themeExposureScore(published)).toBe(74)
  })

  it('still reads snapshots saved under the older spellings', () => {
    expect(themeExposureName({ theme: 'AI', score: 60 })).toBe('AI')
    expect(themeExposureScore({ theme: 'AI', score: 60 })).toBe(60)
  })

  it('reports an absent score as not-a-number rather than zero exposure', () => {
    expect(Number.isFinite(themeExposureScore({ theme_id: 'x' }))).toBe(false)
  })
})

describe('mergeResearchStock', () => {
  it('adds deep research fields without replacing a newer route price', () => {
    const supplied = {
      ticker: 'AAPL', price: 210,
      analysis_v2: { structural: { effective_score: 80 } },
    }
    const fullResearch = {
      research: [{
        ticker: 'AAPL', price: 200, modifiers: { total: 2 }, explainability: { attribution: {} },
        analysis_v2: { structural: { effective_score: 79 }, timeliness: { effective_score: 62 } },
      }],
    }

    expect(mergeResearchStock(supplied, fullResearch)).toMatchObject({
      price: 210,
      modifiers: { total: 2 },
      explainability: { attribution: {} },
      analysis_v2: {
        structural: { effective_score: 80 },
        timeliness: { effective_score: 62 },
      },
    })
  })

  it('keeps a lightweight row unchanged when no deeper row exists', () => {
    const supplied = { ticker: 'NEW', price: 12 }
    expect(mergeResearchStock(supplied, { research: [] })).toBe(supplied)
  })
})

describe('InsideInformationView', () => {
  it('renders nothing for a ticker with no notable disclosed activity', () => {
    const { container } = render(<MemoryRouter><InsideInformationView info={undefined} /></MemoryRouter>)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the institutional flag and combined score', () => {
    render(<MemoryRouter><InsideInformationView info={{
      score: 3.5, institutional_flag: 'CLUSTER_ACCUMULATION', congress_flags: [],
    }} /></MemoryRouter>)

    expect(screen.getByText('Curated managers accumulating')).toBeVisible()
    expect(screen.getByText(/3.5/)).toBeVisible()
    expect(screen.getByRole('link', { name: /Disclosed Positioning screen/ })).toHaveAttribute(
      'href', '/screens/inside-information')
  })

  it('shows Congressional flags with human-readable labels', () => {
    render(<MemoryRouter><InsideInformationView info={{
      score: 1.2, institutional_flag: null, congress_flags: ['EXTRAORDINARY_BUY', 'CLUSTER_TRADE'],
    }} /></MemoryRouter>)

    expect(screen.getByText('First trade in a small, unfamiliar company')).toBeVisible()
    expect(screen.getByText('3+ representatives, 14-day span')).toBeVisible()
  })
})
