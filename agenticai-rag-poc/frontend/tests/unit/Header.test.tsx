import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import Header from '@/components/Header'

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('@/store/authStore', () => ({
  useAuthStore: vi.fn(),
  getTokenExpiry: vi.fn(),
}))

vi.mock('@/components/SettingsModal', () => ({
  default: ({ open, onClose }: { open: boolean; onClose: () => void }) =>
    open ? <div data-testid="settings-modal"><button onClick={onClose}>close-settings</button></div> : null,
}))

vi.mock('@/components/GuardrailsModal', () => ({
  default: ({ open, onClose }: { open: boolean; onClose: () => void }) =>
    open ? <div data-testid="guardrails-modal"><button onClick={onClose}>close-guardrails</button></div> : null,
}))

vi.mock('@/components/RagasDashboardModal', () => ({
  default: ({ open, onClose }: { open: boolean; onClose: () => void }) =>
    open ? <div data-testid="ragas-modal"><button onClick={onClose}>close-ragas</button></div> : null,
}))

vi.mock('@/services/api', () => ({
  authApi: { logout: vi.fn().mockResolvedValue(undefined) },
  settingsApi: { get: vi.fn().mockResolvedValue({}) },
}))

import { useAuthStore, getTokenExpiry } from '@/store/authStore'
import { authApi } from '@/services/api'

interface AuthState {
  username: string | null
  isGuest: boolean
  token: string | null
  clearAuth: () => void
}

function setAuth(overrides: Partial<AuthState> = {}) {
  const state: AuthState = {
    username: 'admin',
    isGuest: false,
    token: 'tok',
    clearAuth: vi.fn(),
    ...overrides,
  }
  // Header calls useAuthStore() without a selector — return the whole state object
  vi.mocked(useAuthStore as unknown as () => AuthState).mockReturnValue(state)
}

function renderHeader(props = {}) {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Header {...props} />
    </MemoryRouter>,
  )
}

describe('Header', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getTokenExpiry).mockReturnValue(null)
    setAuth()
  })

  it('shows signed-in username for admin', () => {
    renderHeader()
    expect(screen.getByText('admin')).toBeTruthy()
  })

  it('shows Guest badge for guest users', () => {
    setAuth({ isGuest: true, username: 'guest' })
    renderHeader()
    expect(screen.getByText('Guest')).toBeTruthy()
  })

  it('shows Sign out button for admin', () => {
    renderHeader()
    expect(screen.getByLabelText('Sign out')).toBeTruthy()
  })

  it('shows Sign in button for guest', () => {
    setAuth({ isGuest: true, username: 'guest' })
    renderHeader()
    expect(screen.getByLabelText('Sign in for full access')).toBeTruthy()
  })

  it('clicking Sign out calls server logout, then clearAuth and navigates to /login', async () => {
    const clearAuth = vi.fn()
    setAuth({ clearAuth })
    renderHeader()
    fireEvent.click(screen.getByLabelText('Sign out'))
    await waitFor(() => expect(clearAuth).toHaveBeenCalled())
    expect(authApi.logout).toHaveBeenCalled()
    expect(mockNavigate).toHaveBeenCalledWith('/login')
  })

  it('clicking Sign out still clears auth when server logout fails', async () => {
    vi.mocked(authApi.logout).mockRejectedValueOnce(new Error('network'))
    const clearAuth = vi.fn()
    setAuth({ clearAuth })
    renderHeader()
    fireEvent.click(screen.getByLabelText('Sign out'))
    await waitFor(() => expect(clearAuth).toHaveBeenCalled())
    expect(mockNavigate).toHaveBeenCalledWith('/login')
  })

  it('clicking Sign in navigates to /login', () => {
    setAuth({ isGuest: true, username: 'guest' })
    renderHeader()
    fireEvent.click(screen.getByLabelText('Sign in for full access'))
    expect(mockNavigate).toHaveBeenCalledWith('/login')
  })

  it('clicking logo navigates to /', () => {
    renderHeader()
    fireEvent.click(screen.getByTestId('logo-home-btn'))
    expect(mockNavigate).toHaveBeenCalledWith('/')
  })

  it('clicking Settings button opens SettingsModal', () => {
    renderHeader()
    fireEvent.click(screen.getByLabelText('Open settings'))
    expect(screen.getByTestId('settings-modal')).toBeTruthy()
  })

  it('clicking Guardrails button opens GuardrailsModal', () => {
    renderHeader()
    fireEvent.click(screen.getByLabelText('Open guardrails'))
    expect(screen.getByTestId('guardrails-modal')).toBeTruthy()
  })

  it('does not show guest info banner for admin', () => {
    renderHeader()
    expect(screen.queryByText(/Guest mode:/)).toBeNull()
  })

  it('shows guest info banner for guest users', () => {
    setAuth({ isGuest: true, username: 'guest' })
    renderHeader()
    expect(screen.getByText(/Guest:/)).toBeTruthy()
  })

  it('shows session countdown when guest token has near-expiry', () => {
    setAuth({ isGuest: true, token: 'guest-tok', username: 'guest' })
    const soon = new Date(Date.now() + 3 * 60_000) // 3 min from now
    vi.mocked(getTokenExpiry).mockReturnValue(soon)
    renderHeader()
    expect(screen.getByText(/Session expires in 3 min/)).toBeTruthy()
  })

  it('external settingsOpen prop controls the modal', () => {
    renderHeader({ settingsOpen: true, onSettingsOpenChange: vi.fn() })
    expect(screen.getByTestId('settings-modal')).toBeTruthy()
  })

  it('shows RAGAS dashboard button for admin', () => {
    renderHeader()
    expect(screen.getByLabelText('RAGAS evaluation dashboard')).toBeTruthy()
  })

  it('shows RAGAS dashboard button for guest (modal restricts trigger internally)', () => {
    setAuth({ isGuest: true, username: 'guest' })
    renderHeader()
    expect(screen.getByLabelText('RAGAS evaluation dashboard')).toBeTruthy()
  })

  it('clicking RAGAS dashboard button opens RAGAS modal', () => {
    renderHeader()
    fireEvent.click(screen.getByLabelText('RAGAS evaluation dashboard'))
    expect(screen.getByTestId('ragas-modal')).toBeTruthy()
  })
})
