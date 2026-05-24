# Voice Export API Schemas

> [← Home](README.md) · [API Reference](api/API.md) · [API Schemas](api/API-SCHEMAS.md)

Schemas for the voice/audio chat export endpoints: redaction, synchronous export, and async job management. All endpoints require a Bearer JWT (`role: "guest"` or `role: "admin"`).

---

## ChatVoiceExportRequest

Sent to `POST /api/chat/voice/export` to generate audio from a chat transcript.

```json
{ "messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
  "format": "mp3" }
```

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `messages` | `ChatMessage[]` | Yes | Ordered chat messages (`role`: `user`\|`assistant`\|`system`) |
| `format` | `"mp3"\|"opus"\|"aac"\|"flac"` | Yes | Desired audio container format |

---

## ChatVoiceExportResponse

Returned synchronously (HTTP 200) when transcript ≤ 4 000 chars, non-production mode, and `defer` is not `true`.

```json
{ "audio": "<base64-encoded audio bytes>", "format": "mp3" }
```

| Field | Type | Description |
|-------|------|-------------|
| `audio` | string | Base64-encoded audio bytes in the requested `format` |
| `format` | `"mp3"\|"opus"\|"aac"\|"flac"` | Confirmed audio format |

---

## ChatVoiceExportAcceptedResponse

Returned **HTTP 202** when deferred — production mode, `defer: true`, or transcript > 4 000 chars after redaction.

```json
{ "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "status": "queued" }
```

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string (UUID) | Stable job identifier; use to poll or cancel |
| `status` | `"queued"` | Always `"queued"` at acceptance time |

Poll via `GET /api/chat/voice/export/jobs/{job_id}`.

---

## ChatVoiceExportJobStatusResponse

Returned by `GET /api/chat/voice/export/jobs/{job_id}` (poll) and `DELETE /api/chat/voice/export/jobs/{job_id}` (cancel).

```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "succeeded",
  "audio": "<base64 audio bytes — present only when succeeded>",
  "format": "mp3",
  "error_code": null, "error_message": null, "retry_count": 0
}
```

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string (UUID) | Job identifier |
| `status` | enum | Current lifecycle state (see below) |
| `audio` | string \| null | Base64 audio — present only when `status` is `"succeeded"` and artifact not yet expired |
| `format` | string | Audio format |
| `error_code` | string \| null | Machine-readable error token when `"failed"` |
| `error_message` | string \| null | Human-readable error detail when `"failed"` |
| `retry_count` | int | OpenAI speech-API retries attempted (max 1) |

**`status` values:** `queued` (accepted, not started) · `running` (TTS in progress) · `succeeded` (audio ready, 10 min artifact retention) · `failed` (after retries; see `error_code`) · `expired` (retention elapsed; `audio` is null) · `canceled` (via DELETE)

**`error` field:** `{ code: string; message: string } | null` — `null` when succeeded or in progress; `code` is machine-readable (e.g. `"tts_timeout"`); `message` is safe to surface to end users.

---

## ChatTranscriptRedactionResponse

Returned by `POST /api/chat/voice/redact`. Backend PII redaction on the transcript without generating audio — useful for previewing what will be spoken before a full export request.

```json
{ "redacted": "Hello, my name is [REDACTED]. I live in [REDACTED]." }
```

| Field | Type | Description |
|-------|------|-------------|
| `redacted` | string | Full transcript with PII tokens replaced by `[REDACTED]` |

Redaction is applied server-side via the active guardrail engine. Original messages are never stored.
