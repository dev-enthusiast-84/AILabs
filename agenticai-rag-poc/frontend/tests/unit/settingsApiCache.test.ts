/**
 * Unit tests for settingsApi cache behaviour (Fix P1).
 * Verifies that the 30-second TTL cache reduces HTTP round-trips.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import axios from 'axios'

// Mock axios so we never touch the network.
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

// Mock authStore to avoid sessionStorage side-effects.
vi.mock('@/store/authStore', () => ({
  useAuthStore: {
    getState: vi.fn(() => ({ clearAuth: vi.fn() })),
  },
  getTokenExpiry: vi.fn(() => null),
}))

describe('settingsApi — cache behaviour', () => {
  let settingsApi: typeof import('@/services/api')['settingsApi']
  let clearSettingsCache: typeof import('@/services/api')['clearSettingsCache']
  let axiosInstance: ReturnType<typeof axios.create>

  beforeEach(async () => {
    vi.resetModules()
    // Re-import so module-level cache state starts fresh.
    const mod = await import('@/services/api')
    settingsApi = mod.settingsApi
    clearSettingsCache = mod.clearSettingsCache

    // Get the mocked axios instance created inside api.ts.
    const axiosMod = await import('axios')
    axiosInstance = (axiosMod as any)._instance

    vi.mocked(axiosInstance.get).mockResolvedValue({
      data: { api_key_source: 'runtime', vector_store_type: 'chroma' },
      headers: {},
    })
    vi.mocked(axiosInstance.post).mockResolvedValue({
      data: { api_key_source: 'env', vector_store_type: 'chroma' },
      headers: {},
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('calls the HTTP client only once when get() is called twice within the TTL', async () => {
    await settingsApi.get()
    await settingsApi.get()
    expect(axiosInstance.get).toHaveBeenCalledTimes(1)
  })

  it('returns cached data on the second call without an extra HTTP request', async () => {
    const first = await settingsApi.get()
    const second = await settingsApi.get()
    expect(first).toEqual(second)
    expect(axiosInstance.get).toHaveBeenCalledTimes(1)
  })

  it('makes a fresh HTTP request after clearSettingsCache() is called', async () => {
    await settingsApi.get()
    clearSettingsCache()
    await settingsApi.get()
    expect(axiosInstance.get).toHaveBeenCalledTimes(2)
  })

  it('update() refreshes the cache so a subsequent get() returns updated data without an HTTP call', async () => {
    // Prime the cache via get().
    await settingsApi.get()
    expect(axiosInstance.get).toHaveBeenCalledTimes(1)

    // update() writes to cache.
    const updated = await settingsApi.update({ api_key: 'new-key' } as any)
    expect(updated.api_key_source).toBe('env')

    // get() should return the cached update without another HTTP call.
    const cached = await settingsApi.get()
    expect(cached.api_key_source).toBe('env')
    expect(axiosInstance.get).toHaveBeenCalledTimes(1) // still only 1
  })
})
