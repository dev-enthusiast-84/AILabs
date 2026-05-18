export interface LoginRequest {
  username: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface DocumentListResponse {
  documents: string[]
  count: number
}

export interface UploadResponse {
  filename: string
  chunks_indexed: number
  message: string
}

export interface QueryRequest {
  question: string
  mode?: 'simple' | 'agentic'
}

export interface QueryResponse {
  answer: string
  sources: string[]
  validation: 'VALID' | 'NEEDS_REVISION'
  tokens_used: number
  mode: 'simple' | 'agentic'
  retry_count?: number
  latency_ms?: number
  trace?: AgentTrace | null
}

export interface AgentTrace {
  original_question: string
  refined_query: string
  chunks_found: number
  validation_reason: string
  retries: number
  chunks_after_grading: number
  chunks_after_rerank: number
  hyde_tokens: number
  hyde_latency_ms: number
  grader_tokens: number
  grader_latency_ms: number
  reranker_latency_ms: number
  planner_tokens: number
  generator_tokens: number
  validator_tokens: number
  planner_latency_ms: number
  generator_latency_ms: number
  validator_latency_ms: number
  planner_model: string
  generator_model: string
  validator_model: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
  validation?: 'VALID' | 'NEEDS_REVISION'
  tokens_used?: number
  mode?: 'simple' | 'agentic'
  timestamp: Date
  retry_count?: number
  latency_ms?: number
  trace?: AgentTrace | null
}

export interface ApiError {
  detail: string | Record<string, string>
}

export interface SettingsResponse {
  // Section 1 — AI Model (all users)
  model: string
  api_key_masked: string
  api_key_source: 'runtime' | 'environment' | 'not_configured'
  allowed_models: string[]
  // Section 2 — Per-node models (admin only)
  planner_model: string
  generator_model: string
  validator_model: string
  // Section 3 — Retrieval (admin only)
  retriever_k: number
  similarity_score_threshold: number
  retriever_use_mmr: boolean
  retriever_fetch_k: number
  max_context_chunks: number
  // Section 4 — Generation limits (admin only)
  max_completion_tokens: number
  token_budget_warning_threshold: number
  // Section 5 — LangSmith observability (admin only)
  langchain_tracing_v2: boolean
  langchain_api_key_masked: string
  langchain_project: string
}

export interface SettingsUpdateRequest {
  // Section 1
  api_key?: string
  model?: string
  // Section 2
  planner_model?: string
  generator_model?: string
  validator_model?: string
  // Section 3
  retriever_k?: number
  similarity_score_threshold?: number
  retriever_use_mmr?: boolean
  retriever_fetch_k?: number
  max_context_chunks?: number
  // Section 4
  max_completion_tokens?: number
  token_budget_warning_threshold?: number
  // Section 5
  langchain_tracing_v2?: boolean
  langchain_api_key?: string
  langchain_project?: string
}

export interface DocumentChunksResponse {
  filename: string
  chunks: string[]
  total_chunks: number
}

export interface DocumentContentResponse {
  filename: string
  content: string
  word_count: number
}

export interface GuardrailRule {
  id: string
  name: string
  description: string
  type: 'word' | 'topic' | 'regex'
  target: 'input' | 'output' | 'both'
  action: 'block' | 'flag' | 'redact'
  severity: 'low' | 'medium' | 'high'
  enabled: boolean
  builtin: boolean
  words: string[]
  keywords: string[]
  pattern: string
  replacement: string
}

export interface GuardrailRuleCreate {
  name: string
  description?: string
  type: 'word' | 'topic' | 'regex'
  target: 'input' | 'output' | 'both'
  action: 'block' | 'flag' | 'redact'
  severity?: 'low' | 'medium' | 'high'
  enabled?: boolean
  words?: string[]
  keywords?: string[]
  pattern?: string
  replacement?: string
}

export interface GuardrailRuleUpdate {
  name?: string
  description?: string
  enabled?: boolean
  words?: string[]
  keywords?: string[]
  pattern?: string
  replacement?: string
  severity?: string
}

export interface GuardrailCheckRequest {
  text: string
  target: 'input' | 'output' | 'both'
}

export interface GuardrailCheckResponse {
  allowed: boolean
  modified_text: string
  flagged: boolean
  violations: Array<{ rule_id: string; rule_name: string; action: string; severity: string }>
}

export interface RagasScores {
  faithfulness: number
  answer_relevancy: number
  context_precision: number
  context_recall: number
  evaluated_at: string
  model: string
  num_samples: number
  has_results?: boolean
}
