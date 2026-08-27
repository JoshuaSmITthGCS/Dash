/** The existing tab idiom (e.g. SwingScreen's tier switcher), generalized for reuse across mediums. */
export default function Tabs({ items = [], active, onSelect, capId }) {
  return (
    <div className="tier-switcher" role="tablist" data-capability-id={capId}>
      {items.map((item) => (
        <button
          key={item.id} type="button" role="tab" aria-selected={item.id === active}
          className={`tab${item.id === active ? ' is-active' : ''}`}
          onClick={() => onSelect?.(item.id)}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
