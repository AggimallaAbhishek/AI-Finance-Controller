import { ExceptionsIcon, MatchesIcon, PlusIcon } from './Icons'

// Only real, working destinations — the Stitch mockups also show "Ledger
// View" / "Audit Trail" / "Reports" links, but this app has no such pages
// yet, and a nav item that goes nowhere is worse than not having it.
const NAV_ITEMS = [
  { id: 'exceptions', label: 'Discrepancies', Icon: ExceptionsIcon },
  { id: 'matches', label: 'Matches', Icon: MatchesIcon },
]

export default function Sidebar({ runId, activeTab, onSelectTab, open, onClose }) {
  return (
    <>
      {open && <div className="sidebar-scrim" onClick={onClose} aria-hidden="true" />}
      <nav className={`sidebar${open ? ' sidebar--open' : ''}`} aria-label="Main">
        <button type="button" className="sidebar__brand" onClick={() => { onSelectTab('overview'); onClose?.() }}>
          <div className="sidebar__eyebrow">AI Finance Controller</div>
          <div className="sidebar__title">Controller Dashboard</div>
          {runId && <div className="sidebar__batch">Run {runId}</div>}
        </button>

        <button
          type="button"
          className="sidebar__cta"
          onClick={() => {
            onSelectTab('upload')
            onClose?.()
          }}
        >
          <PlusIcon />
          New Reconciliation
        </button>

        <ul className="sidebar__nav">
          {NAV_ITEMS.map(({ id, label, Icon }) => (
            <li key={id}>
              <button
                type="button"
                className={`sidebar__link${activeTab === id ? ' sidebar__link--active' : ''}`}
                aria-current={activeTab === id ? 'page' : undefined}
                onClick={() => {
                  onSelectTab(id)
                  onClose?.()
                }}
              >
                <Icon />
                <span>{label}</span>
              </button>
            </li>
          ))}
        </ul>
      </nav>
    </>
  )
}
