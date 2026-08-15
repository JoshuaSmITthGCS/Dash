export default function AutoOverviewLine({ children, tone = 'neutral' }) {
  return <section className={`auto-overview-line tone-${tone}`} aria-label="Automatic ranking overview">
    <span>Auto overview</span>
    <p>{children}</p>
  </section>
}
