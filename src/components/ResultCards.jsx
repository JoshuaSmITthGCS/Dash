import { useEffect, useRef, useState } from 'react'
import { useWindowVirtualizer } from '@tanstack/react-virtual'

function ResultCard({ row, index, title, subtitle, fields, footer, variant }) {
  const asOf = row.as_of || row.data_as_of || row.generated_at || row.date
  return <article className={`result-card ${variant || ''}`} data-index={index}>
    <header>
      <div><strong>{title(row, index)}</strong>{subtitle && <span>{subtitle(row, index)}</span>}</div>
    </header>
    <dl>{fields.map((field) => {
      const value = field.value(row, index)
      if (field.hideEmpty && (value == null || value === '–')) return null
      return <div key={field.label} className={field.className?.(row, index) || ''}><dt>{field.label}</dt><dd>{value ?? '–'}</dd></div>
    })}</dl>
    {(footer || asOf) && <footer>{footer && footer(row, index)}{asOf && <small className="as-of-line">As of {String(asOf).slice(0, 10)}</small>}</footer>}
  </article>
}

function VirtualResultCards(props) {
  const { rows, estimateSize = 250 } = props
  const listRef = useRef(null)
  const virtualizer = useWindowVirtualizer({
    count: rows.length,
    estimateSize: () => estimateSize,
    overscan: 6,
    scrollMargin: listRef.current?.offsetTop ?? 0,
  })
  return <div ref={listRef} className="result-card-list virtualized" style={{ height: virtualizer.getTotalSize() }}>
    {virtualizer.getVirtualItems().map((item) => <div
      key={props.getKey(rows[item.index], item.index)}
      ref={virtualizer.measureElement}
      data-index={item.index}
      className="virtual-result-row"
      style={{ transform: `translateY(${item.start - virtualizer.options.scrollMargin}px)` }}
    ><ResultCard {...props} row={rows[item.index]} index={item.index} /></div>)}
  </div>
}

/**
 * Shared responsive representation for table results. Lists above 50 rows use
 * dynamic window virtualization so mobile routes do not mount every card.
 */
export default function ResultCards(props) {
  const [mobile, setMobile] = useState(() => window.matchMedia?.('(max-width: 900px)').matches ?? false)
  useEffect(() => {
    const query = window.matchMedia?.('(max-width: 900px)')
    if (!query) return undefined
    const update = (event) => setMobile(event.matches)
    query.addEventListener?.('change', update)
    return () => query.removeEventListener?.('change', update)
  }, [])
  if (!mobile) return null
  if (props.rows.length > 50) return <VirtualResultCards {...props} />
  return <div className="result-card-list">{props.rows.map((row, index) =>
    <ResultCard key={props.getKey(row, index)} {...props} row={row} index={index} />)}</div>
}
