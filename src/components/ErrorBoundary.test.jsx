import { render, screen, fireEvent } from '@testing-library/react'

import ErrorBoundary from './ErrorBoundary.jsx'

function Bomb({ shouldThrow }) {
  if (shouldThrow) throw new Error('boom')
  return <div>fine</div>
}

describe('ErrorBoundary', () => {
  const originalError = console.error
  beforeEach(() => { console.error = vi.fn() })
  afterEach(() => { console.error = originalError })

  it('renders children when nothing throws', () => {
    render(<ErrorBoundary><Bomb shouldThrow={false} /></ErrorBoundary>)
    expect(screen.getByText('fine')).toBeVisible()
  })

  it('catches a render error instead of unmounting the whole tree', () => {
    render(<ErrorBoundary><Bomb shouldThrow /></ErrorBoundary>)
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong loading this page.')
    expect(screen.queryByText('fine')).not.toBeInTheDocument()
  })

  it('lets the user retry once the underlying problem is gone', () => {
    const { rerender } = render(<ErrorBoundary><Bomb shouldThrow /></ErrorBoundary>)
    expect(screen.getByRole('alert')).toBeVisible()

    rerender(<ErrorBoundary><Bomb shouldThrow={false} /></ErrorBoundary>)
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByText('fine')).toBeVisible()
  })
})
