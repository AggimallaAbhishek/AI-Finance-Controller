import { useState } from 'react'
import { getTrace, resolveException } from './api'
import { downloadCsv } from './csv'

function formatAmount(amount) {
  if (amount === null || amount === undefined) return '—'
  return `₹${Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
}

function ResolveActions({ recordId, runId, onResolved }) {
  const [mode, setMode] = useState(null) // null | 'no_match' | 'match'
  const [note, setNote] = useState('')
  const [counterpart, setCounterpart] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await resolveException(
        recordId,
        { resolution: mode, note, matchedRecordId: mode === 'match' ? counterpart.trim() : undefined },
        runId,
      )
      // Awaited deliberately: if the resolve itself succeeds but this
      // refresh fails, the error must still surface here — otherwise the
      // form is stuck showing "Resolving…" forever with no way to tell
      // the user, since the row would normally unmount once the parent's
      // exceptions list updates (every resolution creates a new row id,
      // so a successful refresh always remounts or removes this row).
      await onResolved()
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  if (mode === null) {
    return (
      <div className="resolve-actions">
        <button type="button" onClick={() => setMode('no_match')}>
          Confirm no match
        </button>
        <button type="button" onClick={() => setMode('match')}>
          Link to a record
        </button>
      </div>
    )
  }

  return (
    <form className="resolve-form" onSubmit={submit}>
      {mode === 'match' && (
        <label className="resolve-form__field">
          Counterpart record ID
          <input
            value={counterpart}
            onChange={(e) => setCounterpart(e.target.value)}
            placeholder="e.g. BTXN1234567890"
            required
            disabled={submitting}
          />
        </label>
      )}
      <label className="resolve-form__field">
        Note (why?)
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={mode === 'match' ? 'e.g. confirmed via reference lookup with ops' : 'e.g. confirmed with finance, settlement was voided'}
          required
          disabled={submitting}
          rows={2}
        />
      </label>
      {error && <p className="error-text">Couldn’t resolve: {error}</p>}
      <div className="resolve-form__actions">
        <button type="button" onClick={() => setMode(null)} disabled={submitting}>
          Cancel
        </button>
        <button
          type="submit"
          disabled={submitting || !note.trim() || (mode === 'match' && !counterpart.trim())}
        >
          {submitting ? 'Resolving…' : 'Submit'}
        </button>
      </div>
    </form>
  )
}

function ExceptionRow({ exception, runId, onResolved }) {
  const [expanded, setExpanded] = useState(false)
  const [trace, setTrace] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const side = exception.settlement_ref ? 'settlement' : 'bank'
  const recordId = exception.settlement_ref || exception.bank_ref
  const reviewed = exception.tier === 'human'

  async function toggle() {
    const next = !expanded
    setExpanded(next)
    if (next && !trace && !loading) {
      setLoading(true)
      setError(null)
      try {
        setTrace(await getTrace(recordId, runId))
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
  }

  const record = trace?.settlement_record || trace?.bank_record

  return (
    <li className="exception-row">
      <button
        type="button"
        className="exception-row__summary"
        aria-expanded={expanded}
        onClick={toggle}
      >
        <span className={`side-badge side-badge--${side}`}>
          {side === 'settlement' ? 'Settlement' : 'Bank'}
        </span>
        <code className="exception-row__id">{recordId}</code>
        <span className="exception-row__amount">{formatAmount(exception.amount)}</span>
        <span className="exception-row__reason">{exception.reason}</span>
        {reviewed && <span className="reviewed-badge">Reviewed</span>}
        <span className="exception-row__chevron" aria-hidden="true">
          {expanded ? '−' : '+'}
        </span>
      </button>

      {expanded && (
        <div className="exception-row__detail" aria-live="polite">
          {loading && <p className="muted">Loading source record…</p>}
          {error && <p className="error-text">Couldn’t load detail: {error}</p>}
          {record && (
            <dl className="detail-grid">
              <div>
                <dt>Reference ID</dt>
                <dd>{record.reference_id}</dd>
              </div>
              <div>
                <dt>Amount</dt>
                <dd>&#8377;{Number(record.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</dd>
              </div>
              <div>
                <dt>Date</dt>
                <dd>{record.date}</dd>
              </div>
              {side === 'settlement' ? (
                <div>
                  <dt>Status</dt>
                  <dd>{record.status}</dd>
                </div>
              ) : (
                <div>
                  <dt>Narration</dt>
                  <dd>{record.narration}</dd>
                </div>
              )}
            </dl>
          )}
          <ResolveActions recordId={recordId} runId={runId} onResolved={onResolved} />
        </div>
      )}
    </li>
  )
}

export default function ExceptionList({ exceptions, allCount, runId, onResolved }) {
  function exportCsv() {
    downloadCsv(`exceptions-${runId}.csv`, exceptions, [
      { label: 'side', value: (e) => (e.settlement_ref ? 'settlement' : 'bank') },
      { label: 'record_id', value: (e) => e.settlement_ref || e.bank_ref },
      { label: 'amount', value: (e) => e.amount },
      { label: 'date', value: (e) => e.date },
      { label: 'reason', value: (e) => e.reason },
      { label: 'reviewed', value: (e) => (e.tier === 'human' ? 'yes' : 'no') },
    ])
  }

  return (
    <section className="exception-list" aria-label="Exceptions">
      <div className="list-header">
        <h2>
          Exceptions <span className="muted">({exceptions.length})</span>
        </h2>
        <button type="button" className="export-button" onClick={exportCsv} disabled={exceptions.length === 0}>
          Export CSV
        </button>
      </div>
      {exceptions.length === 0 ? (
        <p className="empty-state">
          {allCount === 0 ? 'No exceptions — every record matched.' : 'No exceptions match these filters.'}
        </p>
      ) : (
        <ul className="exception-list__items">
          {exceptions.map((e) => (
            <ExceptionRow key={e.id} exception={e} runId={runId} onResolved={onResolved} />
          ))}
        </ul>
      )}
    </section>
  )
}
