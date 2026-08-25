import { useRef, useState } from 'react'
import { MobileSheet } from '../../components/MobileSheet.jsx'
import Icon from '../../components/Icons.jsx'
import { parsePortfolioImport, planPortfolioImport } from '../../lib/portfolioImport.js'
import { referenceSyncDrift } from '../../lib/referencePortfolio.js'
import { money } from './format.js'

const shown = (value) => (value === null || value === '' ? '—' : value)

/**
 * Uploading a holdings file. The file is parsed and planned in the browser first and nothing
 * is written until the plan on screen is confirmed, because "replace" deletes holdings the
 * file omits -- that is not a thing to discover afterwards.
 */
export default function ImportHoldings({ positions, applyPortfolioImport, onDone }) {
  const inputRef = useRef(null)
  const [parsed, setParsed] = useState(null)
  const [fileName, setFileName] = useState('')
  const [mode, setMode] = useState('replace')
  const [saving, setSaving] = useState(false)

  const choose = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = '' // so re-picking the same file after a fix still fires onChange
    if (!file) return
    setFileName(file.name)
    setParsed(parsePortfolioImport(await file.text()))
    setMode('replace')
  }

  const close = () => {
    setParsed(null)
    setFileName('')
  }

  const apply = async () => {
    setSaving(true)
    const result = await applyPortfolioImport(parsed, mode)
    setSaving(false)
    close()
    onDone(result?.success
      ? `Imported ${fileName}: ${result.added} added · ${result.updated} updated · ${result.removed} removed.`
      : `Could not import ${fileName}: ${result?.error || 'Unknown error'}`)
  }

  const operations = parsed?.ok ? planPortfolioImport(positions, parsed, mode) : []
  const changes = operations
    .map((operation) => ({ operation, drift: referenceSyncDrift(operation) }))
    .filter(({ operation, drift }) => operation.kind !== 'update' || drift.length)
  const removals = operations.filter((operation) => operation.kind === 'remove').length

  return (
    <>
      <button className="secondary-button" onClick={() => inputRef.current?.click()}>
        <Icon name="upload" size={17} />Upload holdings file
      </button>
      <input ref={inputRef} type="file" accept="application/json,.json" onChange={choose}
        className="visually-hidden-input" aria-label="Holdings JSON file" />

      {parsed && (
        <MobileSheet open title={`Import ${fileName}`} onClose={close} className="holding-edit-sheet">
          <div className="import-preview">
            {!parsed.ok ? (
              <div className="unavailable-panel">
                <strong>This file cannot be imported</strong>
                <ul>{parsed.errors.map((error) => <li key={error}>{error}</li>)}</ul>
                <p>Nothing has been changed. Fix the file and pick it again.</p>
              </div>
            ) : (
              <>
                <div className="import-summary">
                  <div><span>Holdings in file</span><strong>{parsed.meta.count}</strong></div>
                  <div><span>Cost basis</span><strong>{money(parsed.meta.costBasisTotal)}</strong></div>
                  {parsed.meta.marketValue != null && (
                    <div><span>Stated value</span><strong>{money(parsed.meta.marketValue)}</strong></div>
                  )}
                </div>
                {parsed.meta.source && <p className="as-of-line">Source: {parsed.meta.source}</p>}

                <fieldset className="import-mode">
                  <legend>How should this file be applied?</legend>
                  <label>
                    <input type="radio" name="import-mode" value="replace" checked={mode === 'replace'}
                      onChange={() => setMode('replace')} />
                    <span><strong>Replace</strong> — the file is the whole portfolio. Holdings it
                      does not list are removed.</span>
                  </label>
                  <label>
                    <input type="radio" name="import-mode" value="merge" checked={mode === 'merge'}
                      onChange={() => setMode('merge')} />
                    <span><strong>Merge</strong> — add and update only. Nothing is removed.</span>
                  </label>
                </fieldset>

                {parsed.warnings?.map((warning) => (
                  <p key={warning} className="as-of-line">{warning}</p>
                ))}

                <div className="import-changes">
                  <strong>{changes.length ? `${changes.length} change${changes.length === 1 ? '' : 's'}` : 'No changes'}</strong>
                  {changes.length === 0 && <p>Your stored portfolio already matches this file.</p>}
                  {changes.length > 0 && (
                    <ul>
                      {changes.map(({ operation, drift }) => (
                        <li key={operation.id}>
                          <span className={`import-action import-action-${operation.kind}`}>{operation.kind}</span>
                          <span>{operation.record.ticker}</span>
                          <span>{operation.kind === 'add'
                            ? `${operation.record.shares} sh · ${money(operation.record.costBasisTotal)}`
                            : operation.kind === 'remove'
                              ? 'not listed in this file'
                              : drift.map((change) => `${change.field}: ${shown(change.from)} → ${shown(change.to)}`).join('; ')}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {removals > 0 && (
                  <p className="import-warning" role="alert">
                    Replacing deletes {removals} stored holding{removals === 1 ? '' : 's'}. Switch to
                    Merge to keep {removals === 1 ? 'it' : 'them'}.
                  </p>
                )}
              </>
            )}
          </div>
          <div className="holding-edit-sheet-actions">
            <button className="secondary-button" onClick={close} disabled={saving}>Cancel</button>
            <button className="primary-button" onClick={apply} disabled={!parsed.ok || saving || !changes.length}>
              {saving ? 'Saving…' : `Save ${changes.length} change${changes.length === 1 ? '' : 's'} to cloud`}
            </button>
          </div>
        </MobileSheet>
      )}
    </>
  )
}
