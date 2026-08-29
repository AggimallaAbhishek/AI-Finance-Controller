import { memo, useState } from 'react'
import { getTrace } from './api'
import { downloadCsv } from './csv'
import { TIER_GROUPS, TIER_HINTS, TIER_LABELS } from './tiers'
import { BankIcon, LinkIcon, PersonIcon, ReceiptIcon, RobotIcon, RuleIcon } from './Icons'

const TIER_ICONS = { rule: RuleIcon, llm: RobotIcon, human: PersonIcon }

// A batch can carry tens of thousands of matches (see data/batch_50000) —
// rendering all of them at once as DOM nodes locks up the tab. Page in
// fixed chunks instead, same "preview, then more on demand" shape as
// Overview's top-5-exceptions-then-view-all, applied to a list long
// enough to need repeating rather than a one-time reveal.
const PAGE_SIZE = 100

function formatAmount(amount) {
  if (amount === null || amount === undefined) return '—'
  return `₹${Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
}

// Connector badges between the two evidence cards — a plain, computed
// fact about the pairing (amounts equal? dates equal?), not a repeat of
// the model's own confidence claim.
function ConnectorBadges({ settlementRecord, bankRecord }) {
  const sameAmount = Number(settlementRecord.amount) === Number(bankRecord.amount)
  const sameDate = settlementRecord.date === bankRecord.date
  return (
    <div className="evidence-connector">
      <LinkIcon />
      <span className={`evidence-connector__badge${sameAmount ? ' evidence-connector__badge--match' : ''}`}>
        {sameAmount ? 'Amount match' : 'Amount differs'}
      </span>
      <span className={`evidence-connector__badge${sameDate ? ' evidence-connector__badge--match' : ''}`}>
        {sameDate ? 'Same date' : 'Date differs'}
      </span>
    </div>
  )
}

const MatchRow = memo(function MatchRow({ match, runId }) {
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
  const tierGroup = TIER_GROUPS[match.confidence]
  const TierIcon = TIER_ICONS[tierGroup]

  return (
    <li className="exception-row">
      <div className="exception-row__head">
        <button
          type="button"
          className="exception-row__summary"
          aria-expanded={expanded}
          aria-label={`${TIER_LABELS[match.confidence] || match.confidence} match, ${match.settlement_ref} to ${match.bank_ref}, details`}
          onClick={toggle}
        >
          <span
            className={`tier-badge${tierGroup ? ` tier-badge--${tierGroup}` : ''}`}
            title={TIER_HINTS[match.confidence]}
          >
            {TierIcon && <TierIcon />}
            {TIER_LABELS[match.confidence] || match.confidence}
          </span>
          <code className="exception-row__id">{match.settlement_ref}</code>
          <span className="muted">&rarr;</span>
          <code className="exception-row__id">{match.bank_ref}</code>
          <span className="exception-row__amount">{formatAmount(match.amount)}</span>
          <span className="exception-row__reason">{match.reason}</span>
          <span className="exception-row__chevron" aria-hidden="true">{expanded ? '−' : '+'}</span>
        </button>
      </div>

      {expanded && (
        <div className="exception-row__detail" aria-live="polite">
          {loading && <p className="muted">Loading source records…</p>}
          {error && <p className="error-text">Couldn't load detail: {error}</p>}
          {settlementRecord ? (
            <div className="evidence-grid">
              <div className="evidence-card">
                <h4 className="evidence-card__title">
                  <ReceiptIcon />
                  Ledger Details (Side A)
                </h4>
                <dl className="detail-grid">
                  <div>
                    <dt>Ref</dt>
                    <dd>{settlementRecord.reference_id}</dd>
                  </div>
                  <div>
                    <dt>Amount</dt>
                    <dd>{formatAmount(settlementRecord.amount)}</dd>
                  </div>
                  <div>
                    <dt>Date</dt>
                    <dd>{settlementRecord.date}</dd>
                  </div>
                </dl>
              </div>

              {bankRecord && <ConnectorBadges settlementRecord={settlementRecord} bankRecord={bankRecord} />}

              {bankRecord && (
                <div className="evidence-card">
                  <h4 className="evidence-card__title">
                    <BankIcon />
                    Bank Details (Side B)
                  </h4>
                  <dl className="detail-grid">
                    <div>
                      <dt>Narration</dt>
                      <dd>{bankRecord.narration}</dd>
                    </div>
                    <div>
                      <dt>Amount</dt>
                      <dd>{formatAmount(bankRecord.amount)}</dd>
                    </div>
                    <div>
                      <dt>Date</dt>
                      <dd>{bankRecord.date}</dd>
                    </div>
                  </dl>
                </div>
              )}

              <div
                className={`evidence-card evidence-card--reasoning evidence-card--${tierGroup || 'rule'}`}
                style={{ gridColumn: '1 / -1' }}
              >
                <h4 className="evidence-card__title">
                  {TierIcon && <TierIcon />}
                  {TIER_LABELS[match.confidence] || match.confidence} Reasoning
                </h4>
                <p>{match.reason}</p>
              </div>
            </div>
          ) : (
            <p className="exception-row__reason-full">{match.reason}</p>
          )}
        </div>
      )}
    </li>
  )
})

export default function MatchList({ matches, runId }) {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  // Adjust state during render (React's documented pattern for "reset when
  // a prop changes"), not an effect: an effect would commit the old page
  // size first, paint up to PAGE_SIZE stale rows, then reset on the next
  // tick — a visible flash, and an extra render pass for no benefit. A new
  // `matches` array means the filters changed (App.jsx's useMemo only
  // produces one when its inputs actually change).
  const [prevMatches, setPrevMatches] = useState(matches)
  if (matches !== prevMatches) {
    setPrevMatches(matches)
    setVisibleCount(PAGE_SIZE)
  }

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

  const visible = matches.slice(0, visibleCount)
  const remaining = matches.length - visible.length

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
        <>
          <ul className="exception-list__items">
            {visible.map((m) => (
              <MatchRow key={m.id} match={m} runId={runId} />
            ))}
          </ul>
          {remaining > 0 && (
            <button
              type="button"
              className="list-load-more"
              onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
            >
              Load {Math.min(PAGE_SIZE, remaining)} more ({remaining} remaining)
            </button>
          )}
        </>
      )}
    </section>
  )
}
