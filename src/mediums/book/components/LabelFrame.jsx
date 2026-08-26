import { STATES } from '../../core/states.js'

/**
 * Typographic weight IS the state encoding, never color (DESIGN.md §5): established = roman,
 * accumulating = italic with a superscript observation count, breached = bold with an
 * editorial-red dagger and a footnote at the foot, unavailable = a bracketed editorial note.
 * Confidence renders as a signed editor's note — plain text, attributed, a separate channel
 * from the four typographic weights above it.
 */
export default function LabelFrame({ parts, capabilityId, children }) {
  const { title, mediumLine, value, read, reference, state, confidence, reason, action } = parts
  const isBreached = state.state === STATES.BREACHED
  const isAccumulating = state.state === STATES.ACCUMULATING
  const isUnavailable = state.state === STATES.UNAVAILABLE

  if (isUnavailable) {
    return (
      <div data-book-table="true" data-capability-id={capabilityId}>
        <p>[not yet reported — {reason}]</p>
      </div>
    )
  }

  return (
    <div data-book-table="true" data-breached={isBreached ? 'true' : undefined} data-capability-id={capabilityId}>
      <p style={{ fontSize: '13px', color: 'var(--ink-secondary)', margin: '0 0 2px', fontStyle: isAccumulating ? 'italic' : 'normal' }}>
        {title}{mediumLine ? ` · ${mediumLine}` : ''}
      </p>
      <p
        style={{
          fontFamily: 'var(--font-mono)', fontSize: '20px', margin: '0 0 2px', fontVariantNumeric: 'tabular-nums',
          fontStyle: isAccumulating ? 'italic' : 'normal',
          fontWeight: isBreached ? 700 : 400,
          color: isBreached ? 'var(--ink-editorial)' : 'var(--ink-primary)',
        }}
      >
        {isAccumulating && state.observations != null ? (
          <>{state.observations}/{state.required ?? '—'}<sup style={{ fontVariantNumeric: 'normal' }} aria-hidden="true">{state.observations}</sup></>
        ) : (
          <>{value ?? read ?? title}{isBreached && <sup data-book-dagger="true" style={{ fontVariantNumeric: 'normal' }}>†</sup>}</>
        )}
      </p>
      {value != null && read && <p style={{ fontSize: '13px', color: 'var(--ink-secondary)' }}>{read}</p>}
      {reference && <p style={{ fontSize: '12px', color: 'var(--ink-faint)' }}>{reference}</p>}
      {isBreached && reason && (
        <p data-book-footnote="true"><sup data-book-dagger="true">†</sup> {reason}</p>
      )}
      <p style={{ fontSize: '12px', color: 'var(--ink-faint)', fontStyle: 'italic' }}>
        — Ed.: confidence {Math.round(confidence.level * 100)}%, {confidence.basis[0]}.
      </p>
      {action}
      {children}
    </div>
  )
}
