import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import toast from 'react-hot-toast'
import {
  ArrowPathIcon,
  BeakerIcon,
  ExclamationTriangleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { settingsApi, extractErrorMessage } from '@/services/api'
import { useAuthStore } from '@/store/authStore'
import type { RagasScores, SettingsResponse } from '@/types'

function MetricTile({ label, score }: { label: string; score: number }) {
  const pct = Math.round(score * 100)
  const colorClass =
    score >= 0.75
      ? { text: 'text-emerald-700', bg: 'bg-emerald-500' }
      : score >= 0.5
      ? { text: 'text-amber-700', bg: 'bg-amber-500' }
      : { text: 'text-rose-700', bg: 'bg-rose-500' }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <p className="text-xs font-medium text-slate-600">{label}</p>
      <p className={`mt-1 text-xl font-bold ${colorClass.text}`}>{pct}%</p>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
        <div className={`h-full rounded-full ${colorClass.bg}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

interface Props {
  open: boolean
  onClose: () => void
}

export default function RagasDashboardModal({ open, onClose }: Props) {
  const onCloseRef = useRef(onClose)
  useEffect(() => { onCloseRef.current = onClose })
  const isGuest = useAuthStore(s => s.isGuest)
  const [settings, setSettings] = useState<SettingsResponse | null>(null)
  const [scores, setScores] = useState<RagasScores | null>(null)
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const [clearing, setClearing] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)
  // True while we are polling after triggering an evaluation
  const [polling, setPolling] = useState(false)
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const stopPolling = () => {
    if (pollingIntervalRef.current !== null) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
    if (pollingTimeoutRef.current !== null) {
      clearTimeout(pollingTimeoutRef.current)
      pollingTimeoutRef.current = null
    }
    setPolling(false)
  }

  const load = async () => {
    setLoading(true)
    try {
      const [settingsResponse, scoresResponse] = await Promise.all([
        settingsApi.get(),
        settingsApi.getRagasScores(),
      ])
      setSettings(settingsResponse)
      setScores(scoresResponse?.has_results === false ? null : scoresResponse)
    } catch (err) {
      toast.error(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!open) return
    void load()
  }, [open])

  // Clean up polling when modal closes
  useEffect(() => {
    if (!open) stopPolling()
  }, [open])

  // Clean up on unmount
  useEffect(() => {
    return () => stopPolling()
  }, [])

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => e.key === 'Escape' && onCloseRef.current()
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open])

  if (!open) return null

  const clearHistory = async () => {
    setClearing(true)
    try {
      await settingsApi.clearRagasScores()
      setScores(null)
      setConfirmClear(false)
      toast.success('Evaluation history cleared.')
    } catch (err) {
      toast.error(extractErrorMessage(err))
    } finally {
      setClearing(false)
    }
  }

  const runEvaluation = async () => {
    if (settings?.api_key_source === 'not_configured') {
      toast.error('OpenAI API key is required before running Ragas evaluation.')
      return
    }
    setRunning(true)
    // Capture the current evaluated_at so we know when a new result arrives
    const previousEvaluatedAt = scores?.evaluated_at ?? null
    try {
      await settingsApi.triggerRagas()
      toast.success('Ragas evaluation started')
      setPolling(true)

      // Poll every 3 seconds for up to 120 seconds
      pollingIntervalRef.current = setInterval(async () => {
        try {
          const updated = await settingsApi.getRagasScores()
          const newScores = updated?.has_results === false ? null : updated
          if (newScores && newScores.evaluated_at !== previousEvaluatedAt) {
            // New result arrived
            setScores(newScores)
            stopPolling()
            toast.success('Evaluation complete.')
          }
        } catch {
          // Silently retry on transient errors during polling
        }
      }, 3000)

      // Timeout after 120 seconds
      pollingTimeoutRef.current = setTimeout(() => {
        stopPolling()
        toast('Evaluation is taking longer than expected. Refresh when ready.', { icon: '⏱' })
      }, 120_000)
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 422) {
        toast.error('Upload documents first before running evaluation.')
      } else if (axios.isAxiosError(err) && err.response?.status === 429) {
        toast.error('Evaluation is already running. Please wait.')
      } else {
        toast.error(extractErrorMessage(err))
      }
    } finally {
      setRunning(false)
    }
  }

  // Contextual empty state message
  const emptyStateMessage = (): string => {
    if (settings?.api_key_source === 'not_configured') {
      return 'Configure an OpenAI API key in Settings first to run evaluations.'
    }
    if (settings?.ragas_evaluation_enabled === false) {
      return 'No results yet. Auto-evaluation is off — enable it in Settings → Pipeline, or click Run to evaluate now (admin only).'
    }
    return 'No results yet. Auto-evaluation samples 1 in 50 queries. Run a manual evaluation to see scores immediately.'
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="ragas-dashboard-title"
    >
      <div className="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-300/40">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div className="flex items-center gap-2">
            <BeakerIcon className="h-5 w-5 text-sky-700" aria-hidden="true" />
            <h2 id="ragas-dashboard-title" className="text-base font-semibold text-slate-900">
              Ragas Dashboard
            </h2>
            {/* Auto-eval status badge (3a) */}
            {settings?.ragas_evaluation_enabled ? (
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200"
                data-testid="ragas-auto-eval-badge"
              >
                Auto ON
              </span>
            ) : (
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-500 border border-slate-200"
                data-testid="ragas-auto-eval-badge"
              >
                Auto OFF
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-slate-500 transition-colors hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-700/40 focus-visible:ring-offset-2"
            aria-label="Close Ragas dashboard"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
          {loading ? (
            <div className="flex items-center justify-center gap-3 py-10">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-sky-600 border-t-transparent" />
              <p className="text-sm text-slate-600">Loading</p>
            </div>
          ) : scores ? (
            <div className="relative">
              {/* Polling overlay (3b) */}
              {polling && (
                <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 rounded-lg bg-white/90 backdrop-blur-sm">
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-sky-600 border-t-transparent" />
                  <p className="text-sm font-medium text-slate-700">Evaluation running…</p>
                  <p className="text-xs text-slate-500">Checking for results every 3s…</p>
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                <MetricTile label="Faithfulness" score={scores.faithfulness} />
                <MetricTile label="Relevancy" score={scores.answer_relevancy} />
                <MetricTile label="Precision" score={scores.context_precision} />
                <MetricTile label="Recall" score={scores.context_recall} />
              </div>
              <p className="mt-3 text-xs text-slate-600">
                {new Date(scores.evaluated_at).toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })}{' '}
                · {scores.model} · {scores.num_samples} samples
              </p>
              {/* Cleanup info — admin only */}
              {!isGuest && (
                <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 space-y-2">
                  <div>
                    <p className="text-xs font-medium text-slate-600">Cleanup</p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Scores are replaced each time evaluation runs (auto: 1 in 50 queries; manual: on demand).
                      Clear history to reset results — the next evaluation will populate fresh scores.
                    </p>
                  </div>
                  {confirmClear ? (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-rose-700 font-medium">Clear all scores?</span>
                      <button
                        type="button"
                        onClick={() => void clearHistory()}
                        disabled={clearing}
                        className="btn-secondary text-xs text-rose-600 border-rose-300 hover:border-rose-400 disabled:opacity-50"
                        data-testid="ragas-clear-confirm-btn"
                      >
                        {clearing ? 'Clearing…' : 'Yes, clear'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmClear(false)}
                        className="text-xs text-slate-500 underline"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirmClear(true)}
                      className="btn-secondary text-xs"
                      data-testid="ragas-clear-btn"
                    >
                      Clear history
                    </button>
                  )}
                </div>
              )}
            </div>
          ) : (
            <>
              {/* Polling overlay when no prior scores (3b) */}
              {polling ? (
                <div className="flex flex-col items-center justify-center gap-2 py-10">
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-sky-600 border-t-transparent" />
                  <p className="text-sm font-medium text-slate-700">Evaluation running…</p>
                  <p className="text-xs text-slate-500">Checking for results every 3s…</p>
                </div>
              ) : (
                <div
                  className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900"
                  data-testid="ragas-status-empty"
                >
                  <ExclamationTriangleIcon className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
                  <p>{emptyStateMessage()}</p>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-3">
          {isGuest && (
            <p className="mr-auto text-xs text-slate-400" data-testid="ragas-guest-info">
              Admin access required to run evaluation.
            </p>
          )}
          <button
            type="button"
            onClick={() => void load()}
            className="btn-secondary text-sm"
            data-testid="ragas-dashboard-refresh-btn"
          >
            <ArrowPathIcon className="h-4 w-4" aria-hidden="true" />
            Refresh
          </button>
          <button
            type="button"
            onClick={() => void runEvaluation()}
            disabled={running || polling || isGuest}
            title={isGuest ? 'Admin access required to run evaluation' : undefined}
            className="btn-primary text-sm disabled:cursor-not-allowed disabled:opacity-60"
            data-testid="ragas-dashboard-run-btn"
          >
            {running || polling ? (
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : (
              <BeakerIcon className="h-4 w-4" aria-hidden="true" />
            )}
            <span>{running || polling ? 'Running' : 'Run'}</span>
          </button>
        </div>
      </div>
    </div>
  )
}
