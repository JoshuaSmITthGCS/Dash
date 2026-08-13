import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import InfoTag from './InfoTag.jsx'

describe('InfoTag', () => {
  it('hides its explanation until opened, via a native details/summary toggle', () => {
    render(<InfoTag label="Momentum"><p>What momentum measures.</p></InfoTag>)
    const toggle = screen.getByRole('group')
    expect(toggle).not.toHaveAttribute('open')
    expect(screen.getByText('What momentum measures.')).toBeInTheDocument()
    // <details> hides its non-summary content via the browser's native semantics rather
    // than removing it from the DOM, so closed state is asserted on the element, not by
    // querying for absence of the text.
  })

  it('is reachable by tap or click, not hover only - the trigger is a real summary control', () => {
    render(<InfoTag label="Reversal"><p>Reversal detail.</p></InfoTag>)
    expect(screen.getByLabelText('About: Reversal').tagName).toBe('SUMMARY')
  })

  it('falls back to a generic label when none is given', () => {
    render(<InfoTag><p>Detail.</p></InfoTag>)
    expect(screen.getByLabelText('About this')).toBeInTheDocument()
  })
})
