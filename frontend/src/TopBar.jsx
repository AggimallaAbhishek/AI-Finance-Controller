import { PlusIcon } from './Icons'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'exceptions', label: 'Exceptions' },
  { id: 'matches', label: 'Matches' },
  { id: 'upload', label: 'Upload & Run' },
]

export default function TopBar({ activeTab, onSelectTab, runId }) {
  return (
    <header className="topbar">
      <div className="topbar__brand-group">
        <span className="topbar__brand">AI Finance Controller</span>
        {runId && <span className="topbar__run">Run {runId}</span>}
      </div>
      <nav className="topbar__tabs" role="tablist" aria-label="Sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={activeTab === t.id}
            className={`topbar__tab${activeTab === t.id ? ' topbar__tab--active' : ''}`}
            onClick={() => onSelectTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <button
        type="button"
        className="topbar__cta"
        aria-label="Start a new reconciliation"
        onClick={() => onSelectTab('upload')}
      >
        <PlusIcon />
        <span>New Reconciliation</span>
      </button>
    </header>
  )
}
