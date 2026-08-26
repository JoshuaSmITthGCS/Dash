import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ResearchScreen from './ResearchScreen.jsx'
import { MediumProvider } from '../MediumContext.jsx'
import { useData } from '../../../lib/useData.js'

vi.mock('../../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

const fakeManifest = { components: {} }

function renderResearch(initialPath = '/v2/research') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <MediumProvider value={fakeManifest}><ResearchScreen /></MediumProvider>
    </MemoryRouter>
  )
}

const REPORT = { research: [{ ticker: 'AAPL', name: 'Apple Inc.', score: 82 }, { ticker: 'MSFT', name: 'Microsoft', score: 75 }] }

describe('ResearchScreen', () => {
  it('reads the ?q= param on mount — the Alerts deep-link fix', () => {
    useData.mockReturnValue({ data: REPORT, loading: false })
    renderResearch('/v2/research?q=MSFT')
    expect(screen.getByTestId('result-count')).toHaveTextContent('1 result')
    expect(screen.getByText(/MSFT/)).toBeInTheDocument()
  })

  it('shows every result with no query', () => {
    useData.mockReturnValue({ data: REPORT, loading: false })
    renderResearch()
    expect(screen.getByTestId('result-count')).toHaveTextContent('2 results')
  })

  it('shows the empty state for a query matching nothing', () => {
    useData.mockReturnValue({ data: REPORT, loading: false })
    renderResearch('/v2/research?q=ZZZZ')
    expect(screen.getByRole('status')).toHaveTextContent('No companies match those filters.')
  })
})
