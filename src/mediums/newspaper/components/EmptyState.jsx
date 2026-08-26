/** "Not yet reported" with the reason, styled as a wire-service placeholder line (DESIGN.md §8). */
export default function EmptyState({ reason }) {
  return (
    <p role="alert" data-column-rule="true" style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--ink-faint)', fontStyle: 'italic' }}>
      NOT YET REPORTED — {reason}
    </p>
  )
}
