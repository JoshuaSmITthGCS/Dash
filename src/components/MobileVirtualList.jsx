import { useEffect, useRef, useState } from 'react'
import { useWindowVirtualizer } from '@tanstack/react-virtual'

function WindowedMobileList({ items, getKey, renderItem, estimateSize, className }) {
  const listRef = useRef(null)
  const virtualizer = useWindowVirtualizer({
    count: items.length,
    estimateSize: () => estimateSize,
    overscan: 5,
    scrollMargin: listRef.current?.offsetTop ?? 0,
  })
  return <div ref={listRef} className={`${className} virtualized`} style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
    {virtualizer.getVirtualItems().map((item) => <div
      key={getKey(items[item.index], item.index)}
      ref={virtualizer.measureElement}
      data-index={item.index}
      className="virtual-result-row"
      style={{ transform: `translateY(${item.start - virtualizer.options.scrollMargin}px)` }}
    >{renderItem(items[item.index], item.index)}</div>)}
  </div>
}

/** Mounts phone cards only at the mobile breakpoint and windows lists above 50 rows. */
export default function MobileVirtualList({ items, getKey, renderItem, estimateSize = 360, className = '' }) {
  const [mobile, setMobile] = useState(() => window.matchMedia?.('(max-width: 900px)').matches ?? false)
  useEffect(() => {
    const query = window.matchMedia?.('(max-width: 900px)')
    if (!query) return undefined
    const update = (event) => setMobile(event.matches)
    query.addEventListener?.('change', update)
    return () => query.removeEventListener?.('change', update)
  }, [])
  if (!mobile) return null
  if (items.length > 50) return <WindowedMobileList items={items} getKey={getKey} renderItem={renderItem} estimateSize={estimateSize} className={className} />
  return <div className={className}>{items.map((item, index) => <div key={getKey(item, index)}>{renderItem(item, index)}</div>)}</div>
}
