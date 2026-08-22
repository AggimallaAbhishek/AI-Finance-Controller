const TIERS = [
  { value: 'exact', label: 'Exact' },
  { value: 'fuzzy-date', label: 'Fuzzy date' },
  { value: 'fuzzy-amount', label: 'Fuzzy amount' },
  { value: 'fuzzy-date-amount', label: 'Fuzzy date+amount' },
  { value: 'llm-reasoned', label: 'LLM-reasoned' },
  { value: 'human-resolved', label: 'Human-resolved' },
]

export default function FilterBar({ filters, onChange, showSide, showTier, resultCount }) {
  function set(patch) {
    onChange({ ...filters, ...patch })
  }

  function toggleTier(tier) {
    const next = filters.tiers.includes(tier)
      ? filters.tiers.filter((t) => t !== tier)
      : [...filters.tiers, tier]
    set({ tiers: next })
  }

  const isDefault =
    !filters.amountMin && !filters.amountMax && !filters.dateFrom && !filters.dateTo &&
    filters.side === 'all' && filters.tiers.length === 0

  return (
    <div className="filter-bar">
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
        <div className="filter-bar__count muted">
          {resultCount} shown
          {!isDefault && (
            <button
              type="button"
              className="filter-bar__clear"
              onClick={() => set({ amountMin: '', amountMax: '', dateFrom: '', dateTo: '', side: 'all', tiers: [] })}
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      {showTier && (
        <div className="filter-bar__chips">
          {TIERS.map((t) => (
            <button
              key={t.value}
              type="button"
              className={`filter-chip${filters.tiers.includes(t.value) ? ' filter-chip--active' : ''}`}
              aria-pressed={filters.tiers.includes(t.value)}
              onClick={() => toggleTier(t.value)}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export function applyFilters(rows, filters, { side } = {}) {
  return rows.filter((r) => {
    const amount = r.amount !== undefined && r.amount !== null ? Number(r.amount) : null
    if (filters.amountMin && (amount === null || amount < Number(filters.amountMin))) return false
    if (filters.amountMax && (amount === null || amount > Number(filters.amountMax))) return false
    if (filters.dateFrom && (!r.date || r.date < filters.dateFrom)) return false
    if (filters.dateTo && (!r.date || r.date > filters.dateTo)) return false
    if (filters.side !== 'all' && side && side(r) !== filters.side) return false
    if (filters.tiers.length > 0 && !filters.tiers.includes(r.confidence)) return false
    return true
  })
}

export const DEFAULT_FILTERS = { amountMin: '', amountMax: '', dateFrom: '', dateTo: '', side: 'all', tiers: [] }
