# Voice Export API Schemas

> [← Home](README.md) · [API Reference](api/API.md) · [API Schemas](api/API-SCHEMAS.md)

Schemas for the voice/audio chat export endpoints: redaction, synchronous export, and async job
management. All endpoints require a Bearer JWT (`role: "guest"` or `role: "admin"`).

---

## ChatVoiceExportRequest

Sent to `POST /api/chat/voice/export` to generate audio from a chat transcript.

```json
{ "messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
  "format": "mp3" }
```

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `messages` | `ChatMessage[]` | Yes | Ordered list of chat messages (`role`: `user`\|`assistant`\|`system`) |
| `format` | `"mp3"\|"opus"\|"aac"\|"flac"` | Yes | Desired audio container format |

---

## ChatVoiceExportResponse

Returned synchronously (HTTP 200) when transcript ≤ 4 000 chars, non-production mode, and
`defer` is not `true`.

```json
{
  "audio":   "<base64-encoded audio bytes>",
  "format":  "mp3"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `audio` | string | Base64-encoded audio bytes in the requested `format` |
| `format` | `"mp3"\|"opus"\|"aac"\|"flac"` | Confirmed audio format |

---

## ChatVoiceExportAcceptedResponse

Returned with **HTTP 202 Accepted** when the export is deferred — production mode, explicit
`defer: true`, or transcript exceeds 4 000 characters after redaction.

```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "queued"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string (UUID) | Stable identifier for the background job; use to poll or cancel |
| `status` | `"queued"` | Always `"queued"` at acceptance time |

Poll the job using `GET /api/chat/voice/export/jobs/{job_id}`.

---

## ChatVoiceExportJobStatusResponse

Returned by `GET /api/chat/voice/export/jobs/{job_id}` (poll) and
`DELETE /api/chat/voice/export/jobs/{job_id}` (cancel).

```json
{
  "job_id":        "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status":        "succeeded",
  "audio":         "<base64-encoded audio bytes>",
  "format":        "mp3",
  "error_code":    null,
  "error_message": null,
  "retry_count":   0
}
```

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string (UUID) | Job identifier |
| `status` | enum (see below) | Current lifecycle state |
| `audio` | string \| null | Base64 audio payload — present only when `status` is `"succeeded"` and the artifact has not yet expired |
| `format` | string | Audio format of the payload |
| `error_code` | string \| null | Machine-readable error token when `status` is `"failed"` |
| `error_message` | string \| null | Human-readable error detail when `status` is `"failed"` |
| `retry_count` | int | Number of OpenAI speech-API retries attempted (max 1) |

**Status values:**

| Value | Meaning |
|-------|---------|
| `queued` | Job accepted, not yet started |
| `running` | OpenAI speech request in progress |
| `succeeded` | Audio ready; artifact retained for 10 minutes |
| `failed` | Speech request failed after retries; see `error_code` |
| `expired` | Artifact retention window elapsed; `audio` is null |
| `canceled` | Canceled via DELETE before completion |

---

## ChatVoiceExportJobResponse.error

When a deferred voice export job reaches a terminal error state, the `error` field on the job status response is:

```typescript
{ code: string; message: string } | null
```

- `null` when the job succeeded or is still in progress.
- `code` — a short machine-readable error category (e.g. `"tts_timeout"`, `"tts_api_error"`).
- `message` — a human-readable description safe to surface to end users.

---

## ChatTranscriptRedactionResponse

Returned by `POST /api/chat/voice/redact`. Performs backend PII redaction on the transcript
without generating any audio — useful for previewing what will be spoken before committing to
an audio export request.

```json
{
  "redacted": "Hello, my name is [REDACTED]. I live in [REDACTED]."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `redacted` | string | The full transcript with PII tokens replaced by `[REDACTED]` |

Redaction is applied server-side via the active guardrail engine. Original messages are never
stored. Display this preview to the user before triggering a full voice export.
