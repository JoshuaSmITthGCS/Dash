import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import CompanyLogo from './CompanyLogo.jsx'

describe('CompanyLogo', () => {
  it('uses existing source logos and falls back safely when they fail', () => {
    render(<CompanyLogo company={{ ticker: 'MSFT', name: 'Microsoft', logo_url: '/logo.png' }} />)
    const image = screen.getByRole('img', { name: 'Microsoft logo' })
    expect(image).toHaveAttribute('loading', 'lazy')
    fireEvent.error(image)
    expect(screen.getByRole('img', { name: 'Microsoft logo unavailable' })).toHaveTextContent('MS')
  })
})
