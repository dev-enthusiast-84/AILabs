import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import LoginPage from '@/pages/LoginPage'

// Mock navigate
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

// Mock api — devCredentials is intentionally absent (endpoint removed, S-10)
vi.mock('@/services/api', () => ({
  authApi: {
    login: vi.fn(),
    guest: vi.fn(),
  },
  documentsApi: {
    remove: vi.fn().mockResolvedValue(undefined),
  },
  extractErrorMessage: (_e: unknown) => 'error',
}))

// Mock store
vi.mock('@/store/authStore', () => ({
  useAuthStore: () => ({
    setAuth: vi.fn(),
    setGuest: vi.fn(),
    clearAuth: vi.fn(),
    username: 'admin',
    token: null,
    isAuthenticated: () => false,
    popGuestUploadedDocs: vi.fn().mockReturnValue([]),
    addGuestUploadedDoc: vi.fn(),
    guestUploadedDocs: [],
  }),
}))

const renderLogin = () =>
  render(
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <LoginPage />
    </BrowserRouter>,
  )

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
  })

  it('renders username and password inputs', () => {
    renderLogin()
    expect(screen.getByTestId('username-input')).toBeInTheDocument()
    expect(screen.getByTestId('password-input')).toBeInTheDocument()
  })

  it('submit button is disabled when inputs are empty', () => {
    renderLogin()
    expect(screen.getByTestId('login-button')).toBeDisabled()
  })

  it('enables submit button when both fields filled', async () => {
    renderLogin()
    fireEvent.change(screen.getByTestId('username-input'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByTestId('password-input'), { target: { value: 'testPassword1' } })
    expect(screen.getByTestId('login-button')).not.toBeDisabled()
  })

  it('calls authApi.login on form submit', async () => {
    const { authApi } = await import('@/services/api')
    vi.mocked(authApi.login).mockResolvedValue({ access_token: 'tok', token_type: 'bearer' })
    renderLogin()
    fireEvent.change(screen.getByTestId('username-input'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByTestId('password-input'), { target: { value: 'testPassword1' } })
    fireEvent.click(screen.getByTestId('login-button'))
    await waitFor(() => expect(authApi.login).toHaveBeenCalledWith({ username: 'admin', password: 'testPassword1' }))
  })

  it('shows an inline error when admin login fails', async () => {
    const { authApi } = await import('@/services/api')
    vi.mocked(authApi.login).mockRejectedValue(new Error('bad login'))
    renderLogin()
    fireEvent.change(screen.getByTestId('username-input'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByTestId('password-input'), { target: { value: 'wrongPassword1' } })
    fireEvent.click(screen.getByTestId('login-button'))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('error'))
  })

  it('shows session invalidation message inline on the login page', () => {
    sessionStorage.setItem('auth_error', 'Your session is no longer valid. Please sign in again.')
    renderLogin()
    expect(screen.getByRole('alert')).toHaveTextContent('Your session is no longer valid')
    expect(sessionStorage.getItem('auth_error')).toBeNull()
  })

  it('shows an inline error when guest login fails', async () => {
    const { authApi } = await import('@/services/api')
    vi.mocked(authApi.guest).mockRejectedValue(new Error('guest blocked'))
    renderLogin()
    fireEvent.click(screen.getByTestId('guest-button'))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('error'))
  })

  it('does not render the auto-fill dev credentials button (endpoint removed S-10)', () => {
    renderLogin()
    expect(screen.queryByTestId('fill-dev-credentials-btn')).not.toBeInTheDocument()
  })
})
