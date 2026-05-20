# Feature Specification: Agentic RAG Query Pipeline

**Feature Branch**: `brownfield/query-pipeline`
**Created**: 2026-05-04
**Status**: Brownfield (describes existing behaviour)
**Input**: Brownfield reverse-spec of `backend/app/agents/rag_agent.py` and `backend/app/api/query.py`

---

> **Brownfield note**: This spec describes what the system CURRENTLY does. No new
> development is implied. All behaviour is sourced directly from the production code.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Successful Grounded Answer (Priority: P1)

A logged-in user submits a natural-language question against documents they have already
uploaded. The system rewrites the question for better retrieval, finds relevant chunks,
generates a grounded answer, and quality-validates the answer — returning the answer,
source filenames, validation status, and cumulative token count.

**Why this priority**: Core value proposition of the product. Every other feature is
ancillary to this path.

**Independent Test**: Upload one document, POST to `/api/query/` with a question whose
answer is present in that document, and assert that `answer` is non-empty, `sources`
contains the document filename, and `validation` equals `"VALID"`.

**Acceptance Scenarios**:

1. **Given** at least one document is indexed and a valid JWT is present,
   **When** `POST /api/query/` is called with `{"question": "What is the leave policy?"}`,
   **Then** the response contains `answer` (non-empty string), `sources` (list of
   filenames drawn from indexed documents), `validation` (`"VALID"` or `"NEEDS_REVISION"`),
   and `tokens_used` (positive integer summing planner + generator + validator LLM calls).

2. **Given** the retrieved context contains information relevant to the question,
   **When** the generator node runs,
   **Then** the answer is grounded exclusively in that context — no invented statistics,
   names, or details absent from the retrieved chunks.

3. **Given** the validator node runs after the generator,
   **When** the answer is faithful to the retrieved context,
   **Then** `validation` is `"VALID"` and the full answer is returned to the caller.

---

### User Story 2 - Fallback When No Relevant Docs Are Found (Priority: P2)

A user asks a question that is semantically unrelated to any indexed content. The
retriever returns zero chunks. The generator must honestly communicate this instead of
hallucinating an answer.

**Why this priority**: Honest fallback prevents user trust erosion; it is a deliberate
product decision enforced by the generator system prompt.

**Independent Test**: Index one document, then query about a completely unrelated topic.
Assert the answer text equals the fallback phrase and `sources` is an empty list.

**Acceptance Scenarios**:

1. **Given** indexed documents exist but none are relevant to the query,
   **When** the retriever node runs and returns zero chunks,
   **Then** `retrieved_context` is set to `"No relevant documents found in the knowledge
   base."` and `sources` is `[]`.

2. **Given** the generator receives a context of `"No relevant documents found ..."`,
   **When** it produces an answer,
   **Then** the answer is exactly (or semantically equivalent to):
   `"I could not find sufficient information in the uploaded documents to answer this question."`

3. **Given** the generator produced the fallback phrase,
   **When** the validator evaluates it,
   **Then** `validation` is `"VALID"` because the validator treats honest "not found"
   statements as correct behaviour, not hallucination.

---

### User Story 3 - Input Blocked by Guardrails (Priority: P2)

A user submits a query that matches an active block-action guardrail rule (e.g., a
prompt-injection pattern). The system must reject the request before any LLM call is made.

**Why this priority**: Security boundary. The pre-LLM check prevents prompt-injection
and SQL-injection patterns from reaching the agent.

**Independent Test**: POST a query containing `"ignore all previous instructions"`;
assert HTTP 400 is returned with `detail: "Query blocked by content policy."` and that
no `tokens_used` is incurred.

**Acceptance Scenarios**:

1. **Given** a query contains a prompt-injection pattern (`ignore all previous
   instructions`, `you are now`, `act as a`, `system prompt`, `[INST]`, etc.),
   **When** the input guardrail check runs after `sanitize_query()`,
   **Then** the endpoint returns HTTP 400 with `"Query blocked by content policy."`.

2. **Given** a query contains a SQL-injection pattern (`UNION SELECT`, `DROP TABLE`,
   `DELETE FROM`, etc.),
   **When** the input guardrail check runs,
   **Then** the endpoint returns HTTP 400 with `"Query blocked by content policy."`.

3. **Given** a query contains a flagged-but-allowed pattern (e.g., an email address),
   **When** the input guardrail check runs,
   **Then** the query proceeds to the agent and the violation is logged server-side only.

---

### User Story 4 - Output Redacted by Guardrails (Priority: P2)

