import axios, { AxiosError } from 'axios'
import type { LoginRequest, TokenResponse, DocumentListResponse, DocumentChunksResponse, DocumentContentResponse, UploadResponse, QueryRequest, QueryResponse, SettingsResponse, SettingsUpdateRequest, GuardrailRule, GuardrailRuleCreate, GuardrailRuleUpdate, GuardrailCheckRequest, GuardrailCheckResponse, RagasScores } from '@/types'

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api'

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

// Global 401 → logout this tab only (sessionStorage is per-tab)
http.interceptors.response.use(
  (res) => res,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      sessionStorage.removeItem('token')
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
}

export const queryApi = {
  ask: async (data: QueryRequest): Promise<QueryResponse> => {
    const res = await http.post<QueryResponse>('/query/', data)
    return res.data
  },
}

export const settingsApi = {
  get: async (): Promise<SettingsResponse> => {
    const res = await http.get<SettingsResponse>('/settings/')
    return res.data
  },
  update: async (data: SettingsUpdateRequest): Promise<SettingsResponse> => {
    const res = await http.post<SettingsResponse>('/settings/', data)
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
    return (error.response?.data as { detail?: string })?.detail ?? error.message
  }
  return 'An unexpected error occurred.'
}
