import { startReconcileAsync } from './api'
import { useReconcileJob } from './useReconcileJob'
import ReconcileProgress from './ReconcileProgress'

export default function ReconcileRunner({ onComplete, icon }) {
  const { job, start, running } = useReconcileJob(onComplete)

  return (
    <div className="reconcile-runner">
      <button
        type="button"
        className="reconcile-runner__button"
        onClick={() => start(startReconcileAsync)}
        disabled={running}
      >
        {icon}
        {running ? 'Running…' : 'Run reconciliation'}
      </button>
      <ReconcileProgress job={job} />
    </div>
  )
}
