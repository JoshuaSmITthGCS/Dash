import { useState } from 'react'
import Icon from './Icons'
import { suggestPriceTargets } from '../lib/watchlistPriceTargets.js'
import { useWatchlist } from '../lib/useWatchlist.js'

/** A star toggle that adds/removes a research row from the signed-in user's Firestore
 * watchlist, seeding dip/good-buy price targets from suggestPriceTargets on add. Used on
 * every research surface (research library, search, stock detail) so "watch this" is a
 * one-click action wherever a stock appears, not something buried on its own page.
 */
export default function WatchlistToggleButton({ stock, size = 20, className = '' }) {
  const { isWatched, addTicker, removeTicker } = useWatchlist()
  const [busy, setBusy] = useState(false)
  if (!stock?.ticker || stock.is_etf) return null
  const watched = isWatched(stock.ticker)

  const toggle = async (event) => {
    event.stopPropagation()
    setBusy(true)
    if (watched) {
      await removeTicker(stock.ticker)
    } else {
      const suggested = suggestPriceTargets(stock)
      await addTicker(stock.ticker, {
        dipPrice: suggested.dipBuy?.price ?? null,
        goodBuyPrice: suggested.goodBuy?.price ?? null,
        source: 'research_list',
      })
    }
    setBusy(false)
  }

  return (
    <button className={`icon-button watchlist-toggle ${watched ? 'watched' : ''} ${className}`} onClick={toggle} disabled={busy}
      aria-label={watched ? `Remove ${stock.ticker} from watchlist` : `Add ${stock.ticker} to watchlist`}
      title={watched ? 'On your watchlist' : 'Add to watchlist'}>
      <Icon name="watchlist" size={size} />
    </button>
  )
}
