# Data Model: Dual RAG Mode

**Date**: 2026-05-14 | **Plan**: [plan.md](plan.md)

## Entities

### RagMode (enumerated string)
| Value | Meaning |
|-------|---------|
| `"simple"` | Single retrieve → generate pass; no planner or validator |
| `"agentic"` | Existing four-stage pipeline (planner → retriever → generator → validator) |

Default: `"agentic"` (backward-compatible).

---

### QueryRequest (updated)
| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `question` | `str` | min 3 / max 1000 chars | unchanged |
| `mode` | `"simple" \| "agentic"` | optional, default `"agentic"` | **new** |

---

### QueryResponse (updated)
| Field | Type | Notes |
|-------|------|-------|
| `answer` | `str` | LLM-generated answer |
| `sources` | `list[str]` | document filenames cited |
| `validation` | `str` | `"VALID"` / `"NEEDS_REVISION"` (agentic) · `"N/A"` (simple) |
| `tokens_used` | `int` | total tokens consumed |
| `mode` | `str` | **new** — echoes back which pipeline was used |

---

### ChatMessage (frontend, updated)
| Field | Type | Notes |
|-------|------|-------|
| `id` | `string` | UUID |
| `role` | `"user" \| "assistant"` | |
| `content` | `string` | |
| `sources` | `string[]` | optional |
| `validation` | `string` | optional |
| `tokens_used` | `number` | optional |
| `mode` | `string` | **new** — optional; set on assistant messages |
| `timestamp` | `Date` | |

---

## State Transitions

```
User selects mode (default: "agentic")
        │
        ▼
User submits question
        │
        ├─ mode="simple" ──▶  sanitize → guardrail-in → retrieve → generate → guardrail-out → response(validation="N/A", mode="simple")
        │
        └─ mode="agentic" ─▶  sanitize → guardrail-in → planner → retrieve → generate → validate → guardrail-out → response(validation=VALID|NEEDS_REVISION, mode="agentic")
```

Both paths terminate at the same `QueryResponse` shape.
