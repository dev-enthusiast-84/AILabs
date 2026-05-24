import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRightStartOnRectangleIcon,
  BeakerIcon,
  BugAntIcon,
  Cog6ToothIcon,
  DocumentMagnifyingGlassIcon,
  UserIcon,
  LockClosedIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline'
import { useAuthStore, getTokenExpiry } from '@/store/authStore'
import { authApi, settingsApi } from '@/services/api'
import SettingsModal from '@/components/SettingsModal'
import GuardrailsModal from '@/components/GuardrailsModal'
import RagasDashboardModal from '@/components/RagasDashboardModal'
import TroubleshootModal from '@/components/TroubleshootModal'

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

/** Small icon button with a CSS tooltip overlay on hover. */
function Tip({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="relative group/tip">
      {children}
      <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 rounded-md bg-slate-800 px-2 py-1 text-xs text-white whitespace-nowrap opacity-0 transition-opacity group-hover/tip:opacity-100 z-50">
        {label}
      </span>
    </div>
  )
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
  const [ragasDashboardOpen, setRagasDashboardOpen] = useState(false)
  const [troubleshootOpen, setTroubleshootOpen] = useState(false)
  const [guestUploadMb, setGuestUploadMb] = useState(3)
  const [guestMaxDocs, setGuestMaxDocs] = useState(1)
  const [adminUploadMb, setAdminUploadMb] = useState(20)
  const settingsOpen = externalOpen ?? internalOpen
  const setSettingsOpen = (open: boolean) => {
    if (!open) onSettingsPrerequisiteNoticeChange?.(null)
    const updateOpen = onSettingsOpenChange ?? setInternalOpen
    updateOpen(open)
  }
  const sessionLabel = useSessionCountdown(isGuest ? token : null)

  useEffect(() => {
    if (!isGuest) return
    settingsApi.get().then((s) => {
      if (s.guest_max_upload_size_mb != null) setGuestUploadMb(s.guest_max_upload_size_mb)
      if (s.guest_max_indexed_documents != null) setGuestMaxDocs(s.guest_max_indexed_documents)
      if (s.max_upload_size_mb != null) setAdminUploadMb(s.max_upload_size_mb)
    }).catch(() => { /* keep defaults */ })
  }, [isGuest])
  const isExpiringSoon = sessionLabel.includes('expired') || /[1-5] min/.test(sessionLabel)

  const handleLogout = () => {
    authApi.logout().catch(() => {
      // Ignore server errors — clear local auth and redirect regardless (OWASP A07)
    }).finally(() => {
      clearAuth()
      navigate('/login')
    })
  }

  const iconBtn = 'inline-flex items-center justify-center w-9 h-9 rounded-xl border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 hover:border-slate-400 active:bg-slate-100 transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2'

  return (
    <>
      {/* Sticky wrapper keeps both the header bar and the guest banner fixed on scroll */}
      <div className="sticky top-0 z-40">
        <header className="bg-white/90 backdrop-blur-md border-b border-slate-200 px-4 sm:px-6 py-3 shadow-sm">
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

              {/* Troubleshooting agent — visible to all */}
              <Tip label="Troubleshoot">
                <button
                  onClick={() => setTroubleshootOpen(true)}
                  className={iconBtn}
                  aria-label="Open troubleshooting agent"
                  data-testid="troubleshoot-btn"
                >
                  <BugAntIcon className="h-4 w-4" />
                </button>
              </Tip>

              {/* RAGAS dashboard — visible to all; modal restricts trigger to admins */}
              <Tip label="RAGAS Dashboard">
                <button
                  onClick={() => setRagasDashboardOpen(true)}
                  className={iconBtn}
                  aria-label="RAGAS evaluation dashboard"
                  data-testid="ragas-dashboard-btn"
                >
                  <BeakerIcon className="h-4 w-4" />
                </button>
              </Tip>

              <Tip label="Guardrails">
                <button
                  onClick={() => setGuardrailsOpen(true)}
                  className={iconBtn}
                  aria-label="Open guardrails"
                  data-testid="guardrails-btn"
                >
                  <ShieldCheckIcon className="h-4 w-4" />
                </button>
              </Tip>

              <Tip label="Settings">
                <button
                  onClick={() => {
                    onSettingsPrerequisiteNoticeChange?.(null)
                    setSettingsOpen(true)
                  }}
                  className={iconBtn}
                  aria-label="Open settings"
                  data-testid="settings-btn"
                >
                  <Cog6ToothIcon className="h-4 w-4" />
                </button>
              </Tip>

              {/* Role-specific last button */}
              {isGuest ? (
                <Tip label="Sign in for full access">
                  <button
                    onClick={() => navigate('/login')}
                    className="inline-flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 text-white hover:brightness-110 active:brightness-95 transition-all focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-2"
                    aria-label="Sign in for full access"
                    data-testid="signin-btn"
                  >
                    <LockClosedIcon className="h-4 w-4" />
                  </button>
                </Tip>
              ) : (
                <Tip label="Sign out">
                  <button
                    onClick={handleLogout}
                    className={iconBtn}
                    aria-label="Sign out"
                  >
                    <ArrowRightStartOnRectangleIcon className="h-4 w-4" />
                  </button>
                </Tip>
              )}
            </div>
          </div>
        </header>

        {/* Guest info banner — concise, single source of truth for session constraints */}
        {isGuest && (
          <div className="bg-amber-50 border-b border-amber-200 px-4 sm:px-6 py-1.5">
            <p className="max-w-7xl mx-auto text-xs text-amber-700 text-center">
              <span className="font-semibold">Guest:</span>{' '}
              {guestMaxDocs} TXT · {guestUploadMb} MB · no delete · 15-min session —{' '}
              <button
                onClick={() => navigate('/login')}
                className="underline font-semibold hover:text-amber-800 transition-colors"
              >
                Sign in
              </button>{' '}
              for PDF, TXT, CSV, XLSX + {adminUploadMb} MB
            </p>
          </div>
        )}
      </div>

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
      <RagasDashboardModal
        open={ragasDashboardOpen}
        onClose={() => setRagasDashboardOpen(false)}
      />
      <TroubleshootModal
        open={troubleshootOpen}
        onClose={() => setTroubleshootOpen(false)}
      />
    </>
  )
}
