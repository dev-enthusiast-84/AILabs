# Data Model: Dependency Upgrade

This feature has no new data entities. The "model" here is the dependency graph — the
before/after version constraints that define what gets installed together.

---

## Dependency Graph: Before (current)

```
langgraph==0.2.73
  └─ langchain-core>=0.3.x          (resolves to 0.3.86 — unpinned, drifts)
  └─ langchain-checkpoint==2.1.2

langchain==0.3.18
  └─ langchain-core>=0.3.x,<0.4.0

langchain-openai==0.3.6
  └─ langchain-core>=0.3.x
  └─ openai>=1.x                    (resolves to 1.61.1)

langchain-community==0.3.17
  └─ langchain-core>=0.3.x

langchain-chroma==0.2.2
  └─ langchain-core>=0.3.x
  └─ chromadb>=0.4                  (resolves to 0.6.3)

langchain-experimental==0.3.4
  └─ langchain-core>=0.3.x

PROBLEM: langchain-core is UNPINNED — drifts upward silently on fresh installs.
```

---

## Dependency Graph: After (target)

```
langgraph==1.2.0
  └─ langchain-core>=1.4.0,<2.0.0   (hard lower bound)
  └─ langchain-checkpoint>=4.1.0

langchain==1.3.1
  └─ langchain-core>=1.4.0,<2.0.0

langchain-openai==1.2.1
  └─ langchain-core>=1.4.0
  └─ openai>=2.0.0                   (forces openai 2.x)

langchain-community==0.4.1
  └─ langchain-core>=1.4.0

langchain-chroma==1.1.0
  └─ langchain-core>=1.4.0
  └─ chromadb>=1.0.0                 (forces chromadb 1.x)

langchain-experimental==0.4.1
  └─ langchain-core>=1.4.0

langchain-text-splitters==1.1.2     (new: split from langchain package)
  └─ langchain-core>=1.4.0

langgraph-prebuilt==1.1.0           (new: split from langgraph package)
  └─ langgraph>=1.0.0

ALL VERSION CONSTRAINTS NOW CONSISTENT — no unpinned drift possible.
```

---

## Code Touch Points (state transitions)

Each of the following represents a specific code location that must change or be verified:

### Confirmed Breaking (must change)

| Location | Before | After |
|----------|--------|-------|
| `backend/app/agents/rag_agent.py:64` | `from langgraph.graph import END, StateGraph` | `from langgraph.graph import END, START, StateGraph` |
| `backend/app/agents/rag_agent.py:645` | `graph.set_entry_point("planner")` | `graph.add_edge(START, "planner")` |

### Verify at install time (may change)

| Location | Current import | Possible new path |
|----------|---------------|-------------------|
| `backend/app/agents/rag_agent.py:58` | `from langchain_community.callbacks import get_openai_callback` | Same path still works in 0.4.1; emit a deprecation. Monitor. |
| `backend/app/rag/pipeline.py:15` | `from langchain_community.callbacks import get_openai_callback` | Same as above. |
| `backend/tests/unit/test_rag_agent.py:165,195,443,472` | `patch("app.agents.rag_agent.get_openai_callback")` | Update if import path in source changes. |
| `backend/app/rag/vector_store.py:286` | `from langchain_chroma import Chroma` (lazy) | Constructor args need live-test verification. |

### No change needed (stable APIs)

- All `langchain_core.documents.Document` usages (6 files)
- All `langchain_core.messages.*` usages
- All `langchain_core.prompts.ChatPromptTemplate` usages
- All `langchain_core.output_parsers.StrOutputParser` usages
- All `langchain_core.embeddings.Embeddings` usages
- All LCEL `|` chain patterns
- `langchain_experimental.text_splitter.SemanticChunker` (lazy import, graceful fallback)
- `langchain_openai.ChatOpenAI` constructor and mock patterns

---

## Requirements Files (before → after delta)

### `backend/requirements.txt` changes

```diff
- langchain==0.3.18
- langchain-core==0.3.86
- langchain-openai==0.3.6
- langchain-community==0.3.17
- langgraph==0.2.73
+ langchain==1.3.1
+ langchain-core==1.4.0
+ langchain-openai==1.2.1
+ langchain-community==0.4.1
+ langgraph==1.2.0
+ langchain-text-splitters==1.1.2
```

### `backend/requirements-dev.txt` changes

```diff
- langchain==0.3.18
- langchain-openai==0.3.6
- langchain-community==0.3.17
- langchain-chroma==0.2.2
- langchain-experimental==0.3.4
- langgraph==0.2.73
+ langchain==1.3.1
+ langchain-openai==1.2.1
+ langchain-community==0.4.1
+ langchain-chroma==1.1.0
+ langchain-experimental==0.4.1
+ langgraph==1.2.0
+ langchain-text-splitters==1.1.2
```

### `backend/docs/` and `CLAUDE.md` changes

The constitution tech-stack table currently reads:
```
| Agent pipeline | LangGraph StateGraph | 0.2.73 |
```
Must be updated to `1.2.0` and the `langchain` row updated to `1.3.1`.
