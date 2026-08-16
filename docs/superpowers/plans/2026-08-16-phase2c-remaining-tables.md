# Phase 2c — Remaining Table Migrations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the three remaining raw `<table>`s onto `DataTable` — `src/components/ResearchEvidence.jsx` (3 tables), `src/pages/SwingScreen.jsx` (1 table), `src/pages/Picks.jsx` (1 table). Portfolio's two tables are already done (see `docs/superpowers/plans/2026-08-16-phase5-portfolio-page-pass.md`).

**Architecture:** Two small, backward-compatible `DataTable` capability additions first (a `rowHeader` column flag, a per-column `defaultSortDir`), each needed by exactly one of the three migrations, each following the same pattern as the `rowClassName` addition already shipped. Then three independent per-file migrations, done in order of size (smallest/cleanest first): ResearchEvidence → SwingScreen → Picks.

**Tech Stack:** React 18, Vitest + `@testing-library/react`, plain CSS modules.

**Spec:** `docs/REDESIGN-STATUS.md` (Phase 2c), `src/components/DataTable.jsx` (existing API + JSDoc).

## Global Constraints

- No text below 11px; no raw hex/px outside `variables.css`.
- `npm run lint && npm test && npm run build` must pass after every task.
- Every column stays `sortable: false` in all three migrations — none of the three tables has column-header sorting today (rows arrive pre-ordered by an external control), and adding one is a scope decision for a later pass, not part of a mechanical port.
- Preserve existing accessible semantics exactly: `<th scope="row">` where the original had it, `aria-label`s on interactive cells carried over verbatim.

---

### Task 1: `DataTable` — add `rowHeader` column flag and per-column `defaultSortDir`

**Why:** `ResearchEvidence.jsx`'s three tables use `<th scope="row">` for the row-identifying cell (Benchmark name / Scenario / Score band) — real accessibility semantics (row-header association for screen readers), not decoration. `DataTable` renders every body cell as `<td>` today; porting these tables without a fix would silently drop that semantic. Separately, `SwingScreen.jsx`'s columns each declare their own default sort direction (`rank`/`ticker` ascending-first, most numeric columns descending-first, `columns.jsx:492-649`) — `DataTable`'s `handleSort` always starts a fresh column at `'desc'` (`nextSort(sort, key)` with no override), which would silently invert the sensible first-click direction for half of SwingScreen's columns. Both are small, additive, backward-compatible column-level flags, following the same pattern as the `rowClassName` prop added in the Phase 5 Portfolio plan.

**Files:**
- Modify: `src/components/DataTable.jsx`
- Test: `src/components/DataTable.test.jsx`

**Interfaces:**
- Produces: `column.rowHeader?: boolean` — when true, that column's body cell renders as `<th scope="row">` instead of `<td>` (desktop table only).
- Produces: `column.defaultSortDir?: 'asc' | 'desc'` — the direction a fresh click on that column's header sorts to; defaults to `'desc'` when omitted (current behavior, unchanged for every already-migrated page).

- [ ] **Step 1: Write the failing tests**

Add to `src/components/DataTable.test.jsx`:

```jsx
  it('renders a rowHeader column as <th scope="row">, other columns as <td>', () => {
    const columns = [
      { key: 'name', label: 'Name', rowHeader: true },
      { key: 'score', label: 'Score', numeric: true },
    ]
    render(<DataTable columns={columns} rows={[{ name: 'Alpha', score: 1 }]} getKey={(row) => row.name} />)
    const bodyRow = screen.getAllByRole('row')[1]
    const rowHeader = within(bodyRow).getByRole('rowheader')
    expect(rowHeader).toHaveTextContent('Alpha')
    expect(rowHeader.tagName).toBe('TH')
  })

  it('starts a column at its own defaultSortDir on first click', () => {
    const columns = [{ key: 'ticker', label: 'Ticker', defaultSortDir: 'asc' }]
    render(<DataTable columns={columns} rows={ROWS} getKey={(row) => row.ticker} />)
    fireEvent.click(within(screen.getByRole('columnheader')).getByRole('button'))
    expect(screen.getByRole('columnheader')).toHaveAttribute('aria-sort', 'ascending')
  })
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- src/components/DataTable.test.jsx -t "rowHeader|defaultSortDir"`
Expected: FAIL — `getByRole('rowheader')` finds nothing (everything renders as `<td>`); the second test finds `aria-sort="descending"` instead of `"ascending"`.

- [ ] **Step 3: Implement `rowHeader`**

In `src/components/DataTable.jsx`, replace the body-cell map (from the `rowClassName` change already in the file):

