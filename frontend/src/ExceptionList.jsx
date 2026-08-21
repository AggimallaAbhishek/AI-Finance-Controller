import { useState } from 'react'
import { getTrace } from './api'

function ExceptionRow({ exception, runId }) {
  const [expanded, setExpanded] = useState(false)
  const [trace, setTrace] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const side = exception.settlement_ref ? 'settlement' : 'bank'
  const recordId = exception.settlement_ref || exception.bank_ref

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
        <span className="exception-row__reason">{exception.reason}</span>
        <span className="exception-row__chevron" aria-hidden="true">
          {expanded ? '−' : '+'}
        </span>
      </button>

      {expanded && (
        <div className="exception-row__detail">
          {loading && <p className="muted">Loading source record…</p>}
          {error && <p className="error-text">Couldn't load detail: {error}</p>}
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
        </div>
      )}
    </li>
  )
}

export default function ExceptionList({ exceptions, runId }) {
  if (exceptions.length === 0) {
    return (
      <section className="exception-list" aria-label="Exceptions">
        <h2>Exceptions</h2>
        <p className="empty-state">No exceptions — every record matched.</p>
      </section>
    )
  }

  return (
    <section className="exception-list" aria-label="Exceptions">
      <h2>
        Exceptions <span className="muted">({exceptions.length})</span>
      </h2>
      <ul className="exception-list__items">
        {exceptions.map((e) => (
          <ExceptionRow key={e.id} exception={e} runId={runId} />
        ))}
      </ul>
    </section>
  )
}
