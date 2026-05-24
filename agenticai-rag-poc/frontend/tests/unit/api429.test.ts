/**
 * Unit tests for the 429 rate-limit interceptor in api.ts (Fix D8).
 * Verifies that a 429 response:
 *   - Produces an Error with "Rate limit" in the message
 *   - Does NOT call clearAuth (i.e. does not log the user out)
 *   - Does NOT redirect to /login
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import axios from 'axios'

// jsdom's window.location is a non-configurable accessor — cannot be replaced
// via Object.defineProperty or vi.stubGlobal.  We use the real window.location
// directly; jsdom records href assignments synchronously (same-origin navigation).

const clearAuthMock = vi.fn()

// Mock axios — returns a controllable instance.
vi.mock('axios', async (importOriginal) => {
  const actual = await importOriginal<typeof import('axios')>()
  const instance = {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  }
  return {
    ...actual,
    default: {
      ...actual.default,
      create: vi.fn(() => instance),
      isAxiosError: actual.default.isAxiosError,
    },
    _instance: instance,
  }
})

vi.mock('@/store/authStore', () => ({
  useAuthStore: {
    getState: vi.fn(() => ({ clearAuth: clearAuthMock })),
  },
  getTokenExpiry: vi.fn(() => null),
}))

// The error handler captured from the interceptors.response.use call in api.ts.
type ErrorHandler = (error: unknown) => Promise<unknown>

describe('api.ts — 429 rate-limit interceptor', () => {
  let errorHandler: ErrorHandler

  beforeEach(async () => {
    vi.resetModules()
    clearAuthMock.mockReset()
    // Reset to the initial jsdom URL before each test.
    window.history.replaceState(null, '', '/')

    const axiosMod = await import('axios')
    const instance = (axiosMod as any)._instance as ReturnType<typeof axios.create>

    // Capture the error handler when api.ts registers its response interceptor.
    vi.mocked(instance.interceptors.response.use).mockImplementationOnce(
      (_success: unknown, handler: unknown) => {
        errorHandler = handler as ErrorHandler
        return 0
      },
    )

    // Importing api.ts triggers interceptor registration.
    await import('@/services/api')
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  /** Build a fake AxiosError-like object for status 429. */
  function make429Error(headers: Record<string, string> = {}): unknown {
    return {
      config: { url: '/query/' },
      response: { status: 429, headers, data: { detail: 'Too many requests' } },
      isAxiosError: true,
      message: 'Request failed with status code 429',
    }
  }

  it('rejects with an Error containing "Rate limit"', async () => {
    await expect(errorHandler(make429Error())).rejects.toMatchObject({
      message: expect.stringMatching(/Rate limit/i),
    })
  })

  it('includes "Please wait a moment" when no retry-after header is present', async () => {
    await expect(errorHandler(make429Error())).rejects.toMatchObject({
      message: expect.stringContaining('Please wait a moment.'),
    })
  })

  it('includes the retry-after value when the header is present', async () => {
    await expect(errorHandler(make429Error({ 'retry-after': '30' }))).rejects.toMatchObject({
      message: expect.stringContaining('30 seconds'),
    })
  })

  it('does NOT call clearAuth on a 429 response', async () => {
    try { await errorHandler(make429Error()) } catch { /* expected rejection */ }
    expect(clearAuthMock).not.toHaveBeenCalled()
  })

  it('does NOT redirect to /login on a 429 response', async () => {
    try { await errorHandler(make429Error()) } catch { /* expected rejection */ }
    // If the interceptor erroneously called window.location.href = '/login',
    // jsdom would record it; we verify the path stayed at '/'.
    expect(window.location.pathname).toBe('/')
  })
})
