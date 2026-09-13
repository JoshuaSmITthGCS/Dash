import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading, Move, RefreshProgress } from '../components/Bits'
import Icon from '../components/Icons.jsx'
import { useScreenRefresh } from '../lib/useScreenRefresh'
import { ScreenNavigation } from './ResearchScreen'
import DataTable from '../components/DataTable.jsx'
import { ResponsiveControlPanel } from '../components/MobileSheet.jsx'
import BarTimeline from '../components/BarTimeline.jsx'

const FLAG_LABELS = {
  LATE_FILING: 'Late filing',
  OPTIONS_TRADE: 'Options trade',
  RARE_TRADER: 'Rare trader',
  CONCENTRATED_SIZE: 'Concentrated size',
  CLUSTER_TRADE: 'Cluster trade',
  SAME_SECTOR_REPEAT: 'Same-sector repeat',
  BUY_SELL_FLIP: 'Buy/sell flip',
  NOVEL_TICKER: 'Novel ticker',
  COMMITTEE_OVERLAP: 'Committee overlap',
}

const TRACKED_TIER_LABELS = {
  activity: 'High activity',
  performance: 'Top 2025 return',
  jurisdiction: 'Committee tracked',
}

const COMPONENT_LABELS = {
  size: 'Size',
  committee_overlap: 'Committee jurisdiction',
  excess_return: 'Beat the S&P',
  filing_delay: 'Disclosure lag',
  news_proximity: 'Traded before the news',
}

const money = (value, digits = 0) =>
  value == null ? '–' : `$${Number(value).toLocaleString('en-US', { maximumFractionDigits: digits })}`

