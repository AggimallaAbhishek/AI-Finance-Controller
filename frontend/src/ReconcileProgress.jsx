import { useEffect, useState } from 'react'
import { CheckCircleIcon, FileIcon, RobotIcon, RuleIcon } from './Icons'
import { formatDuration } from './duration'

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

// Returns the current time, ticking once a second while `active` so the
// elapsed clock keeps moving smoothly between the 500ms status polls (a
// poll only changes `job` when done/total/stage actually change, which can
// be many seconds apart during a slow LLM call). Date.now() is read inside
// the effect, not the render body, so the render itself stays pure.
function useClock(active) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [active])
  return now
}

// Coarse overall-progress fraction: how far through the ordered stage list
// we are, plus how far through the current stage's own done/total count.
// Stages carry no relative weight (a 10,000-row "rules" pass and a
// 5-record "llm" pass are wildly different durations), so this is a rough
// signal for a live bar/ETA, not a precise one — good enough to answer
// "is this almost done" without pretending to more accuracy than the
// underlying per-stage counts support.
function overallFraction(job) {
  const currentIndex = STAGE_ORDER.indexOf(job.stage)
  if (currentIndex === -1) return 0
  const stageFraction = job.total > 0 ? job.done / job.total : 0
  return (currentIndex + stageFraction) / STEPS.length
}

function TimeEstimate({ job }) {
  const now = useClock(job?.status === 'running')
  if (!job || job.status !== 'running' || !job.startedAt) return null

  const fraction = overallFraction(job)
  // Clamped to 0: `now` only refreshes once a second (see useClock), so
  // for up to that first second of a new run it can still hold a stale
  // value from before this run's startedAt — clamping avoids a flashed
  // negative elapsed time in that gap instead of forcing a synchronous
  // setState-in-effect just to close a sub-second window.
  const elapsedMs = Math.max(0, now - job.startedAt)
  const pct = Math.min(99, Math.round(fraction * 100))
  // Extrapolating from under ~8% complete swings wildly (a slow first LLM
  // call alone can eat most of a short run) — show "estimating…" instead
  // of a number that would visibly jump around every poll.
  const canEstimate = fraction > 0.08
  const etaMs = canEstimate ? (elapsedMs * (1 - fraction)) / fraction : null

  return (
    <div className="engine-time-estimate">
      <div className="reconcile-runner__bar reconcile-runner__bar--wide">
        <div
          className="reconcile-runner__bar-fill"
          style={{ transform: `scaleX(${Math.max(fraction, 0.03)})` }}
        />
      </div>
      <div className="engine-time-estimate__row muted">
        <span>{pct}% complete · {formatDuration(elapsedMs / 1000)} elapsed</span>
        <span>{canEstimate ? `~${formatDuration(etaMs / 1000)} remaining` : 'estimating time remaining…'}</span>
      </div>
    </div>
  )
}

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
        <TimeEstimate job={job} />
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
