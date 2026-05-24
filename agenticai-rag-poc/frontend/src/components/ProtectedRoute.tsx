import { useEffect } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { authApi } from '@/services/api'

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated())
  const { isGuest, clearAuth } = useAuthStore()

  useEffect(() => {
    if (!isAuthenticated) return
    authApi.me()
      .then(({ role }) => {
        // If the server reports a role mismatch (e.g. admin→guest), clear local state.
        // 401 responses are handled by the global interceptor (clearAuth + redirect to /login).
        const expectedRole = isGuest ? 'guest' : 'admin'
        if (role !== expectedRole) clearAuth()
      })
      .catch(() => {
        // Network errors should not force logout — the 401 interceptor handles auth failures.
      })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps — intentionally fires once on mount only

  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}