const compactMoney = (value) => {
  if (value == null) return '–'
  if (value >= 1e9) return `$${(value / 1e9).toFixed(3)}B`
  if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`
  return money(value)
}

const pct = (value, digits = 1) =>
  value == null ? '\u2013' : `${value >= 0 ? '+' : ''}${Number(value).toFixed(digits)}%`

// An empty screen has more than one cause, and "nothing was disclosed this week" is the only
// one that needs no attention. Saying that when the disclosure feed actually refused every
// request would hide a broken collector behind a reassuring sentence.
export function emptyNote(data) {
  const failures = data?.collection?.failures || []
  if (data?.reason_code === 'CONGRESS_DISCLOSURE_FEED_UNAVAILABLE') {
    return `Disclosure feed unavailable, so nothing could be collected this run${failures.length ? ` (${failures[0]})` : ''}.`
  }
  if (data?.reason_code === 'NO_DISCLOSURES_IN_PUBLISH_WINDOW') {
    return `No disclosures filed in the trailing ${data.publish_window_days || 120} days.`
  }
  return 'No disclosures collected yet – this screen updates weekly.'
}

// One point per calendar month of the disclosed trade's transaction date (when the
// trade happened, not when it was disclosed), summing each row's amount-range midpoint
// — the disclosure forms report a band, not an exact dollar figure, so the midpoint is
// the least-wrong single number to add across rows.
function monthlyVolume(rows) {
  const byMonth = new Map()
  rows.forEach((row) => {
    const month = (row.transaction_date || '').slice(0, 7)
    if (!month) return
    const lower = row.amount_lower
    const upper = row.amount_upper
    if (lower == null && upper == null) return
    const midpoint = lower != null && upper != null ? (lower + upper) / 2 : (lower ?? upper)
    byMonth.set(month, (byMonth.get(month) || 0) + midpoint)
  })
  return [...byMonth.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([month, value]) => ({ id: month, label: month, value }))
}

// Three tiers over the published per-trade signal_strength (build_congress_screen's
// politician_performance.signal_strength: disclosed size x recency x the filer's shrunk,
// market-relative performance track record). Display-only ranking aid, never an
// advisor_engine input - same disclaimer every other panel on this page already carries.
const SIGNAL_TIERS = [
  { id: 'strong', min: 0.8, tone: 'high', label: 'Strong' },
  { id: 'moderate', min: 0.3, tone: 'watch', label: 'Moderate' },
  { id: 'weak', min: 0, tone: 'neutral', label: 'Weak' },
]

function signalTier(strength) {
  const value = strength ?? 0
  return SIGNAL_TIERS.find((tier) => value >= tier.min) || SIGNAL_TIERS[SIGNAL_TIERS.length - 1]
}

function performanceLookup(data) {
  const board = data?.politician_performance?.leaderboard || []
  const byName = new Map(board.map((row) => [row.politician, row]))
  return (representative) => byName.get(representative) || null
}

// Not a black box: the badge alone is a bucketed strength label, so the expand shows the
// filer's actual shrunk win rate, average alpha vs SPY, and how many priced buys that is
// built from - stats absent for a filer with no priced buy yet (their signal still uses
// the population baseline, but there is nothing politician-specific to show).
function SignalBadge({ strength, stats }) {
  const tier = signalTier(strength)
  return (
    <details className="trade-identity-reveal signal-badge-reveal">
      <summary><span className={`tier ${tier.tone}`}>{tier.label}</span></summary>
      <span className="signal-badge-detail">
        {stats ? <>
          <b>{`${Math.round(stats.win_rate * 100)}% beat S&P`}</b>
          <small>{`avg alpha ${stats.avg_alpha_pct >= 0 ? '+' : ''}${stats.avg_alpha_pct.toFixed(1)}pp · ${stats.n_priced_buys} priced buy${stats.n_priced_buys === 1 ? '' : 's'} · ${stats.confidence} confidence`}</small>
        </> : <b>No priced track record yet</b>}
      </span>
    </details>
  )
}

// politician_performance.py's full leaderboard: the shrunk, market-relative performance
// ranking that signal_strength above already weights every trade by - shown here as its
// own panel so "who actually beats the market" is visible directly, not just folded into a
// per-trade multiplier. price_backfill reports how much of the accumulated disclosure
// history has been priced yet, since coverage fills in gradually across runs rather than
// completing immediately (see politician_performance.py's own docstring for why).
function LeaderboardPanel({ performance, source }) {
  const board = performance?.leaderboard
  if (!board?.length) return null
  const backfill = performance.price_backfill
  return (
    <div className="card political-signals" aria-label="Most profitable politicians">
      <div className="political-signals-head">
        <h2 className="political-signals-title">Most profitable politicians</h2>
        <span className="political-signals-note">
          {`Ranked by shrunk win rate and alpha vs. S&P over each filer's priced disclosed buys, most trades needed to earn the top weight – not a score, not advice.`}
          {backfill && ` ${backfill.equity_buys_priced.toLocaleString('en-US')} of ${backfill.equity_buys_total.toLocaleString('en-US')} disclosed equity buys priced so far (${backfill.coverage_pct}%) – this list grows as more history gets priced.`}
        </span>
      </div>
      <DataTable
        rows={board}
        getKey={(row) => row.politician}
        columns={[
          { key: 'rank', label: '#', cell: (row) => <span className="mono">{row.rank}</span> },
          { key: 'politician', label: 'Politician', cell: (row) => <b>{row.politician}</b> },
          { key: 'performance_score', label: 'Weight', numeric: true, cell: (row) => {
            const tier = signalTier(row.performance_score)
            return <span className={`tier ${tier.tone}`}>{tier.label}</span>
          } },
          { key: 'win_rate', label: 'Win rate', numeric: true,
            cell: (row) => <span className="mono">{`${Math.round(row.win_rate * 100)}%`}</span> },
          { key: 'avg_alpha_pct', label: 'Avg alpha vs S&P', numeric: true, cell: (row) => <Move pct={row.avg_alpha_pct} /> },
          { key: 'n_priced_buys', label: 'Priced buys', numeric: true, cell: (row) => <span className="mono">{row.n_priced_buys}</span> },
          { key: 'confidence', label: 'Confidence', cell: (row) => <span className="mono">{row.confidence}</span> },
          // Third-party, and labelled as such in its own column rather than folded into the
          // alpha beside it: a 2025 calendar-year estimate built from disclosure midpoints is
          // not the same measurement as shrunk alpha over priced buys, and averaging the two
          // would produce a number neither methodology supports.
          { key: 'external_return_2025_pct', label: '2025 return (external)', numeric: true,
            sortValue: (row) => row.external_return_2025_pct ?? -Infinity,
            cell: (row) => row.external_return_2025_pct != null
              ? <span className="mono">{pct(row.external_return_2025_pct)}</span>
              : <span className="mono faint-cell">\u2013</span> },
        ]}
        mobile={{
          titleColumn: 'politician',
          title: (row) => row.politician,
          subtitle: (row) => `${Math.round(row.win_rate * 100)}% win rate · ${row.n_priced_buys} priced buy(s)`,
        }}
      />
      {source?.publisher && (
        <p className="disclaimer">
          {`"2025 return (external)" is ${source.publisher}'s estimate as of ${source.as_of}, benchmarked against ${source.benchmark_symbol || 'SPY'} at ${pct(source.benchmark_return_pct)} – not produced by this pipeline. ${source.methodology || ''}`}
        </p>
      )}
    </div>
  )
}

function activityLookup(activity) {
  const byPolitician = new Map()
  ;(activity || []).forEach((profile) => byPolitician.set(profile.politician, profile))
  return byPolitician
}

// Blends disclosed size with the pipeline's own already-computed novelty flags, log-scaled so
// a flag is worth roughly a 10x-ish size jump rather than being swamped by the multi-order-of-
// magnitude spread between a $1,001 filing and a $25M one. NOVEL_TICKER (this filer has never
// disclosed this stock before) counts more than RARE_TRADER (this filer rarely files at all),
// since the former is about the stock and the latter about the person.
function tradeScore(row) {
  const size = row.amount_upper || row.amount_lower || 0
  const magnitude = size > 0 ? Math.log10(size) : 0
  const flags = row.flags || []
  const noveltyBonus = (flags.includes('NOVEL_TICKER') ? 1.5 : 0) + (flags.includes('RARE_TRADER') ? 1 : 0)
  return magnitude + noveltyBonus
}

