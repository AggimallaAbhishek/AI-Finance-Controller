import { useCallback, useEffect, useMemo, useState } from 'react'
import { getExceptions, getMatches, getRuns } from './api'
import StatsHeader from './StatsHeader'
import ExceptionList from './ExceptionList'
import MatchList from './MatchList'
import RunPicker from './RunPicker'
import ReconcileRunner from './ReconcileRunner'
import FilterBar, { applyFilters, DEFAULT_FILTERS } from './FilterBar'
import ChatPanel from './ChatPanel'

export default function App() {
  const [status, setStatus] = useState('loading') // loading | empty | error | ready
  const [errorMessage, setErrorMessage] = useState('')
  const [runs, setRuns] = useState([])
  const [run, setRun] = useState(null)
  const [matches, setMatches] = useState([])
  const [exceptions, setExceptions] = useState([])
  const [chatOpen, setChatOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('exceptions') // exceptions | matches
  const [filters, setFilters] = useState(DEFAULT_FILTERS)

  const refresh = useCallback(async (runId) => {
    const [{ matches }, { exceptions }] = await Promise.all([getMatches(runId), getExceptions(runId)])
    setMatches(matches)
    setExceptions(exceptions)
  }, [])

  const selectRun = useCallback(async (runId, runList) => {
    const selected = (runList || runs).find((r) => r.run_id === runId)
    if (selected) setRun(selected)
    await refresh(runId)
  }, [refresh, runs])

  useEffect(() => {
    async function load() {
      try {
        const { runs: runList } = await getRuns()
        if (runList.length === 0) {
          setStatus('empty')
          return
        }
        setRuns(runList)
        await selectRun(runList[0].run_id, runList)
        setStatus('ready')
      } catch (e) {
        setErrorMessage(e.message)
        setStatus('error')
      }
    }
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleReconcileComplete(newRunId) {
    const { runs: runList } = await getRuns()
    setRuns(runList)
    await selectRun(newRunId, runList)
  }

  // The run's stored stats are a snapshot from when the automated pipeline
  // ran — a human resolution afterward doesn't rewrite that snapshot (it's
  // an honest historical record of what the algorithm achieved on its
  // own). The dashboard shows *current* state instead, derived live from
  // matches/exceptions so a resolution is reflected immediately.
  const liveStats = useMemo(() => {
    if (!run) return null
    const totalSettlements = run.stats.total_settlements
    return {
      total_settlements: totalSettlements,
      matched: matches.length,
      rule_matched: matches.filter((m) => m.tier === 'rule').length,
      llm_matched: matches.filter((m) => m.tier === 'llm').length,
      human_resolved: matches.filter((m) => m.tier === 'human').length,
      settlement_exceptions: exceptions.filter((e) => e.settlement_ref).length,
      bank_exceptions: exceptions.filter((e) => e.bank_ref && !e.settlement_ref).length,
      match_rate: totalSettlements ? matches.length / totalSettlements : 0,
    }
  }, [run, matches, exceptions])

  if (status === 'loading') {
    return (
      <main className="state-screen">
        <p>Loading reconciliation data…</p>
      </main>
    )
  }

  if (status === 'empty') {
    return (
      <main className="state-screen">
        <h1>AI Finance Controller</h1>
        <p>No reconciliation run found yet.</p>
        <p className="muted">
          Run the pipeline first: <code>python3 reconcile.py --settlement ... --bank ...</code>
        </p>
      </main>
    )
  }

  if (status === 'error') {
    return (
      <main className="state-screen">
        <h1>AI Finance Controller</h1>
        <p className="error-text">Couldn’t load the dashboard: {errorMessage}</p>
        <p className="muted">Is the backend running at the configured API URL?</p>
      </main>
    )
  }

  return (
    <div className="dashboard">
      <StatsHeader run={run} stats={liveStats} />

      <div className="dashboard__body">
        <main className="dashboard__main">
          <ExceptionList
            exceptions={exceptions}
            runId={run.run_id}
            onResolved={() => refresh(run.run_id)}
          />
        </main>

        <div className={`dashboard__chat${chatOpen ? ' dashboard__chat--open' : ''}`}>
          <ChatPanel runId={run.run_id} />
        </div>
      </div>

      <button
        type="button"
        className="chat-toggle"
        onClick={() => setChatOpen((v) => !v)}
        aria-expanded={chatOpen}
      >
        {chatOpen ? 'Close chat' : 'Ask a question'}
      </button>
    </div>
  )
}
