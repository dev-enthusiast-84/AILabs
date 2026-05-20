import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Analytics } from '@vercel/analytics/react'
import { SpeedInsights } from '@vercel/speed-insights/react'
import LoginPage from '@/pages/LoginPage'
import ProtectedRoute from '@/components/ProtectedRoute'

const DashboardPage = lazy(() => import('@/pages/DashboardPage'))

export default function App() {
  const enableVercelObservability = import.meta.env.VITE_ENABLE_VERCEL_OBSERVABILITY === 'true'

  return (
    <>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Suspense fallback={<div className="min-h-screen bg-slate-50" />}>
                <DashboardPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      {enableVercelObservability && (
        <>
          <Analytics />
          <SpeedInsights />
        </>
      )}
    </>
  )
}
