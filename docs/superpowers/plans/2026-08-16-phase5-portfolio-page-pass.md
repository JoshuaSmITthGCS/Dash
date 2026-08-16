# Phase 5 — Portfolio Page Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `src/pages/Portfolio.jsx` and `src/pages/portfolio/*` into compliance with `DESIGN.md` and the `DataTable`/inline-style conventions the rest of the redesign already follows — this is "Portfolio," the next page in Phase 5's traffic order per `docs/REDESIGN-STATUS.md` §2.

**Architecture:** No new pages or data flow. Four independent, sequentially-safe changes to the already-decomposed `src/pages/portfolio/` module set: (1) a small `DataTable` API addition every later table-migration plan will also need, (2) a real 11px-floor bug fix, (3) porting `ComparisonTables.jsx`'s two raw `<table>`s onto `DataTable`, (4) an inline-style-to-class cleanup local to these files. A fifth task links Portfolio's sector-allocation card through to Diversification rather than removing it (Portfolio is the one page where seeing your own allocation while managing it is the point — this is *not* the Dashboard-pass pattern of deleting a duplicate).

**Tech Stack:** React 18 (function components), Vitest + `@testing-library/react`, plain CSS modules (`src/styles/modules/*.css`, token-driven, no CSS-in-JS).

**Spec:** `docs/REDESIGN-STATUS.md` (current state + `DESIGN.md` rules), `DESIGN.md` (design constitution), `docs/REDESIGN-PLAN.md` (original plan, Portfolio bullets).

## Global Constraints

