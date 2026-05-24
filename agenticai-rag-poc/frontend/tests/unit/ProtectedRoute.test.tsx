import { render, screen } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import ProtectedRoute from '@/components/ProtectedRoute'

const mockClearAuth = vi.fn()

vi.mock('@/store/authStore', () => ({
  useAuthStore: vi.fn(),
}))

vi.mock('@/services/api', () => ({
  authApi: {
    me: vi.fn(),
  },
}))

import { useAuthStore } from '@/store/authStore'
import { authApi } from '@/services/api'

function setAuthStore(isAuthenticated: boolean, isGuest: boolean) {
  vi.mocked(useAuthStore as unknown as (sel?: unknown) => unknown).mockImplementation((sel?: unknown) => {
    const state = { isAuthenticated: () => isAuthenticated, isGuest, clearAuth: mockClearAuth }
    if (typeof sel === 'function') return (sel as (s: typeof state) => unknown)(state)
    return state
  })
}

function renderRoute(isAuthenticated: boolean, isGuest = false) {
  setAuthStore(isAuthenticated, isGuest)
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ProtectedRoute>
        <div data-testid="protected-content">Protected</div>
      </ProtectedRoute>
    </MemoryRouter>,
  )
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders children when authenticated', () => {
    vi.mocked(authApi.me).mockResolvedValue({ username: 'admin', role: 'admin' })
    renderRoute(true, false)
    expect(screen.getByTestId('protected-content')).toBeTruthy()
  })

  it('redirects to /login when not authenticated', () => {
    vi.mocked(authApi.me).mockResolvedValue({ username: 'guest', role: 'guest' })
    renderRoute(false)
    expect(screen.queryByTestId('protected-content')).toBeNull()
  })

  it('calls authApi.me on mount when authenticated', async () => {
    vi.mocked(authApi.me).mockResolvedValue({ username: 'admin', role: 'admin' })
    renderRoute(true, false)
    await vi.waitFor(() => expect(authApi.me).toHaveBeenCalledTimes(1))
  })

  it('does not call authApi.me when not authenticated', async () => {
    vi.mocked(authApi.me).mockResolvedValue({ username: 'guest', role: 'guest' })
    renderRoute(false)
    // Give effects time to run
    await new Promise((r) => setTimeout(r, 50))
    expect(authApi.me).not.toHaveBeenCalled()
  })

  it('calls clearAuth when server role does not match expected role (admin token, server returns guest)', async () => {
    vi.mocked(authApi.me).mockResolvedValue({ username: 'admin', role: 'guest' })
    renderRoute(true, false) // isGuest=false → expectedRole='admin', server says 'guest'
    await vi.waitFor(() => expect(mockClearAuth).toHaveBeenCalled())
  })

  it('calls clearAuth when server role does not match expected role (guest token, server returns admin)', async () => {
    vi.mocked(authApi.me).mockResolvedValue({ username: 'guest', role: 'admin' })
    renderRoute(true, true) // isGuest=true → expectedRole='guest', server says 'admin'
    await vi.waitFor(() => expect(mockClearAuth).toHaveBeenCalled())
  })

  it('does not call clearAuth when roles match (admin)', async () => {
    vi.mocked(authApi.me).mockResolvedValue({ username: 'admin', role: 'admin' })
    renderRoute(true, false)
    await vi.waitFor(() => expect(authApi.me).toHaveBeenCalled())
    expect(mockClearAuth).not.toHaveBeenCalled()
  })

  it('does not call clearAuth when roles match (guest)', async () => {
    vi.mocked(authApi.me).mockResolvedValue({ username: 'guest', role: 'guest' })
    renderRoute(true, true)
    await vi.waitFor(() => expect(authApi.me).toHaveBeenCalled())
    expect(mockClearAuth).not.toHaveBeenCalled()
  })

  it('does not call clearAuth on network errors from authApi.me', async () => {
    vi.mocked(authApi.me).mockRejectedValue(new Error('Network error'))
    renderRoute(true, false)
    await vi.waitFor(() => expect(authApi.me).toHaveBeenCalled())
    expect(mockClearAuth).not.toHaveBeenCalled()
  })
})
