import { Empty } from '../../../components/Bits.jsx'

/** The existing `<Empty/>` component, ported as-is (DESIGN.md §12 empty/loading/error). */
export default function EmptyState({ reason }) {
  return <Empty note={reason} />
}