```jsx
              {columns.map((column) => {
                const content = column.cell ? column.cell(row, index) : row[column.key]
                const cellClassName = column.numeric ? 'num' : undefined
                return column.rowHeader ? (
                  <th key={column.key || column.label} scope="row" className={cellClassName}>{content}</th>
                ) : (
                  <td key={column.key || column.label} className={cellClassName}>{content}</td>
                )
              })}
```

- [ ] **Step 4: Implement `defaultSortDir`**

Replace `handleSort` (`:52-56` before this task's edits):

```jsx
  const handleSort = (key) => {
    const column = columns.find((item) => item.key === key)
    const next = nextSort(sort, key, column?.defaultSortDir || 'desc')
    if (isControlled) onSort?.(next)
    else setUncontrolledSort(next)
  }
```

- [ ] **Step 5: Update the JSDoc**

Add two lines to the column-shape doc comment near the top of the file:

```jsx
 * rowHeader      renders this column's body cell as <th scope="row"> instead
 *                of <td> — use for the column that identifies the row.
 * defaultSortDir the direction a fresh click on this column's header sorts
 *                to. Defaults to 'desc'.
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `npm test -- src/components/DataTable.test.jsx`
Expected: PASS, all existing tests still green.

- [ ] **Step 7: Run lint and the full suite**

Run: `npm run lint && npm test`

- [ ] **Step 8: Commit**

```bash
git add src/components/DataTable.jsx src/components/DataTable.test.jsx
git commit -m "DataTable: add rowHeader column flag and per-column defaultSortDir"
```

---

### Task 2: Migrate `ResearchEvidence.jsx`'s three tables

**Files:**
- Modify: `src/components/ResearchEvidence.jsx:56-97` (`BenchmarkPanel`), `:165-200` (`CostPanel`), `:202-237` (`CalibrationPanel`)
- Modify: `src/styles/modules/detail.css:129-137`
- Test: `src/components/ResearchEvidence.test.jsx` (extend existing file — it already covers these three panels; existing tests must keep passing after the markup change, since they assert on visible text, not raw table structure — verify in Step 3 before writing new assertions)

**Interfaces:**
- Consumes: `DataTable` (`rowHeader`, `rowClassName` from Task 1 and the Portfolio plan).
- Produces: same exported names/props (`BenchmarkPanel({ panel })`, `CostPanel({ panel })`, `CalibrationPanel({ panel })`) — no caller change (`src/pages/LiveValidation.jsx:157` uses `ResearchEvidence` as a whole, which composes these).

- [ ] **Step 1: Read the existing test file to confirm what it asserts**

Run: `npm test -- src/components/ResearchEvidence.test.jsx` (baseline, should already pass) and open `src/components/ResearchEvidence.test.jsx` to see whether any assertion queries `getByRole('table')` cell structure directly, vs. text content (which survives the markup change). Note any structure-dependent assertions before editing — they may need `scope="row"`/`role` updates to match the new DOM.

- [ ] **Step 2: Write new failing tests for the DataTable-specific behavior**

Add to `src/components/ResearchEvidence.test.jsx`:

```jsx
  it('BenchmarkPanel pins the ValueSignal self-row with the evidence-row-self class', () => {
    render(<BenchmarkPanel panel={{
      status: 'measured', strategy: { cagr: 0.12, volatility: 0.18, sharpe: 0.9, max_drawdown: -0.2 },
      summary: { beaten_on_cagr_count: 1, verdict: 'Beats one of two.' },
      rows: [{ name: 'SPY', description: 'S&P 500', cagr: 0.1, volatility: 0.15, sharpe: 0.7, max_drawdown: -0.18, beta: 1, annualized_alpha_pct: 2, significant: true, newey_west_t_statistic: 2.1 }],
    }} />)
    const selfRow = screen.getByRole('rowheader', { name: 'ValueSignal' }).closest('tr')
    expect(selfRow).toHaveClass('evidence-row-self')
    expect(screen.getByRole('rowheader', { name: 'SPY' })).toBeInTheDocument()
  })

  it('CalibrationPanel renders only measured score bands as row headers', () => {
    render(<CalibrationPanel panel={{
      status: 'measured',
      fixed_score_bands: [
        { bucket: '80-90', status: 'measured', observations: 12, median_residual_return: 0.03, beat_sector_rate: 0.6 },
        { bucket: '90-100', status: 'accumulating', observations: 0 },
      ],
    }} />)
    expect(screen.getByRole('rowheader', { name: '80-90' })).toBeInTheDocument()
    expect(screen.queryByRole('rowheader', { name: '90-100' })).toBeNull()
  })
```

- [ ] **Step 3: Run to verify they fail**

Run: `npm test -- src/components/ResearchEvidence.test.jsx -t "evidence-row-self|only measured score bands"`
Expected: FAIL — current markup already uses `<th scope="row">` for these cells, so `getByRole('rowheader')` may actually already find them (this is pre-existing raw-`<table>` markup). The class assertion on the self-row is the one that should fail if `evidence-row-self` isn't applied the same way. Read the actual failure before proceeding — if both already pass against the untouched file, that's expected (you're testing current behavior as a safety net for the refactor, not just new behavior); keep them as regression tests.

- [ ] **Step 4: Rewrite `BenchmarkPanel`**

Replace `src/components/ResearchEvidence.jsx:56-97`:

```jsx
export function BenchmarkPanel({ panel }) {
  if (!panel || panel.status !== 'measured') {
    return <NotGenerated panel={panel} name="Benchmark comparison" />
  }
  const strategy = panel.strategy || {}
  const rows = [
    {
      key: '__self__', name: 'ValueSignal', description: undefined, cagr: strategy.cagr,
      volatility: strategy.volatility, sharpe: strategy.sharpe, max_drawdown: strategy.max_drawdown,
      beta: null, annualized_alpha_pct: null, newey_west_t_statistic: null, significant: false, isSelf: true,
    },
    ...panel.rows.map((row) => ({ key: row.name, ...row })),
  ]
  const columns = [
    { key: 'name', label: 'Benchmark', sortable: false, rowHeader: true, cell: (row) => row.name },
    { key: 'cagr', label: 'CAGR', sortable: false, cell: (row) => pct(row.cagr, 2) },
    { key: 'volatility', label: 'Vol', sortable: false, cell: (row) => pct(row.volatility, 2) },
    { key: 'sharpe', label: 'Sharpe', sortable: false, cell: (row) => num(row.sharpe, 3) },
    { key: 'max_drawdown', label: 'Max DD', sortable: false, cell: (row) => pct(row.max_drawdown, 2) },
    { key: 'beta', label: 'Beta', sortable: false, cell: (row) => (row.isSelf ? '–' : num(row.beta)) },
    {
      key: 'annualized_alpha_pct', label: 'Alpha', sortable: false,
      cell: (row) => (row.isSelf ? '–' : row.annualized_alpha_pct == null ? '–' : `${row.annualized_alpha_pct > 0 ? '+' : ''}${num(row.annualized_alpha_pct)}%`),
    },
    {
      key: 'newey_west_t_statistic', label: 'NW t', sortable: false,
      cell: (row) => (row.isSelf ? '–' : <span className={row.significant ? 'evidence-significant' : undefined}>{num(row.newey_west_t_statistic)}</span>),
    },
  ]
  return <section className="card evidence-panel">
    <header className="section-heading">
      <div><span className="eyebrow">Could an ETF have done this?</span>
        <h2>Benchmark comparison</h2>
        <p>Each leg is buy-and-hold from the strategy&apos;s own start date with one entry cost,
          then a Newey-West regression of the strategy on that benchmark.</p></div>
      <span className="chip">{panel.summary?.beaten_on_cagr_count} beaten on CAGR</span>
    </header>
    <div className="evidence-table-scroll">
      <DataTable
        className="evidence-table"
        rows={rows}
        getKey={(row) => row.key}
        columns={columns}
        rowClassName={(row) => (row.isSelf ? 'evidence-row-self' : undefined)}
      />
    </div>
    <p className="evidence-note">{panel.summary?.verdict}</p>
  </section>
}
```

- [ ] **Step 5: Rewrite `CostPanel`'s table**

Replace `src/components/ResearchEvidence.jsx:181-197` (the `<div className="evidence-table-scroll">...</div>` block inside `CostPanel`):

```jsx
    <div className="evidence-table-scroll">
      <DataTable
        className="evidence-table"
        rows={panel.scenarios || []}
        getKey={(row) => row.scenario}
        columns={[
          { key: 'scenario', label: 'Scenario', sortable: false, rowHeader: true, cell: (row) => title(row.scenario) },
          { key: 'cost_bps', label: 'One-way', sortable: false, cell: (row) => `${num(row.cost_bps, 2)} bps` },
          { key: 'total_cost', label: 'Total cost', sortable: false, cell: (row) => (row.total_cost == null ? '–' : `$${Math.round(row.total_cost).toLocaleString()}`) },
          {
            key: 'drag_vs_realized_flat', label: 'vs flat 10bps', sortable: false,
            cell: (row) => (row.drag_vs_realized_flat == null ? '–' : `${row.drag_vs_realized_flat > 0 ? '+' : ''}$${Math.round(row.drag_vs_realized_flat).toLocaleString()}`),
          },
        ]}
      />
    </div>
```

- [ ] **Step 6: Rewrite `CalibrationPanel`'s table**

Replace `src/components/ResearchEvidence.jsx:213-230` (the measured branch's `<div className="evidence-table-scroll">...</div>` block):

```jsx
      ? <div className="evidence-table-scroll">
        <DataTable
          className="evidence-table"
          rows={panel.fixed_score_bands.filter((band) => band.status === 'measured')}
          getKey={(row) => row.bucket}
          columns={[
            { key: 'bucket', label: 'Score band', sortable: false, rowHeader: true, cell: (row) => row.bucket },
            { key: 'observations', label: 'n', sortable: false, cell: (row) => row.observations },
            { key: 'median_residual_return', label: 'Median residual', sortable: false, cell: (row) => signedPct(row.median_residual_return) },
            { key: 'beat_sector_rate', label: 'Beat sector', sortable: false, cell: (row) => pct(row.beat_sector_rate) },
          ]}
        />
      </div>
```

- [ ] **Step 7: Add the `DataTable` import**

At the top of `src/components/ResearchEvidence.jsx`, add:

```jsx
import DataTable from './DataTable.jsx'
```

- [ ] **Step 8: Update CSS — descendant selectors already work, but drop the now-redundant width/border-collapse rule**

In `src/styles/modules/detail.css`, `.evidence-table`'s class now lands on `DataTable`'s wrapper `<div>` (via its `className` prop), not the `<table>` element itself — every existing descendant selector (`.evidence-table th`, `.evidence-table td`, `.evidence-table thead th`, `.evidence-table tbody th[scope="row"]`) still matches regardless of the extra `<div>`/`<table>` nesting in between. Only the bare `.evidence-table { width: 100%; border-collapse: collapse; font: ... }` rule targeted the table element directly for non-inherited box properties; `border-collapse` becomes a no-op on a `<div>` (harmless — `DataTable`'s own base rule in `research.css:250` already sets `border-collapse: collapse` on its actual `<table>`), and `width`/`font` still cascade correctly. No CSS change is required — confirm this visually in Step 10 rather than editing blind.

- [ ] **Step 9: Run tests to verify they pass**

Run: `npm test -- src/components/ResearchEvidence.test.jsx`
Expected: PASS — both new tests and every pre-existing one.

- [ ] **Step 10: Manual browser check**

```bash
npx vite --port 5175 --strictPort &
```
Open `http://localhost:5175/screens/live-validation` (or wherever `LiveValidation` routes — check `src/App.jsx` for the exact path), scroll to the evidence panels, confirm in both themes: the three tables still look identical (mono font, right-aligned numeric cells, the ValueSignal row visually distinct, bold significant t-stats), and border-collapse renders cleanly (no doubled borders from the extra wrapper div).

- [ ] **Step 11: Commit**

```bash
git add src/components/ResearchEvidence.jsx src/components/ResearchEvidence.test.jsx
git commit -m "Migrate ResearchEvidence's three tables onto DataTable"
```

---

### Task 3: Migrate `SwingScreen.jsx`'s table

**Files:**
- Modify: `src/pages/SwingScreen.jsx` (columns array `:492-649`, table+cards render `:751-803`, delete local `compareBy`/`SortHeader` `:405-442`)
- Modify: `src/styles/modules/research.css` (rename `.swing-row-suppressed` styling target if needed — check first, it likely already targets the class name directly and needs no change since `rowClassName` still applies the same class string to the `<tr>`)
- Test: `src/pages/SwingScreen.test.jsx` (extend existing file)

**Interfaces:**
- Consumes: `DataTable`, `dataTableSort.js`'s `compareBy`/`sortRows`/`nextSort` (replacing SwingScreen's local duplicate), `rowClassName`, `defaultSortDir` from Task 1.
- Produces: no exported signature change — `SwingScreen` is a page component, no external consumers.

