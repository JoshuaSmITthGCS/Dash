/** A hand-drawn banner ribbon as a section heading — DESIGN.md §9 layout rhythm. */
export default function SectionHeading({ children }) {
  return (
    <div
      data-chalk-ribbon="true"
      style={{
        display: 'inline-block',
        border: '2px solid var(--chalk-white)',
        borderRadius: '3px 10px 3px 10px / 6px 3px 8px 3px',
        padding: '4px 16px',
        fontFamily: 'var(--font-display)',
        fontSize: '20px',
        color: 'var(--chalk-white)',
        marginBottom: '8px',
      }}
    >
      {children}
    </div>
  )
}
