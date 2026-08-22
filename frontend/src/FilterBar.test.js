import { describe, expect, test } from 'vitest'
import { applyFilters, countActiveFilters, DEFAULT_FILTERS, sortRows } from './FilterBar'

const bySide = (r) => (r.settlement_ref ? 'settlement' : 'bank')

const rows = [
  { id: 1, settlement_ref: 'S1', bank_ref: null, amount: 500, date: '2026-07-10', confidence: null },
  { id: 2, settlement_ref: null, bank_ref: 'B2', amount: 1200, date: '2026-07-15', confidence: null },
  { id: 3, settlement_ref: 'S3', bank_ref: 'B3', amount: 300, date: '2026-07-05', confidence: 'exact' },
  { id: 4, settlement_ref: 'S4', bank_ref: 'B4', amount: 900, date: '2026-07-20', confidence: 'llm-reasoned' },
]

describe('applyFilters', () => {
  test('with default filters, returns every row unchanged', () => {
    expect(applyFilters(rows, DEFAULT_FILTERS)).toEqual(rows)
  })

  test('amountMin excludes rows below the threshold', () => {
    const result = applyFilters(rows, { ...DEFAULT_FILTERS, amountMin: '600' })
    expect(result.map((r) => r.id)).toEqual([2, 4])
  })

  test('amountMax excludes rows above the threshold', () => {
    const result = applyFilters(rows, { ...DEFAULT_FILTERS, amountMax: '500' })
    expect(result.map((r) => r.id)).toEqual([1, 3])
  })

  test('amountMin of "0" (a truthy non-empty string) still applies the filter, not treated as unset', () => {
    // Regression guard: '0' must not be confused with '' (JS: '0' is truthy).
    const result = applyFilters(rows, { ...DEFAULT_FILTERS, amountMin: '0' })
    expect(result.map((r) => r.id)).toEqual([1, 2, 3, 4])
  })

  test('a row with no amount is excluded once an amount filter is active', () => {
    const noAmount = [{ id: 9, settlement_ref: 'S9', amount: null, date: '2026-07-10', confidence: null }]
    expect(applyFilters(noAmount, { ...DEFAULT_FILTERS, amountMin: '1' })).toEqual([])
  })

  test('dateFrom/dateTo filter by ISO string comparison, inclusive', () => {
    const result = applyFilters(rows, { ...DEFAULT_FILTERS, dateFrom: '2026-07-10', dateTo: '2026-07-15' })
    expect(result.map((r) => r.id)).toEqual([1, 2])
  })

  test('side filter only applies when a side accessor is supplied', () => {
    const withSide = applyFilters(rows, { ...DEFAULT_FILTERS, side: 'bank' }, { side: bySide })
    expect(withSide.map((r) => r.id)).toEqual([2])

    // Regression guard: this is the Phase 11 fix that keeps the side filter
    // from silently affecting rows (e.g. Matches) that never pass a side
    // accessor in the first place.
    const withoutSide = applyFilters(rows, { ...DEFAULT_FILTERS, side: 'bank' })
    expect(withoutSide).toEqual(rows)
  })

  test('tiers filter keeps only rows whose confidence is in the selected set', () => {
    const result = applyFilters(rows, { ...DEFAULT_FILTERS, tiers: ['exact'] })
    expect(result.map((r) => r.id)).toEqual([3])
  })

  test('ignoreTiers keeps rows with no confidence tier from being wiped out by an active tier filter', () => {
    // Regression guard: the exact bug fixed earlier — a tier chosen on the
    // Matches tab must not silently empty the Exceptions tab, since
    // exceptions always have confidence: null.
    const result = applyFilters(rows, { ...DEFAULT_FILTERS, tiers: ['llm-reasoned'] }, { ignoreTiers: true })
    expect(result).toEqual(rows)
  })

  test('combines multiple active filters with AND semantics', () => {
    const result = applyFilters(rows, { ...DEFAULT_FILTERS, amountMin: '400', tiers: ['llm-reasoned'] })
    expect(result.map((r) => r.id)).toEqual([4])
  })
})

describe('countActiveFilters', () => {
  test('is zero for default filters', () => {
    expect(countActiveFilters(DEFAULT_FILTERS)).toBe(0)
  })

  test('counts amountMin of "0" as active (a truthy non-empty string)', () => {
    expect(countActiveFilters({ ...DEFAULT_FILTERS, amountMin: '0' })).toBe(1)
  })

  test('counts each independently active field once', () => {
    expect(countActiveFilters({ ...DEFAULT_FILTERS, amountMin: '10', dateFrom: '2026-07-01' })).toBe(2)
  })

  test('side counts as active only when not "all"', () => {
    expect(countActiveFilters({ ...DEFAULT_FILTERS, side: 'all' })).toBe(0)
    expect(countActiveFilters({ ...DEFAULT_FILTERS, side: 'bank' })).toBe(1)
  })

  test('a non-empty tiers array counts as one active field, not one per tier', () => {
    expect(countActiveFilters({ ...DEFAULT_FILTERS, tiers: ['exact', 'llm-reasoned'] })).toBe(1)
  })
})

describe('sortRows', () => {
  const sortable = [
    { id: 1, amount: 500, date: '2026-07-10' },
    { id: 2, amount: 1200, date: '2026-07-15' },
    { id: 3, amount: 300, date: '2026-07-05' },
  ]

  test('an empty sort value returns rows in their original order, unchanged', () => {
    expect(sortRows(sortable, '')).toEqual(sortable)
  })

  test('does not mutate the input array', () => {
    const copy = [...sortable]
    sortRows(sortable, 'amount-asc')
    expect(sortable).toEqual(copy)
  })

  test('amount-asc sorts lowest first', () => {
    expect(sortRows(sortable, 'amount-asc').map((r) => r.id)).toEqual([3, 1, 2])
  })

  test('amount-desc sorts highest first', () => {
    expect(sortRows(sortable, 'amount-desc').map((r) => r.id)).toEqual([2, 1, 3])
  })

  test('date-asc sorts oldest first', () => {
    expect(sortRows(sortable, 'date-asc').map((r) => r.id)).toEqual([3, 1, 2])
  })

  test('date-desc sorts newest first', () => {
    expect(sortRows(sortable, 'date-desc').map((r) => r.id)).toEqual([2, 1, 3])
  })

  test('a row with a missing amount sorts as if it were 0, not thrown or dropped', () => {
    const withMissing = [...sortable, { id: 4, amount: null, date: '2026-07-01' }]
    const result = sortRows(withMissing, 'amount-asc')
    expect(result.map((r) => r.id)).toEqual([4, 3, 1, 2])
  })
})
