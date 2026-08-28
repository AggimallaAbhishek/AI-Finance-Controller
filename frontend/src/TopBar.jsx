import { MenuIcon } from './Icons'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'exceptions', label: 'Exceptions' },
  { id: 'matches', label: 'Matches' },
  { id: 'upload', label: 'Upload & Run' },
]

export default function TopBar({ activeTab, onSelectTab, onOpenSidebar }) {
  return (
    <header className="topbar">
      <button type="button" className="topbar__menu" onClick={onOpenSidebar} aria-label="Open navigation">
        <MenuIcon />
      </button>
      <div className="topbar__brand">AI Finance Controller</div>
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
    </header>
  )
}