// Cross-references two rankings that already exist independently: politician_performance's
// leaderboard (who is highest-ranked by shrunk win rate and alpha vs. S&P over their priced
// disclosed buys) and the raw disclosure feed (what they actually bought). For each of the
// highest-ranked Congress/Senate filers in turn, this takes their highest-scoring disclosed
// stock buy - a blend of disclosed size and novelty (see tradeScore above), not size alone -
// falling through to their next-best buy when the top one duplicates a ticker already picked,
// so all ten stocks are distinct. Executive-branch filers (the President, agency heads) are
// excluded - "congress and senate traders" only. A pick of a person's track record, not a
// claim about the stock; display-only, same as every other panel here.
export function buildTopPicks(leaderboard, results, activity, limit = 10) {
  if (!leaderboard?.length || !results?.length) return []
  const activityByName = activityLookup(activity)
  const ranked = [...leaderboard].sort((left, right) => (left.rank ?? Infinity) - (right.rank ?? Infinity))
  const picks = []
  const usedTickers = new Set()
  for (const entry of ranked) {
    if (picks.length >= limit) break
    const profile = activityByName.get(entry.politician)
    const names = new Set([entry.politician, ...(profile?.name_variants || [])])
    const buys = results
      .filter((row) => names.has(row.representative) && row.transaction_type === 'Purchase'
        && row.chamber !== 'executive' && row.symbol && !usedTickers.has(row.symbol))
      .sort((left, right) => tradeScore(right) - tradeScore(left)
        || (right.transaction_date || '').localeCompare(left.transaction_date || ''))
    if (!buys.length) continue
    usedTickers.add(buys[0].symbol)
    picks.push({ ...buys[0], performance: entry })
  }
  return picks
}

// The headline panel: ten distinct stocks, each the highest-scoring disclosed buy (size blended
// with novelty, see tradeScore) from a different highest-ranked filer, so the page leads with
// "what the most profitable traders are actually buying" rather than making a reader dig for it
// below the full leaderboard and disclosure table.
function TopPicksPanel({ picks }) {
  if (!picks?.length) return null
  return (
    <div className="card political-signals top-picks-panel" aria-label="Top 10 picks from high-alpha traders">
      <div className="political-signals-head">
        <h2 className="political-signals-title">Top 10 picks from high-alpha traders</h2>
        <span className="political-signals-note">
          {`One disclosed buy from each of the top ${picks.length} Congress and Senate filers, ranked by shrunk win rate and alpha vs. the S&P over their priced disclosed buys – ten distinct stocks, one per filer. Within each filer's own buys, this picks the one blending disclosed size with novelty (a stock they haven't disclosed before, or a filer who rarely discloses at all) rather than size alone, falling through to their next-best buy when the top one repeats a ticker already picked. A pick of a person's track record, not a claim about the stock. Not a score, not advice.`}
        </span>
      </div>
      <DataTable
        rows={picks}
        getKey={(row, index) => `${row.representative}-${row.symbol}-${index}`}
        columns={[
          { key: 'rank', label: '#', cell: (row) => <span className="mono">{row.performance.rank}</span> },
          { key: 'politician', label: 'Trader', cell: (row) => (
            <details className="trade-identity-reveal">
              <summary><b>{row.representative}</b></summary>
              <span>
                <b>{`${Math.round(row.performance.win_rate * 100)}% beat S&P`}</b>
                <small>{`avg alpha ${pct(row.performance.avg_alpha_pct)} · ${row.performance.n_priced_buys} priced buy${row.performance.n_priced_buys === 1 ? '' : 's'} · ${row.performance.confidence} confidence`}</small>
              </span>
            </details>) },
          { key: 'symbol', label: 'Stock', cell: (row) => (
            <details className="trade-identity-reveal">
              <summary><b className="mono">{row.symbol}</b></summary>
              <span><b>{row.asset_description || 'Issuer unavailable'}</b></span>
            </details>) },
          { key: 'chamber', label: 'Chamber', cell: (row) => <span className="mono">{row.chamber}</span> },
          { key: 'amount', label: 'Size', numeric: true, cell: (row) => <span className="mono">{row.amount || '–'}</span> },
          { key: 'transaction_date', label: 'Bought', cell: (row) => <span className="mono">{row.transaction_date || '–'}</span> },
          { key: 'flags', label: 'Flags', sortable: false, cell: (row) => <FlagChips flags={row.flags} /> },
          { key: 'excess_return_vs_spy_pct', label: 'Vs S&P since', numeric: true,
            cell: (row) => row.excess_return_vs_spy_pct != null
              ? <Move pct={row.excess_return_vs_spy_pct} />
              : <span className="mono faint-cell">–</span> },
        ]}
        mobile={{
          titleColumn: 'symbol',
          title: (row) => row.symbol,
          subtitle: (row) => `${row.representative} · ${row.transaction_date || 'date unavailable'}`,
        }}
      />
    </div>
  )
}

