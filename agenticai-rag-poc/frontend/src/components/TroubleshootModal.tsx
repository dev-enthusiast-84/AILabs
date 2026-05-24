import { useCallback, useEffect, useRef, useState } from 'react'
import {
  BugAntIcon,
  XMarkIcon,
  ArrowUpTrayIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  TrashIcon,
  ChevronDownIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { troubleshootApi, extractErrorMessage } from '@/services/api'
import type {
  TroubleshootComponent,
  TroubleshootEnvironment,
  TroubleshootSeverity,
  TroubleshootHypothesis,
  TroubleshootResponse,
} from '@/types'

const COMPONENTS: { value: TroubleshootComponent; label: string }[] = [
  { value: 'backend', label: 'Backend (FastAPI)' },
  { value: 'frontend', label: 'Frontend (React)' },
  { value: 'agent', label: 'Agent pipeline (LangGraph)' },
  { value: 'rag', label: 'RAG / Vector store' },
  { value: 'auth', label: 'Auth / JWT' },
  { value: 'deployment', label: 'Deployment (Docker/Vercel)' },
  { value: 'other', label: 'Other' },
]

const ENVIRONMENTS: { value: TroubleshootEnvironment; label: string }[] = [
  { value: 'local', label: 'Local (venv)' },
  { value: 'docker', label: 'Docker Compose' },
  { value: 'vercel', label: 'Vercel' },
  { value: 'production', label: 'Production' },
  { value: 'unknown', label: 'Unknown' },
]

const SEVERITIES: { value: TroubleshootSeverity; label: string; dot: string }[] = [
  { value: 'critical', label: 'Critical', dot: 'bg-rose-500' },
  { value: 'high', label: 'High', dot: 'bg-orange-500' },
  { value: 'medium', label: 'Medium', dot: 'bg-amber-400' },
  { value: 'low', label: 'Low', dot: 'bg-emerald-500' },
]

const MAX_SCREENSHOTS = 3
const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']

function confidenceColor(n: number): string {
  if (n >= 75) return 'text-emerald-700 bg-emerald-50 border-emerald-200'
  if (n >= 50) return 'text-amber-700 bg-amber-50 border-amber-200'
  return 'text-rose-700 bg-rose-50 border-rose-200'
}

function confidenceBar(n: number): string {
  if (n >= 75) return 'bg-emerald-500'
  if (n >= 50) return 'bg-amber-400'
  return 'bg-rose-500'
}

function HypothesisCard({ h, defaultOpen }: { h: TroubleshootHypothesis; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-xl border border-slate-200 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors text-left"
      >
        <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold shrink-0 ${confidenceColor(h.confidence)}`}>
          {h.confidence}%
        </span>
        <span className="flex-1 text-sm font-medium text-slate-800 truncate">{h.title}</span>
        {open ? (
          <ChevronDownIcon className="h-4 w-4 text-slate-400 shrink-0" />
        ) : (
          <ChevronRightIcon className="h-4 w-4 text-slate-400 shrink-0" />
        )}
      </button>
      {open && (
        <div className="px-4 pb-4 pt-3 bg-white space-y-2">
          <div className="h-1.5 w-full rounded-full bg-slate-100 overflow-hidden">
            <div
              className={`h-full rounded-full ${confidenceBar(h.confidence)}`}
              style={{ width: `${h.confidence}%` }}
            />
          </div>
          <p className="text-sm text-slate-600">{h.explanation}</p>
        </div>
      )}
    </div>
  )
}

interface Props {
  open: boolean
  onClose: () => void
}

export default function TroubleshootModal({ open, onClose }: Props) {
  const [errorMessage, setErrorMessage] = useState('')
  const [logContent, setLogContent] = useState('')
  const [component, setComponent] = useState<TroubleshootComponent | ''>('')
  const [environment, setEnvironment] = useState<TroubleshootEnvironment | ''>('')
  const [severity, setSeverity] = useState<TroubleshootSeverity | ''>('')
  const [screenshots, setScreenshots] = useState<File[]>([])
  const [previews, setPreviews] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<TroubleshootResponse | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Reset when closed
  useEffect(() => {
    if (!open) {
      setResult(null)
      setLoading(false)
    }
  }, [open])

  // Revoke object URLs on unmount / screenshot change
  useEffect(() => {
    return () => { previews.forEach((url) => URL.revokeObjectURL(url)) }
  }, [previews])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  const addScreenshots = useCallback((files: FileList | null) => {
    if (!files) return
    const valid = Array.from(files)
      .filter((f) => ACCEPTED_TYPES.includes(f.type))
      .slice(0, MAX_SCREENSHOTS - screenshots.length)
    if (!valid.length) return
    setScreenshots((prev) => [...prev, ...valid])
    setPreviews((prev) => [...prev, ...valid.map((f) => URL.createObjectURL(f))])
  }, [screenshots.length])

  const removeScreenshot = useCallback((idx: number) => {
    URL.revokeObjectURL(previews[idx])
    setScreenshots((prev) => prev.filter((_, i) => i !== idx))
    setPreviews((prev) => prev.filter((_, i) => i !== idx))
  }, [previews])

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    addScreenshots(e.dataTransfer.files)
  }, [addScreenshots])

  const handleAnalyze = useCallback(async () => {
    if (!errorMessage.trim()) {
      toast.error('Paste an error message or stack trace first.')
      return
    }
    setLoading(true)
    setResult(null)
    try {
      const res = await troubleshootApi.analyze({
        errorMessage: errorMessage.trim(),
        logContent: logContent.trim() || undefined,
        component: component || undefined,
        environment: environment || undefined,
        severity: severity || undefined,
        screenshots,
      })
      setResult(res)
    } catch (err) {
      toast.error(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [errorMessage, logContent, component, environment, severity, screenshots])

  const handleReset = useCallback(() => {
    previews.forEach((url) => URL.revokeObjectURL(url))
    setErrorMessage('')
    setLogContent('')
    setComponent('')
    setEnvironment('')
    setSeverity('')
    setScreenshots([])
    setPreviews([])
    setResult(null)
  }, [previews])

  if (!open) return null

  const categoryColors: Record<string, string> = {
    auth: 'bg-rose-100 text-rose-700',
    config: 'bg-amber-100 text-amber-700',
    network: 'bg-sky-100 text-sky-700',
    vectordb: 'bg-violet-100 text-violet-700',
    llm: 'bg-indigo-100 text-indigo-700',
    ingestion: 'bg-teal-100 text-teal-700',
    agent: 'bg-purple-100 text-purple-700',
    frontend: 'bg-pink-100 text-pink-700',
    deployment: 'bg-orange-100 text-orange-700',
    unknown: 'bg-slate-100 text-slate-600',
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/50 backdrop-blur-sm overflow-y-auto py-8 px-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="troubleshoot-title"
    >
      <div className="bg-white border border-slate-200 rounded-2xl shadow-xl shadow-slate-300/40 w-full max-w-2xl flex flex-col overflow-hidden">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <BugAntIcon className="h-5 w-5 text-sky-600" />
            <h2 id="troubleshoot-title" className="text-base font-semibold text-slate-900">
              Troubleshooting Agent
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 transition-colors"
            aria-label="Close troubleshoot"
            data-testid="troubleshoot-close"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-5 overflow-y-auto max-h-[80vh]">

          {!result ? (
            <>
              {/* Error / stack trace */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  Error message or stack trace <span className="text-rose-500">*</span>
                </label>
                <textarea
                  value={errorMessage}
                  onChange={(e) => setErrorMessage(e.target.value)}
                  placeholder="Paste the full error, exception, or stack trace here…"
                  rows={6}
                  maxLength={8000}
                  className="input text-sm font-mono resize-y w-full"
                  data-testid="troubleshoot-error-input"
                />
                <p className="text-xs text-slate-400 text-right mt-0.5">{errorMessage.length}/8000</p>
              </div>

              {/* Log output */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  Log output <span className="text-slate-400 font-normal">(optional)</span>
                </label>
                <textarea
                  value={logContent}
                  onChange={(e) => setLogContent(e.target.value)}
                  placeholder="Paste relevant log lines (uvicorn, pytest, Docker, browser console)…"
                  rows={4}
                  maxLength={12000}
                  className="input text-sm font-mono resize-y w-full"
                  data-testid="troubleshoot-log-input"
                />
              </div>

              {/* Context selectors */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Component</label>
                  <select
                    value={component}
                    onChange={(e) => setComponent(e.target.value as TroubleshootComponent | '')}
                    className="input text-sm w-full"
                    data-testid="troubleshoot-component"
                  >
                    <option value="">— pick one —</option>
                    {COMPONENTS.map((c) => (
                      <option key={c.value} value={c.value}>{c.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Environment</label>
                  <select
                    value={environment}
                    onChange={(e) => setEnvironment(e.target.value as TroubleshootEnvironment | '')}
                    className="input text-sm w-full"
                    data-testid="troubleshoot-environment"
                  >
                    <option value="">— pick one —</option>
                    {ENVIRONMENTS.map((e) => (
                      <option key={e.value} value={e.value}>{e.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Severity</label>
                  <select
                    value={severity}
                    onChange={(e) => setSeverity(e.target.value as TroubleshootSeverity | '')}
                    className="input text-sm w-full"
                    data-testid="troubleshoot-severity"
                  >
                    <option value="">— pick one —</option>
                    {SEVERITIES.map((s) => (
                      <option key={s.value} value={s.value}>{s.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Screenshot upload */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  Screenshots <span className="text-slate-400 font-normal">(optional · up to {MAX_SCREENSHOTS})</span>
                </label>
                <div
                  onDrop={handleDrop}
                  onDragOver={(e) => e.preventDefault()}
                  onClick={() => screenshots.length < MAX_SCREENSHOTS && fileInputRef.current?.click()}
                  className={`relative flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed py-6 transition-colors cursor-pointer
                    ${screenshots.length >= MAX_SCREENSHOTS
                      ? 'border-slate-200 bg-slate-50 cursor-not-allowed opacity-60'
                      : 'border-slate-300 hover:border-sky-400 hover:bg-sky-50/40'}`}
                  data-testid="screenshot-dropzone"
                >
                  <ArrowUpTrayIcon className="h-6 w-6 text-slate-400" />
                  <p className="text-xs text-slate-500">
                    {screenshots.length >= MAX_SCREENSHOTS
                      ? 'Maximum screenshots reached'
                      : 'Drop PNG/JPEG/WebP here or click to browse'}
                  </p>
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  multiple
                  className="hidden"
                  onChange={(e) => addScreenshots(e.target.files)}
                  data-testid="screenshot-file-input"
                />

                {previews.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-3">
                    {previews.map((src, idx) => (
                      <div key={idx} className="relative group">
                        <img
                          src={src}
                          alt={`Screenshot ${idx + 1}`}
                          className="h-20 w-28 object-cover rounded-lg border border-slate-200"
                        />
                        <button
                          type="button"
                          onClick={() => removeScreenshot(idx)}
                          className="absolute -top-1.5 -right-1.5 hidden group-hover:flex items-center justify-center w-5 h-5 rounded-full bg-rose-500 text-white shadow"
                          aria-label={`Remove screenshot ${idx + 1}`}
                        >
                          <TrashIcon className="h-3 w-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            /* ── Results panel ── */
            <div className="space-y-5">
              {/* Category + root cause */}
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-2">
                <div className="flex items-center gap-2">
                  <ExclamationTriangleIcon className="h-4 w-4 text-slate-600 shrink-0" />
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold capitalize ${categoryColors[result.error_category] ?? 'bg-slate-100 text-slate-600'}`}
                  >
                    {result.error_category.replace('_', ' ')}
                  </span>
                </div>
                <p className="text-sm font-medium text-slate-800">{result.root_cause}</p>
              </div>

              {/* Hypotheses */}
              {result.hypotheses.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                    Ranked hypotheses
                  </h3>
                  <div className="space-y-2">
                    {result.hypotheses.map((h) => (
                      <HypothesisCard key={h.rank} h={h} defaultOpen={h.rank === 1} />
                    ))}
                  </div>
                </section>
              )}

              {/* Remediation steps */}
              {result.remediation_steps.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                    Remediation steps
                  </h3>
                  <ol className="space-y-2">
                    {result.remediation_steps.map((step, i) => (
                      <li key={i} className="flex gap-3 text-sm text-slate-700">
                        <span className="flex-none flex items-center justify-center w-6 h-6 rounded-full bg-sky-100 text-sky-700 text-xs font-bold shrink-0 mt-0.5">
                          {i + 1}
                        </span>
                        <span>{step.replace(/^\d+\.\s*/, '')}</span>
                      </li>
                    ))}
                  </ol>
                </section>
              )}

              {/* Affected files */}
              {result.affected_files.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                    Likely affected files
                  </h3>
                  <ul className="space-y-1">
                    {result.affected_files.map((f, i) => (
                      <li key={i} className="font-mono text-xs text-sky-700 bg-sky-50 rounded px-2 py-1 border border-sky-100">
                        {f}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* Follow-up questions */}
              {result.follow_up_questions.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                    Need more info
                  </h3>
                  <ul className="space-y-1.5">
                    {result.follow_up_questions.map((q, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-slate-600">
                        <CheckCircleIcon className="h-4 w-4 text-sky-500 shrink-0 mt-0.5" />
                        {q}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 px-6 py-4 border-t border-slate-200 bg-slate-50">
          {result ? (
            <>
              <button
                type="button"
                onClick={handleReset}
                className="btn-secondary text-sm"
                data-testid="troubleshoot-reset-btn"
              >
                New analysis
              </button>
              <button onClick={onClose} className="btn-primary text-sm">
                Done
              </button>
            </>
          ) : (
            <>
              <button onClick={onClose} className="btn-secondary text-sm">
                Cancel
              </button>
              <button
                type="button"
                onClick={handleAnalyze}
                disabled={loading || !errorMessage.trim()}
                className="btn-primary text-sm disabled:opacity-50 min-w-[120px]"
                data-testid="troubleshoot-analyze-btn"
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                    Analysing…
                  </span>
                ) : (
                  'Analyse'
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
