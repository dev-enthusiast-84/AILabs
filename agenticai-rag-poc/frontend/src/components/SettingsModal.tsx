import { useEffect, useMemo, useRef, useState } from 'react'
import { useToggleSet } from '@/hooks/useToggleSet'
import {
  XMarkIcon,
  EyeIcon,
  EyeSlashIcon,
  Cog6ToothIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  LockClosedIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline'
import axios from 'axios'
import toast from 'react-hot-toast'
import { settingsApi, extractErrorMessage } from '@/services/api'
import { useAuthStore } from '@/store/authStore'
import type { SettingsResponse, SettingsUpdateRequest, RagasScores } from '@/types'

const SOURCE_LABEL: Record<string, string> = {
  runtime: 'set via UI',
  environment: 'from environment',
  not_configured: 'not configured',
}

// Client-side mirrors of the server allowlist and validation rules.
// The server always re-validates — these are for instant UX feedback only.
const ALLOWED_MODELS = [
  'gpt-4o',
  'gpt-4o-mini',
  'gpt-4-turbo',
  'gpt-4',
  'gpt-3.5-turbo',
  'o1-preview',
  'o1-mini',
]
const ALLOWED_EMBEDDING_MODELS = [
  'text-embedding-3-small',
  'text-embedding-3-large',
  'text-embedding-ada-002',
]

// Mirrors backend regex: sk(-proj)?-[A-Za-z0-9_-]{20,}
const API_KEY_RE = /^sk(-proj)?-[A-Za-z0-9_\-]{20,}$/
const PINECONE_INDEX_RE = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/
const PINECONE_NAMESPACE_RE = /^[A-Za-z0-9_.:-]+$/
const PINECONE_REGION_RE = /^[a-z0-9-]+$/

function validateApiKey(key: string): string | null {
  if (!key.trim()) return 'API key must not be empty.'
  if (key.length > 200) return 'API key is too long.'
  if (!API_KEY_RE.test(key.trim()))
    return "Invalid format. Expected 'sk-…' followed by at least 20 alphanumeric characters."
  return null
}

function validateModel(model: string): string | null {
  if (!model.trim()) return 'Please select a model.'
  if (!ALLOWED_MODELS.includes(model)) return 'Selected model is not in the allowed list.'
  return null
}

function validatePineconeKey(key: string): string | null {
  const trimmed = key.trim()
  if (!trimmed) return 'Pinecone API key must not be empty.'
  if (trimmed.length > 300) return 'Pinecone API key is too long.'
  if (/\s/.test(trimmed)) return 'Pinecone API key must not contain whitespace.'
  return null
}

function validateBlobToken(token: string): string | null {
  const trimmed = token.trim()
  if (!trimmed) return 'Blob read/write token must not be empty.'
  if (trimmed.length > 500) return 'Blob read/write token is too long.'
  if (/\s/.test(trimmed)) return 'Blob read/write token must not contain whitespace.'
  return null
}

function validatePineconeIndex(name: string): string | null {
  const trimmed = name.trim()
  if (!trimmed) return 'Pinecone index name is required.'
  if (trimmed.length > 45) return 'Pinecone index name must be 45 characters or fewer.'
  if (!PINECONE_INDEX_RE.test(trimmed)) return 'Use lowercase letters, numbers, and hyphens.'
  return null
}

function validatePineconeNamespace(namespace: string): string | null {
  const trimmed = namespace.trim()
  if (!trimmed) return null
  if (trimmed.length > 100) return 'Pinecone namespace must be 100 characters or fewer.'
  if (!PINECONE_NAMESPACE_RE.test(trimmed)) return 'Use letters, numbers, _, ., :, and - only.'
  return null
}

function validatePineconeRegion(region: string): string | null {
  const trimmed = region.trim()
  if (!trimmed) return 'Pinecone region is required.'
  if (trimmed.length > 50) return 'Pinecone region must be 50 characters or fewer.'
  if (!PINECONE_REGION_RE.test(trimmed)) return 'Use lowercase letters, numbers, and hyphens.'
  return null
}

// ── Accordion section wrapper ──────────────────────────────────────────────────
function SettingsSection({
  title,
  open,
  onToggle,
  children,
}: {
  id: string
  title: string
  open: boolean
  onToggle: () => void
  children: React.ReactNode
}) {
  return (
    <div className="border border-slate-200 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-2.5 text-sm font-medium text-slate-700 hover:text-slate-900 hover:bg-slate-50 transition-colors"
        aria-expanded={open}
      >
        <span>{title}</span>
        <ChevronRightIcon
          className={`h-4 w-4 text-slate-400 transition-transform ${open ? 'rotate-90' : ''}`}
        />
      </button>
      {open && (
        <div className="px-4 pb-4 pt-2 space-y-4 border-t border-slate-200 bg-slate-50/40">
          {children}
        </div>
      )}
    </div>
  )
}

// ── Numeric slider with label and live value ───────────────────────────────────
function LabeledSlider({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
  hint,
  disabled = false,
}: {
  label: string
  value: number
  min: number
  max: number
  step?: number
  onChange: (v: number) => void
  hint?: string
  disabled?: boolean
}) {
  return (
    <div>
      <div className="flex justify-between mb-1">
        <label className="text-xs font-medium text-slate-600">{label}</label>
        <span className="text-xs text-sky-600 font-mono">{value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={disabled}
        className="w-full accent-sky-500 disabled:opacity-50"
      />
      {hint && <p className="text-xs text-slate-400 mt-0.5">{hint}</p>}
    </div>
  )
}

// ── Ragas metric tile ──────────────────────────────────────────────────────────
function MetricTile({ label, score }: { label: string; score: number }) {
  const pct = Math.round(score * 100)
  const colorClass =
    score >= 0.75
      ? { text: 'text-emerald-700', bg: 'bg-emerald-500' }
      : score >= 0.5
      ? { text: 'text-amber-700', bg: 'bg-amber-500' }
      : { text: 'text-rose-700', bg: 'bg-rose-500' }
  return (
    <div className="bg-white border border-slate-200 rounded-lg p-3">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`text-lg font-bold ${colorClass.text}`}>{pct}%</p>
      <div className="mt-1.5 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`h-full ${colorClass.bg} rounded-full`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

interface Props {
  open: boolean
  onClose: () => void
  isGuest?: boolean
  prerequisiteNotice?: string | null
}

export default function SettingsModal({ open, onClose, isGuest = false, prerequisiteNotice = null }: Props) {
  const [current, setCurrent] = useState<SettingsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  // Section 1 — AI Model (all users)
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [embeddingModel, setEmbeddingModel] = useState('text-embedding-3-small')
  const [showKey, setShowKey] = useState(false)
  const [keyError, setKeyError] = useState<string | null>(null)
  const [modelError, setModelError] = useState<string | null>(null)

  // Section 2 — Per-node models (empty string = inherit global)
  const [plannerModel, setPlannerModel] = useState('')
  const [generatorModel, setGeneratorModel] = useState('')
  const [validatorModel, setValidatorModel] = useState('')

  // Section 3 — Retrieval
  const [retrieverK, setRetrieverK] = useState(4)
  const [similarityThreshold, setSimilarityThreshold] = useState(0.0)
  const [useMMR, setUseMMR] = useState(false)
  const [fetchK, setFetchK] = useState(20)
  const [maxContextChunks, setMaxContextChunks] = useState(4)

  // Section 4 — Generation limits
  const [maxCompletionTokens, setMaxCompletionTokens] = useState(1024)
  const [tokenBudgetWarning, setTokenBudgetWarning] = useState(800)

  // Section 5 — LangSmith observability
  const [tracingEnabled, setTracingEnabled] = useState(false)
  const [langsmithKey, setLangsmithKey] = useState('')
  const [langsmithProject, setLangsmithProject] = useState('agenticai-rag-poc')
  const [showLangsmithKey, setShowLangsmithKey] = useState(false)

  // Section 6 — Vector store / Pinecone
  const [vectorStoreType, setVectorStoreType] = useState<SettingsResponse['vector_store_type']>('chroma')
  const [pineconeKey, setPineconeKey] = useState('')
  const [pineconeIndex, setPineconeIndex] = useState('agenticai-rag-poc-documents')
  const [pineconeNamespace, setPineconeNamespace] = useState('agenticai-rag-poc')
  const [pineconeCloud, setPineconeCloud] = useState('aws')
  const [pineconeRegion, setPineconeRegion] = useState('us-east-1')
  const [showPineconeKey, setShowPineconeKey] = useState(false)
  const [pineconeKeyError, setPineconeKeyError] = useState<string | null>(null)
  const [pineconeIndexError, setPineconeIndexError] = useState<string | null>(null)
  const [pineconeNamespaceError, setPineconeNamespaceError] = useState<string | null>(null)
  const [pineconeRegionError, setPineconeRegionError] = useState<string | null>(null)
  const [fileStoreType, setFileStoreType] = useState('local')
  const [blobToken, setBlobToken] = useState('')
  const [showBlobToken, setShowBlobToken] = useState(false)
  const [blobTokenError, setBlobTokenError] = useState<string | null>(null)

  // Section 7 — Ragas evaluation (admin only)
  const [ragasScores, setRagasScores] = useState<RagasScores | null>(null)
  const [ragasNotRun, setRagasNotRun] = useState(false)
  const [ragasRunning, setRagasRunning] = useState(false)

  // Section 8 — Pipeline feature flags (admin only)
  const [hybridBm25, setHybridBm25] = useState(true)
  const [relevanceGrader, setRelevanceGrader] = useState(false)
  const [ragasAutoEval, setRagasAutoEval] = useState(false)
  const [rerankerType, setRerankerType] = useState('none')
  const [chunkerType, setChunkerType] = useState('recursive')
  const [chunkSize, setChunkSize] = useState(800)
  const [chunkOverlap, setChunkOverlap] = useState(100)

  const [openSections, toggleSection] = useToggleSet(['vector-store'])

  const { guestSettingsUsed, markGuestSettingsUsed } = useAuthStore()
  const serverLockKnown = current?.guest_settings_locked !== undefined
  const locked = isGuest && (serverLockKnown ? Boolean(current?.guest_settings_locked) : guestSettingsUsed)
  const staleLocalGuestLock = isGuest && guestSettingsUsed && serverLockKnown && !current?.guest_settings_locked
  const guestSettingsRecoverable = Boolean(current?.guest_settings_recoverable || staleLocalGuestLock)
  const firstFocusRef = useRef<HTMLSelectElement>(null)

  const hasCostImpactingChanges = useMemo(() => {
    if (!current) return false
    const pineconeSelected = vectorStoreType === 'pinecone'
    const blobEnabled = vectorStoreType === 'blob' || fileStoreType === 'blob'
    return Boolean(
      apiKey.trim() ||
        model !== current.model ||
        embeddingModel !== (current.embedding_model ?? 'text-embedding-3-small') ||
        pineconeKey.trim() ||
        (pineconeSelected && (
          pineconeIndex !== current.pinecone_index_name ||
          pineconeNamespace !== current.pinecone_namespace ||
          pineconeCloud !== current.pinecone_cloud ||
          pineconeRegion !== current.pinecone_region
        )) ||
        (blobEnabled && blobToken.trim()) ||
        (!isGuest && (
          plannerModel !== (current.planner_model ?? '') ||
          generatorModel !== (current.generator_model ?? '') ||
          validatorModel !== (current.validator_model ?? '') ||
          retrieverK !== (current.retriever_k ?? 4) ||
          similarityThreshold !== (current.similarity_score_threshold ?? 0.0) ||
          fetchK !== (current.retriever_fetch_k ?? 20) ||
          maxContextChunks !== (current.max_context_chunks ?? 4) ||
          maxCompletionTokens !== (current.max_completion_tokens ?? 1024) ||
          tracingEnabled !== (current.langchain_tracing_v2 ?? false) ||
          langsmithKey.trim()
        ))
    )
  }, [
    apiKey,
    blobToken,
    current,
    embeddingModel,
    fetchK,
    fileStoreType,
    generatorModel,
    isGuest,
    langsmithKey,
    maxCompletionTokens,
    maxContextChunks,
    model,
    pineconeCloud,
    pineconeIndex,
    pineconeKey,
    pineconeNamespace,
    pineconeRegion,
    plannerModel,
    retrieverK,
    similarityThreshold,
    tracingEnabled,
    validatorModel,
    vectorStoreType,
  ])

  // Load current settings when modal opens
  useEffect(() => {
    if (!open) return
    setLoading(true)
    settingsApi
      .get()
      .then((data) => {
        setCurrent(data)
        // Section 1
        setModel(data.model)
        setEmbeddingModel(data.embedding_model ?? 'text-embedding-3-small')
        setApiKey('')
        setKeyError(null)
        setModelError(null)
        // Section 2
        setPlannerModel(data.planner_model ?? '')
        setGeneratorModel(data.generator_model ?? '')
        setValidatorModel(data.validator_model ?? '')
        // Section 3
        setRetrieverK(data.retriever_k ?? 4)
        setSimilarityThreshold(data.similarity_score_threshold ?? 0.0)
        setUseMMR(data.retriever_use_mmr ?? false)
        setFetchK(data.retriever_fetch_k ?? 20)
        setMaxContextChunks(data.max_context_chunks ?? 4)
        // Section 4
        setMaxCompletionTokens(data.max_completion_tokens ?? 1024)
        setTokenBudgetWarning(data.token_budget_warning_threshold ?? 800)
        // Section 5
        setTracingEnabled(data.langchain_tracing_v2 ?? false)
        setLangsmithKey('') // never pre-fill — user must re-enter if changing
        setLangsmithProject(data.langchain_project ?? 'agenticai-rag-poc')
        // Section 6
        setVectorStoreType(data.vector_store_type ?? 'chroma')
        setPineconeKey('') // never pre-fill — user must re-enter if changing
        setPineconeIndex(data.pinecone_index_name ?? 'agenticai-rag-poc-documents')
        setPineconeNamespace(data.pinecone_namespace ?? 'agenticai-rag-poc')
        setPineconeCloud(data.pinecone_cloud ?? 'aws')
        setPineconeRegion(data.pinecone_region ?? 'us-east-1')
        setPineconeKeyError(null)
        setPineconeIndexError(null)
        setPineconeNamespaceError(null)
        setPineconeRegionError(null)
        setFileStoreType(data.file_store_type ?? 'local')
        setBlobToken('')
        setBlobTokenError(null)
        // Section 8 — Pipeline feature flags
        setHybridBm25(data.retriever_hybrid_bm25 ?? true)
        setRelevanceGrader(data.relevance_grader_enabled ?? false)
        setRagasAutoEval(data.ragas_evaluation_enabled ?? false)
        setRerankerType(data.reranker_type ?? 'none')
        setChunkerType(data.chunker_type ?? 'recursive')
        setChunkSize(data.chunk_size ?? 800)
        setChunkOverlap(data.chunk_overlap ?? 100)
      })
      .catch(() => toast.error('Could not load settings.'))
      .finally(() => setLoading(false))
    if (!isGuest) {
      settingsApi.getRagasScores().then((scores) => {
        if (scores) {
          setRagasScores(scores)
        } else {
          setRagasNotRun(true)
        }
      })
    }
    setTimeout(() => firstFocusRef.current?.focus(), 50)
  }, [open, isGuest])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  const handleSave = async () => {
    const payload: SettingsUpdateRequest = {}
    let hasError = false

    // Section 1 validation
    if (apiKey.trim()) {
      const err = validateApiKey(apiKey)
      if (err) {
        setKeyError(err)
        hasError = true
      } else {
        setKeyError(null)
        payload.api_key = apiKey.trim()
      }
    } else {
      setKeyError(null)
    }

    const mErr = validateModel(model)
    if (mErr) {
      setModelError(mErr)
      hasError = true
    } else {
      setModelError(null)
      payload.model = model
    }
    if (embeddingModel !== (current?.embedding_model ?? 'text-embedding-3-small')) {
      payload.embedding_model = embeddingModel
    }

    if (hasError) return

    // Sections 2–5 (admin only — guests never see these fields)
    if (!isGuest) {
      if (plannerModel !== (current?.planner_model ?? ''))
        payload.planner_model = plannerModel
      if (generatorModel !== (current?.generator_model ?? ''))
        payload.generator_model = generatorModel
      if (validatorModel !== (current?.validator_model ?? ''))
        payload.validator_model = validatorModel
      if (retrieverK !== (current?.retriever_k ?? 4))
        payload.retriever_k = retrieverK
      if (similarityThreshold !== (current?.similarity_score_threshold ?? 0.0))
        payload.similarity_score_threshold = similarityThreshold
      if (useMMR !== (current?.retriever_use_mmr ?? false))
        payload.retriever_use_mmr = useMMR
      if (fetchK !== (current?.retriever_fetch_k ?? 20))
        payload.retriever_fetch_k = fetchK
      if (maxContextChunks !== (current?.max_context_chunks ?? 4))
        payload.max_context_chunks = maxContextChunks
      if (maxCompletionTokens !== (current?.max_completion_tokens ?? 1024))
        payload.max_completion_tokens = maxCompletionTokens
      if (tokenBudgetWarning !== (current?.token_budget_warning_threshold ?? 800))
        payload.token_budget_warning_threshold = tokenBudgetWarning
      if (tracingEnabled !== (current?.langchain_tracing_v2 ?? false))
        payload.langchain_tracing_v2 = tracingEnabled
      if (langsmithKey.trim())
        payload.langchain_api_key = langsmithKey.trim()
      if (langsmithProject !== (current?.langchain_project ?? 'agenticai-rag-poc'))
        payload.langchain_project = langsmithProject
      // Section 8 — Pipeline feature flags
      if (hybridBm25 !== (current?.retriever_hybrid_bm25 ?? true))
        payload.retriever_hybrid_bm25 = hybridBm25
      if (relevanceGrader !== (current?.relevance_grader_enabled ?? false))
        payload.relevance_grader_enabled = relevanceGrader
      if (ragasAutoEval !== (current?.ragas_evaluation_enabled ?? false))
        payload.ragas_evaluation_enabled = ragasAutoEval
      if (rerankerType !== (current?.reranker_type ?? 'none'))
        payload.reranker_type = rerankerType
      if (chunkerType !== (current?.chunker_type ?? 'recursive'))
        payload.chunker_type = chunkerType
      if (chunkSize !== (current?.chunk_size ?? 800))
        payload.chunk_size = chunkSize
      if (chunkOverlap !== (current?.chunk_overlap ?? 100))
        payload.chunk_overlap = chunkOverlap
    }

    // Pinecone settings are available to admins and guests. VECTOR_STORE_TYPE is
    // deployment config; UI only supplies Pinecone details when that store is active.
    const pineconeSelected = vectorStoreType === 'pinecone'
    const blobEnabled = vectorStoreType === 'blob' || fileStoreType === 'blob'

    if (pineconeKey.trim()) {
      const err = validatePineconeKey(pineconeKey)
      if (err) {
        setPineconeKeyError(err)
        hasError = true
      } else {
        setPineconeKeyError(null)
        payload.pinecone_api_key = pineconeKey.trim()
      }
    } else if (pineconeSelected && current?.pinecone_api_key_source === 'not_configured') {
      setPineconeKeyError('Pinecone API key is required before using Pinecone.')
      hasError = true
    } else {
      setPineconeKeyError(null)
    }

    if (pineconeSelected) {
      const indexErr = validatePineconeIndex(pineconeIndex)
      if (indexErr) {
        setPineconeIndexError(indexErr)
        hasError = true
      } else {
        setPineconeIndexError(null)
        if (pineconeIndex !== (current?.pinecone_index_name ?? 'agenticai-rag-poc-documents'))
          payload.pinecone_index_name = pineconeIndex.trim().toLowerCase()
      }

      const namespaceErr = validatePineconeNamespace(pineconeNamespace)
      if (namespaceErr) {
        setPineconeNamespaceError(namespaceErr)
        hasError = true
      } else {
        setPineconeNamespaceError(null)
        if (pineconeNamespace !== (current?.pinecone_namespace ?? 'agenticai-rag-poc'))
          payload.pinecone_namespace = pineconeNamespace.trim()
      }

      if (pineconeCloud !== (current?.pinecone_cloud ?? 'aws'))
        payload.pinecone_cloud = pineconeCloud

      const regionErr = validatePineconeRegion(pineconeRegion)
      if (regionErr) {
        setPineconeRegionError(regionErr)
        hasError = true
      } else {
        setPineconeRegionError(null)
        if (pineconeRegion !== (current?.pinecone_region ?? 'us-east-1'))
          payload.pinecone_region = pineconeRegion.trim().toLowerCase()
      }
    } else {
      setPineconeKeyError(null)
      setPineconeIndexError(null)
      setPineconeNamespaceError(null)
      setPineconeRegionError(null)
    }

    if (blobToken.trim()) {
      const err = validateBlobToken(blobToken)
      if (err) {
        setBlobTokenError(err)
        hasError = true
      } else {
        setBlobTokenError(null)
        payload.blob_read_write_token = blobToken.trim()
      }
    } else if (blobEnabled && current?.blob_read_write_token_source === 'not_configured') {
      setBlobTokenError('Blob read/write token is required before using Blob storage.')
      hasError = true
    } else {
      setBlobTokenError(null)
    }

    if (hasError) return

    // Check if there's anything to save
    const hasChanges = Object.keys(payload).length > 0
    if (!hasChanges) {
      toast('Nothing to save — change at least one field.')
      return
    }

    setSaving(true)
    try {
      const updated = await settingsApi.update(payload)
      setCurrent(updated)
      setApiKey('')
      if (isGuest) markGuestSettingsUsed()
      toast.success('Settings saved.')
      onClose()
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        markGuestSettingsUsed()
        toast.error('Settings can only be configured once per guest session.')
        onClose()
        return
      }
      const raw = extractErrorMessage(err)
      try {
        const parsed = JSON.parse(raw)
        if (parsed.api_key) setKeyError(parsed.api_key)
        if (parsed.model) setModelError(parsed.model)
        if (parsed.pinecone_api_key) setPineconeKeyError(parsed.pinecone_api_key)
        if (parsed.pinecone_index_name) setPineconeIndexError(parsed.pinecone_index_name)
        if (parsed.pinecone_namespace) setPineconeNamespaceError(parsed.pinecone_namespace)
        if (parsed.pinecone_region) setPineconeRegionError(parsed.pinecone_region)
        if (parsed.blob_read_write_token) setBlobTokenError(parsed.blob_read_write_token)
      } catch {
        toast.error(raw)
      }
    } finally {
      setSaving(false)
    }
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-title"
    >
      <div className="bg-white border border-slate-200 rounded-2xl shadow-xl shadow-slate-300/40 w-full max-w-md overflow-hidden max-h-[90vh] flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 shrink-0">
          <div className="flex items-center gap-2">
            <Cog6ToothIcon className="h-5 w-5 text-sky-600" />
            <h2 id="settings-title" className="text-base font-semibold text-slate-900">
              Model Settings
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 transition-colors"
            aria-label="Close settings"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        {/* Body — scrollable */}
        <div className="px-6 py-5 space-y-5 overflow-y-auto flex-1">
          {isGuest && (
            <div
              className={`text-xs rounded-lg px-3 py-2.5 border ${
                locked
                  ? 'bg-amber-50 border-amber-200 text-amber-700'
                  : guestSettingsRecoverable
                    ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                  : 'bg-sky-50 border-sky-200 text-sky-700'
              }`}
            >
              {locked ? (
                <div className="flex items-start gap-2">
                  <LockClosedIcon className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                  <span>Settings are locked for this session. Start a new guest session to change them.</span>
                </div>
              ) : guestSettingsRecoverable ? (
                <div className="space-y-1">
                  <p className="font-semibold text-emerald-700">Guest settings need to be re-entered:</p>
                  <p className="text-emerald-600">
                    Your guest session is still valid, but the app restarted and no longer has your runtime settings.
                    Re-enter the required keys and save to continue.
                  </p>
                </div>
              ) : (
                <div className="space-y-1">
                  <p className="font-semibold text-sky-700">Guest settings — one-time configuration:</p>
                  <ul className="list-disc list-inside space-y-0.5 text-sky-600">
                    <li>
                      Enter your <strong className="text-sky-700">OpenAI API key</strong> to enable document Q&amp;A.
                    </li>
                    <li>
                      Select the <strong className="text-sky-700">LLM model</strong> you want to use.
                    </li>
                    <li>
                      Add <strong className="text-sky-700">Pinecone settings</strong> if deployment uses Pinecone storage.
                    </li>
                    <li>
                      Add a <strong className="text-sky-700">Blob token</strong> if deployment uses Blob storage.
                    </li>
                    <li>
                      Click <strong className="text-sky-700">Save</strong> — these settings lock after your first save.
                    </li>
                  </ul>
                </div>
              )}
            </div>
          )}

          {prerequisiteNotice && !loading && (
            <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2.5 text-xs text-sky-800">
              <p className="font-semibold text-sky-900">Settings required before continuing</p>
              <p className="mt-1">{prerequisiteNotice}</p>
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center gap-3 py-6">
              <div className="w-4 h-4 rounded-full border-2 border-sky-500 border-t-transparent animate-spin" />
              <p className="text-sm text-slate-400">Loading…</p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* ── Section 1: AI Model (always visible, always expanded) ── */}
              <div className="space-y-4">
                {/* Model selector */}
                <div>
                  <label
                    htmlFor="model-select"
                    className="block text-sm font-medium text-slate-600 mb-1.5"
                  >
                    LLM Model
                  </label>
                  <select
                    id="model-select"
                    ref={firstFocusRef}
                    value={model}
                    onChange={(e) => {
                      setModel(e.target.value)
                      setModelError(null)
                    }}
                    disabled={locked}
                    className={`input ${modelError ? 'border-rose-400 focus:border-rose-500 focus:ring-rose-400/30' : ''} ${locked ? 'opacity-60 cursor-not-allowed' : ''}`}
                    data-testid="model-select"
                  >
                    {ALLOWED_MODELS.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                  {modelError && (
                    <p className="mt-1 flex items-center gap-1 text-xs text-rose-600">
                      <ExclamationCircleIcon className="h-3.5 w-3.5 shrink-0" />
                      {modelError}
                    </p>
                  )}
                </div>

                <div>
                  <label
                    htmlFor="embedding-model-select"
                    className="block text-sm font-medium text-slate-600 mb-1.5"
                  >
                    Embedding Model
                  </label>
                  <select
                    id="embedding-model-select"
                    value={embeddingModel}
                    onChange={(e) => setEmbeddingModel(e.target.value)}
                    disabled={locked}
                    className={`input ${locked ? 'opacity-60 cursor-not-allowed' : ''}`}
                    data-testid="embedding-model-select"
                  >
                    {ALLOWED_EMBEDDING_MODELS.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-slate-400 mt-1">
                    Used when indexing uploads and searching documents.
                  </p>
                </div>

                {/* API Key */}
                <div>
                  <label
                    htmlFor="api-key-input"
                    className="block text-sm font-medium text-slate-600 mb-1.5"
                  >
                    OpenAI API Key
                  </label>

                  {current && (
                    <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
                      <CheckCircleIcon className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                      <span>
                        Current:{' '}
                        <code className="font-mono bg-slate-100 text-sky-700 px-1.5 py-0.5 rounded">
                          {current.api_key_masked || '—'}
                        </code>{' '}
                        ({SOURCE_LABEL[current.api_key_source] ?? current.api_key_source})
                      </span>
                    </div>
                  )}

                  <div className="relative">
                    <input
                      id="api-key-input"
                      data-testid="api-key-input"
                      type={showKey ? 'text' : 'password'}
                      value={apiKey}
                      onChange={(e) => {
                        setApiKey(e.target.value)
                        setKeyError(null)
                      }}
                      placeholder={locked ? 'Locked for this session' : 'sk-… (leave blank to keep current)'}
                      maxLength={200}
                      autoComplete="off"
                      spellCheck={false}
                      disabled={locked}
                      className={`input pr-10 font-mono text-sm ${
                        keyError ? 'border-rose-400 focus:border-rose-500 focus:ring-rose-400/30' : ''
                      } ${locked ? 'opacity-60 cursor-not-allowed' : ''}`}
                      aria-describedby="api-key-hint"
                    />
                    <button
                      type="button"
                      onClick={() => setShowKey((v) => !v)}
                      className="absolute inset-y-0 right-2 flex items-center text-slate-400 hover:text-slate-700 transition-colors"
                      aria-label={showKey ? 'Hide API key' : 'Show API key'}
                      tabIndex={-1}
                    >
                      {showKey ? (
                        <EyeSlashIcon className="h-4 w-4" />
                      ) : (
                        <EyeIcon className="h-4 w-4" />
                      )}
                    </button>
                  </div>

                  {keyError && (
                    <p className="mt-1 flex items-center gap-1 text-xs text-rose-600">
                      <ExclamationCircleIcon className="h-3.5 w-3.5 shrink-0" />
                      {keyError}
                    </p>
                  )}
                  <p id="api-key-hint" className="mt-1 text-xs text-slate-400">
                    Your key is masked after saving and never stored on disk.
                  </p>
                </div>
              </div>

              {/* ── Sections 2–5: Admin only ── */}
              {!isGuest && (
                <>
                  {/* Section 2 — Per-node models */}
                  <SettingsSection
                    id="per-node"
                    title="Advanced model settings"
                    open={openSections.has('per-node')}
                    onToggle={() => toggleSection('per-node')}
                  >
                    {/* Planner Model */}
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">
                        Planner Model
                      </label>
                      <select
                        value={plannerModel}
                        onChange={(e) => setPlannerModel(e.target.value)}
                        className="input text-sm"
                      >
                        <option value="">(inherit global model)</option>
                        {ALLOWED_MODELS.map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Query rewriting — gpt-4o-mini is sufficient.
                      </p>
                    </div>

                    {/* Generator Model */}
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">
                        Generator Model
                      </label>
                      <select
                        value={generatorModel}
                        onChange={(e) => setGeneratorModel(e.target.value)}
                        className="input text-sm"
                      >
                        <option value="">(inherit global model)</option>
                        {ALLOWED_MODELS.map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Answer generation — gpt-4o recommended for production.
                      </p>
                    </div>

                    {/* Validator Model */}
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">
                        Validator Model
                      </label>
                      <select
                        value={validatorModel}
                        onChange={(e) => setValidatorModel(e.target.value)}
                        className="input text-sm"
                      >
                        <option value="">(inherit global model)</option>
                        {ALLOWED_MODELS.map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Leave as inherit to use the global model above.
                      </p>
                    </div>
                  </SettingsSection>

                  {/* Section 3 — Retrieval */}
                  <SettingsSection
                    id="retrieval"
                    title="Retrieval settings"
                    open={openSections.has('retrieval')}
                    onToggle={() => toggleSection('retrieval')}
                  >
                    <LabeledSlider
                      label="Top-k results"
                      value={retrieverK}
                      min={1}
                      max={20}
                      onChange={setRetrieverK}
                      hint="Chunks retrieved per query."
                    />
                    <LabeledSlider
                      label="Min similarity score"
                      value={similarityThreshold}
                      min={0}
                      max={1}
                      step={0.05}
                      onChange={setSimilarityThreshold}
                      hint="0.0 = disabled. Drops chunks below this cosine similarity."
                    />
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-xs font-medium text-slate-600">Use MMR diversity</p>
                        <p className="text-xs text-slate-400">
                          Max Marginal Relevance reduces redundant chunks.
                        </p>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={useMMR}
                        onClick={() => setUseMMR((v) => !v)}
                        className={`relative w-9 h-5 rounded-full transition-colors ${useMMR ? 'bg-sky-500' : 'bg-slate-200'}`}
                      >
                        <span
                          className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${useMMR ? 'translate-x-4' : ''}`}
                        />
                      </button>
                    </div>
                    {useMMR && (
                      <LabeledSlider
                        label="MMR candidate pool"
                        value={fetchK}
                        min={retrieverK}
                        max={50}
                        onChange={setFetchK}
                        hint={`Must be ≥ top-k (${retrieverK}).`}
                      />
                    )}
                    <LabeledSlider
                      label="Max context chunks"
                      value={maxContextChunks}
                      min={1}
                      max={20}
                      onChange={setMaxContextChunks}
                      hint="Max chunks sent to the LLM prompt."
                    />
                  </SettingsSection>

                  {/* Section 4 — Generation limits */}
                  <SettingsSection
                    id="generation"
                    title="Generation limits"
                    open={openSections.has('generation')}
                    onToggle={() => toggleSection('generation')}
                  >
                    <LabeledSlider
                      label="Max output tokens"
                      value={maxCompletionTokens}
                      min={128}
                      max={4096}
                      step={64}
                      onChange={setMaxCompletionTokens}
                      hint="Hard cap on LLM completion length."
                    />
                    <div>
                      <div className="flex justify-between mb-1">
                        <label className="text-xs font-medium text-slate-600">
                          Token budget warning
                        </label>
                        <span className="text-xs text-sky-600 font-mono">
                          {tokenBudgetWarning}
                        </span>
                      </div>
                      <input
                        type="number"
                        min={0}
                        value={tokenBudgetWarning}
                        onChange={(e) => setTokenBudgetWarning(Number(e.target.value))}
                        className="input text-sm"
                      />
                      <p className="text-xs text-slate-400 mt-0.5">
                        Log a warning when cumulative tokens exceed this (0 = disabled).
                      </p>
                    </div>
                  </SettingsSection>

                  {/* Section 5 — LangSmith observability */}
                  <SettingsSection
                    id="observability"
                    title="Observability (LangSmith)"
                    open={openSections.has('observability')}
                    onToggle={() => toggleSection('observability')}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-xs font-medium text-slate-600">
                          Enable LangSmith tracing
                        </p>
                        <p className="text-xs text-slate-400">
                          Traces all LLM calls to your LangSmith project.
                        </p>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={tracingEnabled}
                        onClick={() => setTracingEnabled((v) => !v)}
                        className={`relative w-9 h-5 rounded-full transition-colors ${tracingEnabled ? 'bg-sky-500' : 'bg-slate-200'}`}
                        data-testid="tracing-toggle"
                      >
                        <span
                          className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${tracingEnabled ? 'translate-x-4' : ''}`}
                        />
                      </button>
                    </div>
                    {tracingEnabled && (
                      <>
                        <div>
                          <label className="block text-xs font-medium text-slate-600 mb-1">
                            LangSmith API Key
                          </label>
                          {current?.langchain_api_key_masked && (
                            <p className="text-xs text-slate-500 mb-1">
                              Current:{' '}
                              <code className="font-mono bg-slate-100 text-sky-700 px-1 rounded">
                                {current.langchain_api_key_masked}
                              </code>
                            </p>
                          )}
                          <div className="relative">
                            <input
                              type={showLangsmithKey ? 'text' : 'password'}
                              value={langsmithKey}
                              onChange={(e) => setLangsmithKey(e.target.value)}
                              placeholder="ls__… (leave blank to keep current)"
                              maxLength={200}
                              autoComplete="off"
                              className="input pr-10 font-mono text-sm"
                              data-testid="langsmith-key-input"
                            />
                            <button
                              type="button"
                              onClick={() => setShowLangsmithKey((v) => !v)}
                              className="absolute inset-y-0 right-2 flex items-center text-slate-400 hover:text-slate-700"
                              tabIndex={-1}
                              aria-label={showLangsmithKey ? 'Hide key' : 'Show key'}
                            >
                              {showLangsmithKey ? (
                                <EyeSlashIcon className="h-4 w-4" />
                              ) : (
                                <EyeIcon className="h-4 w-4" />
                              )}
                            </button>
                          </div>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-slate-600 mb-1">
                            LangSmith Project
                          </label>
                          <input
                            type="text"
                            value={langsmithProject}
                            onChange={(e) => setLangsmithProject(e.target.value)}
                            placeholder="agenticai-rag-poc"
                            maxLength={100}
                            className="input text-sm"
                          />
                        </div>
                      </>
                    )}
                  </SettingsSection>

                  {/* Section 6 — Pipeline feature flags */}
                  <SettingsSection
                    id="pipeline"
                    title="Pipeline settings"
                    open={openSections.has('pipeline')}
                    onToggle={() => toggleSection('pipeline')}
                  >
                    {/* Hybrid BM25 retrieval */}
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-xs font-medium text-slate-600">Hybrid BM25 retrieval</p>
                        <p className="text-xs text-slate-400">
                          Combines BM25 lexical search with dense vector search via RRF fusion.
                        </p>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={hybridBm25}
                        data-testid="hybrid-bm25-toggle"
                        onClick={() => setHybridBm25((v) => !v)}
                        className={`relative w-9 h-5 rounded-full transition-colors ${hybridBm25 ? 'bg-sky-500' : 'bg-slate-200'}`}
                      >
                        <span
                          className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${hybridBm25 ? 'translate-x-4' : ''}`}
                        />
                      </button>
                    </div>

                    {/* Relevance grader */}
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-xs font-medium text-slate-600">Relevance grader</p>
                        <p className="text-xs text-slate-400">
                          Self-RAG: adds one LLM call per query to filter irrelevant chunks.
                        </p>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={relevanceGrader}
                        data-testid="relevance-grader-toggle"
                        onClick={() => setRelevanceGrader((v) => !v)}
                        className={`relative w-9 h-5 rounded-full transition-colors ${relevanceGrader ? 'bg-sky-500' : 'bg-slate-200'}`}
                      >
                        <span
                          className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${relevanceGrader ? 'translate-x-4' : ''}`}
                        />
                      </button>
                    </div>

                    {/* Auto-evaluate with Ragas */}
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-xs font-medium text-slate-600">Auto-evaluate with Ragas</p>
                        <p className="text-xs text-slate-400">
                          Runs Ragas quality evaluation automatically every 50 queries. Requires API key. Admin only.
                        </p>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={ragasAutoEval}
                        data-testid="ragas-auto-eval-toggle"
                        onClick={() => setRagasAutoEval((v) => !v)}
                        disabled={isGuest}
                        className={`relative w-9 h-5 rounded-full transition-colors ${ragasAutoEval ? 'bg-sky-500' : 'bg-slate-200'} ${isGuest ? 'opacity-50 cursor-not-allowed' : ''}`}
                      >
                        <span
                          className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${ragasAutoEval ? 'translate-x-4' : ''}`}
                        />
                      </button>
                    </div>

                    {/* Reranker type */}
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">
                        Reranker
                      </label>
                      <select
                        value={rerankerType}
                        onChange={(e) => setRerankerType(e.target.value)}
                        className="input text-sm"
                        data-testid="reranker-type-select"
                      >
                        <option value="none">none (disabled)</option>
                        <option value="cross-encoder">cross-encoder (requires sentence-transformers)</option>
                      </select>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Cross-encoder reranker improves precision but adds ~80 MB model download.
                      </p>
                    </div>

                    {/* Read-only pipeline config info */}
                    {current?.reranker_top_k != null && (
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-600">Reranker top-k</span>
                        <span className="font-mono text-slate-800">{current.reranker_top_k}</span>
                      </div>
                    )}
                    {current?.retriever_fusion_mode && (
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-600">Retrieval fusion mode</span>
                        <span className="font-mono text-slate-800">{current.retriever_fusion_mode.toUpperCase()}</span>
                      </div>
                    )}
                    {current?.chunker_type === 'semantic' && current?.semantic_breakpoint_threshold_type && (
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-600">Semantic breakpoint</span>
                        <span className="font-mono text-slate-800">{current.semantic_breakpoint_threshold_type}</span>
                      </div>
                    )}

                    {/* Chunker type */}
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">
                        Chunker strategy
                      </label>
                      <select
                        value={chunkerType}
                        onChange={(e) => setChunkerType(e.target.value)}
                        className="input text-sm"
                        data-testid="chunker-type-select"
                      >
                        <option value="recursive">recursive (default, fast)</option>
                        <option value="semantic">semantic (slower, costs tokens)</option>
                      </select>
                    </div>

                    {/* Chunk size + overlap */}
                    <LabeledSlider
                      label="Chunk size"
                      value={chunkSize}
                      min={100}
                      max={4000}
                      step={50}
                      onChange={setChunkSize}
                      hint="Characters per chunk (100–4000)."
                    />
                    <LabeledSlider
                      label="Chunk overlap"
                      value={chunkOverlap}
                      min={0}
                      max={Math.max(0, chunkSize - 50)}
                      step={10}
                      onChange={(v) => setChunkOverlap(Math.min(v, chunkSize - 1))}
                      hint="Must be less than chunk size."
                    />

                    {/* Re-index warning */}
                    <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                      Chunker strategy, chunk size, and chunk overlap apply to newly uploaded documents only. Re-upload existing documents to apply new settings.
                    </div>
                  </SettingsSection>
                </>
              )}

              {/* Section 7 — Vector store / Pinecone */}
                  <SettingsSection
                    id="vector-store"
                    title="Storage settings"
                    open={openSections.has('vector-store')}
                    onToggle={() => toggleSection('vector-store')}
                  >
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">
                        Configured Store
                      </label>
                      <div
                        className="input text-sm bg-slate-100 text-slate-600"
                        data-testid="vector-store-value"
                      >
                        {vectorStoreType}
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Set by <code>VECTOR_STORE_TYPE</code> in the deployment environment.
                      </p>
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">
                        File Store
                      </label>
                      <div className="input text-sm bg-slate-100 text-slate-600">
                        {fileStoreType}
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Set by <code>FILE_STORE_TYPE</code>. Use Blob for durable previews/downloads.
                      </p>
                    </div>

                    {(vectorStoreType === 'blob' || fileStoreType === 'blob') && (
                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1">
                          Blob Read/Write Token
                        </label>
                        {current && (
                          <p className="text-xs text-slate-500 mb-1">
                            Current:{' '}
                            <code className="font-mono bg-slate-100 text-sky-700 px-1 rounded">
                              {current.blob_read_write_token_masked || '—'}
                            </code>{' '}
                            ({SOURCE_LABEL[current.blob_read_write_token_source] ?? current.blob_read_write_token_source})
                          </p>
                        )}
                        <div className="relative">
                          <input
                            type={showBlobToken ? 'text' : 'password'}
                            value={blobToken}
                            onChange={(e) => {
                              setBlobToken(e.target.value)
                              setBlobTokenError(null)
                            }}
                            placeholder="vercel_blob_rw_… (leave blank to keep current)"
                            maxLength={500}
                            autoComplete="off"
                            spellCheck={false}
                            disabled={locked}
                            className={`input pr-10 font-mono text-sm ${
                              blobTokenError ? 'border-rose-400 focus:border-rose-500 focus:ring-rose-400/30' : ''
                            } ${locked ? 'opacity-60 cursor-not-allowed' : ''}`}
                            data-testid="blob-token-input"
                          />
                          <button
                            type="button"
                            onClick={() => setShowBlobToken((v) => !v)}
                            className="absolute inset-y-0 right-2 flex items-center text-slate-400 hover:text-slate-700"
                            tabIndex={-1}
                            aria-label={showBlobToken ? 'Hide Blob token' : 'Show Blob token'}
                          >
                            {showBlobToken ? (
                              <EyeSlashIcon className="h-4 w-4" />
                            ) : (
                              <EyeIcon className="h-4 w-4" />
                            )}
                          </button>
                        </div>
                        {blobTokenError && (
                          <p className="mt-1 flex items-center gap-1 text-xs text-rose-600">
                            <ExclamationCircleIcon className="h-3.5 w-3.5 shrink-0" />
                            {blobTokenError}
                          </p>
                        )}
                      </div>
                    )}

                    {vectorStoreType === 'pinecone' ? (
                      <>
                        <div>
                          <label className="block text-xs font-medium text-slate-600 mb-1">
                            Pinecone API Key
                          </label>
                          {current && (
                            <p className="text-xs text-slate-500 mb-1">
                              Current:{' '}
                              <code className="font-mono bg-slate-100 text-sky-700 px-1 rounded">
                                {current.pinecone_api_key_masked || '—'}
                              </code>{' '}
                              ({SOURCE_LABEL[current.pinecone_api_key_source] ?? current.pinecone_api_key_source})
                            </p>
                          )}
                          <div className="relative">
                            <input
                              type={showPineconeKey ? 'text' : 'password'}
                              value={pineconeKey}
                              onChange={(e) => {
                                setPineconeKey(e.target.value)
                                setPineconeKeyError(null)
                              }}
                              placeholder="pc-… (leave blank to keep current)"
                              maxLength={300}
                              autoComplete="off"
                              spellCheck={false}
                              disabled={locked}
                              className={`input pr-10 font-mono text-sm ${
                                pineconeKeyError ? 'border-rose-400 focus:border-rose-500 focus:ring-rose-400/30' : ''
                              } ${locked ? 'opacity-60 cursor-not-allowed' : ''}`}
                              data-testid="pinecone-key-input"
                            />
                            <button
                              type="button"
                              onClick={() => setShowPineconeKey((v) => !v)}
                              className="absolute inset-y-0 right-2 flex items-center text-slate-400 hover:text-slate-700"
                              tabIndex={-1}
                              aria-label={showPineconeKey ? 'Hide Pinecone key' : 'Show Pinecone key'}
                            >
                              {showPineconeKey ? (
                                <EyeSlashIcon className="h-4 w-4" />
                              ) : (
                                <EyeIcon className="h-4 w-4" />
                              )}
                            </button>
                          </div>
                          {pineconeKeyError && (
                            <p className="mt-1 flex items-center gap-1 text-xs text-rose-600">
                              <ExclamationCircleIcon className="h-3.5 w-3.5 shrink-0" />
                              {pineconeKeyError}
                            </p>
                          )}
                        </div>

                        <div>
                          <label className="block text-xs font-medium text-slate-600 mb-1">
                            Index Name
                          </label>
                          <input
                            type="text"
                            value={pineconeIndex}
                            onChange={(e) => {
                              setPineconeIndex(e.target.value)
                              setPineconeIndexError(null)
                            }}
                            maxLength={45}
                            disabled={locked}
                            className={`input text-sm ${
                              pineconeIndexError ? 'border-rose-400 focus:border-rose-500 focus:ring-rose-400/30' : ''
                            } ${locked ? 'opacity-60 cursor-not-allowed' : ''}`}
                            data-testid="pinecone-index-input"
                          />
                          {pineconeIndexError && (
                            <p className="mt-1 flex items-center gap-1 text-xs text-rose-600">
                              <ExclamationCircleIcon className="h-3.5 w-3.5 shrink-0" />
                              {pineconeIndexError}
                            </p>
                          )}
                        </div>

                        <div>
                          <label className="block text-xs font-medium text-slate-600 mb-1">
                            Namespace
                          </label>
                          <input
                            type="text"
                            value={pineconeNamespace}
                            onChange={(e) => {
                              setPineconeNamespace(e.target.value)
                              setPineconeNamespaceError(null)
                            }}
                            placeholder="optional"
                            maxLength={100}
                            disabled={locked}
                            className={`input text-sm ${
                              pineconeNamespaceError ? 'border-rose-400 focus:border-rose-500 focus:ring-rose-400/30' : ''
                            } ${locked ? 'opacity-60 cursor-not-allowed' : ''}`}
                            data-testid="pinecone-namespace-input"
                          />
                          {pineconeNamespaceError && (
                            <p className="mt-1 flex items-center gap-1 text-xs text-rose-600">
                              <ExclamationCircleIcon className="h-3.5 w-3.5 shrink-0" />
                              {pineconeNamespaceError}
                            </p>
                          )}
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <label className="block text-xs font-medium text-slate-600 mb-1">
                              Cloud
                            </label>
                            <select
                              value={pineconeCloud}
                              onChange={(e) => setPineconeCloud(e.target.value)}
                              disabled={locked}
                              className="input text-sm"
                              data-testid="pinecone-cloud-select"
                            >
                              <option value="aws">aws</option>
                              <option value="gcp">gcp</option>
                              <option value="azure">azure</option>
                            </select>
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-slate-600 mb-1">
                              Region
                            </label>
                            <input
                              type="text"
                              value={pineconeRegion}
                              onChange={(e) => {
                                setPineconeRegion(e.target.value)
                                setPineconeRegionError(null)
                              }}
                              disabled={locked}
                              className={`input text-sm ${
                                pineconeRegionError ? 'border-rose-400 focus:border-rose-500 focus:ring-rose-400/30' : ''
                              } ${locked ? 'opacity-60 cursor-not-allowed' : ''}`}
                              data-testid="pinecone-region-input"
                            />
                          </div>
                        </div>
                        {pineconeRegionError && (
                          <p className="mt-1 flex items-center gap-1 text-xs text-rose-600">
                            <ExclamationCircleIcon className="h-3.5 w-3.5 shrink-0" />
                            {pineconeRegionError}
                          </p>
                        )}
                      </>
                    ) : (
                      <p className="text-xs text-slate-400">
                        Pinecone runtime fields are hidden because this deployment is configured for {vectorStoreType}.
                      </p>
                    )}
                  </SettingsSection>

              {/* Section 7 — Ragas Evaluation */}
              {!isGuest && (
                  <SettingsSection
                    id="ragas"
                    title="Ragas Evaluation"
                    open={openSections.has('ragas')}
                    onToggle={() => toggleSection('ragas')}
                  >
                    {ragasNotRun && !ragasScores ? (
                      <div className="text-xs text-slate-500 space-y-1.5">
                        <p>No evaluation has been run yet.</p>
                        <code className="block bg-slate-100 rounded px-2 py-1 text-slate-600 font-mono text-[11px] leading-relaxed">
                          LIVE_TESTS=1 OPENAI_API_KEY=&lt;your-openai-api-key&gt; pytest tests/live/test_live_ragas.py
                        </code>
                      </div>
                    ) : ragasScores ? (
                      <div className="space-y-3">
                        <div className="grid grid-cols-2 gap-2">
                          <MetricTile label="Faithfulness" score={ragasScores.faithfulness} />
                          <MetricTile label="Answer Relevancy" score={ragasScores.answer_relevancy} />
                          <MetricTile label="Context Precision" score={ragasScores.context_precision} />
                          <MetricTile label="Context Recall" score={ragasScores.context_recall} />
                        </div>
                        <p className="text-xs text-slate-400">
                          Last run:{' '}
                          {new Date(ragasScores.evaluated_at).toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric',
                          })}{' '}
                          · {ragasScores.model} · {ragasScores.num_samples} samples
                        </p>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 py-2">
                        <div className="w-3 h-3 rounded-full border-2 border-sky-500 border-t-transparent animate-spin" />
                        <p className="text-xs text-slate-400">Loading…</p>
                      </div>
                    )}
                    {/* Run Evaluation button — admin only */}
                    {!isGuest && (
                      <div className="pt-1">
                        <button
                          type="button"
                          data-testid="ragas-trigger-btn"
                          disabled={ragasRunning}
                          onClick={async () => {
                            if (current?.api_key_source === 'not_configured' && !apiKey.trim()) {
                              toast.error('OpenAI API key is required before running Ragas evaluation. Enter a key in Settings and save it first.')
                              setKeyError('OpenAI API key is required before running Ragas evaluation.')
                              return
                            }
                            if (apiKey.trim()) {
                              toast.error('Save the OpenAI API key before running Ragas evaluation.')
                              return
                            }
                            setRagasRunning(true)
                            try {
                              await settingsApi.triggerRagas()
                              toast.success('Ragas evaluation started — scores will update shortly')
                              // Reload scores after 5 seconds to pick up results
                              setTimeout(() => {
                                settingsApi.getRagasScores().then((scores) => {
                                  if (scores && scores.has_results) {
                                    setRagasScores(scores)
                                    setRagasNotRun(false)
                                  }
                                })
                              }, 5000)
                            } catch (err) {
                              if (axios.isAxiosError(err)) {
                                if (err.response?.status === 422) {
                                  toast.error('Upload documents first before running evaluation')
                                } else if (err.response?.status === 429) {
                                  toast.error('Evaluation already running. Please wait.')
                                } else {
                                  toast.error(extractErrorMessage(err))
                                }
                              } else {
                                toast.error('Failed to start evaluation.')
                              }
                            } finally {
                              setRagasRunning(false)
                            }
                          }}
                          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-sky-500 text-white hover:bg-sky-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                          {ragasRunning ? (
                            <>
                              <div className="w-3 h-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                              Running…
                            </>
                          ) : (
                            'Run Evaluation'
                          )}
                        </button>
                      </div>
                    )}
                  </SettingsSection>
              )}
            {hasCostImpactingChanges && (
              <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                <ExclamationCircleIcon className="h-4 w-4 shrink-0 mt-0.5" />
                <p>
                  These changes can affect usage charges for the connected provider account. Review API keys,
                  model choices, token limits, storage, and tracing before saving.
                </p>
              </div>
            )}
            </div>
          )}
        </div>

        {/* Footer — buttons only, always fully visible */}
        <div className="px-6 py-4 border-t border-slate-200 bg-slate-50 shrink-0 flex justify-end gap-3">
          <button onClick={onClose} className="btn-secondary text-sm" disabled={saving}>
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || loading || locked}
            className="btn-primary text-sm disabled:opacity-50"
            data-testid="settings-save-btn"
          >
            {saving ? 'Saving…' : locked ? 'Locked' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
