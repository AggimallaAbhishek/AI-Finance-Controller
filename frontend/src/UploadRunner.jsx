import { useState } from 'react'
import { uploadAndReconcile } from './api'
import { useReconcileJob } from './useReconcileJob'
import ReconcileProgress from './ReconcileProgress'

export default function UploadRunner({ onComplete }) {
  const [settlementFile, setSettlementFile] = useState(null)
  const [bankFile, setBankFile] = useState(null)
  const { job, start, running } = useReconcileJob(onComplete)

  function run() {
    start(() => uploadAndReconcile(settlementFile, bankFile))
  }

  return (
    <div className="upload-runner">
      <div className="upload-runner__fields">
        <label className="upload-runner__field">
          Settlement CSV
          <input
            type="file"
            accept=".csv"
            disabled={running}
            onChange={(e) => setSettlementFile(e.target.files[0] || null)}
          />
        </label>
        <label className="upload-runner__field">
          Bank statement CSV
          <input
            type="file"
            accept=".csv"
            disabled={running}
            onChange={(e) => setBankFile(e.target.files[0] || null)}
          />
        </label>
        <button
          type="button"
          className="reconcile-runner__button"
          onClick={run}
          disabled={running || !settlementFile || !bankFile}
        >
          {running ? 'Running…' : 'Run reconciliation'}
        </button>
      </div>
      <ReconcileProgress job={job} />
    </div>
  )
}
