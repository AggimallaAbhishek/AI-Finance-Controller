import { describe, expect, test } from 'vitest'
import { toCsv } from './csv'

const columns = [
  { label: 'id', value: (r) => r.id },
  { label: 'note', value: (r) => r.note },
]

describe('toCsv', () => {
  test('joins header and rows with CRLF', () => {
    const csv = toCsv([{ id: 'A1', note: 'ok' }], columns)
    expect(csv).toBe('id,note\r\nA1,ok')
  })

  test('quotes a cell containing a comma', () => {
    const csv = toCsv([{ id: 'A1', note: 'a, b' }], columns)
    expect(csv).toBe('id,note\r\nA1,"a, b"')
  })

  test('quotes a cell containing a newline', () => {
    const csv = toCsv([{ id: 'A1', note: 'line1\nline2' }], columns)
    expect(csv).toBe('id,note\r\nA1,"line1\nline2"')
  })

  test('escapes an embedded quote by doubling it, then wraps the cell in quotes', () => {
    const csv = toCsv([{ id: 'A1', note: 'she said "hi"' }], columns)
    expect(csv).toBe('id,note\r\nA1,"she said ""hi"""')
  })

  test('renders null and undefined cell values as an empty cell, not the literal string', () => {
    const csv = toCsv([{ id: 'A1', note: null }, { id: 'A2', note: undefined }], columns)
    expect(csv).toBe('id,note\r\nA1,\r\nA2,')
  })

  test('leaves a plain cell unquoted', () => {
    const csv = toCsv([{ id: 'A1', note: 'plain text' }], columns)
    expect(csv).toBe('id,note\r\nA1,plain text')
  })

  test('produces just the header row for an empty row set', () => {
    const csv = toCsv([], columns)
    expect(csv).toBe('id,note')
  })
})