The LLM-generated answer contains PII (email, phone number, SSN, credit card). The
output guardrail automatically redacts the sensitive data before the response is returned
to the caller.

**Why this priority**: Prevents unintentional PII leakage from LLM responses; enforces
OWASP A02 at the output boundary.

**Independent Test**: Inject a document containing a fake email address; query about
that person; assert the response `answer` contains `[EMAIL REDACTED]` instead of the
actual address.

**Acceptance Scenarios**:

1. **Given** the generated answer contains an email address,
   **When** the output guardrail check runs,
   **Then** every email address in `answer` is replaced with `[EMAIL REDACTED]` before
   the response is serialised.

2. **Given** the generated answer contains a phone number, SSN, or credit card number,
   **When** the output guardrail check runs,
   **Then** the matched text is replaced with `[PHONE REDACTED]`, `[SSN REDACTED]`, or
   `[CARD REDACTED]` respectively.

3. **Given** the generated answer triggers an output block-action rule,
   **When** the output guardrail check runs,
   **Then** the entire `answer` field is replaced with `"Response blocked by content
   policy."` — the original answer is discarded.

---

### User Story 5 - No Documents Indexed (Priority: P3)

A user calls the query endpoint before uploading any documents. The system must refuse
immediately without starting the agent pipeline.

**Why this priority**: Guard against vacuous LLM calls that would burn tokens and
return meaningless answers.

**Independent Test**: Start with an empty vector store and POST to `/api/query/`; assert
HTTP 400 is returned with the no-documents message.

**Acceptance Scenarios**:

1. **Given** the vector store contains no indexed documents (empty `list_document_sources()`),
   **When** `POST /api/query/` is called,
   **Then** the response is HTTP 400 with
   `"No documents have been indexed yet. Upload at least one document first."`.

2. **Given** no documents are indexed,
   **When** the 400 is returned,
   **Then** the agent pipeline (`run_agent`) is never invoked and zero tokens are consumed.

---

### User Story 6 - Rate Limiting (Priority: P3)

A client that sends too many queries in a short window is throttled to protect backend
resources.

**Why this priority**: OWASP A04 — rate limits prevent denial-of-service via repeated
expensive LLM calls.

**Independent Test**: Fire 11 identical POST requests from the same IP within one minute;
assert the 11th returns HTTP 429.

**Acceptance Scenarios**:

1. **Given** a single IP address has already sent 10 query requests within one minute,
   **When** an 11th request arrives,
   **Then** the response is HTTP 429 Too Many Requests.

2. **Given** the rate-limit window resets after 60 seconds,
   **When** the same IP sends a new request in the next window,
   **Then** the request is processed normally.

---

### Edge Cases

- **Agent exception**: If `run_agent()` raises any unhandled exception, the endpoint
  returns HTTP 500 with `"The agent encountered an error processing your query. Please try again."`.
  The original exception is chained (not exposed to the client).

- **Token budget warning**: When cumulative `tokens_used` across planner + generator
  exceeds the configured `TOKEN_BUDGET_WARNING_THRESHOLD` (default 800), a structured
  `WARNING` log entry is emitted by the generator node. The response is NOT altered;
  this is a server-side observability signal only.

- **Validator JSON parse failure**: If the validator LLM does not return valid JSON,
  `json.loads()` raises `JSONDecodeError`; the code catches it and defaults
  `validation` to `"VALID"` rather than propagating an error.

- **Unauthenticated request**: The endpoint uses `get_current_user` — any request
  without a valid JWT Bearer token returns HTTP 401 before any pipeline logic runs.

- **Question too short or too long**: `QueryRequest.question` is a Pydantic field with
  `min_length=3, max_length=1000`. Violations return HTTP 422 Unprocessable Entity.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST execute query processing through a fixed four-node
  LangGraph pipeline in the order: Planner → Retriever → Generator → Validator.

- **FR-002**: The Planner node MUST rewrite the user's raw question into a
  search-optimised query using an LLM call (temperature=0.0) before any vector
  similarity search is performed.

- **FR-003**: The Retriever node MUST perform a top-k similarity search (k=4 by
  default via `RETRIEVER_K` config) against the ChromaDB vector store using the
  planner-refined query. It MUST NOT make any LLM call.

- **FR-004**: The Generator node MUST produce an answer grounded exclusively in the
  retrieved context. When context contains no relevant information, it MUST respond
  with the canonical fallback phrase rather than fabricating content.

- **FR-005**: The Validator node MUST call an LLM to quality-check the answer against
  the retrieved context and return a `status` of `"VALID"` or `"NEEDS_REVISION"`. On
  any JSON parse error it MUST default to `"VALID"`.

