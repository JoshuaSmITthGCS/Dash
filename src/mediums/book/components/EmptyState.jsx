/** A bracketed editorial note — DESIGN.md §5 empty/loading/error. */
export default function EmptyState({ reason }) {
  return (
    <p role="alert" data-book-table="true">[not yet reported — {reason}]</p>
  )
}
