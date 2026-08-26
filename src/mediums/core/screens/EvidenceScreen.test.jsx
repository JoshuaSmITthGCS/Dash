import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import EvidenceScreen from './EvidenceScreen.jsx'
import { MediumProvider } from '../MediumContext.jsx'
import { useData } from '../../../lib/useData.js'

vi.mock('../../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

const fakeManifest = { components: {} }

function renderEvidence(path = '/v2/evidence') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <MediumProvider value={fakeManifest}><EvidenceScreen /></MediumProvider>
    </MemoryRouter>
  )
}

describe('EvidenceScreen', () => {
  it('closes the docs-only gap: renders the no-signal-promoted disclosure with live counts', () => {
    useData.mockImplementation((file) => {
      if (file === 'validation/signal_metrics.json') return { data: { summary: { ready: 44, breached: 9, total: 64 } }, loading: false }
      if (file === 'validation/research_evidence.json') return { data: { headline: { ic_periods_accumulated: 0, ic_periods_required: 24 } }, loading: false }
      return { data: null, loading: false }
    })
    renderEvidence()
    expect(screen.getByTestId('promotion-disclosure')).toHaveTextContent('No signal has been promoted')
    expect(screen.getByTestId('promotion-disclosure')).toHaveTextContent('0 of the 24')
    expect(screen.getByTestId('metrics-summary')).toHaveTextContent('44 ready · 9 breached of 64')
  })

  it('shows the unavailable alert when signal metrics have not been published', () => {
    useData.mockReturnValue({ data: null, loading: false })
    renderEvidence()
    expect(screen.getByRole('alert')).toHaveTextContent('Signal metrics unavailable')
  })

  it('does not fetch the validation files for the methodology section', () => {
    useData.mockReturnValue({ data: null, loading: false })
    const { container } = renderEvidence('/v2/evidence?section=methodology')
    expect(container.querySelector('[data-section="methodology"]')).toBeInTheDocument()
    expect(screen.queryByTestId('metrics-summary')).not.toBeInTheDocument()
  })
})
