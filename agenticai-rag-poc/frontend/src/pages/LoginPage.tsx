import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LockClosedIcon, DocumentMagnifyingGlassIcon, UserIcon } from '@heroicons/react/24/outline'
import { authApi, documentsApi, extractErrorMessage } from '@/services/api'
import { useAuthStore } from '@/store/authStore'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [guestLoading, setGuestLoading] = useState(false)
  const [loginError, setLoginError] = useState(() => {
    const message = sessionStorage.getItem('auth_error') ?? ''
    sessionStorage.removeItem('auth_error')
    return message
  })
  const [guestError, setGuestError] = useState('')
  const { setAuth, setGuest, popGuestUploadedDocs } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setLoginError('')
    setGuestError('')
    try {
      const data = await authApi.login({ username, password })
      const guestDocs = popGuestUploadedDocs()
      setAuth(data.access_token, username)
      if (guestDocs.length > 0) {
        await Promise.allSettled(guestDocs.map((doc) => documentsApi.remove(doc)))
      }
      navigate('/', { replace: true })
    } catch (err) {
      const message = extractErrorMessage(err)
      setLoginError(message)
    } finally {
      setLoading(false)
    }
  }

  const handleGuest = async () => {
    setGuestLoading(true)
    setGuestError('')
    setLoginError('')
    try {
      const data = await authApi.guest()
      setGuest(data.access_token)
      navigate('/', { replace: true })
    } catch (err) {
      setGuestError(extractErrorMessage(err))
    } finally {
      setGuestLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-sky-50/40 to-indigo-50/30 flex items-center justify-center p-4 relative overflow-hidden">
      {/* Ambient background orbs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-sky-400/10 rounded-full blur-3xl animate-pulse-slow" />
        <div
          className="absolute -bottom-40 -left-40 w-96 h-96 bg-indigo-400/10 rounded-full blur-3xl animate-pulse-slow"
          style={{ animationDelay: '1.5s' }}
        />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] bg-sky-300/5 rounded-full blur-3xl" />
      </div>

      <div className="w-full max-w-sm relative">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-5 bg-gradient-to-br from-sky-500 to-indigo-600 shadow-lg shadow-sky-500/25 animate-float">
            <DocumentMagnifyingGlassIcon className="h-9 w-9 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-gradient mb-1">Agentic RAG</h1>
          <p className="text-sm text-slate-500">Enterprise Document Q&amp;A</p>
        </div>

        {/* Card */}
        <div className="card-glass p-8">
          <h2 className="text-base font-semibold text-slate-800 mb-6">Sign in to your account</h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-slate-600 mb-1.5">
                Username
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoComplete="username"
                className="input"
                placeholder="admin"
                data-testid="username-input"
              />
            </div>
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-600 mb-1.5">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="input"
                placeholder="••••••••"
                data-testid="password-input"
              />
            </div>
            {loginError && (
              <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
                {loginError}
              </p>
            )}
            <button
              type="submit"
              disabled={loading || !username || !password}
              className="btn-primary w-full mt-2"
              data-testid="login-button"
            >
              <LockClosedIcon className="h-4 w-4" />
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          {/* Divider */}
          <div className="relative my-5">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-slate-200" />
            </div>
            <div className="relative flex justify-center text-xs text-slate-400">
              <span className="bg-white px-3">or</span>
            </div>
          </div>

          {/* Guest entry */}
          <button
            type="button"
            onClick={handleGuest}
            disabled={guestLoading}
            className="btn-secondary w-full"
            data-testid="guest-button"
          >
            <UserIcon className="h-4 w-4" />
            {guestLoading ? 'Entering as guest…' : 'Continue as Guest'}
          </button>
          {guestError && (
            <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
              {guestError}
            </p>
          )}

          <p className="text-xs text-slate-400 text-center mt-2">
            Guest access: chat &amp; TXT upload (one-time settings, 15 min session).
          </p>

          {!__IS_VERCEL__ && (
            <div className="mt-5 border-t border-slate-200 pt-4 flex items-center justify-center">
              <p className="text-xs text-slate-400">
                Password in{' '}
                <code className="bg-slate-100 text-sky-600 px-1.5 py-0.5 rounded text-xs">backend/.env</code>
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
