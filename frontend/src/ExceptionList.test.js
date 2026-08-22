import { describe, expect, test } from 'vitest'
import { filterCandidatesByQuery, findCounterpartCandidates } from './ExceptionList'

describe('findCounterpartCandidates', () => {
  const settlementExc = { id: 1, settlement_ref: 'S1', bank_ref: null }
  const bankExc = { id: 2, settlement_ref: null, bank_ref: 'B2' }
  const anotherSettlementExc = { id: 3, settlement_ref: 'S3', bank_ref: null }
  const anotherBankExc = { id: 4, settlement_ref: null, bank_ref: 'B4' }
  const resolvedMatch = { id: 5, settlement_ref: 'S5', bank_ref: 'B5' } // both sides set — already matched, not an open exception

  const all = [settlementExc, bankExc, anotherSettlementExc, anotherBankExc, resolvedMatch]

  test('for a settlement-side exception, returns only open bank-side exceptions', () => {
    const result = findCounterpartCandidates(all, settlementExc)
    expect(result.map((r) => r.id)).toEqual([2, 4])
  })

  test('for a bank-side exception, returns only open settlement-side exceptions', () => {
    const result = findCounterpartCandidates(all, bankExc)
    expect(result.map((r) => r.id)).toEqual([1, 3])
  })

  test('excludes the record itself even if it somehow matched its own side check', () => {
    const result = findCounterpartCandidates(all, settlementExc)
    expect(result.find((r) => r.id === settlementExc.id)).toBeUndefined()
  })

  test('never returns a row that already has both sides set (not an open exception)', () => {
    const result = findCounterpartCandidates(all, settlementExc)
    expect(result.find((r) => r.id === resolvedMatch.id)).toBeUndefined()
  })

  test('returns an empty list when no opposite-side exception is open', () => {
    const onlySettlements = [settlementExc, anotherSettlementExc]
    expect(findCounterpartCandidates(onlySettlements, settlementExc)).toEqual([])
  })
})

describe('filterCandidatesByQuery', () => {
  const candidates = [
    { settlement_ref: 'STL1001', amount: 100 },
    { settlement_ref: 'STL1002', amount: 200 },
    { bank_ref: 'BTXN9001', amount: 300 },
  ]

  test('with an empty query, returns candidates unfiltered (up to the visible cap)', () => {
    expect(filterCandidatesByQuery(candidates, '')).toEqual(candidates)
  })

  test('with a query, keeps only candidates whose ID contains it, case-insensitively', () => {
    const result = filterCandidatesByQuery(candidates, 'stl100')
    expect(result.map((c) => c.settlement_ref)).toEqual(['STL1001', 'STL1002'])
  })

  test('a query matching nothing returns an empty list', () => {
    expect(filterCandidatesByQuery(candidates, 'nope')).toEqual([])
  })

  test('caps the visible list at 8 even when unfiltered', () => {
    const many = Array.from({ length: 20 }, (_, i) => ({ settlement_ref: `STL${i}` }))
    expect(filterCandidatesByQuery(many, '')).toHaveLength(8)
  })

  test('whitespace-only query behaves like an empty query, not a literal-space match', () => {
    expect(filterCandidatesByQuery(candidates, '   ')).toEqual(candidates)
  })
})
