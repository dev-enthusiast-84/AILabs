import axios, { AxiosError } from 'axios'
import { useAuthStore } from '@/store/authStore'
import type { LoginRequest, TokenResponse, DocumentListResponse, DocumentMetadataResponse, DocumentChunksResponse, DocumentContentResponse, UploadResponse, QueryRequest, QueryResponse, SettingsResponse, SettingsUpdateRequest, GuardrailRule, GuardrailRuleCreate, GuardrailRuleUpdate, GuardrailCheckRequest, GuardrailCheckResponse, RagasScores, ChatVoiceExportRequest, ChatVoiceExportResponse, ChatVoiceExportAcceptedResponse, ChatVoiceExportJobResponse, TranscriptRedactionRequest, TranscriptRedactionResponse } from '@/types'

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api'
const SESSION_COMPAT_HEADER = 'x-app-session-compatibility'
const SESSION_COMPAT_STORAGE_KEY = 'app_session_compatibility'

const http = axios.create({
  baseURL: BASE_URL,
  timeout: 60_000,
})

// Attach JWT on every request — sessionStorage keeps each tab's token isolated
http.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

function refreshSessionIfDeploymentChanged(compatibilityVersion?: string): void {
  if (!compatibilityVersion) return

  const previousVersion = sessionStorage.getItem(SESSION_COMPAT_STORAGE_KEY)
  sessionStorage.setItem(SESSION_COMPAT_STORAGE_KEY, compatibilityVersion)

  const hasActiveSession = Boolean(sessionStorage.getItem('token'))
  if (!previousVersion || previousVersion === compatibilityVersion || !hasActiveSession) {
    return
  }

  useAuthStore.getState().clearAuth()
  sessionStorage.setItem(
    'auth_error',
    'The application was updated and your previous session is no longer compatible. Please sign in again.',
  )
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

// Global 401 → logout this tab only (sessionStorage is per-tab)
http.interceptors.response.use(
  (res) => {
    refreshSessionIfDeploymentChanged(res.headers[SESSION_COMPAT_HEADER])
    return res
  },
  (error: AxiosError) => {
    const requestUrl = error.config?.url ?? ''
    const isLoginRequest = requestUrl.includes('/auth/login') || requestUrl.includes('/auth/guest')
    refreshSessionIfDeploymentChanged(error.response?.headers?.[SESSION_COMPAT_HEADER])
    if (error.response?.status === 429) {
      // Do NOT clear auth or redirect. Just let the error propagate with a clear message.
      const retryAfter = error.response.headers?.['retry-after']
      const waitMsg = retryAfter ? ` Please wait ${retryAfter} seconds.` : ' Please wait a moment.'
      return Promise.reject(new Error(`Rate limit reached.${waitMsg}`))
    }
    if (error.response?.status === 401 && !isLoginRequest) {
      useAuthStore.getState().clearAuth()
      sessionStorage.setItem('auth_error', 'Your session is no longer valid. Please sign in again.')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)

export const authApi = {
  login: async (data: LoginRequest): Promise<TokenResponse> => {
    const res = await http.post<TokenResponse>('/auth/login', data)
    return res.data
  },
  guest: async (): Promise<TokenResponse> => {
    const res = await http.post<TokenResponse>('/auth/guest')
    return res.data
  },
  me: async (): Promise<{ username: string; role: string }> => {
    const res = await http.get<{ username: string; role: string }>('/auth/me')
    return res.data
  },
  logout: async (): Promise<void> => {
    await http.post('/auth/logout')
  },
}

export const documentsApi = {
  list: async (): Promise<DocumentListResponse> => {
    const res = await http.get<DocumentListResponse>('/documents/')
    return res.data
  },
  upload: async (file: File): Promise<UploadResponse> => {
    const form = new FormData()
    form.append('file', file)
    const res = await http.post<UploadResponse>('/documents/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data
  },
  remove: async (filename: string): Promise<{ filename: string; chunks_removed: number }> => {
    const res = await http.delete<{ filename: string; chunks_removed: number }>(`/documents/${encodeURIComponent(filename)}`)
    return res.data
  },
  getChunks: async (filename: string): Promise<DocumentChunksResponse> => {
    const res = await http.get<DocumentChunksResponse>(`/documents/${encodeURIComponent(filename)}/chunks`)
    return res.data
  },
  getContent: async (filename: string): Promise<DocumentContentResponse> => {
    const res = await http.get<DocumentContentResponse>(`/documents/${encodeURIComponent(filename)}/content`)
    return res.data
  },
  getFile: async (filename: string): Promise<Blob> => {
    const res = await http.get(`/documents/${encodeURIComponent(filename)}/file`, {
      responseType: 'blob',
    })
    return res.data
  },
  getMetadata: async (): Promise<DocumentMetadataResponse> => {
    const res = await http.get<DocumentMetadataResponse>('/documents/metadata')
    return res.data
  },
}

export const queryApi = {
  ask: async (data: QueryRequest): Promise<QueryResponse> => {
    const res = await http.post<QueryResponse>('/query/', data)
    return res.data
  },
}

function audioResponseToBlob(response: Pick<ChatVoiceExportResponse, 'audio_base64' | 'audio_mime_type'>): Blob {
  const binary = atob(response.audio_base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return new Blob([bytes], { type: response.audio_mime_type || 'audio/mpeg' })
}

function isAcceptedExport(response: ChatVoiceExportResponse | ChatVoiceExportAcceptedResponse): response is ChatVoiceExportAcceptedResponse {
  return 'job_id' in response
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

export const voiceApi = {
  redactTranscript: async (data: TranscriptRedactionRequest): Promise<TranscriptRedactionResponse> => {
    const res = await http.post<TranscriptRedactionResponse>('/chat/voice/redact', data)
    return res.data
  },
  exportAudio: async (
    data: ChatVoiceExportRequest,
    onStatusChange?: (status: string) => void,
    onJobId?: (jobId: string) => void,
  ): Promise<{ blob: Blob; redacted: boolean }> => {
    const res = await http.post<ChatVoiceExportResponse | ChatVoiceExportAcceptedResponse>('/chat/voice/export', data)
    if (!isAcceptedExport(res.data)) return { blob: audioResponseToBlob(res.data), redacted: res.data.redacted ?? false }

    onJobId?.(res.data.job_id)
    onStatusChange?.('queued')
    const deadline = Date.now() + 120_000
    let retryAfterMs = Math.max(250, res.data.retry_after_seconds * 1000)
    while (Date.now() < deadline) {
      await wait(retryAfterMs)
      const status = await voiceApi.getExportJob(res.data.job_id)
      retryAfterMs = Math.max(250, status.policy.retry_after_seconds * 1000)
      onStatusChange?.(status.status)
      if (status.status === 'succeeded' && status.artifact) return { blob: audioResponseToBlob(status.artifact), redacted: status.redacted ?? false }
      if (status.status === 'failed') throw new Error(status.error?.message ?? 'Audio export failed.')
      if (status.status === 'canceled') throw new Error('Audio export was canceled.')
      if (status.status === 'expired') throw new Error('Audio export expired. Please export again.')
    }
    throw new Error('Audio export is still processing. Please try again.')
  },
  getExportJob: async (jobId: string): Promise<ChatVoiceExportJobResponse> => {
    const res = await http.get<ChatVoiceExportJobResponse>(`/chat/voice/export/jobs/${encodeURIComponent(jobId)}`)
    return res.data
  },
  cancelExportJob: async (jobId: string): Promise<ChatVoiceExportJobResponse> => {
    const res = await http.delete<ChatVoiceExportJobResponse>(`/chat/voice/export/jobs/${encodeURIComponent(jobId)}`)
    return res.data
  },
}

interface _SettingsCacheEntry { data: SettingsResponse; ts: number }
let _settingsCache: _SettingsCacheEntry | null = null
const _SETTINGS_TTL_MS = 30_000

export function clearSettingsCache(): void {
  _settingsCache = null
}

export const settingsApi = {
  get: async (): Promise<SettingsResponse> => {
    if (_settingsCache && Date.now() - _settingsCache.ts < _SETTINGS_TTL_MS) {
      return _settingsCache.data
    }
    const res = await http.get<SettingsResponse>('/settings/')
    _settingsCache = { data: res.data, ts: Date.now() }
    return res.data
  },
  update: async (data: SettingsUpdateRequest): Promise<SettingsResponse> => {
    const res = await http.post<SettingsResponse>('/settings/', data)
    _settingsCache = { data: res.data, ts: Date.now() }
    return res.data
  },
  getRagasScores: async (): Promise<RagasScores | null> => {
    try {
      const res = await http.get<RagasScores>('/settings/ragas-scores')
      return res.data
    } catch {
      return null
    }
  },
  triggerRagas: async (): Promise<{ status: string; message: string }> => {
    const res = await http.post<{ status: string; message: string }>('/settings/ragas-trigger')
    return res.data
  },
}

export const guardrailsApi = {
  list: async (): Promise<GuardrailRule[]> => {
    const res = await http.get<GuardrailRule[]>('/guardrails/')
    return res.data
  },
  get: async (id: string): Promise<GuardrailRule> => {
    const res = await http.get<GuardrailRule>(`/guardrails/${id}`)
    return res.data
  },
  create: async (data: GuardrailRuleCreate): Promise<GuardrailRule> => {
    const res = await http.post<GuardrailRule>('/guardrails/', data)
    return res.data
  },
  update: async (id: string, data: GuardrailRuleUpdate): Promise<GuardrailRule> => {
    const res = await http.patch<GuardrailRule>(`/guardrails/${id}`, data)
    return res.data
  },
  remove: async (id: string): Promise<void> => {
    await http.delete(`/guardrails/${id}`)
  },
  check: async (data: GuardrailCheckRequest): Promise<GuardrailCheckResponse> => {
    const res = await http.post<GuardrailCheckResponse>('/guardrails/check', data)
    return res.data
  },
}

export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (typeof item === 'string') return item
          if (item && typeof item === 'object' && 'msg' in item) {
            return String((item as { msg: unknown }).msg)
          }
          return JSON.stringify(item)
        })
        .join(', ')
    }
    if (detail && typeof detail === 'object') {
      if ('message' in detail && typeof (detail as { message?: unknown }).message === 'string') {
        return (detail as { message: string }).message
      }
      return JSON.stringify(detail)
    }
    return error.message
  }
  return 'An unexpected error occurred.'
}
