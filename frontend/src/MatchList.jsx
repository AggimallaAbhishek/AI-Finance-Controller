import { useState } from 'react'
import { getTrace } from './api'
import { downloadCsv } from './csv'
import { TIER_HINTS, TIER_LABELS } from './tiers'

function formatAmount(amount) {
  if (amount === null || amount === undefined) return '—'
  return `₹${Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
}

function MatchRow({ match, runId }) {
  const [expanded, setExpanded] = useState(false)
  const [trace, setTrace] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  async function toggle() {
    const next = !expanded
    setExpanded(next)
    if (next && !trace && !loading) {
      setLoading(true)
      setError(null)
      try {
        setTrace(await getTrace(match.settlement_ref, runId))
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
  }

  const settlementRecord = trace?.settlement_record
  const bankRecord = trace?.counterpart_bank_record

  return (
    <li className="exception-row">
      <button
        type="button"
        className="exception-row__summary"
        aria-expanded={expanded}
        aria-label={`${TIER_LABELS[match.confidence] || match.confidence} match, ${match.settlement_ref} to ${match.bank_ref}, details`}
        onClick={toggle}
      >
        <span className="tier-badge" title={TIER_HINTS[match.confidence]}>{TIER_LABELS[match.confidence] || match.confidence}</span>
        <code className="exception-row__id">{match.settlement_ref}</code>
        <span className="muted">&rarr;</span>
        <code className="exception-row__id">{match.bank_ref}</code>
        <span className="exception-row__amount">{formatAmount(match.amount)}</span>
        <span className="exception-row__reason">{match.reason}</span>
        <span className="exception-row__chevron" aria-hidden="true">{expanded ? '−' : '+'}</span>
      </button>

      {expanded && (
        <div className="exception-row__detail" aria-live="polite">
          {loading && <p className="muted">Loading source records…</p>}
          {error && <p className="error-text">Couldn't load detail: {error}</p>}
          <p className="exception-row__reason-full">{match.reason}</p>
          {settlementRecord && (
            <dl className="detail-grid">
              <div>
                <dt>Settlement ref</dt>
                <dd>{settlementRecord.reference_id}</dd>
              </div>
              <div>
                <dt>Settlement amount</dt>
                <dd>{formatAmount(settlementRecord.amount)}</dd>
              </div>
              <div>
                <dt>Settlement date</dt>
                <dd>{settlementRecord.date}</dd>
              </div>
              {bankRecord && (
                <>
                  <div>
                    <dt>Bank narration</dt>
                    <dd>{bankRecord.narration}</dd>
                  </div>
                  <div>
                    <dt>Bank amount</dt>
                    <dd>{formatAmount(bankRecord.amount)}</dd>
                  </div>
                  <div>
                    <dt>Bank date</dt>
                    <dd>{bankRecord.date}</dd>
                  </div>
                </>
              )}
            </dl>
          )}
        </div>
      )}
    </li>
  )
}

export default function MatchList({ matches, runId }) {
  function exportCsv() {
    downloadCsv(`matches-${runId}.csv`, matches, [
      { label: 'settlement_ref', value: (r) => r.settlement_ref },
      { label: 'bank_ref', value: (r) => r.bank_ref },
      { label: 'confidence', value: (r) => r.confidence },
      { label: 'amount', value: (r) => r.amount },
      { label: 'date', value: (r) => r.date },
      { label: 'reason', value: (r) => r.reason },
    ])
  }

  return (
    <section className="exception-list" aria-label="Matches">
      <div className="list-header">
        <h2>
          Matches <span className="muted">({matches.length})</span>
        </h2>
        <button type="button" className="export-button" onClick={exportCsv} disabled={matches.length === 0}>
          Export CSV
        </button>
      </div>
      {matches.length === 0 ? (
        <p className="empty-state">No matches to show for these filters.</p>
      ) : (
        <ul className="exception-list__items">
          {matches.map((m) => (
            <MatchRow key={m.id} match={m} runId={runId} />
          ))}
        </ul>
      )}
    </section>
  )
}
