import { describe, expect, it } from 'vitest'
import {
  MEDIUM_META, getMediumMeta, getAllMediumMeta, isKnownMedium,
  isMediumImplemented, loadMedium, DEFAULT_MEDIUM_DURING_BUILD, DEFAULT_MEDIUM_AT_CUTOVER,
} from './registry.js'

describe('MEDIUM_META', () => {
  it('lists exactly twelve mediums', () => {
    expect(MEDIUM_META).toHaveLength(12)
  })

  it('every entry has a unique id', () => {
    const ids = MEDIUM_META.map((entry) => entry.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('classic is the only medium that accepts an inline accent', () => {
    const accentMediums = MEDIUM_META.filter((entry) => entry.acceptsAccent).map((entry) => entry.id)
    expect(accentMediums).toEqual(['classic'])
  })

  it('exactly six mediums are flagged to ship at launch (the recommendation)', () => {
    expect(MEDIUM_META.filter((entry) => entry.shipAtLaunch)).toHaveLength(6)
  })

  it('the build-time default and cutover default are both real, known mediums', () => {
    expect(isKnownMedium(DEFAULT_MEDIUM_DURING_BUILD)).toBe(true)
    expect(isKnownMedium(DEFAULT_MEDIUM_AT_CUTOVER)).toBe(true)
  })
})

describe('getMediumMeta / getAllMediumMeta / isKnownMedium', () => {
  it('finds a known medium by id', () => {
    expect(getMediumMeta('gallery')?.label).toBe('Gallery')
  })

  it('returns null for an unknown id', () => {
    expect(getMediumMeta('made-up')).toBeNull()
  })

  it('returns the full list', () => {
    expect(getAllMediumMeta()).toBe(MEDIUM_META)
  })

  it('isKnownMedium is false for a made-up id', () => {
    expect(isKnownMedium('made-up')).toBe(false)
  })
})

describe('isMediumImplemented / loadMedium', () => {
  it('is true only for mediums that actually have a manifest.js on disk (Phase 2b, in progress)', () => {
    // Grows as Phase 2b lands each medium — update this list alongside each new manifest.js.
    const implemented = new Set(['cockpit', 'neon', 'poster', 'ticker', 'gallery'])
    for (const entry of MEDIUM_META) {
      expect(isMediumImplemented(entry.id)).toBe(implemented.has(entry.id))
    }
  })

  it('rejects with a clear, catchable error for an unknown medium', async () => {
    await expect(loadMedium('not-a-medium')).rejects.toThrow(/Unknown medium/)
  })

  it('rejects with a clear, catchable error for a known-but-unbuilt medium', async () => {
    await expect(loadMedium('book')).rejects.toThrow(/has not been built yet/)
  })
})