// political_tracking.activity_profiles(): who discloses the most, over the FULL accumulated
// store rather than the published window. Deliberately a different ranking from
// LeaderboardPanel above - "whose feed is worth watching at all" and "who has actually been
// right" are different questions, and a filer can top one while sitting nowhere on the
// other, so both are shown rather than one standing in for the other.
function ActivityPanel({ profiles, tracking, source }) {
  // Scoped to this panel on purpose. The disclosure table below has its own tracked-filers
  // filter; one shared flag would mean narrowing this list silently narrowed that one too.
  const [trackedOnly, setTrackedOnly] = useState(false)
  const rows = useMemo(
    () => (trackedOnly ? (profiles || []).filter((row) => row.tracked) : profiles || []),
    [profiles, trackedOnly])
  if (!profiles?.length) return null
  return (
    <div className="card political-signals" aria-label="Most active political traders">
      <div className="political-signals-head">
        <h2 className="political-signals-title">Most active filers</h2>
        <span className="political-signals-note">
          Every disclosure ever collected, rolled up per filer – trade count, distinct stocks, disclosed
          volume (midpoint of each reported range), how long they take to file, and how much of it lands
          in a sector one of their committees oversees. Spelling variants of one person are counted once.
          Not a score, not advice.
          {tracking && ` Committee assignments are curated by hand for ${tracking.committee_profiles} filer(s) – a blank committee column means "not curated yet", never "no overlap".`}
        </span>
        <label className="political-tracked-toggle">
          <input type="checkbox" checked={trackedOnly}
            onChange={() => setTrackedOnly((current) => !current)} />
          {' Show tracked filers only'}
        </label>
      </div>
      {!rows.length ? <Empty note="No tracked filers have disclosed a trade yet." /> : (
        <DataTable
          rows={rows}
          getKey={(row) => row.canonical_name}
          columns={[
            { key: 'rank', label: '#', cell: (row) => <span className="mono">{row.rank}</span> },
            { key: 'politician', label: 'Filer', cell: (row) => (
              <details className="trade-identity-reveal">
                <summary><b>{row.politician}</b>{row.tracked && <span className="chip">Tracked</span>}</summary>
                <span>
                  <b>{row.committees?.length ? row.committees.join(' · ') : 'No curated committee assignments'}</b>
                  <small>
                    {[row.chambers?.join('/'), (row.tracked_tiers || []).map((tier) => TRACKED_TIER_LABELS[tier] || tier).join(' · '),
                      row.name_variants?.length ? `also filed as ${row.name_variants.join(', ')}` : null,
                      row.first_trade_date && `${row.first_trade_date} → ${row.last_trade_date}`].filter(Boolean).join(' · ')}
                  </small>
                </span>
              </details>) },
            { key: 'trades', label: 'Trades', numeric: true, cell: (row) => (
              <span className="mono">{`${row.trades.toLocaleString('en-US')} (${row.buys}b / ${row.sells}s)`}</span>) },
            { key: 'distinct_symbols', label: 'Stocks', numeric: true,
              cell: (row) => <span className="mono">{row.distinct_symbols}</span> },
            { key: 'disclosed_volume_midpoint', label: 'Disclosed volume', numeric: true,
              cell: (row) => <span className="mono">{compactMoney(row.disclosed_volume_midpoint)}</span> },
            { key: 'avg_filing_delay_days', label: 'Avg filing lag', numeric: true, cell: (row) => (
              <span className="mono">{row.avg_filing_delay_days != null ? `${row.avg_filing_delay_days}d` : '\u2013'}</span>) },
            { key: 'late_filings', label: 'Late filings', numeric: true, cell: (row) => (
              <span className="mono">
                {row.late_filing_rate != null ? `${row.late_filings} (${Math.round(row.late_filing_rate * 100)}%)` : row.late_filings}
              </span>) },
            { key: 'committee_overlap_trades', label: 'In their jurisdiction', numeric: true, cell: (row) => (
              <span className="mono">{row.committees?.length ? row.committee_overlap_trades : '\u2013'}</span>) },
            { key: 'performance', label: 'Avg alpha vs S&P', numeric: true,
              sortValue: (row) => row.performance?.avg_alpha_pct ?? -Infinity,
              cell: (row) => row.performance
                ? <Move pct={row.performance.avg_alpha_pct} />
                : <span className="mono faint-cell">\u2013</span> },
            { key: 'external', label: '2025 return', numeric: true,
              sortValue: (row) => row.external?.return_2025_pct ?? -Infinity,
              cell: (row) => row.external?.return_2025_pct != null
                ? <span className="mono">{pct(row.external.return_2025_pct)}</span>
                : <span className="mono faint-cell">\u2013</span> },
          ]}
          mobile={{
            titleColumn: 'politician',
            title: (row) => row.politician,
            subtitle: (row) => `${row.trades.toLocaleString('en-US')} trades · ${row.distinct_symbols} stocks · ${compactMoney(row.disclosed_volume_midpoint)}`,
          }}
        />
      )}
      {source?.publisher && (
        <p className="disclaimer">
          {`"2025 return" is a third-party estimate from ${source.publisher}${source.publication ? `, ${source.publication}` : ''} (as of ${source.as_of}), not computed here: it covers the 2025 calendar year and estimates share counts from disclosure midpoints, so it is not the same measurement as the alpha column beside it and the two must not be compared directly.`}
        </p>
      )}
    </div>
  )
}

