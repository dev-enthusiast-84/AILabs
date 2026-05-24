# Pipeline & Retrieval Environment Variables

> [← Deployment](deployment/DEPLOYMENT.md) · [Environment Variables](deployment/DEPLOY-LOCAL-ENV.md)

Tuning variables for retrieval, chunking, reranking, and Ragas evaluation. These rarely need to change from defaults for a standard deployment.

---

## Retrieval & Chunking

| Variable | Default | Purpose |
|----------|---------|---------|
| `RETRIEVER_K` | `4` | Top-k chunks returned by similarity search |
| `RETRIEVER_FETCH_K` | `20` | Candidate pool size for MMR re-ranking (should be ≥ `RETRIEVER_K`) |
| `RETRIEVER_USE_MMR` | `false` | Max Marginal Relevance search (Chroma only) for chunk diversity |
| `SIMILARITY_SCORE_THRESHOLD` | `0.0` | Min cosine similarity (0–1); `0.0` = disabled |
| `RETRIEVER_FUSION_MODE` | `rrf` | Multi-query fusion: `rrf` (Reciprocal Rank Fusion) or `dedup` |
| `RETRIEVER_RRF_K` | `60` | RRF constant — higher reduces rank-position sensitivity |
| `CHUNK_SIZE` | `800` | Target chunk size in characters for the recursive text splitter |
| `CHUNK_OVERLAP` | `100` | Character overlap between adjacent chunks |
| `RETRIEVER_HYBRID_BM25` | `true` | Fuse BM25 lexical search with dense results via RRF |
| `RETRIEVER_BM25_WEIGHT` | `0.5` | BM25 weight hint (informational; RRF drives actual weighting) |
| `RELEVANCE_GRADER_ENABLED` | `false` | Self-RAG grader drops irrelevant chunks before generation (adds one LLM call) |
| `CHUNKER_TYPE` | `recursive` | `recursive` (default) or `semantic` (embedding-similarity boundaries) |
| `SEMANTIC_BREAKPOINT_THRESHOLD_TYPE` | `percentile` | SemanticChunker type: `percentile`, `standard_deviation`, `interquartile`, `gradient` |

---

## Reranker

| Variable | Default | Purpose |
|----------|---------|---------|
| `RERANKER_TYPE` | `llm-judge` | `llm-judge` (default — OpenAI batch scoring, no extra deps), `cross-encoder` (requires `sentence-transformers`, not on Vercel), or `none` |
| `RERANKER_JUDGE_MODEL` | `gpt-4.1-mini` | OpenAI model used when `RERANKER_TYPE=llm-judge`. Must differ from pipeline models. Configurable at runtime via Settings UI. |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Model used when `RERANKER_TYPE=cross-encoder` |
| `RERANKER_TOP_K` | `4` | Chunks kept after reranking |
| `HF_TOKEN` | — | HuggingFace token for cross-encoder download. Unset = anonymous (rate-limited); app passes `token=False` explicitly so no warning is emitted. |

---

## Ragas Evaluation

| Variable | Default | Purpose |
|----------|---------|---------|
| `RAGAS_EVALUATION_ENABLED` | `false` | When `true`, probabilistic background Ragas evaluation runs every N queries. Toggle at runtime via `POST /api/settings/` (`ragas_evaluation_enabled: true`). Admin only. |
| `RAGAS_SCORES_FILE` | `/tmp/ragas_scores.json` | Path where Ragas results are persisted; read by the admin dashboard |

> On Vercel and Docker, `/tmp` is writable. For persistent score history across restarts, set `RAGAS_SCORES_FILE` to durable storage.
