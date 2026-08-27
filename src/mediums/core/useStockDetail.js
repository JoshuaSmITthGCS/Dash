import { useSearchParams } from 'react-router-dom'

/**
 * Opens/closes the Stock Detail Sheet via a `?ticker=` URL search param — never local
 * component state. Matches the URL-addressability rule every other core screen already
 * follows (`?view=`, `?section=`, `?scope=`), which makes the sheet shareable and
 * back-button-dismissible and lets any call site open it without knowing anything about the
 * sheet's internals: `openStockDetail(row.ticker)`, done.
 *
 * `<StockDetailSheet />` reads `?ticker=` itself via this same hook, so a screen only has to
 * mount it once near its root and call `openStockDetail(ticker)` from wherever a row/button
 * lives — no props threaded down, no shared state lifted up.
 */
export function useStockDetail() {
  const [searchParams, setSearchParams] = useSearchParams()
  const ticker = searchParams.get('ticker')

  const openStockDetail = (nextTicker) => {
    if (!nextTicker) return
    const next = new URLSearchParams(searchParams)
    next.set('ticker', String(nextTicker).toUpperCase())
    setSearchParams(next)
  }

  const closeStockDetail = () => {
    const next = new URLSearchParams(searchParams)
    next.delete('ticker')
    setSearchParams(next)
  }

  return { ticker, openStockDetail, closeStockDetail }
}

export default useStockDetail