- [ ] **Step 1: Confirm `.swing-row-suppressed` doesn't need a CSS change**

Run: `grep -n "swing-row-suppressed" src/styles/modules/*.css` — confirm the rule targets `.swing-row-suppressed` as a `<tr>`-level or descendant selector (not something that assumed raw-table-specific structure). No edit expected here, just confirm before relying on it.

- [ ] **Step 2: Write the failing test**

Add to `src/pages/SwingScreen.test.jsx` (adapt the mock data shape to whatever fixture the existing tests in that file already use — reuse it rather than inventing a new one):

```jsx
  it('sorts rank ascending on first click, not descending', async () => {
    render(<SwingScreen />)
    // adapt to however the existing suite waits for data + finds the table —
    // match the existing tests' setup in this file rather than reinventing it
    const rankHeader = await screen.findByRole('columnheader', { name: /Rank/ })
    fireEvent.click(within(rankHeader).getByRole('button'))
    expect(rankHeader).toHaveAttribute('aria-sort', 'ascending')
  })

  it('applies swing-row-suppressed to a row with suppressed short interest', async () => {
    render(<SwingScreen />)
    const rows = await screen.findAllByRole('row')
    // adapt the fixture/assertion to whichever mocked row has short_interest.suppressed: true
    // in this file's existing mock data; confirm that row's <tr> carries the class.
  })
```

