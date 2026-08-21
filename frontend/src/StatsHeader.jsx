function formatTimestamp(iso) {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export default function StatsHeader({ run, stats }) {
  const { run_id: runId, timestamp } = run
  const matchPct = Math.round(stats.match_rate * 100)
  const totalExceptions = stats.settlement_exceptions + stats.bank_exceptions

  return (
    <header className="stats-header">
      <div className="stats-header__title">
        <h1>AI Finance Controller</h1>
        <p className="stats-header__meta">
          Run <code>{runId}</code> &middot; {formatTimestamp(timestamp)}
        </p>
      </div>

      <div className="stats-header__figures">
        <div className="stat-primary">
          <span className="stat-primary__value">{matchPct}%</span>
          <span className="stat-primary__label">match rate</span>
        </div>

        <dl className="stat-strip">
          <div className="stat-strip__item">
            <dt>Matched</dt>
            <dd>
              {stats.matched} / {stats.total_settlements}
            </dd>
          </div>
          <div className="stat-strip__item">
            <dt>By rule</dt>
            <dd>{stats.rule_matched}</dd>
          </div>
          <div className="stat-strip__item">
            <dt>By LLM</dt>
            <dd>{stats.llm_matched}</dd>
          </div>
          {stats.human_resolved > 0 && (
            <div className="stat-strip__item">
              <dt>By you</dt>
              <dd>{stats.human_resolved}</dd>
            </div>
          )}
          <div className="stat-strip__item stat-strip__item--warn">
            <dt>Exceptions</dt>
            <dd>{totalExceptions}</dd>
          </div>
        </dl>
      </div>
    </header>
  )
}
