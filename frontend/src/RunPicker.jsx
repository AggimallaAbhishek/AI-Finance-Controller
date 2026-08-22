function formatTimestamp(iso) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

// Pure seams, extracted for testing. run_id is a technical identifier
// (`20260822T085902-44b7ac`) — useful for cross-referencing against the
// API/audit trail, but not what a human scanning a dropdown of 15+ runs
// wants leading the label. Deprioritized to a short trailing reference
// instead of dropped, so it's still there when needed.
export function shortRunRef(runId) {
  const i = runId.lastIndexOf('-')
  return i === -1 ? runId : runId.slice(i + 1)
}

export function formatRunOption(run) {
  const pct = Math.round((run.stats.match_rate ?? 0) * 100)
  const total = run.stats.total_settlements ?? '?'
  return `${formatTimestamp(run.timestamp)} · ${pct}% · ${total} records · #${shortRunRef(run.run_id)}`
}

function TrendChart({ runs }) {
  // Oldest to newest, left to right — runs arrives newest-first from the API.
  const chronological = [...runs].reverse()
  const width = 240
  const height = 40
  const barWidth = width / chronological.length
  const maxBarWidth = 28

  return (
    <svg
      className="run-trend"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Match rate trend across runs, oldest to newest"
    >
      {chronological.map((r, i) => {
        const rate = r.stats.match_rate ?? 0
        const w = Math.min(barWidth, maxBarWidth) - 3
        const x = i * barWidth + (barWidth - w) / 2
        const h = Math.max(2, rate * (height - 4))
        return (
          <rect
            key={r.run_id}
            x={x}
            y={height - h}
            width={w}
            height={h}
            rx={1.5}
            className={i === chronological.length - 1 ? 'run-trend__bar run-trend__bar--latest' : 'run-trend__bar'}
          >
            <title>{`${r.run_id}: ${Math.round(rate * 100)}%`}</title>
          </rect>
        )
      })}
    </svg>
  )
}

export default function RunPicker({ runs, currentRunId, onSelect }) {
  return (
    <div className="run-picker">
      <label className="run-picker__select-wrap">
        <span className="sr-only">Select a reconciliation run</span>
        <select
          className="run-picker__select"
          value={currentRunId}
          onChange={(e) => onSelect(e.target.value)}
        >
          {runs.map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {formatRunOption(r)}
            </option>
          ))}
        </select>
      </label>
      {runs.length > 1 && <TrendChart runs={runs} />}
    </div>
  )
}