// political_tracking.unusual_timing(): a ranking of individual disclosures by how many
// separately-computable things are unusual about them at once - size, whether a committee
// the filer sits on has jurisdiction over the stock's sector, how the trade did against SPY,
// how long it went unreported, and (only when the news feed is live) whether it preceded a
// policy headline in that name. A ranking of rows, not of people, and emphatically not an
// allegation: every component is a public, checkable fact, and none of them speak to motive.
function UnusualTimingPanel({ timing }) {
  const rows = timing?.results
  if (!rows?.length) return null
  return (
    <div className="card political-signals" aria-label="Disclosures unusual on several axes">
      <div className="political-signals-head">
        <h2 className="political-signals-title">Unusual on more than one axis</h2>
        <span className="political-signals-note">
          {`Disclosures where several independently-computable things are unusual at the same time – any one of them alone is weak. Ranked out of ${timing.candidates.toLocaleString('en-US')} qualifying disclosure(s), at most ${timing.config?.max_per_filer ?? 2} per filer so one bulk annual filing can't crowd out the rest. Not a finding of wrongdoing, not a score, not advice.`}
          {timing.news_component_active === false && ' The "traded before the news" component is switched off this run because the news feed is not live – it is unmeasured, not zero.'}
        </span>
      </div>
      <DataTable
        rows={rows}
        getKey={(row) => `${row.representative}-${row.ticker}-${row.transaction_date}-${row.rank}`}
        columns={[
          { key: 'rank', label: '#', cell: (row) => <span className="mono">{row.rank}</span> },
          { key: 'unusual_score', label: 'Combined', numeric: true, cell: (row) => {
            const tier = signalTier(row.unusual_score)
            return <span className={`tier ${tier.tone}`}>{row.unusual_score.toFixed(2)}</span>
          } },
          { key: 'ticker', label: 'Stock', cell: (row) => (
            <details className="trade-identity-reveal">
              <summary><b className="mono">{row.ticker}</b></summary>
              <span><b>{row.asset_description || 'Issuer unavailable'}</b></span>
            </details>) },
          { key: 'representative', label: 'Filer', cell: (row) => (
            <details className="trade-identity-reveal">
              <summary><b>{row.representative}</b></summary>
              <span>
                <b>{row.committee_overlap
                  ? `${row.committee_overlap.committees.join(' · ')} – jurisdiction over ${row.committee_overlap.sector}`
                  : 'No curated committee overlap for this trade'}</b>
                <small>{filerRole(row)}</small>
              </span>
            </details>) },
          { key: 'transaction_type', label: 'Type', cell: (row) => row.transaction_type || '\u2013' },
          { key: 'amount', label: 'Size', numeric: true, cell: (row) => <span className="mono">{row.amount || '\u2013'}</span> },
          { key: 'filing_delay_days', label: 'Filed after', numeric: true, cell: (row) => (
            <span className="mono">{row.filing_delay_days != null ? `${row.filing_delay_days}d` : '\u2013'}</span>) },
          { key: 'excess_return_vs_spy_pct', label: 'Vs S&P since', numeric: true,
            cell: (row) => row.excess_return_vs_spy_pct != null
              ? <Move pct={row.excess_return_vs_spy_pct} />
              : <span className="mono faint-cell">\u2013</span> },
          { key: 'components', label: 'What is unusual', sortable: false, cell: (row) => (
            <div className="congress-flag-row">
              {Object.entries(row.components)
                .filter(([, value]) => value > 0)
                .sort(([, left], [, right]) => right - left)
                .map(([name, value]) => (
                  <span key={name} className="chip">{`${COMPONENT_LABELS[name] || name} ${Math.round(value * 100)}%`}</span>
                ))}
            </div>) },
        ]}
        mobile={{
          titleColumn: 'ticker',
          title: (row) => row.ticker,
          subtitle: (row) => `${row.representative} · combined ${row.unusual_score.toFixed(2)}`,
        }}
      />
    </div>
  )
}

function FlagChips({ flags }) {
  if (!flags?.length) return <span className="mono text-faint">–</span>
  return <div className="congress-flag-row">
    {flags.map((flag) => <span key={flag} className="chip">{FLAG_LABELS[flag] || flag}</span>)}
  </div>
}

// A member of Congress reads as "chamber · district"; an executive-branch filer
// (office/agency present, no district) reads as "office · agency" instead.
function filerRole(row) {
  if (row.office) return [row.office, row.agency].filter(Boolean).join(' · ')
  return [row.chamber, row.district].filter(Boolean).join(' · ')
}

function filerLine(row) {
  return [row.representative, filerRole(row)].filter(Boolean).join(' · ')
}

