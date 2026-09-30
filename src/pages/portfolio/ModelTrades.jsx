// A worksheet of the trades that would put the account on the model book. It never places an
// order; it states the dollars, the cost, and the tax consequences before anyone does.

import { useState } from 'react'
import { REBALANCE_MODES, suggestModelTrades } from '../../lib/modelRebalance.js'
import { money } from './format.js'

const FLAG_LABEL = {
  short_term_gain: 'Short-term gain',
  realizes_loss: 'Realizes loss',
}

export default function ModelTrades({ positions, research, costBps, bookSize }) {
  const [mode, setMode] = useState('model_sleeve')
  if (!research?.length || !positions?.length) return null
  const plan = suggestModelTrades({ positions, research, mode, costBps, bookSize })

  return (
    <details className="card card-pad model-trades">
      <summary>
        <span>
          <span className="sec-label">Suggested trades</span>
          <strong>{plan.available ? `${plan.trades.length} trade${plan.trades.length === 1 ? '' : 's'} to match the model book` : 'Match the model book'}</strong>
        </span>
      </summary>
      <div className="model-trades-body">
        <fieldset className="model-trades-mode">
          <legend className="sr-only">Rebalance scope</legend>
          {REBALANCE_MODES.map((option) => (
            <label key={option.id} className={mode === option.id ? 'active' : undefined}>
              <input type="radio" name="model-trades-mode" value={option.id} checked={mode === option.id} onChange={() => setMode(option.id)} />
              <span><b>{option.label}</b><small>{option.blurb}</small></span>
            </label>
          ))}
        </fieldset>

        {!plan.available ? <p className="portfolio-suggested-empty">{plan.reason}</p> : (
          <>
            <div className="model-trades-totals">
              <span><small>Sell / trim</small><strong>{money(plan.totals.sells, 2)}</strong></span>
              <span><small>Buy / add</small><strong>{money(plan.totals.buys, 2)}</strong></span>
              <span><small>Turnover</small><strong>{plan.totals.turnoverPct.toFixed(0)}%</strong></span>
              <span><small>Est. cost · {plan.costBps} bps</small><strong>{money(plan.totals.estimatedCost, 2)}</strong></span>
              <span><small>Short-term gains</small><strong className={plan.totals.shortTermGains > 0 ? 'negative' : undefined}>{money(plan.totals.shortTermGains, 2)}</strong></span>
            </div>
            {plan.trades.length === 0
              ? <p className="portfolio-suggested-empty">Already within ${plan.minTradeUsd} of the model book on every name.</p>
              : (
                <div className="evidence-table-scroll">
                  <table className="evidence-table model-trades-table">
                    <caption className="sr-only">Trades to match the model book</caption>
                    <thead><tr><th scope="col">Ticker</th><th scope="col">Action</th><th scope="col">Amount</th><th scope="col">Shares</th><th scope="col">Why</th><th scope="col">Tax</th></tr></thead>
                    <tbody>
                      {plan.trades.map((trade) => (
                        <tr key={`${trade.action}-${trade.ticker}`}>
                          <th scope="row">{trade.ticker}</th>
                          <td><span className={`model-trade-action model-trade-${trade.action.toLowerCase()}`}>{trade.action}</span></td>
                          <td>{money(trade.amount, 2)}</td>
                          <td>{trade.shares.toFixed(3)}</td>
                          <td className="model-trades-why">{trade.reason}</td>
                          <td>{trade.flag ? `${FLAG_LABEL[trade.flag]} ${money(Math.abs(trade.realizedGain), 2)}` : '–'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            <p className="disclaimer">{plan.methodology}</p>
          </>
        )}
      </div>
    </details>
  )
}
