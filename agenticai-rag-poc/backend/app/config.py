from functools import cached_property, lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_env: str = "development"
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"
    # Bump for deployments that are not compatible with existing browser sessions.
    session_compatibility_version: str = "1"

    # Security — must be set via environment variable; no default to prevent accidental weak keys
    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 45  # 45-minute session for logged-in users

    # Admin credentials — set by setup.sh; never hardcode a value here
    admin_username: str = "admin"
    admin_password: str = ""

    # OpenAI
    openai_api_key: str = ""

    # LLM
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    # Per-node model overrides — empty string means use llm_model.
    # Set generator_model="gpt-4o" for higher-quality answers in production.
    planner_model: str = ""
    generator_model: str = ""
    validator_model: str = ""

    # LangSmith observability (optional — set langchain_tracing_v2=true to enable)
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "agenticai-rag-poc"

    # Vector store
    # "chroma" is the local/Docker default and requires a writable persistent
    # filesystem. Use "pinecone" for Vercel/full-stack production. "memory" is
    # for tests only. "blob" is retained for small Vercel Blob demos/fallbacks.
    vector_store_type: str = "chroma"
    chroma_persist_dir: str = "./chroma_db"

    # Original uploaded file storage. "blob" uses Vercel Blob for durable
    # previews/downloads; token may come from env or runtime Settings UI.
    file_store_type: str = "local"
    blob_read_write_token: str = ""
    vercel_blob_read_write_token: str = ""

    # Pinecone vector store (only needed when VECTOR_STORE_TYPE=pinecone)
    pinecone_api_key: str = ""
    pinecone_index_name: str = "agenticai-rag-poc-documents"
    pinecone_namespace: str = "agenticai-rag-poc"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"

    # RAG chunking
    chunk_size: int = 800
    chunk_overlap: int = 100
    # Chunking strategy: "recursive" (default) or "semantic"
    # "semantic" uses embedding-similarity boundaries (better quality, slower, costs tokens).
    # Re-index all documents after switching — existing chunks used the previous strategy.
    chunker_type: str = "recursive"
    # Breakpoint threshold type for SemanticChunker: "percentile", "standard_deviation",
    # "interquartile", or "gradient"
    semantic_breakpoint_threshold_type: str = "percentile"
    retriever_k: int = 4
    # Minimum cosine similarity score (0–1). Chunks below this threshold are
    # dropped even if they are in the top-k results. Set to 0.0 to disable.
    similarity_score_threshold: float = 0.0
    # When True, use Max Marginal Relevance search to balance relevance + diversity.
    retriever_use_mmr: bool = False
    # fetch_k candidates before MMR re-ranking (should be >= retriever_k)
    retriever_fetch_k: int = 20
    # ── Multi-query fusion strategy ───────────────────────────────────────────
    # "rrf"   — Reciprocal Rank Fusion; combines rankings from all query variants
    #           (recommended; gives higher scores to docs appearing in multiple lists)
    # "dedup" — first-seen ordering; simpler, deterministic
    retriever_fusion_mode: str = "rrf"
    retriever_rrf_k: int = 60           # RRF constant; higher = less rank-position sensitivity
    # ── Hybrid BM25 + dense search ────────────────────────────────────────────
    # When true, BM25 lexical results are fused with dense results via RRF.
    # Requires: pip install rank-bm25
    retriever_hybrid_bm25: bool = True
    retriever_bm25_weight: float = 0.5  # informational; fusion uses RRF, not weighted sum
    # ── Self-RAG relevance grader ─────────────────────────────────────────────
    # Adds one extra LLM call per query to filter irrelevant chunks before generation.
    relevance_grader_enabled: bool = False
    # ── Ragas quality evaluation ──────────────────────────────────────────────
    # When true, Ragas evaluation runs automatically every N queries (see api/query.py).
    # Can be toggled at runtime via POST /api/settings/ {ragas_evaluation_enabled: true}.
    ragas_evaluation_enabled: bool = False
    # ── Cross-encoder reranker ────────────────────────────────────────────────
    # "none"          — disabled (default)
    # "cross-encoder" — requires: pip install sentence-transformers (~80 MB model download)
    reranker_type: str = "none"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_top_k: int = 4

    # Upload limits
    max_upload_size_mb: int = 20
    guest_max_upload_size_mb: int = 2  # smaller cap for unauthenticated/guest uploads
    max_indexed_documents: int = 10
    guest_max_indexed_documents: int = 3
    max_query_length: int = 1000

    # ── Token budget controls (OWASP A04 — Insecure Design) ──────────────────
    # Hard cap on LLM completion tokens per response
    max_completion_tokens: int = 1024
    # Soft warning threshold — logged when exceeded (informational, no hard block)
    token_budget_warning_threshold: int = 800
    # Maximum chunks sent as context to the LLM (controls prompt token spend)
    max_context_chunks: int = 4

    # Rate limiting
    rate_limit_per_minute: int = 30
    # Stricter limit on the expensive query endpoint
    query_rate_limit_per_minute: int = 10
    # Per-IP upload limit for guest users (admins are exempt)
    guest_upload_rate_limit_per_minute: int = 5

    # Guest mode
    guest_token_expire_minutes: int = 15  # 15-minute session timeout
    guest_doc_retention_seconds: int = 3600  # 1 hour

    @cached_property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @cached_property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @cached_property
    def guest_max_upload_size_bytes(self) -> int:
        return self.guest_max_upload_size_mb * 1024 * 1024

    @property
    def effective_max_upload_size_mb(self) -> int:
        """Cap admin uploads at 4 MB on Vercel (serverless body size limit is ~4.5 MB).

        Not cached — reads os.environ at call time so Vercel detection stays accurate.
        """
        import os
        if os.environ.get("VERCEL"):
            return min(self.max_upload_size_mb, 4)
        return self.max_upload_size_mb

    @cached_property
    def effective_max_upload_size_bytes(self) -> int:
        return self.effective_max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
