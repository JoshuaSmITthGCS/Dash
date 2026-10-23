// How much of the account is the model and how much is the owner. Without this split the live
// record can't say whether ValueSignal or the owner's own picks drove the result.

import { money, signedPct } from './format.js'

const pct = (value, digits = 1) => (value == null ? '–' : `${value.toFixed(digits)}%`)
const tone = (value) => (value == null ? undefined : value >= 0 ? 'positive' : 'negative')

function GroupCard({ group }) {
  const { replay } = group
  return (
    <article className="model-alignment-group" aria-label={group.label}>
      <header>
        <span className="sec-label">{group.label}</span>
        <strong>{group.count} holding{group.count === 1 ? '' : 's'} · {pct(group.weightPct)} of value</strong>
      </header>
      <dl className="model-alignment-stats">
        <div><dt>Value</dt><dd>{money(group.value, 2)}</dd></div>
        <div><dt>Unrealized</dt><dd className={tone(group.gain)}>{group.cost > 0 ? `${group.gain >= 0 ? '+' : '−'}${money(Math.abs(group.gain), 2)} · ${signedPct(group.gainPct)}` : '–'}</dd></div>
        <div><dt>Replay return</dt><dd className={tone(replay?.returnPct)}>{signedPct(replay?.returnPct)}</dd></div>
        <div><dt>vs S&amp;P 500</dt><dd className={tone(replay?.excessPct)}>{signedPct(replay?.excessPct)}</dd></div>
        <div><dt>Volatility</dt><dd>{pct(replay?.volatilityPct)}</dd></div>
        <div><dt>Max drawdown</dt><dd>{signedPct(replay?.maxDrawdownPct)}</dd></div>
      </dl>
      {group.tickers.length > 0 && (
        <p className="model-alignment-tickers mono">
          {group.tickers.map(({ ticker, rank }) => (rank ? `${ticker} #${rank}` : ticker)).join(' · ')}
        </p>
      )}
    </article>
  )
}

export default function ModelAlignment({ split }) {
  if (!split?.available) return null
  const [model, own] = split.groups
  const window = model.replay || own.replay
  const lead = model.weightPct != null && own.weightPct != null
    ? own.weightPct > model.weightPct
      ? `Most of this account (${pct(own.weightPct)}) is your own picks, so its live record mostly measures you, not the model.`
      : `Most of this account (${pct(model.weightPct)}) is in names the model ranks, so its live record mostly measures the model.`
    : null
  return (
    <section className="card card-pad model-alignment" aria-labelledby="model-alignment-title">
      <div className="portfolio-section-heading">
        <div><span className="eyebrow">Attribution</span><h3 id="model-alignment-title">Model vs. your own picks</h3></div>
      </div>
      {lead && <p className="model-alignment-lead">{lead}</p>}
      <div className="model-alignment-grid">
        <GroupCard group={model} />
        <GroupCard group={own} />
      </div>
      <p className="disclaimer">
        {split.methodology}
        {window ? ` Replay window ${window.start} to ${window.end}.` : ''}
      </p>
    </section>
  )
}
