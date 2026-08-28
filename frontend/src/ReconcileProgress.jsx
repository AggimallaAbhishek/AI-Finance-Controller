import { CheckCircleIcon, FileIcon, RobotIcon, RuleIcon } from './Icons'

const STAGE_LABELS = {
  starting: 'Starting…',
  rules: 'Applying match rules…',
  llm: 'Reviewing ambiguous cases with the LLM…',
  persisting: 'Saving results…',
}

const STEPS = [
  { stage: 'starting', title: 'Parsing Files & Validation', Icon: FileIcon, waiting: 'Waiting to start…' },
  { stage: 'rules', title: 'Applying Deterministic Rules', Icon: RuleIcon, waiting: 'Pending…' },
  { stage: 'llm', title: 'LLM Reasoning & Fuzzy Matching', Icon: RobotIcon, waiting: 'Pending…' },
  { stage: 'persisting', title: 'Finalizing Exceptions', Icon: CheckCircleIcon, waiting: 'Pending…' },
]
const STAGE_ORDER = STEPS.map((s) => s.stage)

function Stepper({ job }) {
  const currentIndex = job?.status === 'running' ? STAGE_ORDER.indexOf(job.stage) : -1

  return (
    <div className="reconcile-stepper">
      {STEPS.map((step, i) => {
        const state = currentIndex === -1 ? 'idle' : i < currentIndex ? 'done' : i === currentIndex ? 'active' : 'pending'
        let detail = step.waiting
        if (state === 'active') detail = STAGE_LABELS[step.stage] || detail
        else if (state === 'done') detail = 'Complete'
        return (
          <div key={step.stage} className={`reconcile-stepper__step reconcile-stepper__step--${state}`}>
            <span className="reconcile-stepper__icon">
              <step.Icon />
            </span>
            <div className="reconcile-stepper__body">
              <h4>{step.title}</h4>
              <p>{detail}</p>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// Shared progress/error display for ReconcileRunner and UploadRunner.
// variant="inline" (default) is a compact stage/bar for the Overview
// header; variant="stepper" is the vertical Engine Status timeline used
// on the Upload & Run page.
export default function ReconcileProgress({ job, variant = 'inline' }) {
  if (variant === 'stepper') {
    if (job?.status === 'error') {
      return (
        <div className="reconcile-stepper-panel">
          <h3>Engine Status</h3>
          <p className="error-text">Run failed: {job.error}</p>
        </div>
      )
    }
    return (
      <div className={`reconcile-stepper-panel${job ? '' : ' reconcile-stepper-panel--idle'}`}>
        <h3>Engine Status</h3>
        <Stepper job={job} />
      </div>
    )
  }

  if (job?.status === 'running') {
    return (
      <div className="reconcile-runner__progress" aria-live="polite">
        <span className="reconcile-runner__stage">{STAGE_LABELS[job.stage] || job.stage}</span>
        <div className="reconcile-runner__bar">
          <div
            className="reconcile-runner__bar-fill"
            style={{ transform: `scaleX(${job.total > 0 ? job.done / job.total : 0.08})` }}
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
