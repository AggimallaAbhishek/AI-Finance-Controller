import { useEffect, useState } from 'react'
import { getExceptions, getRuns } from './api'
import StatsHeader from './StatsHeader'
import ExceptionList from './ExceptionList'
import ChatPanel from './ChatPanel'

export default function App() {
  const [status, setStatus] = useState('loading') // loading | empty | error | ready
  const [errorMessage, setErrorMessage] = useState('')
  const [run, setRun] = useState(null)
  const [exceptions, setExceptions] = useState([])
  const [chatOpen, setChatOpen] = useState(false)

  useEffect(() => {
    async function load() {
      try {
        const { runs } = await getRuns()
        if (runs.length === 0) {
          setStatus('empty')
          return
        }
        const latest = runs[0]
        setRun(latest)
        const { exceptions } = await getExceptions(latest.run_id)
        setExceptions(exceptions)
        setStatus('ready')
      } catch (e) {
        setErrorMessage(e.message)
        setStatus('error')
      }
    }
    load()
  }, [])

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
      <StatsHeader run={run} />

      <div className="dashboard__body">
        <main className="dashboard__main">
          <ExceptionList exceptions={exceptions} runId={run.run_id} />
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
