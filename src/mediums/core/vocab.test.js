import { describe, expect, it } from 'vitest'
import { t, isKnownVocabKey, CANONICAL_VOCAB } from './vocab.js'

describe('t', () => {
  it('returns the medium override when present', () => {
    expect(t({ section: 'room' }, 'section')).toBe('room')
  })

  it('falls back to the canonical word when the medium has no override', () => {
    expect(t({}, 'section')).toBe(CANONICAL_VOCAB.section)
  })

  it('falls back to the canonical word for a missing vocabulary object', () => {
    expect(t(undefined, 'settings')).toBe('settings')
  })

  it('returns the raw key for a key with no canonical entry, never throws', () => {
    expect(t({}, 'not-a-real-key')).toBe('not-a-real-key')
  })
})

describe('isKnownVocabKey', () => {
  it('is true for canonical keys', () => {
    expect(isKnownVocabKey('section')).toBe(true)
  })

  it('is false for an unknown key', () => {
    expect(isKnownVocabKey('bogus')).toBe(false)
  })
})
