import { useEffect, useRef, useState } from 'react'
import { getTrace, resolveException } from './api'
import { downloadCsv } from './csv'
import { BankIcon, ReceiptIcon } from './Icons'

function formatAmount(amount) {
  if (amount === null || amount === undefined) return '—'
  return `₹${Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
}

export function recordIdOf(exception) {
  return exception.settlement_ref || exception.bank_ref
}

// Pure seams, extracted for testing — candidate sourcing/filtering for the
// resolve-to-match counterpart picker.
export function findCounterpartCandidates(allExceptions, exception) {
  const side = exception.settlement_ref ? 'settlement' : 'bank'
  return allExceptions.filter((e) =>
    e.id !== exception.id && (side === 'settlement' ? e.bank_ref && !e.settlement_ref : e.settlement_ref && !e.bank_ref)
  )
}

const MAX_VISIBLE_CANDIDATES = 8

export function filterCandidatesByQuery(candidates, query) {
  const q = query.trim().toLowerCase()
  const matches = q
    ? candidates.filter((c) => (c.settlement_ref || c.bank_ref || '').toLowerCase().includes(q))
    : candidates
  return matches.slice(0, MAX_VISIBLE_CANDIDATES)
}

function CheckIcon() {
  return (
    <svg className="resolve-confirmation__icon" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M3 8.5L6.5 12L13 4.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// Searchable picker for the resolve-to-match counterpart — sourced from the
// currently open exceptions on the opposite side, not free text, so a typo
// can't silently link the wrong record into the audit trail.
function CounterpartPicker({ candidates, value, onChange, disabled }) {
  const [open, setOpen] = useState(false)
  const [highlightIndex, setHighlightIndex] = useState(0)
  const containerRef = useRef(null)

  useEffect(() => {
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const visible = filterCandidatesByQuery(candidates, value)

  function select(candidate) {
    onChange(candidate.settlement_ref || candidate.bank_ref)
    setOpen(false)
  }

  function handleKeyDown(e) {
    if (!open || visible.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightIndex((i) => Math.min(i + 1, visible.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && visible[highlightIndex]) {
      e.preventDefault()
      select(visible[highlightIndex])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="counterpart-picker" ref={containerRef}>
      <input
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
          setOpen(true)
          setHighlightIndex(0)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        placeholder="Search open exceptions by ID…"
        required
        disabled={disabled}
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        autoComplete="off"
      />
      {open && visible.length > 0 && (
        // tabIndex=-1: Chrome makes an overflow:auto container an implicit
        // tab stop once its content overflows, even with no tabindex set —
        // without this, keyboard users hit an extra, silent stop here
        // between the input and the Note field.
        <ul className="counterpart-picker__list" role="listbox" tabIndex={-1}>
          {visible.map((c, i) => {
            const id = c.settlement_ref || c.bank_ref
            return (
              <li key={id} role="option" aria-selected={i === highlightIndex}>
                {/* tabIndex=-1: standard combobox pattern — options are
                    navigated via ArrowUp/Down + Enter on the input, never
                    via Tab. Without this, tabbing walked through up to 8
                    real buttons and skipped past the Note field entirely. */}
                <button
                  type="button"
                  tabIndex={-1}
                  className={`counterpart-picker__option${i === highlightIndex ? ' counterpart-picker__option--active' : ''}`}
                  onMouseEnter={() => setHighlightIndex(i)}
                  onClick={() => select(c)}
                >
                  <code>{id}</code>
                  <span className="muted">{formatAmount(c.amount)} · {c.date || '—'}</span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
      {open && value.trim() && visible.length === 0 && (
        <p className="counterpart-picker__empty muted">
          No open exceptions match "{value}" — you can still enter an ID directly.
        </p>
      )}
    </div>
  )
}

function ResolveActions({ recordId, candidates, runId, onResolved }) {
  const [mode, setMode] = useState(null) // null | 'no_match' | 'match'
  const [note, setNote] = useState('')
  const [counterpart, setCounterpart] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [justResolved, setJustResolved] = useState(null) // null | 'matched' | 'exception'

  async function submit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const result = await resolveException(
        recordId,
        { resolution: mode, note, matchedRecordId: mode === 'match' ? counterpart.trim() : undefined },
        runId,
      )
      setJustResolved(result.match_status)
      // Held briefly so the resolution reads as a real, closed action
      // instead of the row silently vanishing. Awaited deliberately: if
      // the resolve itself succeeds but this refresh fails, the error
      // must still surface here — otherwise the row is stuck showing
      // "Resolved" forever with no way to tell the user, since the row
      // would normally unmount once the parent's exceptions list updates.
      await new Promise((resolve) => setTimeout(resolve, 1100))
      await onResolved()
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
      setJustResolved(null)
    }
  }

  if (justResolved) {
    return (
      <div className="resolve-confirmation" role="status">
        <CheckIcon />
        <span>
          {justResolved === 'matched' ? 'Recorded as a human-resolved match.' : 'Recorded as a confirmed no-match.'}
        </span>
      </div>
    )
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
          <CounterpartPicker candidates={candidates} value={counterpart} onChange={setCounterpart} disabled={submitting} />
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
      <p className="resolve-form__permanence muted">
        This is recorded permanently in the audit trail and can’t be undone —
        double-check before submitting.
      </p>
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

// "Confirm no match" only — "Link to a record" inherently can't be bulked,
// since each exception needs a different counterpart. One shared note,
// but onConfirm still submits one resolveException() call per record, so
// the audit trail gets N distinct tier:human rows, never a merged action.
function BulkResolveBar({ selectedCount, onConfirmNoMatch, onClear }) {
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [progress, setProgress] = useState(null) // null | {done, total}
  const [result, setResult] = useState(null) // null | {succeeded, failed: [{id, error}]}

  async function submit(e) {
    e.preventDefault()
    setSubmitting(true)
    setResult(null)
    const outcome = await onConfirmNoMatch(note, (done, total) => setProgress({ done, total }))
    setSubmitting(false)
    setProgress(null)
    setResult(outcome)
    if (outcome.failed.length === 0) {
      setOpen(false)
      setNote('')
    }
  }

  return (
    <div className="bulk-bar" role="region" aria-label="Bulk actions">
      <div className="bulk-bar__summary">
        <span>{selectedCount} selected</span>
        {!open && !submitting && (
          <>
            <button type="button" onClick={() => setOpen(true)}>
              Confirm no match for {selectedCount}
            </button>
            <button type="button" className="bulk-bar__clear" onClick={onClear}>
              Clear selection
            </button>
          </>
        )}
      </div>

      {open && !submitting && !result && (
        <form className="resolve-form" onSubmit={submit}>
          <label className="resolve-form__field">
            Note (why? applies to all {selectedCount})
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. confirmed with finance during periodic no-match review"
              required
              rows={2}
            />
          </label>
          <p className="resolve-form__permanence muted">
            This records {selectedCount} separate, permanent audit entries — one per exception — and can’t be undone.
          </p>
          <div className="resolve-form__actions">
            <button type="button" onClick={() => setOpen(false)}>
              Cancel
            </button>
            <button type="submit" disabled={!note.trim()}>
              Confirm no match for {selectedCount}
            </button>
          </div>
        </form>
      )}

      {submitting && progress && (
        <p className="muted" aria-live="polite">
          Resolving {progress.done} of {progress.total}…
        </p>
      )}

      {result && (
        <p className={result.failed.length ? 'error-text' : 'muted'} role="status">
          {result.failed.length === 0
            ? `Resolved all ${result.succeeded}.`
            : `Resolved ${result.succeeded} of ${result.succeeded + result.failed.length} — ${result.failed.length} failed (${result.failed.map((f) => f.id).join(', ')}). Still-selected records can be retried.`}
        </p>
      )}
    </div>
  )
}

function ExceptionRow({ exception, allExceptions, runId, onResolved, selected, onToggleSelect }) {
  const [expanded, setExpanded] = useState(false)
  const [trace, setTrace] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const side = exception.settlement_ref ? 'settlement' : 'bank'
  const recordId = recordIdOf(exception)
  const reviewed = exception.tier === 'human'

  const candidates = findCounterpartCandidates(allExceptions, exception)

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
      <div className="exception-row__head">
        <input
          type="checkbox"
          className="exception-row__select"
          checked={selected}
          onChange={() => onToggleSelect(recordId)}
          aria-label={`Select ${recordId} for bulk action`}
        />
        <button
          type="button"
          className="exception-row__summary"
          aria-expanded={expanded}
          aria-label={`${side === 'settlement' ? 'Settlement' : 'Bank'} exception ${recordId}, details`}
          onClick={toggle}
        >
          <span className={`side-badge side-badge--${side}`}>
            {side === 'settlement' ? <ReceiptIcon /> : <BankIcon />}
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
      </div>

      {expanded && (
        <div className="exception-row__detail" aria-live="polite">
          {loading && <p className="muted">Loading source record…</p>}
          {error && <p className="error-text">Couldn't load detail: {error}</p>}
          <p className="exception-row__reason-full">{exception.reason}</p>
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
          <ResolveActions recordId={recordId} candidates={candidates} runId={runId} onResolved={onResolved} />
        </div>
      )}
    </li>
  )
}

export default function ExceptionList({ exceptions, allExceptions, allCount, runId, onResolved }) {
  const [selectedIds, setSelectedIds] = useState(new Set())

  // Only counts selections against currently-visible (filtered) rows —
  // a stale selection from before a filter change just stops mattering
  // rather than needing an explicit reset effect.
  const visibleSelectedIds = exceptions.map(recordIdOf).filter((id) => selectedIds.has(id))
  const allSelected = exceptions.length > 0 && visibleSelectedIds.length === exceptions.length

  // Escape clears the bulk selection — but not while focus is inside a
  // form field (e.g. typing the bulk note), where Escape shouldn't wipe
  // out a selection the user is actively acting on.
  useEffect(() => {
    if (visibleSelectedIds.length === 0) return
    function handleKeyDown(e) {
      if (e.key !== 'Escape') return
      const tag = document.activeElement?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      setSelectedIds(new Set())
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleSelectedIds.length])

  function toggleSelect(id) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleSelectAll() {
    setSelectedIds(allSelected ? new Set() : new Set(exceptions.map(recordIdOf)))
  }

  async function handleBulkConfirmNoMatch(note, onProgress) {
    const ids = [...visibleSelectedIds]
    const failed = []
    for (let i = 0; i < ids.length; i++) {
      try {
        await resolveException(ids[i], { resolution: 'no_match', note }, runId)
      } catch (err) {
        failed.push({ id: ids[i], error: err.message })
      }
      onProgress(i + 1, ids.length)
    }
    setSelectedIds(new Set(failed.map((f) => f.id)))
    await onResolved()
    return { succeeded: ids.length - failed.length, failed }
  }

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
        <div className="list-header__actions">
          {exceptions.length > 0 && (
            <label className="list-header__select-all">
              <input type="checkbox" checked={allSelected} onChange={toggleSelectAll} />
              Select all shown
            </label>
          )}
          <button type="button" className="export-button" onClick={exportCsv} disabled={exceptions.length === 0}>
            Export CSV
          </button>
        </div>
      </div>

      {visibleSelectedIds.length > 0 && (
        <BulkResolveBar
          selectedCount={visibleSelectedIds.length}
          onConfirmNoMatch={handleBulkConfirmNoMatch}
          onClear={() => setSelectedIds(new Set())}
        />
      )}

      {exceptions.length === 0 ? (
        <p className="empty-state">
          {allCount === 0 ? 'No exceptions — every record matched.' : 'No exceptions match these filters.'}
        </p>
      ) : (
        <ul className="exception-list__items">
          {exceptions.map((e) => (
            <ExceptionRow
              key={e.id}
              exception={e}
              allExceptions={allExceptions}
              runId={runId}
              onResolved={onResolved}
              selected={selectedIds.has(recordIdOf(e))}
              onToggleSelect={toggleSelect}
            />
          ))}
        </ul>
      )}
    </section>
  )
}
