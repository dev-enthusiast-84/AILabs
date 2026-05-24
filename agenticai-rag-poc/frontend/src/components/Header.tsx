import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRightStartOnRectangleIcon,
  Cog6ToothIcon,
  DocumentMagnifyingGlassIcon,
  UserIcon,
  LockClosedIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline'
import { useAuthStore, getTokenExpiry } from '@/store/authStore'
import { authApi } from '@/services/api'
import SettingsModal from '@/components/SettingsModal'
import GuardrailsModal from '@/components/GuardrailsModal'

function useSessionCountdown(token: string | null): string {
  const [label, setLabel] = useState('')

  useEffect(() => {
    if (!token) { setLabel(''); return }
    const expiry = getTokenExpiry(token)
    if (!expiry) { setLabel(''); return }

    const tick = () => {
      const remaining = expiry.getTime() - Date.now()
      if (remaining <= 0) { setLabel('Session expired'); return }
      const mins = Math.ceil(remaining / 60_000)
      setLabel(mins <= 5 ? `Session expires in ${mins} min` : `${mins} min remaining`)
    }
    tick()
    const id = setInterval(tick, 30_000)
    return () => clearInterval(id)
  }, [token])

  return label
}

interface Props {
  /** When provided, the parent controls the settings modal (lift state up). */
  settingsOpen?: boolean
  onSettingsOpenChange?: (open: boolean) => void
  settingsPrerequisiteNotice?: string | null
  onSettingsPrerequisiteNoticeChange?: (notice: string | null) => void
}

export default function Header({
  settingsOpen: externalOpen,
  onSettingsOpenChange,
  settingsPrerequisiteNotice = null,
  onSettingsPrerequisiteNoticeChange,
}: Props) {
  const { username, isGuest, token, clearAuth } = useAuthStore()
  const navigate = useNavigate()
  const [internalOpen, setInternalOpen] = useState(false)
  const [guardrailsOpen, setGuardrailsOpen] = useState(false)
  const settingsOpen = externalOpen ?? internalOpen
  const setSettingsOpen = (open: boolean) => {
    if (!open) onSettingsPrerequisiteNoticeChange?.(null)
    const updateOpen = onSettingsOpenChange ?? setInternalOpen
    updateOpen(open)
  }
  const sessionLabel = useSessionCountdown(isGuest ? token : null)
  const isExpiringSoon = sessionLabel.includes('expired') || /[1-5] min/.test(sessionLabel)

  const handleLogout = () => {
    authApi.logout().catch(() => {
      // Ignore server errors — clear local auth and redirect regardless (OWASP A07)
    }).finally(() => {
      clearAuth()
      navigate('/login')
    })
  }

  return (
    <>
      <header className="bg-white/90 backdrop-blur-md border-b border-slate-200 px-4 sm:px-6 py-3 sticky top-0 z-40 shadow-sm">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-3">
          {/* Logo */}
          <button
            type="button"
            onClick={() => navigate('/')}
            className="flex items-center gap-3 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 group"
            aria-label="Go to home"
            data-testid="logo-home-btn"
          >
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-sky-500 to-indigo-600 shadow-glow-sky group-hover:brightness-110 transition-all duration-150 shrink-0">
              <DocumentMagnifyingGlassIcon className="h-4 w-4 text-white" />
            </div>
            <div className="text-left hidden sm:block">
              <h1 className="text-sm font-bold text-gradient leading-tight">Agentic RAG</h1>
              <p className="text-xs text-slate-400 leading-tight">Enterprise Document Q&amp;A</p>
            </div>
          </button>

          {/* Nav actions */}
          <div className="flex items-center gap-2">
            {/* Role indicator */}
            {isGuest ? (
              <>
                <span className="badge-guest hidden sm:inline-flex">
                  <UserIcon className="h-3 w-3" />
                  Guest
                </span>
                {sessionLabel && (
                  <span className={`hidden md:inline text-xs font-medium ${isExpiringSoon ? 'text-rose-500' : 'text-slate-400'}`}>
                    {sessionLabel}
                  </span>
                )}
              </>
            ) : (
              <span className="text-xs text-slate-500 hidden sm:inline">
                Signed in as <span className="font-semibold text-sky-600">{username}</span>
              </span>
            )}

            {/* Shared action buttons */}
            <button
              onClick={() => setGuardrailsOpen(true)}
              className="btn-secondary text-xs py-1.5 px-3"
              aria-label="Open guardrails"
              data-testid="guardrails-btn"
            >
              <ShieldCheckIcon className="h-4 w-4" />
              <span className="hidden sm:inline">Guardrails</span>
            </button>
            <button
              onClick={() => {
                onSettingsPrerequisiteNoticeChange?.(null)
                setSettingsOpen(true)
              }}
              className="btn-secondary text-xs py-1.5 px-3"
              aria-label="Open settings"
              data-testid="settings-btn"
            >
              <Cog6ToothIcon className="h-4 w-4" />
              <span className="hidden sm:inline">Settings</span>
            </button>

            {/* Role-specific last button */}
            {isGuest ? (
              <button
                onClick={() => navigate('/login')}
                className="btn-primary text-xs py-1.5 px-3"
                aria-label="Sign in for full access"
                data-testid="signin-btn"
              >
                <LockClosedIcon className="h-4 w-4" />
                <span className="hidden sm:inline">Sign in</span>
              </button>
            ) : (
              <button
                onClick={handleLogout}
                className="btn-secondary text-xs py-1.5 px-3"
                aria-label="Sign out"
              >
                <ArrowRightStartOnRectangleIcon className="h-4 w-4" />
                <span className="hidden sm:inline">Sign out</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Guest info banner */}
      {isGuest && (
        <div className="bg-amber-50 border-b border-amber-200 px-4 sm:px-6 py-2">
          <p className="max-w-7xl mx-auto text-xs text-amber-700 text-center">
            <span className="font-semibold">Guest mode:</span> upload 1 TXT file (up to 2 MB) · query documents · configure settings once · 15-minute session.{' '}
            <button
              onClick={() => navigate('/login')}
              className="underline font-semibold hover:text-amber-800 transition-colors"
            >
              Sign in
            </button>{' '}
            to unlock PDF/CSV/XLSX · 20 MB files · 45-minute session · unlimited settings changes.
          </p>
        </div>
      )}

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        isGuest={isGuest}
        prerequisiteNotice={settingsPrerequisiteNotice}
      />
      <GuardrailsModal
        open={guardrailsOpen}
        onClose={() => setGuardrailsOpen(false)}
        isGuest={isGuest}
      />
    </>
  )
}
