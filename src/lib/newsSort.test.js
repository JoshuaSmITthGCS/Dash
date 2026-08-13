import { describe, expect, it } from 'vitest'
import { nextNewsSort, sortNews } from './newsSort'

describe('news sorting', () => {
  const items = [
    { url: 'no-date', published_at: null, research_rank: null, headline_direction: null, rating: null, allocationPct: null },
    { url: 'old', published_at: '2026-01-01T00:00:00Z', research_rank: 12, headline_direction: -0.4, rating: -2, allocationPct: 3.5 },
    { url: 'new', published_at: '2026-08-01T00:00:00Z', research_rank: 3, headline_direction: 0.8, rating: 4, allocationPct: 18.2 },
  ]

  it('sorts by date, newest first by default, unavailable dates last', () => {
    expect(sortNews(items, 'date', 'desc').map((item) => item.url))
      .toEqual(['new', 'old', 'no-date'])
  })

  it('sorts by relevance, best (lowest) rank first', () => {
    expect(sortNews(items, 'relevance', 'asc').map((item) => item.url))
      .toEqual(['new', 'old', 'no-date'])
  })

  it('sorts by sentiment, most positive first', () => {
    expect(sortNews(items, 'sentiment', 'desc').map((item) => item.url))
      .toEqual(['new', 'old', 'no-date'])
  })

  it('sorts by rating, best (highest) first', () => {
    expect(sortNews(items, 'rating', 'desc').map((item) => item.url))
      .toEqual(['new', 'old', 'no-date'])
  })

  it('sorts by allocation, largest position first', () => {
    expect(sortNews(items, 'allocation', 'desc').map((item) => item.url))
      .toEqual(['new', 'old', 'no-date'])
  })

  it('defaults relevance to ascending and other keys to descending, and toggles an active column', () => {
    expect(nextNewsSort({ key: 'date', direction: 'desc' }, 'relevance'))
      .toEqual({ key: 'relevance', direction: 'asc' })
    expect(nextNewsSort({ key: 'relevance', direction: 'asc' }, 'sentiment'))
      .toEqual({ key: 'sentiment', direction: 'desc' })
    expect(nextNewsSort({ key: 'sentiment', direction: 'desc' }, 'sentiment'))
      .toEqual({ key: 'sentiment', direction: 'asc' })
  })
})