// notable_signals()'s top-5 leaderboard: display-only, not a score - see
// build_congress_screen.py's docstring on why this never feeds the research score the way
// congress_signal.score_congressional_buying does.
function SignalsPanel({ signals }) {
  if (!signals?.length) return null
  return (
    <div className="card political-signals" aria-label="Most notable disclosures">
      <div className="political-signals-head">
        <h2 className="political-signals-title">Top disclosed signals</h2>
        <span className="political-signals-note">Largest, most novel, or most clustered disclosed trades this window – not a score, not advice.</span>
      </div>
      <ol className="political-signals-list">
        {signals.map((signal) => (
          <li key={signal.ticker} className="political-signal-card">
            <span className={`chip signal-direction ${signal.direction === 'BUY' ? 'positive' : 'negative'}`}>
              {signal.direction}
            </span>
            <b className="mono">{signal.ticker}</b>
            <span className="political-signal-filer">{filerLine(signal)}</span>
            <FlagChips flags={signal.flags} />
          </li>
        ))}
      </ol>
    </div>
  )
}

// top_ticker_aggregates()'s per-stock leaderboard: every disclosed trade in the window
// rolled up by ticker, so a stock several different filers quietly bought in separate
// tranches ranks alongside one filer's single outsized trade - display-only, same
// disclaimer as SignalsPanel above.
function TopTickersPanel({ tickers }) {
  if (!tickers?.length) return null
  return (
    <div className="card political-signals" aria-label="Top 10 unusual stocks">
      <div className="political-signals-head">
        <h2 className="political-signals-title">Top 10 unusual stocks</h2>
        <span className="political-signals-note">
          Every disclosed Congress and executive-branch trade this window, rolled up per stock by disclosed
          volume, how many distinct filers traded it, and clustering/novelty flags – not a score, not advice.
        </span>
      </div>
      <DataTable
        rows={tickers}
        getKey={(row) => row.ticker}
        columns={[
          { key: 'rank', label: '#', cell: (row) => <span className="mono">{row.rank}</span> },
          { key: 'symbol', label: 'Stock', cell: (row) => (
            <details className="trade-identity-reveal">
              <summary><b className="mono">{row.ticker}</b></summary>
              <span><b>{row.asset_description || 'Issuer unavailable'}</b></span>
            </details>) },
          { key: 'disclosed_volume_midpoint', label: 'Disclosed volume', numeric: true,
            cell: (row) => <span className="mono">{compactMoney(row.disclosed_volume_midpoint)}</span> },
          { key: 'max_single_trade_amount_upper', label: 'Biggest single trade', numeric: true,
            cell: (row) => <span className="mono">{compactMoney(row.max_single_trade_amount_upper)}</span> },
          { key: 'trade_count', label: 'Trades', numeric: true, cell: (row) => (
            <span className="mono">{`${row.trade_count} (${row.buy_count} buy / ${row.sell_count} sell)`}</span>) },
          { key: 'unique_politicians', label: 'Distinct filers', numeric: true, cell: (row) => (
            <details className="trade-identity-reveal">
              <summary><span className="mono">{row.unique_politicians}</span></summary>
              <span>{(row.politicians || []).join(', ') || 'Filer unavailable'}</span>
            </details>) },
          { key: 'flags', label: 'Flags', sortable: false, cell: (row) => <FlagChips flags={row.flags} /> },
        ]}
        mobile={{
          titleColumn: 'symbol',
          title: (row) => row.ticker,
          subtitle: (row) => `${compactMoney(row.disclosed_volume_midpoint)} disclosed · ${row.unique_politicians} filer(s)`,
        }}
      />
    </div>
  )
}

