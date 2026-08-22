import { useEffect, useRef, useState } from 'react'
import { getReconcileStatus } from './api'

const POLL_INTERVAL_MS = 500

// Shared by ReconcileRunner (default-data runs) and UploadRunner (custom
// CSVs) so the 500ms-poll/completion logic exists in exactly one place.
// poll/start are plain (unmemoized) functions, same as the original
// ReconcileRunner component before this was extracted — neither is used
// in a dependency array, so useCallback would add nothing here.
export function useReconcileJob(onComplete) {
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

  async function start(startFn) {
    setJob({ status: 'running', stage: 'starting', done: 0, total: 0 })
    try {
      const { job_id: jobId } = await startFn()
      poll(jobId)
    } catch (e) {
      setJob({ status: 'error', error: e.message })
    }
  }

  return { job, start, running: job?.status === 'running' }
}
