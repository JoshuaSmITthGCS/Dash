// The two same-day comparison tables behind the "Vs S&P 500" and "$N Calculator" tabs.
// Both answer the same question — what the identical dollars on the identical day would
// have done in the index — so they share the date cell and the footnote.

import { fixedBasisAlternative } from '../../lib/portfolioPerformance'
import { money, moveColor } from './format.js'
import { Move } from './PortfolioBits.jsx'

function PurchaseDateCell({ pos, onPurchaseDateChange }) {
  return (
    <td className="mono num">
      <input
        className="portfolio-date-input"
        type="date"
        value={pos.purchaseDate || ''}
        aria-label={`${pos.ticker} purchase date`}
        onChange={(event) => onPurchaseDateChange(pos.id, event.target.value)}
      />
    </td>
  )
}

function DollarsAheadCell({ value }) {
  return (
    <td className="mono num" style={{ color: moveColor(value) }}>
      {value == null ? '–' : `${value >= 0 ? '+' : '−'}${money(Math.abs(value))}`}
    </td>
  )
}

function ComparisonFootnote() {
  return (
    <p style={{ color: 'var(--text-faint)', fontSize: 12, marginTop: 12 }}>
      Add or correct a purchase date above to calculate the same-day comparison. Positions
      bought before the published benchmark window show “–” rather than being compared
      against the wrong entry price.
    </p>
  )
}

export function BenchmarkTable({ sortedPositions, versusIndex, onPurchaseDateChange }) {
  return (
    <div className="card card-pad table-wrap">
      <div className="callout" style={{ margin: '0 0 16px' }}>
        <strong>The only fair comparison:</strong> what each position is worth now against
        what the identical dollars, invested on the identical day, would be worth in the S&P 500.
      </div>
      <table>
        <thead>
          <tr>
            <th>Ticker</th><th className="num">Purchased</th><th className="num">Invested</th>
            <th className="num">Now</th><th className="num">Return</th>
            <th className="num">S&P instead</th><th className="num">S&P return</th>
            <th className="num">Dollars ahead</th>
          </tr>
        </thead>
        <tbody>
          {sortedPositions.map((pos) => (
            <tr key={pos.id || pos.ticker}>
              <td className="mono">{pos.ticker}</td>
              <PurchaseDateCell pos={pos} onPurchaseDateChange={onPurchaseDateChange} />
              <td className="mono num">{money(pos.totalCost)}</td>
              <td className="mono num">{money(pos.currentValue)}</td>
              <td className="num"><Move value={pos.gainPct} /></td>
              <td className="mono num">{pos.versusBenchmark ? money(pos.versusBenchmark.value) : '–'}</td>
              <td className="num">
                {pos.versusBenchmark ? <Move value={pos.versusBenchmark.gainPct} /> : <span className="mono">–</span>}
              </td>
              <DollarsAheadCell value={pos.versusBenchmark ? pos.currentValue - pos.versusBenchmark.value : null} />
            </tr>
          ))}
          {versusIndex && (
            <tr style={{ fontWeight: 600 }}>
              <td className="mono">TOTAL</td>
              <td className="num">–</td>
              <td className="mono num">{money(versusIndex.invested)}</td>
              <td className="mono num">{money(versusIndex.holdingsValue)}</td>
              <td className="num"><Move value={versusIndex.holdingsReturnPct} /></td>
              <td className="mono num">{money(versusIndex.benchmarkValue)}</td>
              <td className="num"><Move value={versusIndex.benchmarkReturnPct} /></td>
              <DollarsAheadCell value={versusIndex.dollarsAhead} />
            </tr>
          )}
        </tbody>
      </table>
      <ComparisonFootnote />
    </div>
  )
}

export function FixedBasisTable({ sortedPositions, fixedBasisTotal, basis, benchmarkHistory, positionCount, onPurchaseDateChange }) {
  return (
    <div className="card card-pad table-wrap">
      <div className="callout" style={{ margin: '0 0 16px' }}>
        <strong>${basis} calculator:</strong> what ${basis} would be worth today if it went into
        each position on the day you actually bought it, against the same ${basis} in the
        S&amp;P 500 from that same day. Not what you actually invested – same fair, same-day
        comparison as "Vs S&amp;P 500", just a flat ${basis} everywhere.
      </div>
      <table>
        <thead>
          <tr>
            <th>Ticker</th><th className="num">Purchased</th><th className="num">${basis} invested</th>
            <th className="num">Now</th><th className="num">Return</th>
            <th className="num">S&P instead</th><th className="num">S&P return</th>
            <th className="num">Dollars ahead</th>
          </tr>
        </thead>
        <tbody>
          {sortedPositions.map((pos) => {
            const calc = fixedBasisAlternative(pos, pos.priceInfo?.history, benchmarkHistory, basis)
            return (
              <tr key={pos.id || pos.ticker}>
                <td className="mono">{pos.ticker}</td>
                <PurchaseDateCell pos={pos} onPurchaseDateChange={onPurchaseDateChange} />
                <td className="mono num">{money(basis)}</td>
                <td className="mono num">{calc ? money(calc.stockValue) : '–'}</td>
                <td className="num">
                  {calc ? <Move value={calc.stockReturnPct} /> : <span className="mono">–</span>}
                </td>
                <td className="mono num">{calc ? money(calc.benchmarkValue) : '–'}</td>
                <td className="num">
                  {calc ? <Move value={calc.benchmarkReturnPct} /> : <span className="mono">–</span>}
                </td>
                <DollarsAheadCell value={calc ? calc.dollarsAhead : null} />
              </tr>
            )
          })}
          {fixedBasisTotal && (
            <tr style={{ fontWeight: 600 }}>
              <td className="mono">TOTAL</td>
              <td className="num">–</td>
              <td className="mono num">{money(fixedBasisTotal.invested)}</td>
              <td className="mono num">{money(fixedBasisTotal.stockValue)}</td>
              <td className="num"><Move value={fixedBasisTotal.stockReturnPct} /></td>
              <td className="mono num">{money(fixedBasisTotal.benchmarkValue)}</td>
              <td className="num"><Move value={fixedBasisTotal.benchmarkReturnPct} /></td>
              <DollarsAheadCell value={fixedBasisTotal.dollarsAhead} />
            </tr>
          )}
          {positionCount === 0 && (
            <tr>
              <td colSpan="8" style={{ textAlign: 'center', padding: 40, opacity: 0.5 }}>
                No positions yet. Click "+ Add Position" to start tracking.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <ComparisonFootnote />
    </div>
  )
}
