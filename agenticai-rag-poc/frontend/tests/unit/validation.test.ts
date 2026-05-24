import { describe, it, expect } from 'vitest'

// Client-side input validation utilities
function isQueryTooLong(query: string, maxLen = 1000): boolean {
  return query.length > maxLen
}

function isQueryEmpty(query: string): boolean {
  return !query.trim()
}

describe('Client-side query validation', () => {
  it('detects empty query', () => {
    expect(isQueryEmpty('   ')).toBe(true)
    expect(isQueryEmpty('valid query')).toBe(false)
  })

  it('detects query exceeding max length', () => {
    expect(isQueryTooLong('a'.repeat(1001))).toBe(true)
    expect(isQueryTooLong('a'.repeat(1000))).toBe(false)
  })
})