- [ ] **Step 3: Run to verify they fail**

Run: `npm test -- src/pages/SwingScreen.test.jsx -t "sorts rank ascending|swing-row-suppressed"`
Expected: FAIL against the current raw-table implementation (no `columnheader`/`button` role structure from `DataTable` exists yet — the current `SortHeader` renders its own button but without `DataTable`'s `aria-sort` wiring verified by these exact assertions; run first and read the actual failure before proceeding).

- [ ] **Step 4: Delete the local `compareBy` and `SortHeader`**

Remove `src/pages/SwingScreen.jsx:405-442` (the `SortHeader` component and the local `compareBy` — both duplicates of `src/lib/dataTableSort.js`, per that file's own doc comment: *"was previously implemented once inside SwingScreen"*).

Add the import at the top of the file:

```jsx
import DataTable from '../components/DataTable.jsx'
```

- [ ] **Step 5: Adapt the columns array**

In `columns` (`:492-649`), for every column: rename `get` → `sortValue`, `num` → `numeric`, `defaultDir` → `defaultSortDir`, and strip the `<td key="...">...</td>` wrapper from every `cell` so it returns the inner content only. Example for the first three columns (apply the same transform to the rest — `verdict`, `percentile`, `driver`, `upside`, `round_trip`, `trend`, `sector`, `composite_z`, the `legs.map(...)` block, `coverage`, `return_20d`, `liquidity`, `short_interest`, `flags`):

```jsx
  const columns = useMemo(() => [
    {
      key: 'rank', label: 'Rank', sortValue: (row) => row.rank, defaultSortDir: 'asc',
      cell: (row) => `#${row.rank}`,
    },
    {
      key: 'ticker', label: 'Ticker', sortValue: (row) => row.ticker, defaultSortDir: 'asc',
      cell: (row) => <><b>{row.ticker}</b><span className="swing-row-name">{row.name}</span></>,
    },
    {
      key: 'verdict', label: 'Verdict', defaultSortDir: 'desc',
      hint: 'Where this row stands once ranking, eligibility and cost are combined.',
      sortValue: (row) => VERDICT_ORDER[verdictFor(row).label] ?? -1,
      cell: (row) => {
        const verdict = verdictFor(row)
        return <span className={`tier ${verdict.tone}`} title={verdict.title}>{verdict.label}</span>
      },
    },
```

For the `percentile` column (whose original `<td>` carried `className="swing-strength-cell"` and a `title` — those move onto the returned node, not the cell wrapper, since `DataTable` no longer lets a column set the `<td>`'s own class/title beyond `numeric`):

```jsx
    {
      key: 'percentile', label: 'Signal', defaultSortDir: 'desc', numeric: true, full: true,
      hint: 'Rank within this tier, in words. The exact percentile and composite z stay on the row.',
      sortValue: (row) => row.percentile,
      cell: (row) => {
        const strength = strengthFor(row.percentile)
        return (
          <span className="swing-strength-cell"
            title={`${row.percentile == null ? 'unranked' : `${row.percentile.toFixed(0)}th percentile`} in this tier · composite ${z(row.composite_z)}`}>
            <span className={`swing-strength-label ${strength.tone}`}>{strength.label}</span>
            <span className="swing-strength-track" aria-hidden="true">
              <span className={`swing-strength-fill ${strength.tone}`} style={{ width: `${strength.width}%` }} />
            </span>
          </span>
        )
      },
    },
```

Apply the identical mechanical transform (rename fields, unwrap `<td>` into a `<span>` or fragment carrying whatever `className`/`title` the original `<td>` had) to every remaining column definition through line 649, including the dynamic `legs.map(...)` block — its `cell` already returns `<LegCell .../>` without a `<td>` wrapper visible in the excerpt read for this plan, so re-check that component's actual return value against the live file before assuming no change is needed there.

- [ ] **Step 6: Replace the render**

Replace `src/pages/SwingScreen.jsx:791-803` (the raw `<table>`) together with the `ResultCards` call above it (`:751-770`) with a single `DataTable`:

```jsx
        <DataTable
          rows={rows}
          getKey={(row) => row.ticker}
          columns={shown}
          rowClassName={(row) => (row.short_interest?.suppressed ? 'swing-row-suppressed' : undefined)}
          className="research-table"
          mobile={{
            variant: preferences.mobileResearchView,
            title: (row) => `#${row.rank} · ${row.ticker}`,
            subtitle: (row) => row.sector || 'Unclassified',
            fields: preferences.mobileResearchView === 'detailed' ? [
              { label: 'Composite', value: (row) => z(row.composite_z) },
              { label: 'Percentile', value: (row) => (row.percentile == null ? '–' : row.percentile.toFixed(0)) },
              ...legs.map(([key, label]) => ({
                label, value: (row) => (row.legs?.[key]?.applied ? z(row.legs[key].z) : '–'),
              })),
              ...(tier ? [{ label: 'Net edge (bps)', value: (row) => bps(row.economics_net_edge_bps) }] : []),
              { label: 'Signal coverage', value: (row) => pct((row.coverage || 0) * 100) },
              { label: 'Short interest', value: (row) => shortInterestLabel(row) },
              { label: 'Flags', value: (row) => (row.reason_codes || []).join(', ') || 'None' },
            ] : [
              { label: 'Composite', value: (row) => z(row.composite_z) },
              { label: 'Percentile', value: (row) => (row.percentile == null ? '–' : row.percentile.toFixed(0)) },
              ...(tier ? [{ label: 'Net edge (bps)', value: (row) => bps(row.economics_net_edge_bps) }] : []),
              { label: 'Signal coverage', value: (row) => pct((row.coverage || 0) * 100) },
              { label: 'Flags', value: (row) => (row.reason_codes || []).join(', ') || 'None' },
            ],
          }}
        />
```

Remove the now-unused `sort`/`onSort`/`compareBy(active.get, ...)` derivation at `:653-659` (`DataTable` manages sort state internally when uncontrolled — passing no `sort`/`onSort` props). Keep `rows` as `filtered` (the pre-sort, pre-`DataTable` filtered array) rather than the old locally-sorted `rows` variable, since `DataTable` now owns sorting.

- [ ] **Step 7: Run the test file, fix fallout**

Run: `npm test -- src/pages/SwingScreen.test.jsx`
Expected: work through failures one at a time — this is the largest mechanical transform in the plan and the existing test file (`src/pages/SwingScreen.test.jsx`) will catch anything the column-by-column rewrite missed (a stray `<td>` still present inside a `cell`, a class that didn't carry over). Fix forward; do not weaken an assertion to make it pass without understanding why it changed.

- [ ] **Step 8: Run lint, full suite, build**

Run: `npm run lint && npm test && npm run build`

- [ ] **Step 9: Manual browser check**

With the dev server running, open `http://localhost:5175/screens/swing`, toggle "Simple"/"Every number", toggle mobile width (390px) vs desktop (1440px) in both themes, and confirm: header-click sorting still works with sensible first-click directions (Rank ascending, Composite descending), a suppressed row is still visually distinct, and the mobile card list still renders (now via `DataTable`'s own mobile branch instead of the always-mounted `ResultCards`).

- [ ] **Step 10: Commit**

```bash
git add src/pages/SwingScreen.jsx src/pages/SwingScreen.test.jsx
git commit -m "Migrate SwingScreen onto DataTable, drop duplicate compareBy/SortHeader"
```

---

### Task 4: Migrate `Picks.jsx`'s `ResearchPool` table

**Files:**
- Modify: `src/pages/Picks.jsx:378-429` (`ResearchPool`)
- Test: `src/pages/Picks.test.jsx` (extend existing file)

**Interfaces:**
- Consumes: `DataTable`.
- Produces: no exported signature change (`ResearchPool` is a page-local component).

- [ ] **Step 1: Write the failing test**

Add to `src/pages/Picks.test.jsx`, matching whatever mock-data/render pattern the existing tests in that file already use:

```jsx
  it('renders 17 columns including the model-score pair only when a ranking model is active', async () => {
    // Reuse this file's existing render + mock-data setup. Assert the header row's
    // column count differs by exactly 2 between a plain sort and a ranking-model sort,
    // matching the current modelActive-conditional Model score / Why it ranks here columns.
  })
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- src/pages/Picks.test.jsx -t "17 columns"`

- [ ] **Step 3: Rewrite `ResearchPool`**

Replace `src/pages/Picks.jsx:378-429`:

```jsx
function picksColumns({ modelActive, onOpen, onBuy, buyingTicker, heldTickers, alertingTicker, alertStatuses, onSetAlert }) {
  return [
    { key: 'rank', label: 'Rank', sortable: false, cell: (row, index) => <span className="rank">{`#${index + 1}`}</span> },
    {
      key: 'company', label: 'Company', sortable: false,
      cell: (row) => <div className="table-company company-with-logo"><CompanyLogo company={row} size={34} /><div><b>{row.ticker}</b><span>{row.name}</span><small>{row.sector || 'Unclassified'}</small></div></div>,
    },
    {
      key: 'type', label: 'Type', sortable: false,
      cell: (row) => <><span className="chip asset-chip">{row.is_etf ? 'ETF' : 'Stock'}</span> <ScreenChips row={row} /></>,
    },
    { key: 'stance', label: 'Stance', sortable: false, cell: (row) => <Tier label={row.stance} /> },
    {
      key: 'rating', label: 'Rating', sortable: false,
      cell: (row) => <RatingBadge value={row.rating} title="-5 (worst) to +5 (best), a percentile read of the published score against its own pool (stocks vs. stocks, ETFs vs. ETFs), pulled toward 0 the less confident the underlying data is." />,
    },
    {
      key: 'signal', label: 'Signal', sortable: false,
      cell: (row) => (row.is_etf ? '–' : <ActionPill recommendation={getRecommendation(row)} />),
    },
    ...(modelActive ? [
      { key: 'model_score', label: 'Model score', sortable: false, numeric: true, cell: (row) => <span className="mono score-cell">{row.modelScore ? Math.round(row.modelScore.score) : '–'}</span> },
      { key: 'model_reason', label: 'Why it ranks here', sortable: false, cell: (row) => <span className="lens-reason-cell">{modelReason(row) || '–'}</span> },
    ] : []),
    { key: 'score', label: 'Score', sortable: false, numeric: true, cell: (row) => <span className="mono score-cell">{row.score}</span> },
    { key: 'fundamentals', label: 'Fundamentals', sortable: false, numeric: true, cell: (row) => <span className="mono">{row.components?.fundamentals == null ? '–' : Math.round(row.components.fundamentals)}</span> },
    { key: 'return_20d', label: '20-day return', sortable: false, numeric: true, cell: (row) => <Move pct={row.technical_detail?.return_20d} /> },
    { key: 'confidence', label: 'Confidence', sortable: false, numeric: true, cell: (row) => <span className="mono">{finite(row.data_coverage) ? `${Math.round(row.data_coverage * 100)}%` : '–'}</span> },
    {
      key: 'timing', label: 'Timing', sortable: false,
      cell: (row) => <EntryTimingAction row={row} alerting={alertingTicker === row.ticker}
        alertStatus={alertStatuses[row.ticker]} onSetAlert={onSetAlert} />,
    },
    { key: 'portfolio_pct', label: '% of my portfolio', sortable: false, numeric: true, cell: (row) => <span className="mono">{row.portfolioPct == null ? '–' : `${row.portfolioPct.toFixed(1)}%`}</span> },
    {
      key: 'portfolio', label: 'Portfolio', sortable: false,
      cell: (row) => (heldTickers.has(row.ticker)
        ? <span className="holding-chip held">Bought</span>
        : <button className="primary-button compact research-table-buy" disabled={buyingTicker === row.ticker || !row.price} onClick={() => onBuy(row)}>{buyingTicker === row.ticker ? 'Adding…' : 'Buy $100'}</button>),
    },
    { key: 'watchlist', label: <span className="sr-only">Watchlist</span>, sortable: false, cell: (row) => <WatchlistToggleButton stock={row} size={17} /> },
    {
      key: 'open', label: <span className="sr-only">Open</span>, sortable: false,
      cell: (row) => <button className="icon-button" onClick={() => onOpen(row)} aria-label={`Open ${row.name} research`}><Icon name="chevron" /></button>,
    },
  ]
}

