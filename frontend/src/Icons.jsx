// Small hand-drawn icon set (20x20, stroke-based) — keeps the audit-grade
// visual language without pulling in the Material Symbols web font just
// for a dozen glyphs.
const common = { width: 16, height: 16, viewBox: '0 0 20 20', fill: 'none', 'aria-hidden': true }

export function OverviewIcon() {
  return (
    <svg {...common}>
      <rect x="3" y="3" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.6" />
      <rect x="11" y="3" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.6" />
      <rect x="3" y="11" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.6" />
      <rect x="11" y="11" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  )
}

export function ExceptionsIcon() {
  return (
    <svg {...common}>
      <path d="M10 3l7 12.5H3L10 3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M10 8.5v3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="10" cy="13.5" r="0.9" fill="currentColor" />
    </svg>
  )
}

export function MatchesIcon() {
  return (
    <svg {...common}>
      <path d="M2.5 10l3 3.5L9 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M9.5 10l3 3.5 5-6.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function UploadIcon() {
  return (
    <svg {...common}>
      <path d="M10 13V4M10 4L6.5 7.5M10 4l3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M3.5 14v1.5A1.5 1.5 0 005 17h10a1.5 1.5 0 001.5-1.5V14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

export function PlusIcon() {
  return (
    <svg {...common}>
      <path d="M10 4.5v11M4.5 10h11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

export function BankIcon() {
  return (
    <svg {...common}>
      <path d="M3 8l7-4.5L17 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 8.5v6M8 8.5v6M12 8.5v6M16 8.5v6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M3 16h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

export function ReceiptIcon() {
  return (
    <svg {...common}>
      <path d="M5 3h10v14l-2-1.3L11 17l-1.5-1.3L8 17l-1.5-1.3L5 17V3z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M7.5 7h5M7.5 10h5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  )
}

export function RobotIcon() {
  return (
    <svg {...common}>
      <rect x="4" y="7" width="12" height="9" rx="2.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M10 7V4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="10" cy="3" r="1.1" fill="currentColor" />
      <circle cx="7.5" cy="11.5" r="1" fill="currentColor" />
      <circle cx="12.5" cy="11.5" r="1" fill="currentColor" />
      <path d="M7.5 14.2c.7.5 4.3.5 5 0" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  )
}

export function PersonIcon() {
  return (
    <svg {...common}>
      <circle cx="10" cy="6.5" r="3" stroke="currentColor" strokeWidth="1.6" />
      <path d="M3.5 16.5c1.3-3.3 4-5 6.5-5s5.2 1.7 6.5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

export function SendIcon() {
  return (
    <svg {...common}>
      <path d="M17 3L3 9.5l6 2 2 6L17 3z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

export function ChevronIcon({ direction = 'down' }) {
  const rotation = { down: 0, up: 180, left: 90, right: -90 }[direction]
  return (
    <svg {...common} style={{ transform: `rotate(${rotation}deg)` }}>
      <path d="M5 7.5l5 5 5-5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function LinkIcon() {
  return (
    <svg {...common}>
      <path d="M8.5 11.5l3-3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M9.5 6.5l1-1a2.8 2.8 0 014 4l-1 1M10.5 13.5l-1 1a2.8 2.8 0 01-4-4l1-1" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function ReasoningIcon() {
  return (
    <svg {...common}>
      <path d="M10 3a5 5 0 00-3 9v2h6v-2a5 5 0 00-3-9z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M8 17h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

export function FileIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 3h8l5 5v13a1 1 0 01-1 1H6a1 1 0 01-1-1V4a1 1 0 011-1z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  )
}

export function CheckCircleIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 12.5l2.5 2.5L16 9.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function InfoIcon() {
  return (
    <svg {...common}>
      <circle cx="10" cy="10" r="7.25" stroke="currentColor" strokeWidth="1.5" />
      <path d="M10 9v5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="10" cy="6.3" r="0.9" fill="currentColor" />
    </svg>
  )
}

export function PlayIcon() {
  return (
    <svg {...common}>
      <path d="M5.5 3.5l11 6.5-11 6.5v-13z" fill="currentColor" />
    </svg>
  )
}

export function FilterIcon() {
  return (
    <svg {...common}>
      <path d="M3 4.5h14M6 10h8M8.5 15.5h3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

export function DownloadIcon() {
  return (
    <svg {...common}>
      <path d="M10 3v9.5M10 12.5l-3.5-3.5M10 12.5l3.5-3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M3.5 14v1.5A1.5 1.5 0 005 17h10a1.5 1.5 0 001.5-1.5V14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

export function MenuIcon() {
  return (
    <svg {...common}>
      <path d="M3 5.5h14M3 10h14M3 14.5h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

export function CloseIcon() {
  return (
    <svg {...common}>
      <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

// "git-merge"-style glyph, per the design system's provenance icon spec
// (rule = git-merge, llm = cpu, human = person).
export function RuleIcon() {
  return (
    <svg {...common}>
      <circle cx="6" cy="5" r="1.6" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="6" cy="15" r="1.6" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="14" cy="10" r="1.6" stroke="currentColor" strokeWidth="1.5" />
      <path d="M6 6.6V11a2.5 2.5 0 002.5 2.5H12.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M6 13.4V9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}
