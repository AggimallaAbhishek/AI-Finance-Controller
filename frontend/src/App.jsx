import { useCallback, useEffect, useMemo, useState } from 'react'
import { getExceptions, getMatches, getRuns } from './api'
import TopBar from './TopBar'
import Overview from './Overview'
import ExceptionList from './ExceptionList'
import MatchList from './MatchList'
import ReconcileRunner from './ReconcileRunner'
import UploadRunner from './UploadRunner'
import FilterBar, { applyFilters, DEFAULT_FILTERS, sortRows } from './FilterBar'
import ChatPanel from './ChatPanel'

export default function App() {
  const [status, setStatus] = useState('loading') // loading | empty | error | ready
  const [errorMessage, setErrorMessage] = useState('')
  const [runs, setRuns] = useState([])
  const [run, setRun] = useState(null)
  const [matches, setMatches] = useState([])
  const [exceptions, setExceptions] = useState([])
  const [chatOpen, setChatOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('overview') // overview | exceptions | matches | upload
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [sort, setSort] = useState('')

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

  async function handleUploadComplete(newRunId) {
    await handleReconcileComplete(newRunId)
    // Switch off the Upload & Run tab so the new run's results are
    // immediately visible instead of a completed, static progress bar.
    setActiveTab('overview')
  }

  // The run's stored stats are a snapshot from when the automated pipeline
  // ran — a human resolution afterward doesn't rewrite that snapshot (it's
  // an honest historical record of what the algorithm achieved on its
  // own). The dashboard shows *current* state instead, derived live from
  // matches/exceptions so a resolution is reflected immediately.
  const liveStats = useMemo(() => {
    if (!run) return null
    const totalSettlements = run.stats.total_settlements
    // settled_settlements is frozen at reconcile time, like total_settlements
    // above — a settlement's status never changes after the run, so there's
    // no live-vs-snapshot divergence to worry about here.
    const settledSettlements = run.stats.settled_settlements
    return {
      total_settlements: totalSettlements,
      settled_settlements: settledSettlements,
      matched: matches.length,
      rule_matched: matches.filter((m) => m.tier === 'rule').length,
      algo_matched: matches.filter((m) => m.tier === 'algo').length,
      llm_matched: matches.filter((m) => m.tier === 'llm').length,
      human_resolved: matches.filter((m) => m.tier === 'human').length,
      settlement_exceptions: exceptions.filter((e) => e.settlement_ref).length,
      bank_exceptions: exceptions.filter((e) => e.bank_ref && !e.settlement_ref).length,
      match_rate: totalSettlements ? matches.length / totalSettlements : 0,
      // Excludes reversed/pending settlements from the denominator — see
      // reconcile.py's stats dict for the full rationale.
      matchable_match_rate: settledSettlements ? matches.length / settledSettlements : 0,
    }
  }, [run, matches, exceptions])

  const filteredExceptions = useMemo(
    () => sortRows(applyFilters(exceptions, filters, {
      side: (e) => (e.settlement_ref ? 'settlement' : 'bank'),
      // Tier chips are only ever shown on the Matches tab (exceptions have
      // no confidence tier — reconcile.py never sets one on an exception
      // row), so a tier picked while on Matches must never suppress
      // exceptions once the user switches tabs.
      ignoreTiers: true,
    }), sort),
    [exceptions, filters, sort],
  )
  const filteredMatches = useMemo(
    () => sortRows(applyFilters(matches, filters), sort),
    [matches, filters, sort],
  )

  async function handleFirstRun(newRunId) {
    const { runs: runList } = await getRuns()
    setRuns(runList)
    await selectRun(newRunId, runList)
    setStatus('ready')
  }

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
        <ReconcileRunner onComplete={handleFirstRun} />
        <p className="muted">Or upload your own data:</p>
        <UploadRunner onComplete={handleFirstRun} />
        <p className="muted">
          Or from the command line: <code>python3 reconcile.py --settlement ... --bank ...</code>
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
    <div className="app-shell">
      <TopBar activeTab={activeTab} onSelectTab={setActiveTab} runId={run.run_id} />

      <div className="app-shell__body">
        <main className="app-shell__page">
          {activeTab === 'overview' && (
            <Overview
              run={run}
              stats={liveStats}
              runs={runs}
              onSelectRun={selectRun}
              onReconcileComplete={handleReconcileComplete}
              exceptions={exceptions}
              onViewExceptions={() => setActiveTab('exceptions')}
            />
          )}

          {activeTab === 'exceptions' && (
            <>
              <FilterBar
                filters={filters}
                onChange={setFilters}
                showSide
                resultCount={filteredExceptions.length}
                sort={sort}
                onSortChange={setSort}
              />
              <ExceptionList
                exceptions={filteredExceptions}
                allExceptions={exceptions}
                allCount={exceptions.length}
                runId={run.run_id}
                onResolved={() => refresh(run.run_id)}
              />
            </>
          )}

          {activeTab === 'matches' && (
            <>
              <div className="page-header">
                <h1>Reconciled Matches</h1>
                <p className="muted">Review verified pairings from run {run.run_id}.</p>
              </div>
              <FilterBar
                filters={filters}
                onChange={setFilters}
                showTier
                resultCount={filteredMatches.length}
                sort={sort}
                onSortChange={setSort}
              />
              <MatchList matches={filteredMatches} runId={run.run_id} />
            </>
          )}

          {activeTab === 'upload' && (
            <>
              <div className="page-header">
                <h1>Initiate Reconciliation</h1>
                <p className="muted">
                  Upload your settlement file and corresponding bank statement. The system applies deterministic
                  rules for exact matches, then LLM reasoning to resolve fuzzy discrepancies, before presenting
                  exceptions for manual review.
                </p>
              </div>
              <UploadRunner onComplete={handleUploadComplete} />
            </>
          )}
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
