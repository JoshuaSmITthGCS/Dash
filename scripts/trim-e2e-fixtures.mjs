// Regenerates tests/e2e/fixtures/data/** from public/data/** so Playwright's mocked
// `**/data/**` route (tests/e2e/utils/mockData.mjs's mockDataRoutes()) has a trimmed fixture
// for every file the six core screens (src/mediums/core/screens/*.jsx) actually fetch via
// useData(), not just the four hand-trimmed files that existed before this script.
//
// Two trimming tiers:
//   - Tier 1 (trimTicketFile / trimEtfSnapshot): advisor.json, screens/congress-trades.json,
//     and the four etf/<TICKER>.json index snapshots — too large for row truncation to make a
//     dent, so these get real structural trimming keyed on the ticker set the already-trimmed
//     report.json/screens/swing.json fixtures reference (so cross-file lookups stay resolvable)
//     plus a buffer of extra tickers for "ticker not in my portfolio" test paths.
//   - Tier 2 (trimTier2Object): every other published screen/recipe file, truncated to a
//     representative sample of top-level rows with each row's own schema left untouched.
//
// Run with: node scripts/trim-e2e-fixtures.mjs

import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const PUBLIC_DATA = path.join(root, 'public/data')
const FIXTURES_DATA = path.join(root, 'tests/e2e/fixtures/data')

const TIER2_ROWS = 15
const EXTRA_TICKER_COUNT = 25
const ETF_HISTORY_DAYS = 280 // covers MarketsScreen's longest RANGE_DAYS window ('1Y' = 253) with headroom
const ETF_FULL_RANGE_KEYS = new Set(['1M', '3M', '6M', 'YTD', '1Y']) // small enough to keep intact
const ETF_LONG_RANGE_SAMPLE = 60 // 3Y/5Y/MAX get stride-sampled to this many points

const TIER1_ETF_TICKERS = ['SPY', 'QQQ', 'DIA', 'IWM']

// Every other file the six core screens fetch, per the useData()/RECIPE_FILES/STRATEGY_SCREENS
// inventory — see the task write-up this script was generated for. Any path with no matching
// file under public/data/ is skipped (logged), not fatal, since some recipes may not have
// published data yet.
const TIER2_FILES = [
  'benchmark-report.json',
  'etfs.json',
  'factors/french.json',
  'theme-peers.json',
  'validation/monte_carlo_projection.json',
  'screens/backtest-comparison.json',
  'screens/options-backtest.json',
  'screens/shadow-portfolios.json',
  'screens/inside-information.json',
  'screens/options.json',
  'screens/momentum.json',
  'screens/quality-value.json',
  'screens/earnings-timeliness.json',
  'screens/structural-tactical.json',
  'screens/early-session.json',
  'screens/institutional-13f.json',
  'screens/covered-calls.json',
  'screens/covered-calls-backtest.json',
  'screens/cash-secured-puts.json',
  'screens/cash-secured-puts-backtest.json',
  'screens/protective-puts.json',
  'screens/protective-puts-backtest.json',
  'screens/collars.json',
  'screens/collars-backtest.json',
  'screens/vertical-spreads.json',
  'screens/vertical-spreads-backtest.json',
  'screens/advanced-strategies.json',
  'screens/advanced-strategies-backtest.json',
  'screens/short-term-trades.json',
  'screens/short-term-trades-backtest.json',
]

function readPublicJson(relPath) {
  const full = path.join(PUBLIC_DATA, relPath)
  if (!fs.existsSync(full)) return null
  return JSON.parse(fs.readFileSync(full, 'utf8'))
}

function readFixtureJson(relPath) {
  return JSON.parse(fs.readFileSync(path.join(FIXTURES_DATA, relPath), 'utf8'))
}

function writeFixtureJson(relPath, data) {
  const full = path.join(FIXTURES_DATA, relPath)
  fs.mkdirSync(path.dirname(full), { recursive: true })
  fs.writeFileSync(full, `${JSON.stringify(data, null, 2)}\n`)
  const kb = (fs.statSync(full).size / 1024).toFixed(1)
  console.log(`  wrote ${relPath} (${kb} KB)`)
}

// Evenly spread `count` indices across `arr` (always including the first and last element),
// so a truncated array keeps some variety instead of just its first N rows.
function strideSample(arr, count) {
  if (!Array.isArray(arr) || arr.length <= count) return Array.isArray(arr) ? arr.slice() : arr
  if (count <= 1) return arr.slice(0, 1)
  const step = (arr.length - 1) / (count - 1)
  const indices = new Set()
  for (let i = 0; i < count; i++) indices.add(Math.round(i * step))
  return [...indices].sort((a, b) => a - b).map((i) => arr[i])
}

// ---- Tier 1: ticker set shared by advisor.json + screens/congress-trades.json ----

function collectRequiredTickers(reportFixture, swingFixture) {
  const tickers = new Set()
  const addFrom = (rows) => {
    for (const row of rows || []) if (row?.ticker) tickers.add(row.ticker)
  }
  addFrom(reportFixture.research)
  addFrom(reportFixture.portfolio_coverage)
  addFrom(reportFixture.screen_universe)
  addFrom(swingFixture.results)
  return tickers
}

