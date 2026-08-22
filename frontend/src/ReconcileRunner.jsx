import { useEffect, useRef, useState } from 'react'
import { getReconcileStatus, startReconcileAsync } from './api'

const STAGE_LABELS = {
  starting: 'Starting…',
  rules: 'Applying match rules…',
  llm: 'Reviewing ambiguous cases with the LLM…',
  persisting: 'Saving results…',
}

const POLL_INTERVAL_MS = 500

export default function ReconcileRunner({ onComplete }) {
  const [job, setJob] = useState(null) // null | {status, stage, done, total, result, error}
  const pollRef = useRef(null)

  useEffect(() => () => clearTimeout(pollRef.current), [])

  async function poll(jobId) {
    try {
      const status = await getReconcileStatus(jobId)
      setJob(status)
      if (status.status === 'running') {
        pollRef.current = setTimeout(() => poll(jobId), POLL_INTERVAL_MS)
      } else if (status.status === 'done') {
        onComplete(status.result.run_id)
      }
    } catch (e) {
      setJob({ status: 'error', error: e.message })
    }
  }

  async function start() {
    setJob({ status: 'running', stage: 'starting', done: 0, total: 0 })
    try {
      const { job_id: jobId } = await startReconcileAsync()
      poll(jobId)
    } catch (e) {
      setJob({ status: 'error', error: e.message })
    }
  }

  const running = job?.status === 'running'

  return (
    <div className="reconcile-runner">
      <button type="button" className="reconcile-runner__button" onClick={start} disabled={running}>
        {running ? 'Running…' : 'Run reconciliation'}
      </button>
      {running && (
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
      )}
      {job?.status === 'error' && <p className="error-text">Run failed: {job.error}</p>}
    </div>
  )
}
