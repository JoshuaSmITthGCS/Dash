import { useId, useState } from 'react'

/**
 * Pairwise correlation as a diverging heatmap.
 *
 * Replaces a raw <td> matrix of numbers. Correlation is a signed quantity, so it
 * takes a diverging scale: two hues with a neutral gray at zero, which is what
 * makes "these two moved independently" read as absent rather than as weak.
 *
 * The numbers are not thrown away — every cell still prints its value, and the
 * table view is one click away, because a colour scale is a summary and the
 * matrix is the evidence.
 */

const STEPS = [
  { max: -0.5, token: '--diverging-neg-3', ink: '#ffffff' },
  { max: -0.25, token: '--diverging-neg-2', ink: 'var(--text-primary)' },
  { max: -0.08, token: '--diverging-neg-1', ink: 'var(--text-primary)' },
  { max: 0.08, token: '--diverging-zero', ink: 'var(--text-primary)' },
  { max: 0.35, token: '--diverging-pos-1', ink: 'var(--text-primary)' },
  { max: 0.6, token: '--diverging-pos-2', ink: 'var(--text-primary)' },
  { max: Infinity, token: '--diverging-pos-3', ink: '#ffffff' },
]

const step = (value) => STEPS.find((item) => value <= item.max) || STEPS[STEPS.length - 1]

const BAND_LABEL = (value) => value >= 0.6 ? 'moves in near-lockstep'
  : value >= 0.35 ? 'moves together'
    : value > 0.08 ? 'moves loosely together'
      : value >= -0.08 ? 'moves independently'
        : value > -0.35 ? 'moves loosely opposite'
          : 'moves opposite'

export default function CorrelationHeatmap({ tickers, matrix, observations, caption }) {
  const [view, setView] = useState('heatmap')
  const [hover, setHover] = useState(null)
  const titleId = useId()

  if (!tickers?.length || !matrix?.length) return null

  const readout = hover
    ? `${tickers[hover.row]} and ${tickers[hover.column]}: ${matrix[hover.row][hover.column].toFixed(2)} — ${BAND_LABEL(matrix[hover.row][hover.column])}`
    : `${tickers.length} holdings over ${observations} common daily returns. Hover a cell for the pair.`

  return (
    <figure className="correlation-figure" aria-labelledby={titleId}>
      <figcaption className="correlation-head">
        <span id={titleId} className="sr-only">
          Pairwise correlation of {tickers.length} holdings over {observations} common daily returns
        </span>
        <p className="correlation-readout" aria-live="polite">{readout}</p>
        <div className="correlation-toggle" role="group" aria-label="Correlation view">
          <button type="button" aria-pressed={view === 'heatmap'} onClick={() => setView('heatmap')}>Heatmap</button>
          <button type="button" aria-pressed={view === 'table'} onClick={() => setView('table')}>Table</button>
        </div>
      </figcaption>

      {view === 'table' ? (
        <div className="correlation-table-wrap">
          <table className="correlation-table">
            <caption className="sr-only">{caption || 'Pairwise correlation matrix'}</caption>
            <thead>
              <tr><th scope="col">Holding</th>{tickers.map((ticker) => <th scope="col" key={ticker}>{ticker}</th>)}</tr>
            </thead>
            <tbody>
              {tickers.map((ticker, row) => (
                <tr key={ticker}>
                  <th scope="row">{ticker}</th>
                  {matrix[row].map((value, column) => (
                    <td key={tickers[column]} className="num">{value.toFixed(2)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <>
          <div
            className="correlation-grid"
            style={{ '--corr-columns': tickers.length }}
            onMouseLeave={() => setHover(null)}
          >
            <div aria-hidden="true" />
            {tickers.map((ticker) => <div key={`c-${ticker}`} className="correlation-label">{ticker}</div>)}
            {matrix.map((cells, row) => (
              <Row key={tickers[row]} row={row} cells={cells} tickers={tickers} onHover={setHover} hover={hover} />
            ))}
          </div>

          <div className="correlation-legend">
            <span>−1.0</span>
            <span className="correlation-ramp" aria-hidden="true">
              {STEPS.map((item) => <i key={item.token} style={{ background: `var(${item.token})` }} />)}
            </span>
            <span>+1.0</span>
            <small>Neutral gray at zero · {observations} common observations</small>
          </div>
        </>
      )}
    </figure>
  )
}

function Row({ row, cells, tickers, onHover, hover }) {
  return (
    <>
      <div className="correlation-label correlation-label-row">{tickers[row]}</div>
      {cells.map((value, column) => {
        const diagonal = row === column
        const active = hover && (hover.row === row || hover.column === column)
        const { token, ink } = step(value)
        return (
          <div
            key={tickers[column]}
            className={`correlation-cell${diagonal ? ' is-diagonal' : ''}${active ? ' is-active' : ''}`}
            style={diagonal ? undefined : { background: `var(${token})`, color: ink }}
            onMouseEnter={() => onHover({ row, column })}
            onFocus={() => onHover({ row, column })}
            tabIndex={diagonal ? -1 : 0}
            role="img"
            aria-label={`${tickers[row]} and ${tickers[column]}: ${value.toFixed(2)}, ${BAND_LABEL(value)}`}
          >
            {diagonal ? '—' : value.toFixed(2)}
          </div>
        )
      })}
    </>
  )
}