// Extra tickers for "not in my portfolio"/"not published" test paths — prefer names that
// already carry full research detail (advisor.research is the small, deeply-enriched array),
// then fill any remaining slots from the much larger screen_universe/universe lists.
function pickExtraTickers(advisor, required, count) {
  const extra = new Set()
  const tryAdd = (ticker) => {
    if (extra.size >= count || !ticker || required.has(ticker) || extra.has(ticker)) return
    extra.add(ticker)
  }
  for (const row of advisor.research || []) tryAdd(row.ticker)
  if (extra.size < count) {
    for (const row of strideSample(advisor.screen_universe || [], count * 4)) tryAdd(row?.ticker)
  }
  if (extra.size < count) {
    for (const ticker of advisor.universe || []) tryAdd(ticker)
  }
  return extra
}

function trimAdvisor(advisor, keep) {
  const byTicker = (rows) => (rows || []).filter((row) => keep.has(row?.ticker))
  const trimmed = { ...advisor }
  trimmed.research = byTicker(advisor.research)
  trimmed.screen_universe = byTicker(advisor.screen_universe)
  trimmed.portfolio_coverage = byTicker(advisor.portfolio_coverage)
  trimmed.news = byTicker(advisor.news)
  trimmed.universe = (advisor.universe || []).filter((ticker) => keep.has(ticker))
  if (advisor.theme_screen?.by_ticker) {
    const by_ticker = {}
    for (const [ticker, value] of Object.entries(advisor.theme_screen.by_ticker)) {
      if (keep.has(ticker)) by_ticker[ticker] = value
    }
    trimmed.theme_screen = { ...advisor.theme_screen, by_ticker }
  }
  return trimmed
}

// screens/congress-trades.json keys its rows by `symbol`, not `ticker`; `signals` (the "most
// notable disclosures" panel) is left intact — it's already only 5 rows and isn't cross-
// referenced by ticker against any other fixture.
function trimCongressTrades(data, keep) {
  return { ...data, results: (data.results || []).filter((row) => keep.has(row?.symbol)) }
}

function trimEtfSnapshot(data) {
  const trimmed = { ...data }
  if (data.price_series) {
    trimmed.price_series = {
      ...data.price_series,
      fund: Array.isArray(data.price_series.fund) ? data.price_series.fund.slice(-ETF_HISTORY_DAYS) : data.price_series.fund,
      benchmark: Array.isArray(data.price_series.benchmark) ? data.price_series.benchmark.slice(-ETF_HISTORY_DAYS) : data.price_series.benchmark,
    }
  }
  if (data.chart_ranges) {
    const chart_ranges = {}
    for (const [key, range] of Object.entries(data.chart_ranges)) {
      const series = ETF_FULL_RANGE_KEYS.has(key) ? range.series : strideSample(range.series, ETF_LONG_RANGE_SAMPLE)
      chart_ranges[key] = { ...range, series, observation_count: Array.isArray(series) ? series.length : range.observation_count }
    }
    trimmed.chart_ranges = chart_ranges
  }
  return trimmed
}

// ---- Tier 2: generic top-level array truncation, row schema untouched ----

function trimTier2Object(data) {
  const trimmed = {}
  for (const [key, value] of Object.entries(data)) {
    trimmed[key] = Array.isArray(value) ? strideSample(value, TIER2_ROWS) : value
  }
  return trimmed
}

function main() {
  console.log('Loading reference fixtures (report.json, screens/swing.json)...')
  const reportFixture = readFixtureJson('report.json')
  const swingFixture = readFixtureJson('screens/swing.json')
  const required = collectRequiredTickers(reportFixture, swingFixture)
  console.log(`  ${required.size} tickers referenced by existing fixtures`)

  console.log('Loading public/data/advisor.json (~47MB, single parse)...')
  const advisor = readPublicJson('advisor.json')
  if (!advisor) throw new Error('public/data/advisor.json not found — cannot compute the Tier 1 ticker set')

  const extra = pickExtraTickers(advisor, required, EXTRA_TICKER_COUNT)
  const keep = new Set([...required, ...extra])
  console.log(`  keeping ${keep.size} tickers total (${required.size} required + ${extra.size} extra)`)

  console.log('Tier 1: advisor.json, screens/congress-trades.json, etf/{SPY,QQQ,DIA,IWM}.json')
  writeFixtureJson('advisor.json', trimAdvisor(advisor, keep))

  const congress = readPublicJson('screens/congress-trades.json')
  if (congress) writeFixtureJson('screens/congress-trades.json', trimCongressTrades(congress, keep))
  else console.warn('  SKIP screens/congress-trades.json (no source file under public/data/)')

  for (const ticker of TIER1_ETF_TICKERS) {
    const rel = `etf/${ticker}.json`
    const data = readPublicJson(rel)
    if (data) writeFixtureJson(rel, trimEtfSnapshot(data))
    else console.warn(`  SKIP ${rel} (no source file under public/data/)`)
  }

  console.log(`Tier 2: ${TIER2_FILES.length} recipe/backtest files, truncated to ~${TIER2_ROWS} rows per top-level array`)
  const skipped = []
  for (const rel of TIER2_FILES) {
    const data = readPublicJson(rel)
    if (data) {
      writeFixtureJson(rel, trimTier2Object(data))
    } else {
      skipped.push(rel)
      console.warn(`  SKIP ${rel} (no source file under public/data/)`)
    }
  }

  console.log('Done.')
  if (skipped.length) console.log(`Skipped, no public/data/ source: ${skipped.join(', ')}`)
}

main()
