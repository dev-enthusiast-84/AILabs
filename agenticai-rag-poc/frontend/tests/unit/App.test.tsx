/**
 * Tests that Vercel Analytics and Speed Insights are opt-in.
 * They inject /_vercel scripts, which fail to load when the project feature is disabled.
 */
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import App from '@/App'

// Render stable test-ids so assertions don't depend on internal implementation details
vi.mock('@vercel/analytics/react', () => ({
  Analytics: () => <div data-testid="vercel-analytics" />,
}))

vi.mock('@vercel/speed-insights/react', () => ({
  SpeedInsights: () => <div data-testid="vercel-speed-insights" />,
}))

vi.mock('@/pages/LoginPage', () => ({
  default: () => <div>Login</div>,
}))

vi.mock('@/pages/DashboardPage', () => ({
  default: () => <div>Dashboard</div>,
}))

vi.mock('@/components/ProtectedRoute', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

const renderApp = (initialPath = '/login') =>
  render(
    <MemoryRouter initialEntries={[initialPath]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <App />
    </MemoryRouter>,
  )

describe('App — Vercel observability', () => {
  beforeEach(() => {
    vi.unstubAllEnvs()
  })

  it('does not render observability scripts by default', () => {
    renderApp()
    expect(screen.queryByTestId('vercel-analytics')).not.toBeInTheDocument()
    expect(screen.queryByTestId('vercel-speed-insights')).not.toBeInTheDocument()
  })

  it('renders Analytics and SpeedInsights when explicitly enabled', () => {
    vi.stubEnv('VITE_ENABLE_VERCEL_OBSERVABILITY', 'true')
    renderApp()
    expect(screen.getByTestId('vercel-analytics')).toBeInTheDocument()
    expect(screen.getByTestId('vercel-speed-insights')).toBeInTheDocument()
  })

  it('renders both components on every route when enabled', async () => {
    vi.stubEnv('VITE_ENABLE_VERCEL_OBSERVABILITY', 'true')
    await act(async () => { renderApp('/') })
    expect(screen.getByTestId('vercel-analytics')).toBeInTheDocument()
    expect(screen.getByTestId('vercel-speed-insights')).toBeInTheDocument()
  })
})
