import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Tier, MetricPills, Move, Loading, Empty } from '../components/Bits.jsx'
import { ActionPill } from '../components/ActionGuidance.jsx'
import Icon from '../components/Icons.jsx'
import StockDetailModal from '../components/StockDetailModal.jsx'
import WatchlistToggleButton from '../components/WatchlistToggleButton.jsx'
import { getRecommendation } from '../lib/recommendation'
import CompanyLogo from '../components/CompanyLogo.jsx'
import Sparkline from '../components/Sparkline.jsx'
import InfoTag from '../components/InfoTag.jsx'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'
import { rankBreakoutInProgress, rankMomentum, rankReversal } from '../lib/researchScreens.js'
import {
  RANKING_MODELS, isRankingModel, modelCoverage, modelReason, rankByModel,
} from '../lib/rankingModels.js'
import { allocateFunds } from '../lib/fundsAllocation.js'
import MobileVirtualList from '../components/MobileVirtualList.jsx'
import { entryTiming } from '../lib/entryTiming.js'
import { useAlerts } from '../lib/useAlerts.js'

// Two different kinds of sort share one control, and the difference matters.
//
// A COLUMN SORT (score, 20-day return, sector valuation, fundamentals, data confidence)
// re-orders the whole research list by one published field. Every row still appears; only
// the order changes.
//
// A RANKING MODEL (research, fundamentals, sector valuation, catalyst, momentum, reversal,
// value turnaround, analyst conviction, peer read-through) is a separate scoring model with
// its own declared composition, not an ordering of one universal score - see
// src/lib/rankingModels.js. It scans the whole scored universe, keeps only the names that
// clear its own gate, scores them against sector peers, shrinks each score by that model's
// own confidence, and publishes the best MODEL_LIMIT. Selecting "Reversal" hands back the
// twenty best reversal candidates in the universe, ranked by a reversal model - not the
// fundamentals leaderboard shuffled. The header states how many names cleared the gate and
// counts the reasons the rest did not.
function finite(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

const MODEL_LIMIT = 20

const COLUMN_SORTS = {
  publishedScore: ['Published research score', (a, b) => (b.score ?? -1) - (a.score ?? -1),
    'The score the pipeline published for this row, exactly as calibrated: 78% fundamentals (valuation, profitability, financial health, growth, capital allocation, accounting quality), 18% market behavior, 4% news sentiment, plus small bounded modifiers. This is the number the point-in-time store and the validation harness are accumulating observations against, so it is shown unchanged rather than recomposed. Only computed for fully published companies.'],
  return: ['20-day return', (a, b) => (b.technical_detail?.return_20d ?? -999) - (a.technical_detail?.return_20d ?? -999),
    'Raw trailing 20-trading-day price return. Not a predictive score and not risk-adjusted - purely "what has the price done lately." Available for the full scored universe.'],
  confidence: ['Data confidence', (a, b) => (b.confidence ?? -1) - (a.confidence ?? -1),
    'How complete and reliable the underlying data was, not how attractive the company is. A high number means more inputs resolved. Only computed for fully published companies; each ranking model additionally reports its own mode-specific confidence over the inputs it actually reads.'],
}

// Model descriptions are generated from the model registry so the text and the arithmetic
// cannot drift: the weights quoted here are literally the weights being applied.
function modelDescription(key) {
  const model = RANKING_MODELS[key]
  const composition = model.components
    .map(([, label, weight]) => `${Math.round(weight * 100)}% ${label.toLowerCase()}`)
    .join(', ')
  return `${model.question} A separate ranking model over the whole scored universe, not a re-sort of the published score. Composition: ${composition}. `
    + 'Components a company cannot legitimately report are dropped and the remaining weights renormalized rather than scored as zero, so a business is never marked down for the shape of its balance sheet. '
    + 'Valuation and quality components are ranked against industry peers where the sample supports it, otherwise sector, otherwise the whole universe. '
    + `The score is then shrunk toward 50 by this model's own confidence, so a high reading resting on one thin input cannot outrank a well-evidenced lower one. Top ${MODEL_LIMIT} shown; the weights are frozen starting priors, not measured optima.`
}

const SORTS = {
  ...COLUMN_SORTS,
  ...Object.fromEntries(Object.keys(RANKING_MODELS).map((key) => (
    [key, [RANKING_MODELS[key].label, null, modelDescription(key)]]
  ))),
}

const etfStance = (score) => score >= 80 ? 'Attractive' : score >= 70 ? 'Promising' : score >= 55 ? 'Neutral' : 'Caution'

function normalizeEtf(row) {
  const score = row.scores?.overall ?? row.quality_score ?? null
  return {
    ...row,
    is_etf: true,
    asset_type: 'etf',
    score,
    stance: etfStance(score),
    components: {
      fundamentals: row.scores?.quality,
      market_behavior: row.scores?.performance,
      news_sentiment: null,
    },
    fundamental_categories: row.scores,
    technical_detail: {
      return_20d: row.returns?.['1m'],
      return_252d: row.returns?.['1y'],
      max_drawdown_252d: row.max_drawdown,
      beta: row.beta,
    },
    strengths: [
      row.expense_ratio != null ? `${row.expense_ratio.toFixed(2)}% expense ratio` : null,
      row.peer_rank ? `#${row.peer_rank} of ${row.peer_group_size} in its peer group` : null,
    ].filter(Boolean),
    risks: [
      row.max_drawdown != null ? `${Math.abs(row.max_drawdown).toFixed(1)}% maximum drawdown in the measured window` : null,
      row.tracking_error_pct != null ? `${row.tracking_error_pct.toFixed(2)}% tracking error` : null,
    ].filter(Boolean),
    researchType: 'ETF',
  }
}

// Corroboration is lens-specific (a name can be corroborated under Momentum and thin
// under Catalyst), so the chip only rides on the `screen` block the active lens attached
// to this row - a row viewed under a plain column sort was never corroboration-checked and
// correctly shows nothing. Same visible-chip-plus-native-tooltip pattern EntryTimingAction
// already uses below for its reason text, kept consistent rather than introducing a second
// explanatory affordance style.
function ThinEvidenceChip({ row }) {
  const result = row.modelScore
  if (!result) return null
  // Two separate warnings, both lens-specific. A capped score means the model found a reason
  // the setup may be price discovery rather than opportunity; low mode confidence means the
  // model could not read enough of what it needs on this row.
  if (result.cap) {
    return (
      <span className="chip screen-chip screen-chip-thin-evidence" title={result.cap.reason}>
        Thesis risk
      </span>
    )
  }
  if (result.confidencePercent < 50) {
    const weakest = result.confidenceInputs
      .filter((input) => input.resolved < 1)
      .map((input) => input.label)
      .join(', ')
    return (
      <span className="chip screen-chip screen-chip-thin-evidence"
        title={`This model resolved ${result.confidencePercent}% of the inputs it reads. Weak or missing: ${weakest || 'none'}.`}>
        Thin evidence
      </span>
    )
  }
  return null
}

// A row scored on the lightweight universe projection carries no price history, no data
// confidence, and no statement-level detail - the pipeline publishes those only for the
// top-ranked companies. Saying so is the honest reading of an empty metric; rendering a
// missing confidence as "0%" (which the card used to do) reads as a measured zero and is
// simply wrong.
function isLightData(row) {
  return !row.is_etf && !finite(row.confidence)
}

function LightDataChip({ row }) {
  if (!isLightData(row)) return null
  return (
    <span className="chip screen-chip screen-chip-light-data"
      title="Scored on the lighter universe data set: price/valuation/analyst inputs only. Price history, data confidence and statement-level metrics are published for the top-ranked companies, so they read as – on this row until it next lands in the published leaderboard.">
      Lighter data
    </span>
  )
}

function ScreenChips({ row }) {
  return <>
    {row.screenTags?.map((tag) => (
      <span key={tag} className={`chip screen-chip screen-chip-${tag.toLowerCase()}`}>{tag}</span>
    ))}
    <ThinEvidenceChip row={row} />
    <LightDataChip row={row} />
  </>
}

// "Why is this a reversal?" used to have no answer anywhere in the UI - the row carried a
// bare Reversal chip and nothing else. The model already computes every component that
// produced the score; this renders them, including the ones it had to drop.
function ModelWhy({ row }) {
  const result = row.modelScore
  if (!result) return null
  return (
    <div className="model-why">
      <p className="lens-reason">
        <b>{RANKING_MODELS[result.model].label} {Math.round(result.score)}</b>
        {result.raw !== result.score && (
          <span className="model-why-shrink" title={`Raw ${result.raw}, shrunk toward neutral because this model resolved ${result.confidencePercent}% of the inputs it reads.`}>
            {' '}(raw {Math.round(result.raw)} · {result.confidencePercent}% model confidence)
          </span>
        )}
      </p>
      <ul className="model-why-components">
        {result.components.map((component) => (
          <li key={component.key}>
            <span>{component.label}</span>
            <b>{Math.round(component.value)}</b>
            <small>{component.contribution.toFixed(0)}% of score{component.level === 'industry' || component.level === 'sector'
              ? ` · vs ${component.level} peers (n=${component.sampleSize})` : ''}</small>
          </li>
        ))}
      </ul>
      {result.droppedComponents.length > 0 && (
        <p className="model-why-dropped">
          Not applicable to this company, weight redistributed rather than scored zero:{' '}
          {result.droppedComponents.map((component) => component.label.toLowerCase()).join(', ')}.
        </p>
      )}
      {result.cap && <p className="model-why-cap">Score capped at {result.cap.limit}: {result.cap.reason}.</p>}
    </div>
  )
}

/** Every buy-worthy row with actionable confidence gets one of Buy Now, Review, or Set Low
 * Alert (src/lib/entryTiming.js,
 * built on the existing dipWatch floor/recovery estimate) surfaced right on the research
 * list, not one click deeper in the stock detail modal.
 */
function EntryTimingAction({ row, alerting, alertStatus, onSetAlert }) {
  const timing = entryTiming(row)
  if (!timing) return null
  if (timing.verdict === 'buy_now') {
    return <span className="chip entry-timing-chip buy-now" title={timing.reason}>Buy Now</span>
  }
  if (timing.verdict === 'review') {
    return <span className="chip entry-timing-chip review" title={timing.reason}>Review</span>
  }
  if (timing.verdict === 'insufficient_data') {
    return <span className="chip entry-timing-chip no-call" title={timing.reason}>No timing call</span>
  }
  return (
    <span className="entry-timing-wrap">
      <button
        className="chip entry-timing-chip set-low-alert"
        title={timing.reason}
        disabled={alerting}
        onClick={(event) => { event.stopPropagation(); onSetAlert(row, timing) }}
      >
        {alerting ? 'Setting alert…' : `Set Low Alert · $${timing.alertPrice.toFixed(2)}`}
      </button>
      {alertStatus && (
        <small className={`entry-timing-status ${alertStatus.error ? 'error' : ''}`} role="status">{alertStatus.message}</small>
      )}
    </span>
  )
}

/**
 * What the model actually saw. A screen returning four names because only four cleared its
 * gate and one returning four because the other 871 rows lack a field it reads look identical
 * on screen; this states which happened, counted from the same rows the model just ranked.
 */
function ModelSummary({ sort, coverage, shown }) {
  if (!coverage) return null
  const model = RANKING_MODELS[sort]
  return (
    <section className="lens-summary card" aria-label={`${model.label} model coverage`}>
      <p className="lens-summary-head"><b>{model.label}</b> — {model.question}</p>
      <p>
        {coverage.qualified === 0
          ? `No company clears this model's gate under the current filters, out of ${coverage.scanned} scanned.`
          : `Showing the top ${shown} of ${coverage.qualified} ${coverage.qualified === 1 ? 'company that clears' : 'companies that clear'} it, scored against all ${coverage.scanned} companies in the universe.`}
      </p>
      <p className="lens-summary-composition">
        {model.components.map(([, label, weight]) => `${Math.round(weight * 100)}% ${label.toLowerCase()}`).join(' · ')}
      </p>
      {coverage.excluded > 0 && (
        <>
          <p className="lens-summary-gap">
            {coverage.excluded} of {coverage.scanned} did not clear the gate.
            {coverage.binding && ` Most common reason: ${coverage.binding.reason} (${coverage.binding.count}).`}
          </p>
          <ul className="lens-summary-inputs">
            {coverage.reasons.slice(0, 4).map((entry) => (
              <li key={entry.reason}><b>{entry.count}</b> {entry.reason}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

function ResearchCard({ row, rank, onOpen, held, buying, buyStatus, onBuy, alertingTicker, alertStatuses, onSetAlert }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <article className="research-mobile-card">
      <div className="research-card-head">
        <span className="rank-badge">#{rank}</span>
        <CompanyLogo company={row} size={42} />
        <div><h2>{row.ticker}</h2><p>{row.name}</p></div>
        <WatchlistToggleButton stock={row} size={18} />
        <span className="mobile-score">{row.score}<small>score</small></span>
      </div>
      <div className="research-card-badges">
        <Tier label={row.stance} />
        {row.is_etf ? <span className="chip asset-chip">ETF</span> : <ActionPill recommendation={getRecommendation(row)} />}
        <ScreenChips row={row} />
        <span className={`holding-chip ${held ? 'held' : ''}`}>{held ? 'Bought' : 'Not bought'}</span>
        <EntryTimingAction row={row} alerting={alertingTicker === row.ticker}
          alertStatus={alertStatuses[row.ticker]} onSetAlert={onSetAlert} />
      </div>
      <ModelWhy row={row} />
      <dl className="research-card-metrics">
        <div><dt>Fundamentals</dt><dd>{row.components?.fundamentals == null ? '–' : Math.round(row.components.fundamentals)}</dd></div>
        <div><dt>20-day return</dt><dd><Move pct={row.technical_detail?.return_20d} capsule /></dd></div>
        <div><dt>Data confidence</dt><dd>{finite(row.confidence) ? `${Math.round(row.confidence * 100)}%` : '–'}</dd></div>
      </dl>
      <Sparkline values={(row.history?.closes || []).slice(-22)} label={`${row.ticker} one-month daily close trend`} height={54} className="research-card-spark" />
      <small className="as-of-line">{isLightData(row)
        ? 'Scored on the lighter universe data set – no published price history for this row'
        : `As of ${row.history?.dates?.at(-1) || row.data_as_of || 'the latest published close'}`}</small>
      <button className="expand-button" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
        {expanded ? 'Hide secondary metrics' : 'Show secondary metrics'}
        <Icon name="chevron" size={17} className={expanded ? 'rotated' : ''} />
      </button>
      {expanded && (
        <div className="research-expanded">
          <MetricPills {...row} isEtf={row.is_etf} fundamental_coverage={row.fundamental_detail?.coverage} />
          <div className="evidence-grid">
            <div><b>Strengths</b><ul>{row.strengths?.map((item) => <li key={item}>{item}</li>)}</ul></div>
            <div><b>Risks & gaps</b><ul>{row.risks?.map((item) => <li key={item}>{item}</li>)}</ul></div>
          </div>
          <button className="primary-button compact" onClick={() => onOpen(row)}>Full research <Icon name="arrow" size={17} /></button>
        </div>
      )}
      <div className="research-trade-row">
        <span>{held ? 'Already tracked in your portfolio' : row.price ? `Today · $100 at $${Number(row.price).toFixed(2)} = ${(100 / Number(row.price)).toFixed(4)} shares` : 'Current price unavailable'}</span>
        <button className={held ? 'secondary-button compact' : 'primary-button compact'} disabled={held || buying || !row.price} onClick={() => onBuy(row)}>
          {held ? 'Bought' : buying ? 'Adding…' : 'Buy $100'}
        </button>
      </div>
      {buyStatus && <p className={`research-trade-status ${buyStatus.error ? 'error' : ''}`} role="status">{buyStatus.message}</p>}
    </article>
  )
}

function ResearchPool({ label, rows, onOpen, heldTickers, buyingTicker, buyStatuses, onBuy,
                       alertingTicker, alertStatuses, onSetAlert, sort }) {
  if (!rows.length) return null
  const modelActive = isRankingModel(sort)
  return (
    <section className="research-pool" aria-label={label}>
      {label && <h2 className="research-pool-title">{label} <span className="research-pool-count">{rows.length}</span></h2>}
      <MobileVirtualList className="research-mobile-list" items={rows} getKey={(row) => row.ticker} estimateSize={390}
        renderItem={(row, index) => <ResearchCard row={row}
          rank={index + 1} onOpen={onOpen}
          held={heldTickers.has(row.ticker)} buying={buyingTicker === row.ticker}
          buyStatus={buyStatuses[row.ticker]} onBuy={onBuy}
          alertingTicker={alertingTicker} alertStatuses={alertStatuses} onSetAlert={onSetAlert} />} />
      <div className="research-table card">
        <table>
          <thead><tr>
            <th scope="col">Rank</th><th scope="col">Company</th><th scope="col">Type</th><th scope="col">Research rating</th><th scope="col">Signal</th>
            {modelActive && <th scope="col">Model score</th>}
            {modelActive && <th scope="col">Why it ranks here</th>}
            <th scope="col" className="num">Score</th><th scope="col" className="num">Fundamentals</th>
            <th scope="col" className="num">20-day return</th><th scope="col" className="num">Confidence</th><th scope="col">Timing</th><th scope="col">Portfolio</th>
            <th scope="col"><span className="sr-only">Watchlist</span></th><th scope="col"><span className="sr-only">Open</span></th>
          </tr></thead>
          <tbody>{rows.map((row, index) => (
            <tr key={row.ticker}>
              <td className="rank">#{index + 1}</td>
              <td><div className="table-company company-with-logo"><CompanyLogo company={row} size={34} /><div><b>{row.ticker}</b><span>{row.name}</span><small>{row.sector || 'Unclassified'}</small></div></div></td>
              <td><span className="chip asset-chip">{row.is_etf ? 'ETF' : 'Stock'}</span> <ScreenChips row={row} /></td>
              <td><Tier label={row.stance} /></td><td>{row.is_etf ? '–' : <ActionPill recommendation={getRecommendation(row)} />}</td>
              {modelActive && <td className="mono num score-cell">{row.modelScore ? Math.round(row.modelScore.score) : '–'}</td>}
              {modelActive && <td className="lens-reason-cell">{modelReason(row) || '–'}</td>}
              <td className="mono num score-cell">{row.score}</td>
              <td className="mono num">{row.components?.fundamentals == null ? '–' : Math.round(row.components.fundamentals)}</td>
              <td className="num"><Move pct={row.technical_detail?.return_20d} /></td>
              <td className="mono num">{finite(row.confidence) ? `${Math.round(row.confidence * 100)}%` : '–'}</td>
              <td><EntryTimingAction row={row} alerting={alertingTicker === row.ticker}
                alertStatus={alertStatuses[row.ticker]} onSetAlert={onSetAlert} /></td>
              <td>{heldTickers.has(row.ticker)
                ? <span className="holding-chip held">Bought</span>
                : <button className="primary-button compact research-table-buy" disabled={buyingTicker === row.ticker || !row.price} onClick={() => onBuy(row)}>{buyingTicker === row.ticker ? 'Adding…' : 'Buy $100'}</button>}</td>
              <td><WatchlistToggleButton stock={row} size={17} /></td>
              <td><button className="icon-button" onClick={() => onOpen(row)} aria-label={`Open ${row.name} research`}><Icon name="chevron" /></button></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </section>
  )
}

export default function Picks() {
  const { data, loading } = useData('advisor.json')
  const { data: etfData, loading: etfLoading } = useData('etfs.json')
  const { positions, loading: portfolioLoading, addPosition } = useFirebasePortfolio()
  const { createRule } = useAlerts()
  const [sector, setSector] = useState('all')
  // Defaults to a plain column sort, not a model: the page's job on arrival is to let
  // someone browse the whole ranked list. Every model is a screen that can legitimately
  // hide most of the universe, which is the right behaviour once a question has been
  // asked and the wrong one before it has.
  const [sort, setSort] = useState('publishedScore')
  const [query, setQuery] = useState('')
  const [assetType, setAssetType] = useState('all')
  const [ownership, setOwnership] = useState('all')
  const [selectedStock, setSelectedStock] = useState(null)
  const [buyingTicker, setBuyingTicker] = useState('')
  const [buyStatuses, setBuyStatuses] = useState({})
  const [tradeNotice, setTradeNotice] = useState(null)
  const [availableFunds, setAvailableFunds] = useState('')
  const [alertingTicker, setAlertingTicker] = useState('')
  const [alertStatuses, setAlertStatuses] = useState({})

  // The published leaderboard (data.research, the top ~40 by fundamentals-first score) plus
  // the rest of the scored universe (data.screen_universe, lightweight rows with no price
  // history) - merged so a strategy lens like Catalyst or Tailwind can surface a name that
  // isn't a top fundamentals score today, not just re-sort the same 40 names. Deduped by
  // ticker the same way FastGrowthScreen and ThemeExposureScreen already merge these two
  // arrays; the two are mutually exclusive by construction so this never drops a row.
  // Funds carry their own ticker in the ETF file, so anything appearing there is excluded
  // from the stock pool even when its advisor row omits `is_etf` (the lightweight
  // screen_universe projection dropped that flag until recently, which let VOO and VGT
  // compete in screens that gate on per-security fundamentals a fund does not have).
  const etfTickers = useMemo(
    () => new Set((etfData?.etfs || []).map((row) => row.ticker)),
    [etfData],
  )
  const stockResearch = useMemo(() => [...new Map(
    [...(data?.research || []), ...(data?.screen_universe || [])]
      .filter((row) => !row.is_etf && !etfTickers.has(row.ticker))
      .map((row) => [row.ticker, row]),
  ).values()], [data, etfTickers])
  // Momentum and reversal are separate screens (see /screens/momentum, /screens/matrix), each
  // with their own qualifying bar – but a stock that clears one of those bars is worth flagging
  // right here in the single ranked list rather than only inside its own separate page. Ranking
  // itself is untouched: these are stickers on top of the existing sort, not a second ordering.
  const research = useMemo(() => {
    const momentumTickers = new Set(rankMomentum(stockResearch, stockResearch.length).map((row) => row.ticker))
    const reversalTickers = new Set(rankReversal(stockResearch, stockResearch.length).map((row) => row.ticker))
    const breakoutTickers = new Set(rankBreakoutInProgress(stockResearch, stockResearch.length).map((row) => row.ticker))
    return [
      ...stockResearch.map((row) => ({
        ...row,
        researchType: 'Stock',
        screenTags: [
          breakoutTickers.has(row.ticker) ? 'Breakout' : null,
          momentumTickers.has(row.ticker) ? 'Momentum' : null,
          reversalTickers.has(row.ticker) ? 'Reversal' : null,
        ].filter(Boolean),
      })),
      ...(etfData?.etfs || []).map(normalizeEtf),
    ]
  }, [stockResearch, etfData])
  const heldTickers = useMemo(() => new Set(positions.map((position) => String(position.ticker || '').toUpperCase())), [positions])
  const sectors = useMemo(() => [...new Set(research.map((row) => row.sector).filter(Boolean))].sort(), [research])

  if (loading || etfLoading || portfolioLoading) return <Loading />
  if (!data?.research) return <Empty />

  const normalized = query.trim().toLowerCase()
  // Stocks and ETFs are scored by two different models (fundamentals-first vs a blended
  // performance/risk/cost/liquidity/quality fund score) with different scales and
  // distributions – sorting or bucket-weighting them together as one "score" ranking made
  // whichever model happened to produce higher numbers crowd out the other. Filtering keeps
  // both pools available; ranking never mixes them again after this split.
  const filtered = research
    .filter((row) => sector === 'all' || row.sector === sector)
    .filter((row) => ownership === 'all' || (ownership === 'bought') === heldTickers.has(row.ticker))
    .filter((row) => !normalized || row.ticker.toLowerCase().includes(normalized) || String(row.name || '').toLowerCase().includes(normalized))
  const filteredStocks = filtered.filter((row) => !row.is_etf)
  const filteredEtfs = filtered.filter((row) => row.is_etf)
  const modelActive = isRankingModel(sort)
  // Filters narrow the universe the model scores over, so "Reversal within Technology"
  // returns the best reversals in Technology - and peer percentiles are computed within that
  // same filtered set, not against a universe the user has already excluded.
  const coverage = modelActive ? modelCoverage(filteredStocks, sort) : null
  // Every model is stocks-only by construction: each reads per-security fundamentals, news,
  // insider or theme data a diversified fund does not report.
  const stockRows = modelActive
    ? rankByModel(filteredStocks, sort, MODEL_LIMIT)
    : filteredStocks.slice().sort(SORTS[sort][1])
  const etfRows = modelActive ? [] : filteredEtfs.slice().sort(SORTS[sort][1])
  const showStocks = assetType !== 'etf'
  const showEtfs = assetType !== 'stock' && !modelActive
  const rows = [...(showStocks ? stockRows : []), ...(showEtfs ? etfRows : [])]

  // Ranked separately for the same reason: exponentiating an ETF's fund score and a stock's
  // fundamentals score into one weighted split would let the model with the larger raw
  // numbers dominate the bucket sizes regardless of actual conviction. Default view
  // allocates across stocks; switch the asset-type filter to ETFs to allocate across those.
  const allocationPool = assetType === 'etf' ? etfRows : stockRows
  // Under a strategy lens the bucket split has to weight by that lens's own rank score,
  // not by the long-term research score - otherwise picking "Reversal" would size the
  // buckets by exactly the ranking the user just chose to look past.
  const allocation = allocateFunds(allocationPool, Number(availableFunds), {
    limit: 8,
    scoreOf: modelActive ? ((row) => row.modelScore?.score) : undefined,
  })

  const handleQuickBuy = async (row) => {
    const price = Number(row.price)
    if (!Number.isFinite(price) || price <= 0 || heldTickers.has(row.ticker)) return
    const shares = Number((100 / price).toFixed(6))
    const localToday = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10)
    setBuyingTicker(row.ticker)
    setBuyStatuses((current) => ({ ...current, [row.ticker]: null }))
    const result = await addPosition(row.ticker, shares, price, localToday, 'share')
    setBuyingTicker('')
    const notice = result?.success
      ? { message: `${shares.toFixed(4)} ${row.ticker} shares added at $${price.toFixed(2)} for $100 on ${localToday}.` }
      : { error: true, message: result?.error ? `Could not add ${row.ticker}: ${result.error}` : 'Sign in to add this trade to your portfolio.' }
    setBuyStatuses((current) => ({ ...current, [row.ticker]: notice }))
    setTradeNotice(notice)
  }

  const handleSetLowAlert = async (row, timing) => {
    setAlertingTicker(row.ticker)
    setAlertStatuses((current) => ({ ...current, [row.ticker]: null }))
    const result = await createRule({
      type: 'price_cross', ticker: row.ticker, direction: 'below', threshold: timing.alertPrice,
    })
    setAlertingTicker('')
    setAlertStatuses((current) => ({
      ...current,
      [row.ticker]: result?.success
        ? { message: `Alert set: ${row.ticker} below $${timing.alertPrice.toFixed(2)}.` }
        : { error: true, message: result?.error || `Could not set an alert for ${row.ticker}.` },
    }))
  }

  return (
    <>
      <div className="page-head">
        <div><span className="eyebrow">Evidence library</span><h1 className="page-title">Company <span className="accent">research</span></h1>
          <p className="page-sub">Compare the ranked evidence behind every published company. Confidence measures data completeness, not expected performance.</p></div>
        <div className="result-count"><strong>{rows.length}</strong><span>results</span></div>
      </div>

      <div className="research-toolbar">
        <label className="search-field">
          <Icon name="research" size={18} /><span className="sr-only">Search companies</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search ticker or company" />
        </label>
        <label><span className="sr-only">Filter by sector</span><select value={sector} onChange={(event) => setSector(event.target.value)}>
          <option value="all">All sectors</option>{sectors.map((item) => <option key={item}>{item}</option>)}
        </select></label>
        <span className="sort-with-info">
          <label><span className="sr-only">Sort research</span><select value={sort} onChange={(event) => setSort(event.target.value)}>
            {/* Grouped because the two kinds behave differently: a column sort re-orders
                every row, a model screens the universe and returns only what clears it. */}
            <optgroup label="Sort the full list">
              {Object.keys(COLUMN_SORTS).map((key) => (
                <option key={key} value={key}>Sort: {SORTS[key][0]}</option>
              ))}
            </optgroup>
            <optgroup label="Rank by model (top 20)">
              {Object.keys(RANKING_MODELS).map((key) => (
                <option key={key} value={key}>Model: {RANKING_MODELS[key].label}</option>
              ))}
            </optgroup>
          </select></label>
          <InfoTag label={SORTS[sort][0]}>
            <strong>{SORTS[sort][0]}</strong>
            <p>{SORTS[sort][2]}</p>
          </InfoTag>
        </span>
        <label><span className="sr-only">Filter by asset type</span><select value={assetType} onChange={(event) => setAssetType(event.target.value)}>
          <option value="all">Stocks &amp; ETFs</option><option value="stock">Stocks</option><option value="etf">ETFs</option>
        </select></label>
        <label><span className="sr-only">Filter by ownership</span><select value={ownership} onChange={(event) => setOwnership(event.target.value)}>
          <option value="all">Bought &amp; not bought</option><option value="bought">Bought</option><option value="not-bought">Not bought</option>
        </select></label>
      </div>
      {tradeNotice && <div className={`research-trade-notice ${tradeNotice.error ? 'error' : ''}`} role="status" aria-live="polite">{tradeNotice.message}</div>}
      {modelActive && <ModelSummary sort={sort} coverage={coverage} shown={stockRows.length} />}

      <section className="card allocation-planner" aria-labelledby="allocation-planner-title">
        <header className="allocation-planner-head">
          <div><span className="eyebrow">Bucket planner</span><h2 id="allocation-planner-title">Split available funds by rank</h2></div>
          <label className="allocation-funds-field">
            <span className="sr-only">Available funds</span>
            <span aria-hidden="true">$</span>
            <input type="number" min="0" step="1" inputMode="decimal" placeholder="Available funds"
              value={availableFunds} onChange={(event) => setAvailableFunds(event.target.value)} />
          </label>
        </header>
        <p className="allocation-planner-note">
          Weighted by {modelActive ? `${RANKING_MODELS[sort].label.toLowerCase()} model score` : 'published score'} against
          the top {Math.min(allocationPool.length, 8)} {assetType === 'etf' ? 'ETFs' : 'stocks'} in
          the current sort and filters. This is not an even split. A higher-scored {assetType === 'etf' ? 'fund' : 'company'} gets
          a disproportionately larger bucket, the way a real allocation would. Stocks and ETFs are never weighted against each
          other here – they come from two different scoring models with different scales, so mixing them would let whichever
          model happens to produce larger numbers dominate the split.
        </p>
        {allocation.available ? (
          <div className="allocation-bucket-list">
            {allocation.buckets.map((bucket) => (
              <div className="allocation-bucket-row" key={bucket.ticker}>
                <div className="allocation-bucket-id">
                  <b>{bucket.ticker}</b><span>{bucket.isEtf ? 'ETF' : 'Stock'} · score {Math.round(bucket.score)}</span>
                </div>
                <div className="allocation-bucket-bar" aria-hidden="true"><span style={{ width: `${bucket.weightPct}%` }} /></div>
                <div className="allocation-bucket-amount">
                  <strong>${bucket.amount.toFixed(2)}</strong>
                  <span>{bucket.weightPct.toFixed(1)}%{bucket.shares != null ? ` · ${bucket.shares.toFixed(4)} sh` : ''}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="allocation-planner-empty">{availableFunds ? allocation.reason : 'Enter available funds to see a suggested bucket split.'}</p>
        )}
      </section>

      {showStocks && <ResearchPool label={showStocks && showEtfs ? 'Stocks' : null} rows={stockRows}
        onOpen={setSelectedStock} heldTickers={heldTickers} buyingTicker={buyingTicker}
        buyStatuses={buyStatuses} onBuy={handleQuickBuy}
        alertingTicker={alertingTicker} alertStatuses={alertStatuses} onSetAlert={handleSetLowAlert} sort={sort} />}
      {showEtfs && <ResearchPool label={showStocks && showEtfs ? 'ETFs' : null} rows={etfRows}
        onOpen={setSelectedStock} heldTickers={heldTickers} buyingTicker={buyingTicker}
        buyStatuses={buyStatuses} onBuy={handleQuickBuy}
        alertingTicker={alertingTicker} alertStatuses={alertStatuses} onSetAlert={handleSetLowAlert} sort={sort} />}

      {!rows.length && <Empty note={modelActive
        ? (assetType === 'etf'
          ? `${RANKING_MODELS[sort].label} is a per-security model – it reads fundamentals, news, insider and theme data a fund does not report. Switch the asset filter back to stocks, or sort by published score to rank ETFs.`
          : `No company clears the ${RANKING_MODELS[sort].label} gate under these filters. The coverage panel above counts why.`)
        : 'No companies match those filters.'} />}
      <div className="disclaimer">Research covers {(data?.research || []).length} fully published companies plus {(data?.screen_universe || []).length} more scored on a lighter data set ({stockResearch.length} total), and {etfData?.etfs?.length || 0} ETFs. The nine ranking models each answer a different question with their own declared composition, gate, and confidence measure – a name can rank first under one and not appear at all under another, which is the intent. Each model scores against industry or sector peers, drops components a company cannot legitimately report rather than scoring them zero, shrinks the result by how much of its own input set resolved, and publishes the top {MODEL_LIMIT}. The weights are frozen starting priors chosen from the literature, not measured optima; the point-in-time store is accumulating observations to test them. “Published research score”, “20-day return” and “Data confidence” are plain column sorts over the whole list, not models. “Buy $100” records a fractional-share portfolio entry at the displayed current price and today’s date; it does not place a brokerage order. Rankings do not imply suitability or portfolio allocation.</div>
      {selectedStock && <StockDetailModal stock={selectedStock} benchmarkHistory={data.benchmark_history} onClose={() => setSelectedStock(null)} />}
    </>
  )
}
