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

      <p className="stats-header__summary">
        <span className="stats-header__rate">{matchPct}%</span> matched
        <span className="muted">
          {' '}
          ({stats.matched}/{stats.total_settlements})
        </span>
        <span className="stats-header__divider" aria-hidden="true">
          &middot;
        </span>
        <span className="stats-header__figure stats-header__figure--rule">{stats.rule_matched}</span> by rule
        <span className="stats-header__divider" aria-hidden="true">
          &middot;
        </span>
        <span className="stats-header__figure stats-header__figure--llm">{stats.llm_matched}</span> by LLM
        <span className="stats-header__divider" aria-hidden="true">
          &middot;
        </span>
        <span className="stats-header__figure stats-header__figure--human">{stats.human_resolved}</span> by you
        <span className="stats-header__divider" aria-hidden="true">
          &middot;
        </span>
        <span className="stats-header__figure stats-header__figure--warn">{totalExceptions}</span> open exception
        {totalExceptions === 1 ? '' : 's'}
      </p>
    </header>
  )
}
