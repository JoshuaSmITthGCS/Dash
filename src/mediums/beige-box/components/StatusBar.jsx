/** The persistent bottom status bar — carries as-of + the selected item's reason, DESIGN.md §10. */
export default function StatusBar({ text = 'Ready.', asOf }) {
  return (
    <div data-beige-statusbar="true" role="status">
      <span>{text}</span>
      {asOf && <span>as of {asOf}</span>}
    </div>
  )
}
