import { describe, expect, test } from 'vitest'
import { formatRunOption, shortRunRef } from './RunPicker'

describe('shortRunRef', () => {
  test('returns the part after the last hyphen', () => {
    expect(shortRunRef('20260822T085902-44b7ac')).toBe('44b7ac')
  })

  test('falls back to the full id when there is no hyphen', () => {
    expect(shortRunRef('nohyphenid')).toBe('nohyphenid')
  })
})

describe('formatRunOption', () => {
  test('leads with date, match rate, and record count — not the technical run_id', () => {
    const run = {
      run_id: '20260822T085902-44b7ac',
      timestamp: '2026-08-22T08:59:02.000Z',
      stats: { match_rate: 0.9, total_settlements: 100 },
    }
    const label = formatRunOption(run)
    expect(label).toContain('90%')
    expect(label).toContain('100 records')
    expect(label).toContain('#44b7ac')
    // The run_id's leading date-time technical prefix must not appear —
    // only the human-formatted timestamp and the short trailing reference.
    expect(label).not.toContain('20260822T085902-44b7ac')
    expect(label.indexOf('90%')).toBeLessThan(label.indexOf('#44b7ac'))
  })

  test('rounds match rate to the nearest whole percent', () => {
    const run = { run_id: 'r-abc123', timestamp: '2026-08-22T08:59:02.000Z', stats: { match_rate: 0.666, total_settlements: 3 } }
    expect(formatRunOption(run)).toContain('67%')
  })

  test('handles a missing match_rate as 0%, not a crash', () => {
    const run = { run_id: 'r-abc123', timestamp: '2026-08-22T08:59:02.000Z', stats: { total_settlements: 3 } }
    expect(formatRunOption(run)).toContain('0%')
  })
})
