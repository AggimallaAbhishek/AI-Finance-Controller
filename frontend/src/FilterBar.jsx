import { useState } from 'react'
import { TIERS } from './tiers'

// Pure seam, extracted for testing — how many filter fields are currently
// narrowing the list, used both for the disclosure's default open/closed
// state and its "N active" badge.
export function countActiveFilters(filters) {
  let count = 0
  if (filters.amountMin) count++
  if (filters.amountMax) count++
  if (filters.dateFrom) count++
  if (filters.dateTo) count++
  if (filters.side !== 'all') count++
  if (filters.tiers.length > 0) count++
  return count
}

export const SORT_OPTIONS = [
  { value: '', label: 'Default order' },
  { value: 'amount-desc', label: 'Amount: high to low' },
  { value: 'amount-asc', label: 'Amount: low to high' },
  { value: 'date-desc', label: 'Date: newest first' },
  { value: 'date-asc', label: 'Date: oldest first' },
]

// Pure seam, extracted for testing. sort is one of SORT_OPTIONS' values
// ("field-direction", or "" for the original API order).
export function sortRows(rows, sort) {
  if (!sort) return rows
  const [field, direction] = sort.split('-')
  const multiplier = direction === 'desc' ? -1 : 1
  return [...rows].sort((a, b) => {
    const av = field === 'amount' ? Number(a.amount ?? 0) : a.date || ''
    const bv = field === 'amount' ? Number(b.amount ?? 0) : b.date || ''
    if (av < bv) return -1 * multiplier
    if (av > bv) return 1 * multiplier
    return 0
  })
}

export default function FilterBar({ filters, onChange, showSide, showTier, resultCount, sort, onSortChange }) {
  const activeCount = countActiveFilters(filters)
  // Starts open only when filters are already active (e.g. returning from
  // the Upload & Run tab with filters still set) — otherwise collapsed, so
  // a fresh view isn't showing 5 fields + 6 chips before the user asked
  // for them.
  const [expanded, setExpanded] = useState(activeCount > 0)

  function set(patch) {
    onChange({ ...filters, ...patch })
  }

  function toggleTier(tier) {
    const next = filters.tiers.includes(tier)
      ? filters.tiers.filter((t) => t !== tier)
      : [...filters.tiers, tier]
    set({ tiers: next })
  }

  return (
    <div className="filter-bar">
      <div className="filter-bar__summary">
        <button
          type="button"
          className="filter-bar__toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
        >
          Filters
          {activeCount > 0 && <span className="filter-bar__badge">{activeCount}</span>}
        </button>
        <span className="muted">{resultCount} shown</span>
        <label className="filter-bar__sort">
          <span className="sr-only">Sort</span>
          <select value={sort} onChange={(e) => onSortChange(e.target.value)}>
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.value ? `Sort: ${o.label}` : o.label}
              </option>
            ))}
          </select>
        </label>
        {activeCount > 0 && (
          <button
            type="button"
            className="filter-bar__clear"
            onClick={() => set({ amountMin: '', amountMax: '', dateFrom: '', dateTo: '', side: 'all', tiers: [] })}
          >
            Clear filters
          </button>
        )}
      </div>

      {expanded && (
        <>
          <div className="filter-bar__row">
            <label className="filter-bar__field">
              Amount min
              <input
                type="number"
                inputMode="decimal"
                placeholder="₹0"
                value={filters.amountMin}
                onChange={(e) => set({ amountMin: e.target.value })}
              />
            </label>
            <label className="filter-bar__field">
              Amount max
              <input
                type="number"
                inputMode="decimal"
                placeholder="Any"
                value={filters.amountMax}
                onChange={(e) => set({ amountMax: e.target.value })}
              />
            </label>
            <label className="filter-bar__field">
              Date from
              <input type="date" value={filters.dateFrom} onChange={(e) => set({ dateFrom: e.target.value })} />
            </label>
            <label className="filter-bar__field">
              Date to
              <input type="date" value={filters.dateTo} onChange={(e) => set({ dateTo: e.target.value })} />
            </label>
            {showSide && (
              <label className="filter-bar__field">
                Side
                <select value={filters.side} onChange={(e) => set({ side: e.target.value })}>
                  <option value="all">Both</option>
                  <option value="settlement">Settlement</option>
                  <option value="bank">Bank</option>
                </select>
              </label>
            )}
          </div>

          {showTier && (
            <div className="filter-bar__chips">
              {TIERS.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  className={`filter-chip${filters.tiers.includes(t.value) ? ' filter-chip--active' : ''}`}
                  aria-pressed={filters.tiers.includes(t.value)}
                  title={t.hint}
                  onClick={() => toggleTier(t.value)}
                >
                  <span className={`filter-chip__dot filter-chip__dot--${t.group}`} aria-hidden="true" />
                  {t.label}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export function applyFilters(rows, filters, { side, ignoreTiers } = {}) {
  return rows.filter((r) => {
    const amount = r.amount !== undefined && r.amount !== null ? Number(r.amount) : null
    if (filters.amountMin && (amount === null || amount < Number(filters.amountMin))) return false
    if (filters.amountMax && (amount === null || amount > Number(filters.amountMax))) return false
    if (filters.dateFrom && (!r.date || r.date < filters.dateFrom)) return false
    if (filters.dateTo && (!r.date || r.date > filters.dateTo)) return false
    if (filters.side !== 'all' && side && side(r) !== filters.side) return false
    if (!ignoreTiers && filters.tiers.length > 0 && !filters.tiers.includes(r.confidence)) return false
    return true
  })
}

export const DEFAULT_FILTERS = { amountMin: '', amountMax: '', dateFrom: '', dateTo: '', side: 'all', tiers: [] }
