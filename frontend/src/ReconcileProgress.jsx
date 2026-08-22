const STAGE_LABELS = {
  starting: 'Starting…',
  rules: 'Applying match rules…',
  llm: 'Reviewing ambiguous cases with the LLM…',
  persisting: 'Saving results…',
}

// Shared progress/error display for ReconcileRunner and UploadRunner.
export default function ReconcileProgress({ job }) {
  if (job?.status === 'running') {
    return (
      <div className="reconcile-runner__progress" aria-live="polite">
        <span className="reconcile-runner__stage">{STAGE_LABELS[job.stage] || job.stage}</span>
        <div className="reconcile-runner__bar">
          <div
            className="reconcile-runner__bar-fill"
            style={{ width: job.total > 0 ? `${Math.round((job.done / job.total) * 100)}%` : '8%' }}
          />
        </div>
        {job.total > 0 && (
          <span className="muted reconcile-runner__count">{job.done} / {job.total}</span>
        )}
      </div>
    )
  }
  if (job?.status === 'error') {
    return <p className="error-text">Run failed: {job.error}</p>
  }
  return null
}
