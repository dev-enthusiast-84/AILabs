/**
 * Client-side display masking — defense-in-depth only.
 *
 * All 11 patterns mirror backend/app/voice/redaction.py _PATTERNS in the same
 * evaluation order. The canonical label taxonomy is defined in
 * .specify/specs/011-universal-redactions/contracts/redaction-contract.json.
 */

export const REDACTION_LABELS: readonly string[] = [
  '[REDACTED_PRIVATE_KEY]',
  '[REDACTED_API_KEY]',
  '[REDACTED_TOKEN]',
  '[REDACTED_PASSWORD]',
  '[REDACTED_SECRET]',
  '[REDACTED_EMAIL]',
  '[REDACTED_SSN]',
  '[REDACTED_PHONE]',
  '[REDACTED_PAYMENT_CARD]',
] as const

// Compiled once at module load — same ordering as the backend _PATTERNS tuple.
// Pattern 10 (payment card) MUST precede pattern 11 (long-token catch-all).
const _PATTERNS: Array<{ label: string; re: RegExp }> = [
  // 1 — PEM private key block
  {
    label: '[REDACTED_PRIVATE_KEY]',
    re: /-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z0-9 ]*PRIVATE KEY-----/gi,
  },
  // 2 — OpenAI / Anthropic-style API key (sk- / sk-proj-)
  {
    label: '[REDACTED_API_KEY]',
    re: /\bsk(?:-proj)?-[A-Za-z0-9_-]{20,}\b/g,
  },
  // 3 — Bearer header token (entire "Bearer <value>" span becomes the label)
  {
    label: '[REDACTED_TOKEN]',
    re: /\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b/gi,
  },
  // 4 — password / passwd / pwd key=value
  {
    label: '[REDACTED_PASSWORD]',
    re: /\b(password|passwd|pwd)\s*[:=]\s*([^\s,;]+)/gi,
  },
  // 5 — access_token / refresh_token / id_token / api_token key=value
  {
    label: '[REDACTED_TOKEN]',
    re: /\b(access[_-]?token|refresh[_-]?token|id[_-]?token|api[_-]?token)\s*[:=]\s*([A-Za-z0-9._~+/=-]{12,})/gi,
  },
  // 6 — secret / client_secret / api_secret key=value
  {
    label: '[REDACTED_SECRET]',
    re: /\b(secret|client[_-]?secret|api[_-]?secret)\s*[:=]\s*([A-Za-z0-9._~+/=-]{12,})/gi,
  },
  // 7 — email address
  {
    label: '[REDACTED_EMAIL]',
    re: /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,
  },
  // 8 — US Social Security Number (canonical label: REDACTED_SSN, not GOV_ID)
  {
    label: '[REDACTED_SSN]',
    re: /\b\d{3}-\d{2}-\d{4}\b/g,
  },
  // 9 — US phone number
  {
    label: '[REDACTED_PHONE]',
    re: /(?<!\w)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\w)/g,
  },
  // 10 — Payment card (13–19 digits with optional separators) — MUST precede pattern 11
  {
    label: '[REDACTED_PAYMENT_CARD]',
    re: /\b(?:\d[ -]*?){13,19}\b/g,
  },
  // 11 — Long opaque token catch-all (≥32 alphanumeric chars)
  {
    label: '[REDACTED_SECRET]',
    re: /\b[A-Za-z0-9_-]{32,}\b/g,
  },
]

/**
 * Replace any sensitive values in `text` with their canonical redaction labels.
 * Returns `text` unchanged when no pattern matches (no false positives for normal prose).
 */
export function maskSensitive(text: string): string {
  let result = text
  for (const { label, re } of _PATTERNS) {
    // Reset lastIndex so stateful global regexes restart on each call.
    re.lastIndex = 0
    result = result.replace(re, label)
  }
  return result
}
