/**
 * The ROUTE-INVENTORY.md §2 redirect map, as data. Consumed by:
 *   - App.jsx, at cutover, to generate <Navigate replace> routes for every retired path
 *   - the Phase 3 no-404/params-mapped assertion
 *   - a docs-consistency check that this table matches ROUTE-INVENTORY.md's own table
 *
 * `to` is a function of the matched params (from react-router's :param syntax in `from`) so a
 * param-carrying redirect (e.g. /search?q=X -> /research?q=X) maps its param instead of
 * dropping it. Every entry here has a matching row in ROUTE-INVENTORY.md §2 — this file must
 * never diverge from that document; update both together.
 */
export const REDIRECTS = Object.freeze([
  // Screens family -> /screens?recipe=<id>
  { from: '/screens/momentum', to: () => '/screens?recipe=momentum' },
  { from: '/screens/quality-value', to: () => '/screens?recipe=quality-value' },
  { from: '/screens/earnings', to: () => '/screens?recipe=earnings' },
  { from: '/screens/matrix', to: () => '/screens?recipe=matrix' },
  { from: '/screens/swing', to: () => '/screens?recipe=swing' },
  { from: '/screens/fast-growth', to: () => '/screens?recipe=fast-growth' },
  { from: '/screens/themes', to: () => '/screens?recipe=themes' },
  { from: '/screens/early-session', to: () => '/screens?recipe=early-session' },
  { from: '/screens/politics', to: () => '/screens?recipe=politics' },
  { from: '/screens/institutional', to: () => '/screens?recipe=institutional' },
  { from: '/screens/inside-information', to: () => '/screens?recipe=inside-information' },
  { from: '/screens/options', to: () => '/screens?recipe=options' },
  // Options' 7 per-strategy routes and their own 7 legacy flat redirects both chain-collapse
  // directly to the new URL — never redirect through the old /screens/options/<id> hop first.
  ...['short-term-trades', 'covered-call', 'cash-secured-put', 'protective-put', 'collar', 'vertical-spread', 'advanced-strategies']
    .flatMap((id) => [
      { from: `/screens/options/${id}`, to: () => `/screens?recipe=options&strategy=${id}` },
      { from: `/screens/${id}`, to: () => `/screens?recipe=options&strategy=${id}` },
    ]),

  // Evidence family -> /evidence?section=<s>
  { from: '/screens/backtests', to: () => '/evidence?section=backtests' },
  { from: '/screens/shadow', to: () => '/evidence?section=shadow' },
  { from: '/screens/validation', to: () => '/evidence?section=validation' },
  { from: '/methodology', to: () => '/evidence?section=methodology' },
  { from: '/glossary', to: () => '/evidence?section=glossary' },

  // Portfolio family -> /portfolio?view=<v>, absorbing Finances and Planning
  { from: '/finances', to: () => '/portfolio?view=finances' },
  { from: '/planning', to: () => '/portfolio?view=planning' },
  { from: '/portfolio/performance', to: () => '/portfolio?view=performance' },
  { from: '/portfolio/data-overview', to: () => '/portfolio?view=data' },
  { from: '/portfolio/diversification', to: () => '/portfolio?view=diversification' },
  { from: '/portfolio/insights', to: () => '/portfolio?view=insights' },

  // Markets family -> /markets?view=<v>, resolving /market vs /markets
  { from: '/news', to: () => '/markets?view=news' },
  { from: '/market', to: () => '/markets?view=news' },

  // Research family -> /research, absorbing Watchlist and Search (param mapped, not dropped)
  { from: '/watchlist', to: () => '/research?view=watchlist' },
  { from: '/search', to: (params, search) => `/research?q=${encodeURIComponent(search.get('q') || '')}` },
])

/** Finds the redirect entry for a path, or null if the path isn't retired. */
export function findRedirect(pathname) {
  return REDIRECTS.find((entry) => entry.from === pathname) || null
}

/** Resolves a redirect's destination URL given the current search params (for param-mapped entries). */
export function resolveRedirect(entry, searchParams = new URLSearchParams()) {
  return entry.to({}, searchParams)
}
