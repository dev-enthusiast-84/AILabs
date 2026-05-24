import { describe, it, expect } from 'vitest'
import { maskSensitive, REDACTION_LABELS } from '@/lib/redact'

// ── REDACTION_LABELS constant ─────────────────────────────────────────────────

describe('REDACTION_LABELS', () => {
  it('contains all canonical label strings', () => {
    expect(REDACTION_LABELS).toContain('[REDACTED_PRIVATE_KEY]')
    expect(REDACTION_LABELS).toContain('[REDACTED_API_KEY]')
    expect(REDACTION_LABELS).toContain('[REDACTED_TOKEN]')
    expect(REDACTION_LABELS).toContain('[REDACTED_PASSWORD]')
    expect(REDACTION_LABELS).toContain('[REDACTED_SECRET]')
    expect(REDACTION_LABELS).toContain('[REDACTED_EMAIL]')
    expect(REDACTION_LABELS).toContain('[REDACTED_SSN]')
    expect(REDACTION_LABELS).toContain('[REDACTED_PHONE]')
    expect(REDACTION_LABELS).toContain('[REDACTED_PAYMENT_CARD]')
  })

  it('does NOT contain [REDACTED_GOV_ID] — that was the old incorrect frontend label', () => {
    expect(REDACTION_LABELS).not.toContain('[REDACTED_GOV_ID]')
  })
})

// ── Non-sensitive text passthrough ────────────────────────────────────────────

describe('maskSensitive — no false positives', () => {
  const cleanInputs = [
    'What is the remote work policy?',
    'Hello, how can I help you today?',
    'The meeting is at 3pm on Tuesday.',
    'Paris is the capital of France.',
    '',
    'I have 12345 items in my cart.',
    'Call us at extension 1234.',
  ]

  cleanInputs.forEach((text) => {
    it(`passes through unchanged: "${text.slice(0, 40)}"`, () => {
      expect(maskSensitive(text)).toBe(text)
    })
  })
})

// ── Pattern 1: PEM private key ────────────────────────────────────────────────

describe('maskSensitive — PEM private key', () => {
  it('redacts RSA private key block', () => {
    const text =
      '-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----'
    const result = maskSensitive(text)
    expect(result).toContain('[REDACTED_PRIVATE_KEY]')
    expect(result).not.toContain('MIIEpAIBAAKCAQEA')
  })

  it('redacts EC private key block', () => {
    const text = '-----BEGIN EC PRIVATE KEY-----\ndata\n-----END EC PRIVATE KEY-----'
    expect(maskSensitive(text)).toContain('[REDACTED_PRIVATE_KEY]')
  })
})

// ── Pattern 2: API key ────────────────────────────────────────────────────────

describe('maskSensitive — API key', () => {
  it('redacts sk- prefixed API key', () => {
    const text = 'my key is sk-abcdefghijklmnopqrstuvwxyz12345'
    const result = maskSensitive(text)
    expect(result).toContain('[REDACTED_API_KEY]')
    expect(result).not.toContain('sk-abcdefghijklmnopqrstuvwxyz12345')
  })

  it('redacts sk-proj- prefixed API key', () => {
    const text = 'key=sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef'
    expect(maskSensitive(text)).toContain('[REDACTED_API_KEY]')
  })

  it('does not redact sk-short (too short)', () => {
    expect(maskSensitive('sk-short')).not.toContain('[REDACTED_API_KEY]')
  })
})

// ── Pattern 3: Bearer token ───────────────────────────────────────────────────

describe('maskSensitive — Bearer token', () => {
  it('redacts Bearer token and does NOT preserve the "Bearer" prefix', () => {
    const text = 'Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig'
    const result = maskSensitive(text)
    expect(result).toContain('[REDACTED_TOKEN]')
    // The canonical label does not preserve "Bearer" prefix (unlike old frontend behaviour)
    expect(result).not.toMatch(/Bearer\s+\[REDACTED_TOKEN\]/)
  })

  it('is case-insensitive for bearer keyword', () => {
    const text = 'authorization: bearer AAABBBCCCDDDEEEFFFGGG'
    expect(maskSensitive(text)).toContain('[REDACTED_TOKEN]')
  })
})

// ── Pattern 4: password= ──────────────────────────────────────────────────────

describe('maskSensitive — password key=value', () => {
  it('redacts password= with [REDACTED_PASSWORD]', () => {
    const result = maskSensitive('password=SuperSecret123')
    expect(result).toContain('[REDACTED_PASSWORD]')
    expect(result).not.toContain('SuperSecret123')
  })

  it('redacts passwd: value', () => {
    expect(maskSensitive('passwd: MyP@ssw0rd')).toContain('[REDACTED_PASSWORD]')
  })

  it('redacts pwd=value', () => {
    expect(maskSensitive('host=db.example.com pwd=s3cr3t')).toContain('[REDACTED_PASSWORD]')
  })
})

// ── Pattern 5: access/refresh/id/api token ────────────────────────────────────

