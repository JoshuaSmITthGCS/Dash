import { describe, expect, it } from 'vitest'
import { formatElapsed } from './useData'

describe('formatElapsed', () => {
  it('shows seconds only under a minute', () => {
    expect(formatElapsed(45_000)).toBe('45s')
  })

  it('shows minutes and seconds past a minute', () => {
    expect(formatElapsed(102_000)).toBe('1m 42s')
  })

  it('never goes negative on a clock skew', () => {
    expect(formatElapsed(-500)).toBe('0s')
  })

  it('rounds down mid-second', () => {
    expect(formatElapsed(59_900)).toBe('59s')
  })
})
