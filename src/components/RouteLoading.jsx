// Shared Suspense fallback for both App.jsx (Classic) and MediumApp.jsx (/v2, e2e-harness) —
// extracted so neither root has to statically import the other to reuse it. No Firebase
// dependency; safe on both sides of the main.jsx bootstrap split.
export default function RouteLoading({ pathname }) {
  const label = pathname.startsWith('/portfolio')
    ? 'Opening your portfolio'
    : pathname.startsWith('/research') ? 'Opening research' : 'Opening page'
  return (
    <div className="route-loading" role="status" aria-live="polite">
      <span className="loading-mark" aria-hidden="true" />
      <strong>{label}…</strong>
      <span>Loading the latest saved view.</span>
    </div>
  )
}