function ResearchPool({ label, rows, onOpen, heldTickers, buyingTicker, buyStatuses, onBuy,
                       alertingTicker, alertStatuses, onSetAlert, sort }) {
  if (!rows.length) return null
  const modelActive = isRankingModel(sort)
  return (
    <section className="research-pool" aria-label={label}>
      {label && <h2 className="research-pool-title">{label} <span className="research-pool-count">{rows.length}</span></h2>}
      <DataTable
        rows={rows}
        getKey={(row) => row.ticker}
        columns={picksColumns({ modelActive, onOpen, onBuy, buyingTicker, heldTickers, alertingTicker, alertStatuses, onSetAlert })}
        className="research-table"
        mobile={{
          renderItem: (row, index) => <ResearchCard row={row}
            rank={index + 1} onOpen={onOpen}
            held={heldTickers.has(row.ticker)} buying={buyingTicker === row.ticker}
            buyStatus={buyStatuses[row.ticker]} onBuy={onBuy}
            alertingTicker={alertingTicker} alertStatuses={alertStatuses} onSetAlert={onSetAlert} />,
          className: 'research-mobile-list',
          estimateSize: 390,
        }}
      />
    </section>
  )
}
```

Add the import at the top of the file: `import DataTable from '../components/DataTable.jsx'`. Remove the now-unused `MobileVirtualList` import if `ResearchPool` was its only caller in this file (grep the rest of `Picks.jsx` for `MobileVirtualList` before removing the import — if another component in the same file still uses it directly, keep the import).

- [ ] **Step 4: Run the test file, fix fallout**

Run: `npm test -- src/pages/Picks.test.jsx`
Expected: work through failures column by column, same discipline as Task 3 Step 7 — the existing suite is the safety net for a 17-column mechanical transform; don't weaken assertions.

- [ ] **Step 5: Run lint, full suite, build**

Run: `npm run lint && npm test && npm run build`

- [ ] **Step 6: Manual browser check**

Open `http://localhost:5175/picks` (confirm exact route in `src/App.jsx`), switch between plain and ranking-model sort (to exercise `modelActive`'s conditional columns), toggle 390px/1440px width and both themes. Confirm: all 15/17 columns render correctly, the Buy button and watchlist/open icon buttons still work, and the mobile card list renders via `ResearchCard` unchanged.

