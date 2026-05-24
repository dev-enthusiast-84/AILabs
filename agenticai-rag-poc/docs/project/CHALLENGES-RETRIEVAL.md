# Retrieval Quality and Reranking

> [← Limitations & Challenges](project/CHALLENGES.md) · [← Project](project/PROJECT.md) · [← Home](README.md)

Design decisions and trade-offs for the retrieval pipeline: chunking strategies, hybrid search, reranker selection, and grounded generation quality. For the full challenges overview see [Limitations & Challenges](project/CHALLENGES.md).

---

## Chunking and Retrieval Quality

RAG quality is sensitive to chunk size, overlap, metadata, and retrieval parameters. Approaches evaluated:

- **Recursive chunking** (default) — fast, deterministic, low token cost.
- **Semantic chunking** — splits on embedding-similarity boundaries; better quality on prose but slower and costs extra tokens.
- **Contextual chunk headers** — each chunk prefixed with `[Document: <source>]` so the vector captures document provenance.
- **HyDE** — hypothetical answer passage embedded alongside the user question; improves recall for abstract questions.
- **Multi-query fan-out + RRF** — Planner generates 2 rephrases; all 3 queries plus HyDE fan out in parallel and fuse via Reciprocal Rank Fusion.
- **BM25 hybrid** — lexical BM25 fused with dense results via RRF (default: `RETRIEVER_HYBRID_BM25=true`).
- **Reranking** — three modes: `none` (default), `cross-encoder` (auto-activates when `sentence-transformers` installed, ~80 MB), `llm-judge` (smart default on Vercel or when sentence-transformers absent). Set `RERANKER_TYPE` to override.

**Trade-off:** Each additional retrieval feature adds latency and LLM cost. Defaults balance quality and cost for a capstone deployment.

---

## Reranker Selection: Cost and Deployment Constraints

Choosing a reranker for a Vercel-deployed RAG pipeline involves three competing constraints: **cost**, **package size**, and **reranking quality**.

### Package Size Eliminates Local Model Options

Vercel serverless functions have a ~250 MB unzipped bundle limit. Models that ship weights locally are ruled out:

| Reranker | Reason excluded |
|----------|----------------|
| Cross-encoder (sentence-transformers) | ~80 MB PyTorch weights; exceeds bundle limit |
| BGE Reranker | HuggingFace local weights; same constraint |
| ColBERT / ragatouille | PyTorch dependency; exceeds bundle limit |
| MonoT5 / RankT5 | T5 weights; same constraint |
| FlashRank | ONNX models; unreliable cold-start downloads in serverless |

### API-Based Rerankers: Cost Comparison

| Option | Input cost per 1M tokens | Notes |
|--------|--------------------------|-------|
| **Jina Reranker** | **$18.00** | 1M token free tier on signup |
| **OpenAI o4-mini** (LLM-as-Judge) | $1.10 input + $4.40 output | Reasoning capability included |
| **OpenAI o3-mini** (LLM-as-Judge) | $1.10 input + $4.40 output | |
| **OpenAI o1** (LLM-as-Judge) | $15.00 input + $60.00 output | |
| **Cohere Rerank** | ~$1.00 | Dedicated reranking API |
| **RRF** | $0 | Pure algorithm, no model |

Jina at $18/1M input tokens is more expensive than most OpenAI reasoning models on input cost alone, making LLM-as-Judge via o4-mini a better value if neural reranking quality is required.

### Decision

- **Default (`RERANKER_TYPE=none` + RRF):** Free, deterministic, already present in the retrieval fusion stage, no API dependency. Chosen as the default.
- **Vercel fallback (`llm-judge`):** When sentence-transformers is absent (always on Vercel), `llm-judge` activates — o4-mini provides reasoning-quality reranking at lower per-token cost than Jina.
- **Upgrade path:** Cohere Rerank (`RERANKER_TYPE=cohere`) is the recommended paid option — lightweight package, ~$1/1M tokens, no Vercel size concerns.
- **Jina avoided:** Cost per token exceeds both Cohere and OpenAI reasoning models; not recommended for this stack.

---

## Grounded Generation and Hallucination Control

LLMs can produce confident-sounding answers when context does not contain the information. Mitigations:

- Generator is prompted to answer **only** from retrieved context and to state when information is absent.
- **Validator node** independently re-reads the question and generated answer against context and classifies as `VALID` or `NEEDS_REVISION`; the pipeline retries generation up to 2 times.
- Answer exposes `validation` field and `tokens_used` per-node trace in the API response.

**Remaining constraint:** The Validator uses the same underlying LLM, so systematic hallucination in the model family may not be caught. External human review or Ragas evaluation is recommended for critical use cases.