describe('maskSensitive — token key=value', () => {
  it('redacts access_token= with [REDACTED_TOKEN]', () => {
    const result = maskSensitive('access_token=eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9payload')
    expect(result).toContain('[REDACTED_TOKEN]')
  })

  it('redacts refresh_token= with [REDACTED_TOKEN]', () => {
    expect(maskSensitive('refresh_token=abcdefghijklmnopqrstuvwxyz1234')).toContain('[REDACTED_TOKEN]')
  })

  it('redacts api_token= with [REDACTED_TOKEN]', () => {
    expect(maskSensitive('api_token=AAAABBBBCCCCDDDDEEEE1234')).toContain('[REDACTED_TOKEN]')
  })
})

// ── Pattern 6: secret= ────────────────────────────────────────────────────────

describe('maskSensitive — secret key=value', () => {
  it('redacts client_secret= with [REDACTED_SECRET]', () => {
    expect(maskSensitive('client_secret=abcdefghijklmnopqrstuvwxyz')).toContain('[REDACTED_SECRET]')
  })

  it('redacts api_secret= with [REDACTED_SECRET]', () => {
    expect(maskSensitive('api_secret=XXXXXXXXXXXXXXXXXXXXXXXXXXX')).toContain('[REDACTED_SECRET]')
  })

  it('does NOT produce [REDACTED_SECRET] for short values (under 12 chars)', () => {
    // "secret=short" has value "short" = 5 chars < 12 minimum
    const result = maskSensitive('secret=short')
    expect(result).not.toContain('[REDACTED_SECRET]')
  })
})

// ── Pattern 7: email address ──────────────────────────────────────────────────

describe('maskSensitive — email address', () => {
  it('redacts a standard email address', () => {
    const result = maskSensitive('contact us at support@example.com for help')
    expect(result).toContain('[REDACTED_EMAIL]')
    expect(result).not.toContain('support@example.com')
  })

  it('redacts uppercase domain', () => {
    expect(maskSensitive('ADMIN@COMPANY.ORG')).toContain('[REDACTED_EMAIL]')
  })
})

// ── Pattern 8: US SSN ─────────────────────────────────────────────────────────

describe('maskSensitive — US SSN', () => {
  it('redacts SSN with canonical [REDACTED_SSN] label', () => {
    const result = maskSensitive('SSN: 123-45-6789')
    expect(result).toContain('[REDACTED_SSN]')
    expect(result).not.toContain('123-45-6789')
  })

  it('does NOT use the old [REDACTED_GOV_ID] label for SSNs', () => {
    const result = maskSensitive('987-65-4321')
    expect(result).not.toContain('[REDACTED_GOV_ID]')
    expect(result).toContain('[REDACTED_SSN]')
  })
})

// ── Pattern 9: US phone number ────────────────────────────────────────────────

describe('maskSensitive — US phone number', () => {
  it('redacts dashed format', () => {
    const result = maskSensitive('call me at 555-867-5309')
    expect(result).toContain('[REDACTED_PHONE]')
    expect(result).not.toContain('555-867-5309')
  })

  it('redacts with country code +1', () => {
    expect(maskSensitive('reach me at +1 800 555 1234')).toContain('[REDACTED_PHONE]')
  })

  it('redacts parentheses format', () => {
    expect(maskSensitive('phone: (415) 555-2671')).toContain('[REDACTED_PHONE]')
  })
})

// ── Pattern 10: Payment card ──────────────────────────────────────────────────

describe('maskSensitive — payment card', () => {
  it('redacts 16-digit card with spaces', () => {
    const result = maskSensitive('card: 4111 1111 1111 1111')
    expect(result).toContain('[REDACTED_PAYMENT_CARD]')
    expect(result).not.toContain('4111')
  })

  it('redacts 16-digit card without spaces', () => {
    expect(maskSensitive('card=4111111111111111')).toContain('[REDACTED_PAYMENT_CARD]')
  })
})

// ── Pattern ordering: payment card before long-token catch-all ───────────────

describe('maskSensitive — pattern ordering invariant', () => {
  it('card number receives [REDACTED_PAYMENT_CARD] not [REDACTED_SECRET]', () => {
    const result = maskSensitive('4111111111111111')
    expect(result).toContain('[REDACTED_PAYMENT_CARD]')
    expect(result).not.toContain('[REDACTED_SECRET]')
  })
})

// ── Pattern 11: Long opaque token catch-all ───────────────────────────────────

describe('maskSensitive — long token catch-all', () => {
  it('redacts a 40-char opaque token with [REDACTED_SECRET]', () => {
    const result = maskSensitive('token: abcdefghijklmnopqrstuvwxyzABCDEFGH')
    expect(result).toContain('[REDACTED_SECRET]')
  })
})

// ── Idempotency and repeated calls ────────────────────────────────────────────

describe('maskSensitive — idempotency', () => {
  it('calling maskSensitive twice returns the same result', () => {
    const text = 'email me at user@example.com and call 555-867-5309'
    expect(maskSensitive(maskSensitive(text))).toBe(maskSensitive(text))
  })

  it('global regex lastIndex is reset on each call (no cross-call state)', () => {
    const text = 'sk-abcdefghijklmnopqrstuvwxyz12345'
    const r1 = maskSensitive(text)
    const r2 = maskSensitive(text)
    expect(r1).toBe(r2)
    expect(r1).toContain('[REDACTED_API_KEY]')
  })
})
