import { DownloadIcon, FilterIcon, PlayIcon } from './Icons'
import RunPicker from './RunPicker'
import ReconcileRunner from './ReconcileRunner'

function formatTimestamp(iso) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function formatAmount(amount) {
  if (amount === null || amount === undefined) return '—'
  return `₹${Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
}

function recordIdOf(exception) {
  return exception.settlement_ref || exception.bank_ref
}

function counterpartOf(exception) {
  return exception.settlement_ref ? exception.bank_ref : exception.settlement_ref
}

export default function Overview({
  run,
  stats,
  runs,
  onSelectRun,
  onReconcileComplete,
  exceptions,
  onViewExceptions,
}) {
  const matchPct = Math.round(stats.match_rate * 100)
  const total = stats.total_settlements || 1
  const totalExceptions = stats.settlement_exceptions + stats.bank_exceptions
  // algo-reconstructed matches share the rule segment/color: both are "the
  // deterministic engine decided this, no LLM call," differentiated by
  // label (see tiers.js), not by a dedicated hue in the provenance palette.
  const ruleMatched = stats.rule_matched + (stats.algo_matched || 0)
  const rulePct = (ruleMatched / total) * 100
  const llmPct = (stats.llm_matched / total) * 100
  const humanPct = (stats.human_resolved / total) * 100
  const openPct = (totalExceptions / total) * 100
  const hasNonSettled = stats.settled_settlements != null && stats.settled_settlements < stats.total_settlements
  const matchablePct = stats.settled_settlements ? Math.round((stats.matched / stats.settled_settlements) * 100) : null

  const preview = exceptions.slice(0, 5)

  return (
    <div className="overview">
      <section className="overview-card">
        <div className="overview-card__head">
          <div>
            <div className="overview-card__title-row">
              <h1>Reconciliation Overview</h1>
              <code className="overview-card__run-id">{run.run_id}</code>
            </div>
            <p className="overview-card__meta">Run completed {formatTimestamp(run.timestamp)}</p>
          </div>
          <div className="overview-card__actions">
            <RunPicker runs={runs} currentRunId={run.run_id} onSelect={onSelectRun} />
            <ReconcileRunner onComplete={onReconcileComplete} icon={<PlayIcon />} />
          </div>
        </div>

        <div className="overview-card__stats">
          <div className="overview-card__rate-row">
            <span className="overview-card__rate">{matchPct}%</span>
            <span className="muted">
              matched ({stats.matched}/{stats.total_settlements})
            </span>
          </div>
          <div className="overview-bar" role="img" aria-label={`${stats.rule_matched} matched by rule, ${stats.llm_matched} by LLM, ${stats.human_resolved} by you, ${totalExceptions} open exceptions`}>
            <div className="overview-bar__seg overview-bar__seg--rule" style={{ width: `${rulePct}%` }} />
            <div className="overview-bar__seg overview-bar__seg--llm" style={{ width: `${llmPct}%` }} />
            <div className="overview-bar__seg overview-bar__seg--human" style={{ width: `${humanPct}%` }} />
            <div className="overview-bar__seg overview-bar__seg--open" style={{ width: `${openPct}%` }} />
          </div>
          <div className="overview-legend">
            <span className="overview-legend__item">
              <span className="overview-legend__dot overview-legend__dot--rule" />
              <strong>{stats.rule_matched}</strong>&nbsp;by rule
            </span>
            <span className="overview-legend__item">
              <span className="overview-legend__dot overview-legend__dot--llm" />
              <strong>{stats.llm_matched}</strong>&nbsp;by LLM
            </span>
            <span className="overview-legend__item">
              <span className="overview-legend__dot overview-legend__dot--human" />
              <strong>{stats.human_resolved}</strong>&nbsp;by you
            </span>
            <span className="overview-legend__item overview-legend__item--open">
              <span className="overview-legend__dot overview-legend__dot--open" />
              {totalExceptions} open exception{totalExceptions === 1 ? '' : 's'}
            </span>
          </div>
        </div>
      </section>

      <section className="overview-preview">
        <div className="overview-preview__head">
          <h2>Top Exceptions</h2>
          <div className="overview-preview__actions">
            <button type="button" onClick={onViewExceptions}>
              <FilterIcon /> Filter
            </button>
            <button type="button" onClick={onViewExceptions}>
              <DownloadIcon /> Export
            </button>
          </div>
        </div>

        {preview.length === 0 ? (
          <p className="empty-state">No open exceptions — every record matched.</p>
        ) : (
          <div className="overview-table-wrap">
            <table className="overview-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Internal Ref</th>
                  <th>External Ref</th>
                  <th className="overview-table__amount">Amount</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {preview.map((e) => {
                  const id = recordIdOf(e)
                  const isSettlement = Boolean(e.settlement_ref)
                  const counterpart = counterpartOf(e)
                  return (
                    <tr key={e.id} onClick={onViewExceptions} tabIndex={0} role="button">
                      <td>
                        <code>{id}</code>
                      </td>
                      <td className={isSettlement ? '' : 'overview-table__muted'}>
                        {isSettlement ? id : 'Not found'}
                      </td>
                      <td className={isSettlement ? 'overview-table__muted' : ''}>
                        {isSettlement ? counterpart || 'Not found' : id}
                      </td>
                      <td className="overview-table__amount">
                        <code>{formatAmount(e.amount)}</code>
                      </td>
                      <td>
                        <div className="overview-table__reason">
                          {e.tier === 'human' && <span className="reviewed-badge">Reviewed</span>}
                          <span className="overview-table__reason-text">{e.reason}</span>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {exceptions.length > preview.length && (
          <button type="button" className="overview-preview__view-all" onClick={onViewExceptions}>
            View all {exceptions.length} exceptions →
          </button>
        )}
      </section>
    </div>
  )
}
