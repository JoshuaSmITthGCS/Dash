import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer, useWindowVirtualizer } from '@tanstack/react-virtual'
import { useMediaQuery } from '../lib/useMediaQuery.js'
import { nextSort, sortRows } from '../lib/dataTableSort.js'
import ResultCards from './ResultCards.jsx'
import MobileVirtualList from './MobileVirtualList.jsx'

// Matches `td { padding: var(--sp-3); ... }` in research.css: ~12px top/bottom padding
// plus a --fs-xs line and a 1px border-bottom lands close to 48px for a typical row.
// Only an initial guess - each virtualizer self-corrects via ResizeObserver measurement.
const ROW_HEIGHT_ESTIMATE = 48

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
 * The desktop `<table>` virtualizes too, past `virtualizeFrom` rows, using the same
 * "two padding rows" technique either way: an element-scoped virtualizer when the
 * wrapper's own CSS gives it `overflow-y: auto` (an internally-scrolling table, e.g.
 * `.research-table`'s `max-height: 72dvh`), a window-scoped one otherwise (a table
 * that grows with the page). Detected once per mount from computed style, not passed
 * in, so a page's existing className is the only thing that decides it.
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

  const wrapperRef = useRef(null)
  const [internalScroll, setInternalScroll] = useState(null)

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

  // Starts `null` ("not yet measured"), not `false` — the wrapper ref (and therefore its
  // offsetTop, which the window virtualizer's scrollMargin needs) doesn't exist until after
  // the first commit, so this must go through at least one state change post-mount even when
  // the measured answer turns out to be `false`, or a window-scrolled table would virtualize
  // forever against a scrollMargin of 0 — nothing else would trigger the re-render that reads
  // the real offsetTop.
  //
  // Detected from rendered geometry (scrollHeight vs clientHeight), not computed style: CSS
  // requires `overflow-y` to compute to `auto` whenever `overflow-x` is non-`visible` and
  // overflow-y was left at its `visible` default (the box can't clip one axis and not the
  // other), so `.data-table`'s base `overflow-x: auto` alone makes every wrapper's *computed*
  // overflow-y read `auto` — including tables with no height constraint at all. Only a real
  // `max-height` (like `.research-table`'s `72dvh`) actually clips, and clipping is the thing
  // that matters here: the padding-row technique keeps scrollHeight equal to the full
  // un-virtualized height throughout, so this comparison stays correct after virtualizing too.
  useLayoutEffect(() => {
    if (!wrapperRef.current) return
    setInternalScroll(wrapperRef.current.scrollHeight > wrapperRef.current.clientHeight + 1)
  }, [className, ordered.length])

  // Both virtualizers are always instantiated (rules of hooks — which one is active
  // can't gate whether either hook runs) and given count:0 when unused, which makes
  // them no-ops. Only the active one's output is read.
  const virtualizeDesktop = !isMobile && ordered.length > virtualizeFrom
  const elementVirtualizer = useVirtualizer({
    count: virtualizeDesktop && internalScroll === true ? ordered.length : 0,
    getScrollElement: () => wrapperRef.current,
    estimateSize: () => ROW_HEIGHT_ESTIMATE,
    overscan: 8,
  })
  const windowVirtualizer = useWindowVirtualizer({
    count: virtualizeDesktop && internalScroll !== true ? ordered.length : 0,
    estimateSize: () => ROW_HEIGHT_ESTIMATE,
    overscan: 8,
    scrollMargin: wrapperRef.current?.offsetTop ?? 0,
  })
  const virtualizer = internalScroll === true ? elementVirtualizer : windowVirtualizer
  const scrollMargin = internalScroll === true ? 0 : (windowVirtualizer.options.scrollMargin || 0)

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

  const renderRow = (row, index, measureRef) => (
    <tr key={getKey(row, index)} data-index={index} ref={measureRef} className={rowClassName?.(row, index) || undefined}>
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
  )

  const virtualItems = virtualizeDesktop ? virtualizer.getVirtualItems() : null
  const totalSize = virtualizeDesktop ? virtualizer.getTotalSize() : 0

  return (
    <div ref={wrapperRef} className={`data-table ${className}`.trim()}>
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
          {virtualizeDesktop ? (
            <>
              {virtualItems.length > 0 && (
                <tr aria-hidden="true" style={{ height: virtualItems[0].start - scrollMargin }}>
                  <td colSpan={columns.length} style={{ padding: 0, border: 0 }} />
                </tr>
              )}
              {virtualItems.map((virtualRow) => renderRow(ordered[virtualRow.index], virtualRow.index, virtualizer.measureElement))}
              {virtualItems.length > 0 && (
                <tr aria-hidden="true" style={{ height: totalSize - (virtualItems.at(-1).end - scrollMargin) }}>
                  <td colSpan={columns.length} style={{ padding: 0, border: 0 }} />
                </tr>
              )}
            </>
          ) : ordered.map((row, index) => renderRow(row, index))}
        </tbody>
      </table>
    </div>
  )
}