- [ ] **Step 7: Commit**

```bash
git add src/pages/Picks.jsx src/pages/Picks.test.jsx
git commit -m "Migrate Picks' ResearchPool table onto DataTable"
```

---

### Task 5: Verification pass and status-doc update

- [ ] **Step 1: Full verification loop**

```bash
npm run lint && npm test && npm run build
npx vite --port 5175 --strictPort &
node design/typefloor.mjs
node design/a11ycheck.mjs
```
Expected: all pass, 0 type-floor violations, 0 unnamed controls. Kill the dev server after.

- [ ] **Step 2: Update `docs/REDESIGN-STATUS.md`**

In §1 "What is done", add after the Phase 5 Portfolio subsection added by the prior plan:

```markdown
### Phase 2c — all four remaining tables migrated to DataTable ✅
`ResearchEvidence.jsx`'s three tables, `SwingScreen.jsx`, and `Picks.jsx`'s
`ResearchPool` all now run on `DataTable`. Two more capabilities added to
support them: `rowHeader` (a column renders as `<th scope="row">`, preserving
the row-identity semantics `ResearchEvidence`'s tables already had) and
per-column `defaultSortDir` (SwingScreen's columns each have a sensible first
click direction — rank ascending, most numeric columns descending — which a
single global default would have flattened). SwingScreen's locally duplicated
`compareBy`/`SortHeader` are deleted in favor of the shared `dataTableSort.js`
and `DataTable`'s own header. Every migrated column stays `sortable: false`
where the original had no header-click sort (Portfolio's comparison tables,
ResearchEvidence, Picks) — that remains a scope decision for later, not a
side effect of the port.
```

In §2 "What is left", remove the "### Phase 2c — four tables still off `DataTable`" section entirely (it's now done).

- [ ] **Step 3: Update `TODO.md`**

Replace the "Three tables not yet on `DataTable`" bullet (added by the Portfolio plan) with:

```markdown
- **All tables now on `DataTable`.** Picks, SwingScreen, and ResearchEvidence's
  three evidence tables migrated; Portfolio's two comparison tables migrated
  in the Phase 5 pass. `DataTable` gained `rowClassName`, `rowHeader`, and
  per-column `defaultSortDir` along the way.
```

- [ ] **Step 4: Commit**

```bash
git add docs/REDESIGN-STATUS.md TODO.md
git commit -m "docs: record Phase 2c table migrations as done"
```
