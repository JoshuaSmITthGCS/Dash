// The two same-day comparison tables behind the "Vs S&P 500" and "$N Calculator" tabs.
// Both answer the same question — what the identical dollars on the identical day would
// have done in the index — so they share one column set, the date cell, and the footnote.
// Neither has column-header sorting: rows arrive pre-ordered from PortfolioSortToolbar.

import DataTable from '../../components/DataTable.jsx'
import { fixedBasisAlternative } from '../../lib/portfolioPerformance'
import { money, moveColor } from './format.js'
import { Move } from './PortfolioBits.jsx'

function DollarsAhead({ value }) {
  return (
    <span className="mono" style={{ color: moveColor(value) }}>
      {value == null ? '–' : `${value >= 0 ? '+' : '−'}${money(Math.abs(value))}`}
    </span>
  )
}

function comparisonColumns({ investedLabel, onPurchaseDateChange }) {
  return [
    { key: 'ticker', label: 'Ticker', sortable: false, cell: (row) => <span className="mono">{row.ticker}</span> },
    {
      key: 'purchaseDate', label: 'Purchased', sortable: false,
      cell: (row) => (
        <input
          className="portfolio-date-input"
          type="date"
          value={row.purchaseDate || ''}
          aria-label={`${row.ticker} purchase date`}
          onChange={(event) => onPurchaseDateChange(row.id, event.target.value)}
        />
      ),
    },
    { key: 'invested', label: investedLabel, numeric: true, sortable: false, cell: (row) => <span className="mono">{money(row.invested)}</span> },
    { key: 'now', label: 'Now', numeric: true, sortable: false, cell: (row) => <span className="mono">{row.now == null ? '–' : money(row.now)}</span> },
    { key: 'returnPct', label: 'Return', numeric: true, sortable: false, cell: (row) => (row.returnPct == null ? <span className="mono">–</span> : <Move value={row.returnPct} />) },
    { key: 'benchmarkValue', label: 'S&P instead', numeric: true, sortable: false, cell: (row) => <span className="mono">{row.benchmarkValue == null ? '–' : money(row.benchmarkValue)}</span> },
    { key: 'benchmarkReturnPct', label: 'S&P return', numeric: true, sortable: false, cell: (row) => (row.benchmarkReturnPct == null ? <span className="mono">–</span> : <Move value={row.benchmarkReturnPct} />) },
    { key: 'dollarsAhead', label: 'Dollars ahead', numeric: true, sortable: false, cell: (row) => <DollarsAhead value={row.dollarsAhead} /> },
  ]
}

function ComparisonFootnote() {
  return (
    <p className="comparison-footnote">
      Add or correct a purchase date above to calculate the same-day comparison. Positions
      bought before the published benchmark window show "–" rather than being compared
      against the wrong entry price.
    </p>
  )
}

export function BenchmarkTable({ sortedPositions, versusIndex, onPurchaseDateChange }) {
  const rows = sortedPositions.map((pos) => ({
    id: pos.id || pos.ticker,
    ticker: pos.ticker,
    purchaseDate: pos.purchaseDate,
    invested: pos.totalCost,
    now: pos.currentValue,
    returnPct: pos.gainPct,
    benchmarkValue: pos.versusBenchmark?.value ?? null,
    benchmarkReturnPct: pos.versusBenchmark?.gainPct ?? null,
    dollarsAhead: pos.versusBenchmark ? pos.currentValue - pos.versusBenchmark.value : null,
  }))
  if (versusIndex) {
    rows.push({
      id: '__total__', ticker: 'TOTAL', purchaseDate: null, invested: versusIndex.invested,
      now: versusIndex.holdingsValue, returnPct: versusIndex.holdingsReturnPct,
      benchmarkValue: versusIndex.benchmarkValue, benchmarkReturnPct: versusIndex.benchmarkReturnPct,
      dollarsAhead: versusIndex.dollarsAhead, isTotal: true,
    })
  }
  return (
    <div className="card card-pad">
      <div className="callout callout--tables-gap">
        <strong>The only fair comparison:</strong> what each position is worth now against
        what the identical dollars, invested on the identical day, would be worth in the S&P 500.
      </div>
      {sortedPositions.length === 0 ? (
        <p className="comparison-empty-cell">No positions yet. Click "+ Add Position" to start tracking.</p>
      ) : (
        <DataTable
          rows={rows}
          getKey={(row) => row.id}
          columns={comparisonColumns({ investedLabel: 'Invested', onPurchaseDateChange })}
          rowClassName={(row) => (row.isTotal ? 'comparison-total-row' : undefined)}
        />
      )}
      <ComparisonFootnote />
    </div>
  )
}

export function FixedBasisTable({ sortedPositions, fixedBasisTotal, basis, benchmarkHistory, positionCount, onPurchaseDateChange }) {
  const rows = sortedPositions.map((pos) => {
    const calc = fixedBasisAlternative(pos, pos.priceInfo?.history, benchmarkHistory, basis)
    return {
      id: pos.id || pos.ticker,
      ticker: pos.ticker,
      purchaseDate: pos.purchaseDate,
      invested: basis,
      now: calc?.stockValue ?? null,
      returnPct: calc?.stockReturnPct ?? null,
      benchmarkValue: calc?.benchmarkValue ?? null,
      benchmarkReturnPct: calc?.benchmarkReturnPct ?? null,
      dollarsAhead: calc?.dollarsAhead ?? null,
    }
  })
  if (fixedBasisTotal) {
    rows.push({
      id: '__total__', ticker: 'TOTAL', purchaseDate: null, invested: fixedBasisTotal.invested,
      now: fixedBasisTotal.stockValue, returnPct: fixedBasisTotal.stockReturnPct,
      benchmarkValue: fixedBasisTotal.benchmarkValue, benchmarkReturnPct: fixedBasisTotal.benchmarkReturnPct,
      dollarsAhead: fixedBasisTotal.dollarsAhead, isTotal: true,
    })
  }
  return (
    <div className="card card-pad">
      <div className="callout callout--tables-gap">
        <strong>${basis} calculator:</strong> what ${basis} would be worth today if it went into
        each position on the day you actually bought it, against the same ${basis} in the
        S&amp;P 500 from that same day. Not what you actually invested – same fair, same-day
        comparison as "Vs S&amp;P 500", just a flat ${basis} everywhere.
      </div>
      {positionCount === 0 ? (
        <p className="comparison-empty-cell">No positions yet. Click "+ Add Position" to start tracking.</p>
      ) : (
        <DataTable
          rows={rows}
          getKey={(row) => row.id}
          columns={comparisonColumns({ investedLabel: `$${basis} invested`, onPurchaseDateChange })}
          rowClassName={(row) => (row.isTotal ? 'comparison-total-row' : undefined)}
        />
      )}
      <ComparisonFootnote />
    </div>
  )
}
