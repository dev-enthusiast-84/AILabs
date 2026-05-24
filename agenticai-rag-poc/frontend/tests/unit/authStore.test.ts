/**
 * Unit tests for authStore — focuses on isAuthenticated() expiry logic
 * introduced in Fix S2 (token expiry check).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from '@/store/authStore'

/** Build a minimal unsigned JWT with the given payload. */
function makeToken(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.sig`
}

beforeEach(() => {
  // Reset auth state between tests so they don't bleed into each other.
  useAuthStore.getState().clearAuth()
})

describe('authStore — isAuthenticated()', () => {
  it('returns false when no token is stored', () => {
    expect(useAuthStore.getState().isAuthenticated()).toBe(false)
  })

  it('returns false for an expired token (exp in the past)', () => {
    const expiredToken = makeToken({ sub: 'admin', exp: 1 }) // Unix epoch 1970
    useAuthStore.getState().setAuth(expiredToken, 'admin')
    expect(useAuthStore.getState().isAuthenticated()).toBe(false)
  })

  it('returns true for a valid token (exp well in the future)', () => {
    const validToken = makeToken({ sub: 'admin', exp: Math.floor(Date.now() / 1000) + 3600 })
    useAuthStore.getState().setAuth(validToken, 'admin')
    expect(useAuthStore.getState().isAuthenticated()).toBe(true)
  })

  it('returns true when the token has no exp claim (non-JWT / test tokens treated as valid)', () => {
    const noExpToken = makeToken({ sub: 'admin' }) // no exp field
    useAuthStore.getState().setAuth(noExpToken, 'admin')
    expect(useAuthStore.getState().isAuthenticated()).toBe(true)
  })

  it('returns false after clearAuth() regardless of previous state', () => {
    const validToken = makeToken({ sub: 'admin', exp: Math.floor(Date.now() / 1000) + 3600 })
    useAuthStore.getState().setAuth(validToken, 'admin')
    expect(useAuthStore.getState().isAuthenticated()).toBe(true)
    useAuthStore.getState().clearAuth()
    expect(useAuthStore.getState().isAuthenticated()).toBe(false)
  })

  it('returns true for a guest token that has not yet expired', () => {
    const guestToken = makeToken({ sub: 'guest', exp: Math.floor(Date.now() / 1000) + 900 })
    useAuthStore.getState().setGuest(guestToken)
    expect(useAuthStore.getState().isAuthenticated()).toBe(true)
  })

  it('returns false for a guest token that has already expired', () => {
    const expiredGuestToken = makeToken({ sub: 'guest', exp: Math.floor(Date.now() / 1000) - 1 })
    useAuthStore.getState().setGuest(expiredGuestToken)
    expect(useAuthStore.getState().isAuthenticated()).toBe(false)
  })
})