export default function PoliticalTrading() {
  const { data, loading, error, reload } = useData('screens/congress-trades.json')
  const refresh = useScreenRefresh('congress', reload)
  const [filters, setFilters] = useState({ chamber: 'all', flag: 'all', signal: 'all', filer: 'all', sort: 'disclosed' })
  const [trackedOnly, setTrackedOnly] = useState(false)
  const rows = data?.results || []
  const summary = data?.summary
  const lookupPerformance = useMemo(() => performanceLookup(data), [data])
  const topPicks = useMemo(
    () => buildTopPicks(data?.politician_performance?.leaderboard, rows, data?.politician_activity),
    [data, rows])

  // The filer picker lists whoever actually appears in this window, most-disclosed first -
  // a roster of all 500-odd members would be mostly empty options.
  const filerOptions = useMemo(() => {
    const counts = new Map()
    rows.forEach((row) => {
      if (row.representative) counts.set(row.representative, (counts.get(row.representative) || 0) + 1)
    })
    return [...counts.entries()]
      .sort(([leftName, left], [rightName, right]) => right - left || leftName.localeCompare(rightName))
      .map(([name, count]) => ({ name, count }))
  }, [rows])

  // Which filers the pipeline tracks, resolved through the activity profiles so a filer's
  // several disclosed spellings all match the one roster entry.
  const trackedNames = useMemo(() => new Set(
    (data?.politician_activity || [])
      .filter((profile) => profile.tracked)
      .flatMap((profile) => [profile.politician, ...(profile.name_variants || [])])), [data])

  const filtered = useMemo(() => {
    let next = rows.filter((row) => filters.chamber === 'all' || row.chamber === filters.chamber)
    if (filters.flag !== 'all') next = next.filter((row) => (row.flags || []).includes(filters.flag))
    if (filters.signal !== 'all') next = next.filter((row) => signalTier(row.signal_strength).id === filters.signal)
    if (filters.filer !== 'all') next = next.filter((row) => row.representative === filters.filer)
    if (trackedOnly) next = next.filter((row) => trackedNames.has(row.representative))
    const sorted = [...next]
    if (filters.sort === 'amount') {
      sorted.sort((left, right) => (right.amount_upper || 0) - (left.amount_upper || 0))
    } else if (filters.sort === 'performance') {
      sorted.sort((left, right) => (right.return_since_purchase_pct ?? -Infinity) - (left.return_since_purchase_pct ?? -Infinity))
    } else if (filters.sort === 'excess') {
      sorted.sort((left, right) => (right.excess_return_vs_spy_pct ?? -Infinity) - (left.excess_return_vs_spy_pct ?? -Infinity))
    } else if (filters.sort === 'signal') {
      sorted.sort((left, right) => (right.signal_strength ?? -Infinity) - (left.signal_strength ?? -Infinity))
    } else {
      sorted.sort((left, right) => (right.disclosure_date || '').localeCompare(left.disclosure_date || ''))
    }
    return sorted
  }, [rows, filters, trackedOnly, trackedNames])

  const update = (key) => (event) => setFilters((current) => ({ ...current, [key]: event.target.value }))
  const volumeByMonth = useMemo(() => monthlyVolume(rows), [rows])

  return <>
    <ScreenNavigation />
    <div className="page-head">
      <div>
        <span className="eyebrow">STOCK Act &amp; OGE 278-T disclosures</span>
        <h1 className="page-title">Political <span className="accent">trade alert</span></h1>
        <p className="page-sub">
          Senate, House, and executive-branch (OGE Form 278-T, including the President) trade disclosures,
          collected weekly from Financial Modeling Prep and the public House/Senate/executive-branch disclosure
          datasets – all mirrors of the same Clerk, eFD, and OGE filings. Flags are computed directly from the
          disclosure data – a late filing, an options trade, an unusually large or clustered position, a repeat
          pattern – not a claim that any trade was improper. Where a plain stock purchase has enough price
          history, "since purchase" shows how the stock has actually performed – a price fact, not a claim about
          why it moved or a recommendation to trade.
        </p>
      </div>
      {refresh.available && (
        <div className="page-actions">
          {/* This screen is on a weekly cron and the main research refresh does not
              collect it, so without this the only way to re-run it is to wait. */}
          <button className="secondary-button" onClick={refresh.requestRefresh} disabled={refresh.refreshing}
            title="Re-run the disclosure collection now – it reads every configured source and takes a few minutes">
            <Icon name="sync" size={17} className={refresh.refreshing ? 'refresh-spin' : ''} />
            {refresh.refreshing ? 'Collecting…' : 'Re-run collection'}
          </button>
        </div>
      )}
    </div>

    <RefreshProgress active={refresh.refreshing} elapsedLabel={refresh.elapsedLabel}
      percent={refresh.progress} stage={refresh.stage} />
    {refresh.message && (
      <div className={`card etf-state${refresh.status === 'error' ? '' : ' subtle'}`}
        role={refresh.status === 'error' ? 'alert' : 'status'}>
        <span>{refresh.message}</span>
      </div>
    )}

    {loading ? <Loading /> : error ? (
      <div className="card etf-state" role="alert"><strong>Political trades screen unavailable</strong><span>{error.message}</span></div>
    ) : <>
      {data && data.status === 'partial' && (
        // Rows are real but incomplete: at least one source answered and at least one did
        // not, so what follows understates the week rather than describing it.
        <div className="card etf-state" role="alert">
          <strong>Collected from some sources only</strong>
          <span>{`Some disclosures below may be missing – ${(data.collection?.failures || []).join('; ')}`}</span>
        </div>
      )}

      <TopPicksPanel picks={topPicks} />
      <LeaderboardPanel performance={data?.politician_performance}
        source={data?.politician_performance?.external_source} />
      <ActivityPanel profiles={data?.politician_activity} tracking={data?.tracking}
        source={data?.politician_performance?.external_source} />
      <UnusualTimingPanel timing={data?.unusual_timing} />
      <SignalsPanel signals={data?.signals} />
      <TopTickersPanel tickers={data?.top_tickers} />

      {summary && (
        <div className="grid congress-kpi-grid">
          <div className="card kpi">
            <div className="kpi-label">Trades</div>
            <div className="kpi-value">{summary.trades.toLocaleString('en-US')}</div>
          </div>
          <div className="card kpi">
            <div className="kpi-label">Filings</div>
            <div className="kpi-value">{summary.filings_estimated.toLocaleString('en-US')}</div>
            <div className="kpi-note">estimated</div>
          </div>
          <div className="card kpi">
            <div className="kpi-label">Volume</div>
            <div className="kpi-value">{compactMoney(summary.volume_upper)}</div>
            <div className="kpi-note">range ceiling</div>
          </div>
          <div className="card kpi">
            <div className="kpi-label">Politicians</div>
            <div className="kpi-value">{summary.politicians.toLocaleString('en-US')}</div>
          </div>
          <div className="card kpi">
            <div className="kpi-label">Issuers</div>
            <div className="kpi-value">{summary.issuers.toLocaleString('en-US')}</div>
          </div>
        </div>
      )}

      <BarTimeline
        points={volumeByMonth}
        yLabel="Disclosed volume"
        yFormatter={compactMoney}
        caption="Disclosed trade volume by month, midpoint of each disclosure's reported amount range"
      />

      <ResponsiveControlPanel label="Filter and sort" title="Filter disclosures"><div className="screen-filters" aria-label="Disclosure filters">
        <label>Chamber
          <select value={filters.chamber} onChange={update('chamber')}>
            <option value="all">All</option>
            <option value="senate">Senate</option>
            <option value="house">House</option>
            <option value="executive">Executive branch</option>
          </select>
        </label>
        <label>Flag
          <select value={filters.flag} onChange={update('flag')}>
            <option value="all">All</option>
            {Object.entries(FLAG_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>Signal
          <select value={filters.signal} onChange={update('signal')}>
            <option value="all">All</option>
            {SIGNAL_TIERS.map((tier) => <option key={tier.id} value={tier.id}>{tier.label}</option>)}
          </select>
        </label>
        <label>Filer
          <select value={filters.filer} onChange={update('filer')}>
            <option value="all">All</option>
            {filerOptions.map(({ name, count }) => (
              <option key={name} value={name}>{`${name} (${count})`}</option>
            ))}
          </select>
        </label>
        <label className="political-tracked-toggle">
          <input type="checkbox" checked={trackedOnly}
            onChange={() => setTrackedOnly((current) => !current)} />
          {' Tracked filers only'}
        </label>
        <label>Sort by
          <select value={filters.sort} onChange={update('sort')}>
            <option value="disclosed">Most recently disclosed</option>
            <option value="amount">Largest reported amount</option>
            <option value="performance">Best performance since purchase</option>
            <option value="excess">Best vs. the S&amp;P since purchase</option>
            <option value="signal">Highest weighted signal</option>
          </select>
        </label>
      </div></ResponsiveControlPanel>

      {!filtered.length ? (
        <Empty note={rows.length ? 'No disclosures match these filters.' : emptyNote(data)} />
      ) : (
        <DataTable
          rows={filtered}
          getKey={(row, index) => `${row.representative}-${row.symbol}-${row.transaction_date}-${index}`}
          columns={[
            { key: 'symbol', label: 'Stock', cell: (row) => (
              <details className="trade-identity-reveal">
                <summary><b className="mono">{row.symbol || '\u2013'}</b></summary>
                <span><b>{row.asset_description || 'Issuer unavailable'}</b><small>{row.representative || 'Representative unavailable'} \u00b7 {filerRole(row)}</small></span>
              </details>) },
            { key: 'signal_strength', label: 'Signal', numeric: true,
              cell: (row) => <SignalBadge strength={row.signal_strength} stats={lookupPerformance(row.representative)} /> },
            { key: 'transaction_type', label: 'Type', cell: (row) => row.transaction_type || '\u2013' },
            { key: 'amount', label: 'Size', numeric: true, cell: (row) => <span className="mono">{row.amount || '\u2013'}</span> },
            { key: 'transaction_date', label: 'Traded', cell: (row) => <span className="mono">{row.transaction_date || '\u2013'}</span> },
            { key: 'filing_delay_days', label: 'Filed after',
              cell: (row) => <span className="mono">{row.filing_delay_days != null ? `${row.filing_delay_days}d` : '\u2013'}</span> },
            { key: 'return_since_purchase_pct', label: 'Since purchase', numeric: true,
              cell: (row) => row.return_since_purchase_pct != null
                ? <Move pct={row.return_since_purchase_pct} />
                : <span className="mono faint-cell">–</span> },
            // "Since purchase" alone mostly measures what the market did over the holding
            // window: +20% in a +20% market is a flat trade. This is the same number the
            // leaderboard aggregates, per row.
            { key: 'excess_return_vs_spy_pct', label: 'Vs S&P', numeric: true,
              cell: (row) => row.excess_return_vs_spy_pct != null
                ? <Move pct={row.excess_return_vs_spy_pct} />
                : <span className="mono faint-cell">–</span> },
            { key: 'flags', label: 'Flags', sortable: false, cell: (row) => <FlagChips flags={row.flags} /> },
          ]}
          mobile={{
            titleColumn: 'symbol',
            title: (row) => row.symbol || 'Ticker unavailable',
            subtitle: (row) => `${row.transaction_type || 'Transaction'} \u00b7 ${row.transaction_date || 'date unavailable'}`,
          }}
        />
      )}

      <p className="disclaimer">
        {data?.history_days != null && `${data.history_days} day(s) of accumulated history. `}
        Reported amounts are STOCK Act ranges, not exact figures. "Since purchase" only appears for a plain stock
        purchase with enough collected price history, and reflects the price move alone, nothing else.
        Research only, not investment advice. Schema {data?.schema_version} · model {data?.model_version}.
      </p>
    </>}
  </>
}
