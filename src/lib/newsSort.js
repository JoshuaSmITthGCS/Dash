export const NEWS_SORT_OPTIONS = [
  { key: 'date', label: 'Date' },
  { key: 'relevance', label: 'Relevance' },
  { key: 'sentiment', label: 'Sentiment' },
]

// Lower research_rank means a stronger candidate (rank 1 = best), so relevance sorts ascending
// by default while date and sentiment sort with the strongest/most-recent value first.
const VALUE_FOR = {
  date: (item) => item.published_at ? new Date(item.published_at).getTime() : null,
  relevance: (item) => item.research_rank,
  sentiment: (item) => item.headline_direction,
}

export function sortNews(items, key, direction = 'desc') {
  const valueFor = VALUE_FOR[key] || VALUE_FOR.date
  const multiplier = direction === 'desc' ? -1 : 1

  return items
    .map((item, index) => ({ item, index }))
    .sort((left, right) => {
      const a = valueFor(left.item)
      const b = valueFor(right.item)
      const aMissing = a == null || (typeof a === 'number' && !Number.isFinite(a))
      const bMissing = b == null || (typeof b === 'number' && !Number.isFinite(b))
      if (aMissing !== bMissing) return aMissing ? 1 : -1
      if (aMissing) return left.index - right.index

      const comparison = Number(a) - Number(b)
      return comparison === 0 ? left.index - right.index : comparison * multiplier
    })
    .map(({ item }) => item)
}

export function nextNewsSort(current, key) {
  if (current.key === key) {
    return { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
  }
  return { key, direction: key === 'relevance' ? 'asc' : 'desc' }
}
