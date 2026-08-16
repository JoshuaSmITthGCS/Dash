import { useMemo, useState } from 'react'
import { useMediaQuery } from '../lib/useMediaQuery.js'
import { nextSort, sortRows } from '../lib/dataTableSort.js'
import ResultCards from './ResultCards.jsx'
import MobileVirtualList from './MobileVirtualList.jsx'

/**
 * The one table entry point.
 *
 * Three strategies used to coexist: raw `<table>` written out in 13 files, the
 * `ResultCards` mobile fallback, and `MobileVirtualList`. Which of them a page
 * used, and whether its mobile view virtualized, was decided per page. DataTable
 * makes that one decision: a semantic table on desktop, and below the mobile
 * breakpoint the same rows as cards — virtualized automatically once the list is
 * long enough that mounting every card costs something.
 *
 * Exactly one of the two trees is mounted, so a long list is never built twice.
 *
 * Columns:
 *   key        stable id, also the sort key
 *   label      header text
 *   cell       (row, index) => node. Defaults to row[key].
 *   sortValue  (row) => comparable. Defaults to row[key]. Omit `sortable` to
 *              make the column unsortable.
 *   sortable   default true when the column has a key
 *   numeric    right-aligns and sets tabular figures
 *   hint       header title attribute
 *   header     node to render after the label (an InfoTag, typically)
 *
 * Mobile config maps the same rows onto ResultCards; when it is omitted the
 * table simply scrolls horizontally, which is the right answer for a matrix.
 *
 * rowClassName  optional (row, index) => className, applied to the desktop <tr>.
 *               Use it for a pinned or summary row (a TOTAL row, a suppressed
 *               row) that needs different styling than the rest of the body.
 * rowHeader      renders this column's body cell as <th scope="row"> instead
 *                of <td> — use for the column that identifies the row.
 * defaultSortDir the direction a fresh click on this column's header sorts
 *                to. Defaults to 'desc'.
 */
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
  const [uncontrolledSort, setUncontrolledSort] = useState(defaultSort)
  const isControlled = controlledSort !== undefined
  const sort = isControlled ? controlledSort : uncontrolledSort
  const isMobile = useMediaQuery(mobileBreakpoint)

  const handleSort = (key) => {
    const column = columns.find((item) => item.key === key)
    const next = nextSort(sort, key, column?.defaultSortDir || 'desc')
    if (isControlled) onSort?.(next)
    else setUncontrolledSort(next)
  }

  // A controlled parent is responsible for its own ordering; sorting again here
  // would fight it.
  const ordered = useMemo(
    () => (isControlled ? rows : sortRows(rows, columns, sort)),
    [isControlled, rows, columns, sort],
  )

  if (!ordered.length && empty) return empty

  if (isMobile && mobile?.renderItem) {
    // A page with a bespoke mobile card (not a label/value list) keeps it, and
    // still gets virtualization from the same place as every other table.
    return (
      <MobileVirtualList
        className={mobile.className || 'research-mobile-list'}
        items={ordered}
        getKey={getKey}
        renderItem={mobile.renderItem}
        estimateSize={mobile.estimateSize}
      />
    )
  }

  if (isMobile && mobile) {
    // Card fields default to the columns themselves, so a column added to the
    // table cannot silently go missing from the mobile view.
    const fields = mobile.fields || columns
      .filter((column) => column.key !== mobile.titleColumn)
      .map((column) => ({
        label: column.label,
        value: column.cell || ((row) => row[column.key]),
        hideEmpty: column.hideEmpty,
      }))
    return (
      <ResultCards
        rows={ordered}
        getKey={getKey}
        title={mobile.title}
        subtitle={mobile.subtitle}
        fields={fields}
        footer={mobile.footer}
        variant={mobile.variant}
        estimateSize={mobile.estimateSize}
        forceMobile
        virtualizeFrom={virtualizeFrom}
      />
    )
  }

  return (
    <div className={`data-table ${className}`.trim()}>
      <table>
        {caption && <caption>{caption}</caption>}
        <thead>
          <tr>
            {columns.map((column) => {
              const sortable = column.sortable !== false && Boolean(column.key)
              const active = sortable && sort?.key === column.key
              return (
                <th
                  key={column.key || column.label}
                  scope="col"
                  className={column.numeric ? 'num' : undefined}
                  // The caret is aria-hidden and the direction rides on aria-sort, so a
                  // screen reader announces the column and its state rather than a triangle,
                  // and the accessible name stays stable while the direction changes.
                  aria-sort={sortable ? (active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none') : undefined}
                >
                  {sortable ? (
                    <button
                      type="button"
                      className={`data-table-sort${active ? ' is-active' : ''}`}
                      onClick={() => handleSort(column.key)}
                      title={column.hint || `Sort by ${column.label}`}
                    >
                      {column.label}
                      <span aria-hidden="true" className="data-table-caret">
                        {active ? (sort.dir === 'asc' ? '▲' : '▼') : '↕'}
                      </span>
                    </button>
                  ) : column.label}
                  {column.header}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {ordered.map((row, index) => (
            <tr key={getKey(row, index)} className={rowClassName?.(row, index) || undefined}>
              {columns.map((column) => {
                const content = column.cell ? column.cell(row, index) : row[column.key]
                const cellClassName = column.numeric ? 'num' : undefined
                return column.rowHeader ? (
                  <th key={column.key || column.label} scope="row" className={cellClassName}>{content}</th>
                ) : (
                  <td key={column.key || column.label} className={cellClassName}>{content}</td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