- No text below 11px, anywhere (`DESIGN.md`).
- No raw hex, px font-size, or px spacing outside `src/styles/variables.css` — every new class uses `var(--fs-*)`/`var(--sp-*)` tokens.
- `positive`/`negative`/`warning` colors are state, never decoration — `moveColor()`-derived colors stay inline (they're genuinely computed per row).
- The 11 CSS modules load in source order and the cascade depends on it (`src/styles/index.css`); add new rules to the existing module a class's siblings already live in, don't create new modules.
- `npm run lint && npm test && npm run build` must pass after every task.
- Firebase is offline locally, so `/portfolio*` routes render their empty state unless given `?portfolioPreview=1` (`docs/REDESIGN-STATUS.md` §4) — use that query param for every manual/browser check in this plan.

---

### Task 1: `DataTable` — add `rowClassName`

**Why now:** three of the four Phase 2c table migrations (Portfolio's TOTAL rows here, plus SwingScreen's suppressed rows and ResearchEvidence's pinned self-row in later plans) need a way to put a class on a `<tr>`. `DataTable` has no such hook today. Doing this once, with a test, means every later migration plan reuses it instead of inventing its own workaround.

**Files:**
- Modify: `src/components/DataTable.jsx:33-46` (props), `:146-154` (body row render)
- Test: `src/components/DataTable.test.jsx`

**Interfaces:**
- Produces: `rowClassName?: (row, index) => string | undefined` — new optional `DataTable` prop. When provided, its return value is applied as the `<tr>`'s `className` (desktop table body only; mobile card/list rendering is untouched — a summary row belongs in the table body, not the card list, so this is intentionally desktop-only).

- [ ] **Step 1: Write the failing test**

Add to `src/components/DataTable.test.jsx` (same file, alongside the existing `describe('DataTable', ...)` block — add this as a new `it` inside it):

```jsx
  it('applies rowClassName to the matching <tr>, leaving others unset', () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} getKey={(row) => row.ticker}
      rowClassName={(row) => (row.ticker === 'BBB' ? 'is-total' : undefined)} />)
    const rows = screen.getAllByRole('row').slice(1) // drop the header row
    expect(rows.map((row) => row.className)).toEqual(['', 'is-total', ''])
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/components/DataTable.test.jsx -t "applies rowClassName"`
Expected: FAIL — `rows.map(...)` returns `['', '', '']` (no row ever gets a class), assertion mismatch.

- [ ] **Step 3: Implement**

In `src/components/DataTable.jsx`, add the prop to the destructured signature (`:33-46`):

```jsx
export default function DataTable({
  columns,
  rows,
  getKey = (row, index) => row.id ?? row.ticker ?? index,
  sort: controlledSort,
  onSort,
  defaultSort = null,
  caption,
  className = '',
  empty = null,
  mobile = null,
  mobileBreakpoint = '(max-width: 900px)',
  virtualizeFrom = 50,
  rowClassName,
}) {
```

Then in the body-row map (`:146-154`):

```jsx
        <tbody>
          {ordered.map((row, index) => (
            <tr key={getKey(row, index)} className={rowClassName?.(row, index) || undefined}>
              {columns.map((column) => (
                <td key={column.key || column.label} className={column.numeric ? 'num' : undefined}>
                  {column.cell ? column.cell(row, index) : row[column.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
```

Also update the JSDoc block above the component (`:19-32`) — add one line after the `mobile config` paragraph:

```jsx
 * rowClassName  optional (row, index) => className, applied to the desktop <tr>.
 *               Use it for a pinned or summary row (a TOTAL row, a suppressed
 *               row) that needs different styling than the rest of the body.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- src/components/DataTable.test.jsx`
Expected: PASS, all existing `DataTable` tests still green (no signature change to any existing prop).

- [ ] **Step 5: Commit**

```bash
git add src/components/DataTable.jsx src/components/DataTable.test.jsx
git commit -m "DataTable: add rowClassName for summary/pinned rows"
```

---

### Task 2: Fix the 11px-floor violation in `HoldingCard.jsx` and dedupe the cost-mode select

**Why:** `HoldingCard.jsx:51` sets `fontSize: 9` on the cost-basis-unit `<select>` inside the mobile edit sheet — a live `DESIGN.md` hard-rule breach ("No text below 11px, anywhere"). A `.field-mode-select` class already exists (`src/styles/modules/base.css:214-217`, `font-size: var(--fs-2xs)` = 11px) and is already used by the *other* cost-basis-unit select in `Holdings.jsx`'s `AddPositionForm` (`src/pages/portfolio/Holdings.jsx:27`) — these are the same UI pattern in two places, one correct, one broken and duplicated. Reusing the existing class fixes the bug and removes the duplicate style block in one move.

**Files:**
- Modify: `src/styles/modules/base.css:214-217` (add two sibling classes)
- Modify: `src/pages/portfolio/HoldingCard.jsx:47-54`
- Modify: `src/pages/portfolio/Holdings.jsx:25-32`
- Test: `src/pages/portfolio/HoldingCard.test.jsx` (new file — no test currently covers this component)

**Interfaces:**
- Consumes: existing `.field-mode-select` (`src/styles/modules/base.css:214`)
- Produces: two new CSS classes, `.field-mode-row` and `.field-row-label`, usable by any future cost-basis-style field header.

- [ ] **Step 1: Write the failing test**

Create `src/pages/portfolio/HoldingCard.test.jsx`:

```jsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import HoldingCard from './HoldingCard.jsx'

const POS = {
  id: 'AAPL', ticker: 'AAPL', dayMove: { pct: 1.2 }, currentPrice: 190, priceInfo: { name: 'Apple Inc.' },
  allocationPct: 5, currentValue: 1900, gainPct: 12, rating: 2, recommendation: { action: 'hold' },
  trendValues: [1, 2, 3], shares: 10, costBasis: 150, quoteSource: 'live', stopLoss: null,
}

function forms(editingId) {
  return {
    editingId, editForm: { shares: '10', costMode: 'share', costBasis: '150', purchaseDate: '2026-01-01' },
    setEditForm: vi.fn(), editSaving: false, startEdit: vi.fn(), cancelEdit: vi.fn(), saveEdit: vi.fn(),
    sellingId: null, startSell: vi.fn(), removingId: null, handleRemove: vi.fn(),
  }
}

describe('HoldingCard edit sheet', () => {
  it('renders the cost-basis unit select at the 11px floor, not smaller', () => {
    render(<HoldingCard pos={POS} essentialOnly={false} forms={forms('AAPL')} onSelectStock={vi.fn()} />)
    const select = screen.getByDisplayValue('$/share')
    expect(select).toHaveClass('field-mode-select')
    expect(select).not.toHaveAttribute('style')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/pages/portfolio/HoldingCard.test.jsx`
Expected: FAIL — the select still carries an inline `style` attribute (`toHaveAttribute('style')` assertion fails since one exists) and lacks the `field-mode-select` class.

- [ ] **Step 3: Add the two CSS classes**

In `src/styles/modules/base.css`, right after the existing `.field-mode-select` rule (`:214-217`):

```css
.field-mode-select {
  min-height: auto; height: 20px; padding: 0 var(--sp-0-5);
  border: 0; background: transparent; color: var(--text-tertiary); font-size: var(--fs-2xs);
}
.field-mode-row { display: flex; justify-content: space-between; }
.field-row-label {
  display: flex; justify-content: space-between; align-items: baseline;
  gap: var(--sp-1-5); margin-bottom: var(--sp-1); font-size: var(--fs-sm);
}
```

- [ ] **Step 4: Fix `HoldingCard.jsx`**

Replace lines 47-54:

```jsx
            <label>
              <span style={{ display: 'flex', justifyContent: 'space-between' }}>
                Cost basis
                <select value={editForm.costMode} onChange={(e) => setEditForm({ ...editForm, costMode: e.target.value })}
                  style={{ minHeight: 'auto', height: 18, padding: '0 2px', border: 0, background: 'transparent', color: 'var(--text-faint)', fontSize: 9, textTransform: 'none', letterSpacing: 0 }}>
                  <option value="share">$/share</option>
                  <option value="total">Total $</option>
                </select>
              </span>
```

with:

```jsx
            <label>
              <span className="field-mode-row">
                Cost basis
                <select value={editForm.costMode} onChange={(e) => setEditForm({ ...editForm, costMode: e.target.value })}
                  className="field-mode-select">
                  <option value="share">$/share</option>
                  <option value="total">Total $</option>
                </select>
              </span>
```

- [ ] **Step 5: Apply the same dedupe to `Holdings.jsx`'s `AddPositionForm`**

In `src/pages/portfolio/Holdings.jsx`, replace line 25:

```jsx
          <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 6, marginBottom: 4, fontSize: 13 }}>
```

with:

```jsx
          <label className="field-row-label">
```

(the `<select className="field-mode-select" ...>` on line 27 is already correct — no change needed there.)

- [ ] **Step 6: Run test to verify it passes**

Run: `npm test -- src/pages/portfolio/HoldingCard.test.jsx`
Expected: PASS.

- [ ] **Step 7: Run the full test suite and lint**

Run: `npm run lint && npm test`
Expected: both pass — this touches a shared class (`base.css`) and two components; confirm nothing else regressed.

- [ ] **Step 8: Commit**

```bash
git add src/styles/modules/base.css src/pages/portfolio/HoldingCard.jsx src/pages/portfolio/Holdings.jsx src/pages/portfolio/HoldingCard.test.jsx
git commit -m "Fix 11px type-floor breach in holding-card cost-basis select, dedupe with AddPositionForm"
```

---

### Task 3: Migrate `ComparisonTables.jsx`'s two tables onto `DataTable`

**Why:** `BenchmarkTable` and `FixedBasisTable` (`src/pages/portfolio/ComparisonTables.jsx`) are 2 of the 4 raw `<table>`s left in the app (`docs/REDESIGN-STATUS.md` Phase 2c). They are near-duplicates of each other (7 of 8 columns identical) with copy-pasted `TOTAL`-row and empty-state markup. Porting both onto `DataTable` via one shared column-builder removes the duplication, and (as a side effect, confirmed by reading `src/styles/modules/research.css:249` — `.data-table { max-width: 100%; overflow-x: auto }`) fixes a real mobile-overflow gap: today these two tables have no scroll wrapper at all (`.table-wrap` is applied but is not a real CSS rule — confirmed by grep, it does nothing), so they can overflow the viewport on narrow screens with no way to see the rest of the row. `DataTable`'s own wrapper fixes that for free.

Row-level sorting is intentionally **not** added: today these tables have no column-header sort (rows arrive pre-ordered from `PortfolioSortToolbar`, external to the table), and adding one is a scope decision for a future pass, not a mechanical port — every column stays `sortable: false`.

**Files:**
- Modify: `src/pages/portfolio/ComparisonTables.jsx` (full rewrite of the file's exports, same two exported function names/props)
- Modify: `src/styles/modules/portfolio.css` (new rules for the total row, empty cell, footnote)
- Test: `src/pages/portfolio/ComparisonTables.test.jsx` (new file)

**Interfaces:**
- Consumes: `DataTable` from `src/components/DataTable.jsx` (`rowClassName` from Task 1), `money`, `moveColor` from `./format.js`, `Move` from `./PortfolioBits.jsx`, `fixedBasisAlternative` from `../../lib/portfolioPerformance`.
- Produces: `BenchmarkTable({ sortedPositions, versusIndex, onPurchaseDateChange })` and `FixedBasisTable({ sortedPositions, fixedBasisTotal, basis, benchmarkHistory, positionCount, onPurchaseDateChange })` — **same names, same props** as today (consumed by `src/pages/portfolio/Holdings.jsx:7,146,157` — no caller change needed).

- [ ] **Step 1: Write the failing tests**

Create `src/pages/portfolio/ComparisonTables.test.jsx`:

```jsx
import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { BenchmarkTable, FixedBasisTable } from './ComparisonTables.jsx'

function setViewport(matches) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  }))
}

const POSITIONS = [
  {
    id: 'AAA', ticker: 'AAA', purchaseDate: '2026-01-01', totalCost: 1000, currentValue: 1200, gainPct: 20,
    versusBenchmark: { value: 1100, gainPct: 10 },
  },
  {
    id: 'BBB', ticker: 'BBB', purchaseDate: '', totalCost: 500, currentValue: 480, gainPct: -4,
    versusBenchmark: null,
  },
]

describe('BenchmarkTable', () => {
  it('renders one row per position with an editable purchase-date input', () => {
    setViewport(false)
    const onChange = vi.fn()
    render(<BenchmarkTable sortedPositions={POSITIONS} versusIndex={null} onPurchaseDateChange={onChange} />)
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(3) // header + 2 positions, no TOTAL
    const dateInput = screen.getByLabelText('AAA purchase date')
    fireEvent.change(dateInput, { target: { value: '2026-02-01' } })
    expect(onChange).toHaveBeenCalledWith('AAA', '2026-02-01')
  })

  it('shows a dash, not a crash, when a position has no benchmark comparison', () => {
    setViewport(false)
    render(<BenchmarkTable sortedPositions={POSITIONS} versusIndex={null} onPurchaseDateChange={vi.fn()} />)
    const bbbRow = screen.getByText('BBB').closest('tr')
    expect(within(bbbRow).getAllByText('–').length).toBeGreaterThan(0)
  })

  it('appends a bold TOTAL row when versusIndex is provided', () => {
    setViewport(false)
    render(<BenchmarkTable sortedPositions={POSITIONS} onPurchaseDateChange={vi.fn()} versusIndex={{
      invested: 1500, holdingsValue: 1680, holdingsReturnPct: 12, benchmarkValue: 1600,
      benchmarkReturnPct: 6.7, dollarsAhead: 80,
    }} />)
    const totalRow = screen.getByText('TOTAL').closest('tr')
    expect(totalRow).toHaveClass('comparison-total-row')
  })
})

describe('FixedBasisTable', () => {
  it('renders the empty state instead of a table when there are no positions', () => {
    setViewport(false)
    render(<FixedBasisTable sortedPositions={[]} fixedBasisTotal={null} basis={1000}
      benchmarkHistory={null} positionCount={0} onPurchaseDateChange={vi.fn()} />)
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByText(/No positions yet/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- src/pages/portfolio/ComparisonTables.test.jsx`
Expected: FAIL — module still exports the raw-`<table>` implementation; `getByRole('table')` finds the old markup, `comparison-total-row` class doesn't exist yet, the empty-state assertion may pass by accident (old code already handles it) but the others fail.

- [ ] **Step 3: Rewrite `src/pages/portfolio/ComparisonTables.jsx`**

```jsx
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
      <DataTable
        rows={rows}
        getKey={(row) => row.id}
        columns={comparisonColumns({ investedLabel: 'Invested', onPurchaseDateChange })}
        rowClassName={(row) => (row.isTotal ? 'comparison-total-row' : undefined)}
      />
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
```

- [ ] **Step 4: Add the new CSS classes**

In `src/styles/modules/portfolio.css`, near the existing `.portfolio-date-input` rule (`:72`):

```css
.comparison-total-row { font-weight: var(--fw-bold); }
.comparison-empty-cell { padding: var(--sp-10) 0; text-align: center; opacity: .5; }
.comparison-footnote { margin-top: var(--sp-3); color: var(--text-faint); font-size: var(--fs-xs); }
.callout--tables-gap { margin: 0 0 var(--sp-4); }
```

(`--sp-10` = 40px, matches the original `padding: 40`; `--sp-3` = 12px matches `marginTop: 12`; `--fs-xs` = 12px matches `fontSize: 12`; `--sp-4` = 16px matches `margin: '0 0 16px'`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `npm test -- src/pages/portfolio/ComparisonTables.test.jsx`
Expected: PASS.

- [ ] **Step 6: Run the full suite, lint, and build**

Run: `npm run lint && npm test && npm run build`
Expected: all pass. `Holdings.jsx` imports `BenchmarkTable`/`FixedBasisTable` by name with the same props (`src/pages/portfolio/Holdings.jsx:7,146,157`) — no caller change needed, so this should not surface anywhere else, but the full suite run confirms it.

- [ ] **Step 7: Manual browser check**

```bash
npx vite --port 5175 --strictPort &
```
Open `http://localhost:5175/portfolio?portfolioPreview=1`, switch to "Vs S&P 500" and "$N Calculator" tabs in both light and dark theme, at 1440px and 390px width. Confirm: date inputs are still editable, the TOTAL row is bold, dollars-ahead is still colored, and at 390px the table scrolls horizontally inside its own box instead of pushing the page wide (the mobile-overflow fix this task claims). Kill the dev server after (`kill %1` or note the PID).

- [ ] **Step 8: Commit**

```bash
git add src/pages/portfolio/ComparisonTables.jsx src/pages/portfolio/ComparisonTables.test.jsx src/styles/modules/portfolio.css
git commit -m "Migrate Portfolio comparison tables onto DataTable, fix latent mobile overflow"
```

---

### Task 4: Inline-style diet — `Holdings.jsx` and `PortfolioBits.jsx`

**Why:** `docs/REDESIGN-STATUS.md` Phase 2e names Portfolio as a top inline-style offender. After Tasks 2–3, the remaining STATIC (non-computed) sites in this file group are 5 in `Holdings.jsx` (the `field-row-label` one is already done in Task 2) and 1 in `PortfolioBits.jsx`.

**Files:**
- Modify: `src/pages/portfolio/Holdings.jsx:9-49,111,121`
- Modify: `src/pages/portfolio/PortfolioBits.jsx:45-57`
- Modify: `src/styles/modules/portfolio.css`

**Interfaces:** none — pure markup/class changes, no prop or export signature changes.

- [ ] **Step 1: Add the CSS classes**

In `src/styles/modules/portfolio.css`, near `.portfolio-mobile-list` (`:20`):

```css
.add-position-card { margin-bottom: var(--sp-5); padding: var(--sp-5); }
.add-position-card h3 { margin-bottom: var(--sp-4); }
.add-position-form { display: grid; grid-template-columns: repeat(4, 1fr) auto; gap: var(--sp-3); align-items: end; }
.add-position-toggle { margin-left: auto; }
.filters--gap { margin-bottom: var(--sp-5); }
.stop-loss-note { font-size: var(--fs-xs); }
```

- [ ] **Step 2: Update `Holdings.jsx`**

Line 11: `<div className="card" style={{ marginBottom: 20, padding: 20 }}>` → `<div className="card add-position-card">`

Line 12: `<h3 style={{ marginBottom: 16 }}>Add New Position</h3>` → `<h3>Add New Position</h3>` (rule now lives on `.add-position-card h3`)

Line 13: `<form onSubmit={onSubmit} style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr) auto', gap: 12, alignItems: 'end' }}>` → `<form onSubmit={onSubmit} className="add-position-form">`

Line 111: `<div className="filters" style={{ marginBottom: 20 }}>` → `<div className="filters filters--gap">`

Line 121: `<button className="tab active" onClick={() => forms.setShowAddForm(!forms.showAddForm)} style={{ marginLeft: 'auto' }}>` → `<button className="tab active add-position-toggle" onClick={() => forms.setShowAddForm(!forms.showAddForm)}>`

- [ ] **Step 3: Update `PortfolioBits.jsx`**

Line 50, `StopLossNote`:

```jsx
    <span className="mono stop-loss-note" style={{ color: past ? 'var(--neg)' : close ? 'var(--warn)' : 'var(--text-faint)', fontSize: 12 }}>
```

becomes:

```jsx
    <span className="mono stop-loss-note" style={{ color: past ? 'var(--neg)' : close ? 'var(--warn)' : 'var(--text-faint)' }}>
```

(font-size now comes from the `.stop-loss-note` base rule added in Step 1; the color stays inline since it's genuinely computed per-position.)

- [ ] **Step 4: Verify no existing test asserts on the removed inline styles**

Run: `npm test -- src/pages/portfolio`
Expected: PASS. (No existing test in this directory currently asserts on `style` attributes for these elements — `portfolioModels.test.js` only tests the pure model functions. If this fails, read the failure and fix the assertion to check the class instead of the removed style, don't revert the markup change.)

- [ ] **Step 5: Run lint and build**

Run: `npm run lint && npm run build`
Expected: both pass.

- [ ] **Step 6: Manual browser check**

With the dev server running (`npx vite --port 5175 --strictPort`), open `http://localhost:5175/portfolio?portfolioPreview=1`, expand "+ Add Position", and confirm the form still lays out as a 4-column grid with the button flush right, in both themes. Toggle a holding into its stop-loss state (or inspect one that already has `stopLoss` data) and confirm the note still renders at a readable size.

- [ ] **Step 7: Commit**

```bash
git add src/pages/portfolio/Holdings.jsx src/pages/portfolio/PortfolioBits.jsx src/styles/modules/portfolio.css
git commit -m "Portfolio: convert remaining static inline styles to classes"
```

---

### Task 5: Link Portfolio's sector-allocation card through to Diversification

**Why:** `Summary.jsx`'s `AllocationSection` (`:77-101`) draws sector allocation via `AllocationDonut`; `Dashboard.jsx:411-422` draws the same data the same way and links onward to `/portfolio/diversification`; `Diversification.jsx` draws a third, independent implementation. Research confirmed this is real triplication, but **unlike** the Dashboard-pass precedent (which deleted a duplicate `PerformanceMetrics` copy because Dashboard's copy was mostly-empty overview noise), Portfolio Summary's sector card is not noise — it's the one place a reader sees their own allocation while actively managing the portfolio. Deleting it would be a regression, not a cleanup. The fix here is additive: link through to the fuller Diversification view, matching the pattern Dashboard already established for exactly this kind of "quick view here, full detail there" relationship, without removing the quick view itself.

**Files:**
- Modify: `src/pages/portfolio/Summary.jsx:94-97`
- Modify: `src/styles/modules/portfolio.css`
- Test: none required — this is a static markup addition (a `<Link>`), no new logic to unit test; verified by browser check.

**Interfaces:** none — no prop/export changes. `Summary.jsx` will need `Link` from `react-router-dom` (already a project dependency, used elsewhere in this same directory via `NavLink` in `PortfolioBits.jsx:3`).

- [ ] **Step 1: Add the import**

In `src/pages/portfolio/Summary.jsx`, add to the top import block (after line 3, before `GrowthChart`):

```jsx
import { Link } from 'react-router-dom'
```

- [ ] **Step 2: Add the link-through**

Replace `src/pages/portfolio/Summary.jsx:94-97`:

```jsx
        <article className="portfolio-allocation-card portfolio-sector-card">
          <header><div><span className="eyebrow">By exposure</span><h3>Sector allocation</h3></div><small>ETF look-through where available</small></header>
          {sectorAllocation.length ? <AllocationDonut sectors={sectorAllocation} totalLabel={money(totalValue)} /> : <div className="unavailable-panel"><strong>Sector data unavailable</strong><p>Priced holdings with sector coverage will appear here.</p></div>}
        </article>
```

with:

```jsx
        <article className="portfolio-allocation-card portfolio-sector-card">
          <header><div><span className="eyebrow">By exposure</span><h3>Sector allocation</h3></div><small>ETF look-through where available</small></header>
          {sectorAllocation.length ? <AllocationDonut sectors={sectorAllocation} totalLabel={money(totalValue)} /> : <div className="unavailable-panel"><strong>Sector data unavailable</strong><p>Priced holdings with sector coverage will appear here.</p></div>}
          <Link to="/portfolio/diversification" className="sector-card-link">Full concentration &amp; correlation breakdown →</Link>
        </article>
```

- [ ] **Step 3: Add the CSS**

In `src/styles/modules/portfolio.css`, near `.portfolio-allocation-card` (grep for it to find the exact block first — it is styled in this file per the module's own scope):

```css
.sector-card-link { display: inline-block; margin-top: var(--sp-3); color: var(--brand-primary); font-size: var(--fs-xs); font-weight: var(--fw-bold); }
```

- [ ] **Step 4: Run lint and build**

Run: `npm run lint && npm run build`
Expected: both pass.

- [ ] **Step 5: Manual browser check**

Open `http://localhost:5175/portfolio?portfolioPreview=1`, scroll to "Allocation" → "By exposure", confirm the new link renders below the donut (or below the unavailable-panel state) and navigates to `/portfolio/diversification` on click, in both themes.

- [ ] **Step 6: Commit**

```bash
git add src/pages/portfolio/Summary.jsx src/styles/modules/portfolio.css
git commit -m "Portfolio Summary: link sector-allocation card through to Diversification"
```

---

### Task 6: Full verification pass and status-doc update

**Files:**
- Modify: `docs/REDESIGN-STATUS.md` (§1 "What is done" — add a Portfolio entry; §2 "What is left" — Phase 5 pointer moves to the next page)
- Modify: `TODO.md` (mirror the same summary per the file's own header instruction: "Everything below is also summarised in `TODO.md`")

- [ ] **Step 1: Run the full verification loop**

```bash
npm run lint && npm test && npm run build
```
Expected: all green.

- [ ] **Step 2: Run the design scripts**

```bash
npx vite --port 5175 --strictPort &
node design/typefloor.mjs
node design/a11ycheck.mjs
```
Expected: `typefloor.mjs` reports 0 violations (it already covers `/portfolio?portfolioPreview=1` and `/portfolio/performance?portfolioPreview=1` by default — confirm the HoldingCard fix from Task 2 is actually exercised: holdings only render when `sortedPositions` is non-empty, which the `?portfolioPreview=1` fixture must provide — if the sweep reports 0 rows measured for holding cards, check `src/lib/portfolioPreview.js` or wherever the preview fixture lives and use real preview data, don't skip the check). `a11ycheck.mjs` should show no new unlabelled-control regressions from the `DataTable`-based tables (the `aria-label` on each purchase-date input, carried over verbatim from the old markup, should still satisfy it).

- [ ] **Step 3: Update `docs/REDESIGN-STATUS.md`**

In §1 "What is done", add a new subsection after "### Phase 6 — metadata + type floor" and its SVG sub-section (i.e., right before the closing `---` that starts §2):

```markdown
### Phase 5 — Portfolio (done)
Second page in traffic order, after Dashboard. `ComparisonTables.jsx`'s two raw
`<table>`s now run on `DataTable` (one shared column set, `rowClassName` — new
`DataTable` prop, see below — for the bold TOTAL row), which incidentally fixed a
mobile-overflow gap neither table had a scroll wrapper for. Fixed a real
`DESIGN.md` breach: the edit-sheet's cost-basis-unit select was `fontSize: 9`,
below the 11px floor, and duplicated (with the bug) a pattern `AddPositionForm`
already had right — both now share `.field-mode-select`. 6 more static inline
styles converted to classes. Sector allocation is drawn on Summary, Dashboard,
and Diversification — Dashboard already links through to Diversification instead
of duplicating; Summary's copy stays (it's the one place you see your own
allocation while managing it) and now also links through, rather than being cut.

`DataTable` gained a `rowClassName(row, index)` prop (`src/components/DataTable.jsx`)
for pinned/summary rows — the remaining Phase 2c migrations (SwingScreen's
suppressed rows, ResearchEvidence's pinned self-row) reuse it instead of each
inventing a workaround.
```

In §2 "What is left", under "### Phase 5 — page-by-page pass", update the traffic-order line:

```markdown
### Phase 5 — page-by-page pass · DASHBOARD + PORTFOLIO DONE · rest not started
Per the plan, in traffic order: ~~Dashboard~~ → ~~Portfolio~~ → Picks → SwingScreen +
screens family → Finances/Planning/Insights/Watchlist/Markets →
Methodology/Glossary/Settings/Alerts → empty states.
```

(leave the rest of that section's Dashboard writeup untouched — only the header line and traffic-order sentence change.)

- [ ] **Step 4: Update `TODO.md`**

Find the SVG type-floor entry (already marked "fixed" per prior work) and, immediately after it, add a matching short entry following the same style as the rest of the file:

```markdown
### Phase 5 — Portfolio page pass — done
`ComparisonTables.jsx` migrated to `DataTable` (`rowClassName` added for the
TOTAL row), one real 11px-floor bug fixed (holding-card cost-basis select was
`fontSize: 9`), 6 static inline styles converted to classes, sector-allocation
card on Summary now links through to Diversification. Full detail in
`docs/REDESIGN-STATUS.md` §1.
```

- [ ] **Step 5: Final commit**

```bash
git add docs/REDESIGN-STATUS.md TODO.md
git commit -m "docs: record Portfolio page pass (Phase 5) as done"
```
