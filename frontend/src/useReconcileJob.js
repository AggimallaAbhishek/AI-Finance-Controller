import { useCallback, useEffect, useRef, useState } from 'react'
import { getReconcileStatus } from './api'

const POLL_INTERVAL_MS = 500

// Shared by ReconcileRunner (default-data runs) and UploadRunner (custom
// CSVs) so the 500ms-poll/completion logic exists in exactly one place.
export function useReconcileJob(onComplete) {
  const [job, setJob] = useState(null) // null | {status, stage, done, total, result, error}
  const pollRef = useRef(null)

  useEffect(() => () => clearTimeout(pollRef.current), [])

  const poll = useCallback(async (jobId) => {
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
  }, [onComplete])

  const start = useCallback(async (startFn) => {
    setJob({ status: 'running', stage: 'starting', done: 0, total: 0 })
    try {
      const { job_id: jobId } = await startFn()
      poll(jobId)
    } catch (e) {
      setJob({ status: 'error', error: e.message })
    }
  }, [poll])

  return { job, start, running: job?.status === 'running' }
}