- **FR-006**: Every LLM-calling node (Planner, Generator, Validator) MUST track token
  consumption via `get_openai_callback()` and accumulate the count into `AgentState.tokens_used`.

- **FR-007**: The API endpoint MUST call `sanitize_query()` (bleach + injection-pattern
  stripping) on the raw question BEFORE evaluating guardrails or invoking the agent.

- **FR-008**: The API endpoint MUST run an input guardrail check AFTER sanitization;
  if any active block-action rule matches, it MUST return HTTP 400 immediately without
  invoking the agent.

- **FR-009**: The API endpoint MUST run an output guardrail check on the generated
  answer; if a block-action rule fires the entire answer MUST be replaced with
  `"Response blocked by content policy."`.

- **FR-010**: Flagged (non-blocking) guardrail violations MUST be logged server-side
  via structlog and MUST NOT alter the query flow or the response content.

- **FR-011**: The endpoint MUST return HTTP 400 with an informative message when
  `list_document_sources()` returns an empty list.

- **FR-012**: The endpoint MUST return HTTP 500 (with a safe generic message) when
  `run_agent()` raises an unhandled exception.

- **FR-013**: The endpoint MUST enforce a rate limit of 10 requests per minute per
  client IP address (configurable via `QUERY_RATE_LIMIT_PER_MINUTE`).

- **FR-014**: The `QueryResponse` schema MUST include: `answer` (str), `sources`
  (list of strings — deduplicated document filenames), `validation` (str), and
  `tokens_used` (int, default 0).

- **FR-015**: The agent singleton (`_AGENT`) MUST be compiled lazily on first use
  and reused for subsequent requests. It is reset to `None` by `apply_runtime_settings()`
  when API key or model is changed.

### Key Entities

- **AgentState**: LangGraph TypedDict carrying pipeline state between nodes.
  Fields: `question` (str, mutated by Planner), `retrieved_context` (str),
  `answer` (str), `validation` (str), `tokens_used` (int, accumulated),
  `messages` (list[BaseMessage], append-only via `operator.add`), `sources` (list[str]).

- **QueryRequest**: Pydantic input model. `question` field: `min_length=3`,
  `max_length=1000`.

- **QueryResponse**: Pydantic output model. Fields: `answer`, `sources`, `validation`,
  `tokens_used` (default 0).

- **GuardrailResult**: Returned by `GuardrailEngine.check()`. Fields: `allowed` (bool),
  `modified_text` (str — redacted answer or original), `violations` (list), `flagged` (bool).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a query whose answer exists in indexed documents, the `answer` field
  is non-empty and `sources` contains at least one document filename in 100% of
  successful calls.

- **SC-002**: The pipeline never invokes an LLM when a document-indexed precondition
  fails or a block-action guardrail fires (zero tokens consumed for those paths).

- **SC-003**: `tokens_used` in the response equals the sum of planner + generator +
  validator callback totals as measured by `get_openai_callback()`.

- **SC-004**: A 10/minute-per-IP rate cap is enforced; the 11th request within one
  minute from the same IP returns HTTP 429.

- **SC-005**: Output PII redaction (email, phone, SSN, credit card) is applied before
  the response is returned; no raw PII appears in the serialised `QueryResponse`.

- **SC-006**: The validator defaults to `"VALID"` on JSON parse failure in 100% of
  observed cases — no 500 errors arise from malformed validator LLM output.

---

## Assumptions

- The ChromaDB vector store is pre-populated by the document upload pipeline; the query
  pipeline has no responsibility for ingestion or indexing.

- The `_llm()` factory reads the effective API key and model at call time from
  `settings_store`, so a runtime settings change is reflected in the very next agent
  invocation after the singleton is cleared.

- `sanitize_query()` (from `guardrails/safety.py`) strips HTML and regex-detected
  injection patterns; the input guardrail engine is a second, configurable layer on top.

- All four LangGraph nodes run synchronously inside a single `run_agent()` call;
  there is no async fan-out within the graph.

- The `sources` list is deduplicated using a Python `set` in the retriever node;
  ordering within the list is not guaranteed.

- Token counting relies on LangChain's `get_openai_callback()` context manager; if
  a node's LLM call errors before the callback records usage, `tokens_used` for that
  node defaults to 0 and the error propagates.

- The rate limiter (`slowapi`) uses the client's remote IP address (`get_remote_address`)
  as the key; clients behind NAT share a rate limit bucket.
