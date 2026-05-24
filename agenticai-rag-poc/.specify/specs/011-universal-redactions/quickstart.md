# Quickstart: Universal Redactions

**How to develop, test, and verify the redaction layer locally.**

---

## Prerequisites

- Backend venv active: `cd backend && source .venv/bin/activate`
- Frontend deps installed: `cd frontend && npm ci`

---

## Verifying backend redaction patterns

```bash
cd backend && source .venv/bin/activate

python -c "
from app.voice.redaction import redact_sensitive_text, redact_and_flag

fixtures = [
    ('email',        'Contact us at user@example.com for support'),
    ('ssn',          'SSN: 123-45-6789'),
    ('phone',        'Call +1 (555) 867-5309'),
    ('payment_card', 'Card: 4111 1111 1111 1111'),
    ('api_key',      'Key: sk-proj-abcdef1234567890abcd'),
    ('bearer_token', 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig'),
    ('password',     'password=s3cr3t!value'),
    ('secret',       'client_secret=abc123def456ghi789'),
    ('private_key',  '-----BEGIN RSA PRIVATE KEY-----\nMIIEpA==\n-----END RSA PRIVATE KEY-----'),
]
for name, text in fixtures:
    result = redact_and_flag(text)
    status = '✓ REDACTED' if result.was_redacted else '✗ NOT REDACTED'
    print(f'{name:15} {status}  →  {result.text[:60]}')
"
```

---

## Running the test suite

```bash
# Backend redaction unit tests
cd backend && pytest tests/unit/test_redaction.py -v

# Guardrail coverage matrix (9 surfaces)
cd backend && pytest tests/unit/test_guardrail_coverage_matrix.py -v

# Full backend suite with coverage
cd backend && pytest tests/unit/ tests/integration/ -v --cov=app --cov-report=term-missing
# Expect: ≥98% coverage

# Frontend redaction unit tests
cd frontend && npm test -- --reporter=verbose redact
# Expect: all maskSensitive() fixture tests pass + non-sensitive passthrough
```

---

## Verifying label taxonomy consistency

```bash
# Backend labels
cd backend && python -c "
from app.voice.redaction import _PATTERNS
labels = sorted({p.label for p in _PATTERNS})
print('Backend labels:')
for l in labels: print(' ', l)
"

# Frontend labels (after lib/redact.ts is created)
cd frontend && node -e "
const { REDACTION_LABELS } = require('./src/lib/redact.ts')
console.log('Frontend labels:')
REDACTION_LABELS.forEach(l => console.log(' ', l))
"
# Both lists must be identical.
```

---

## Verifying display masking in the browser

1. Start the full stack: `cd backend && uvicorn app.main:app --reload --port 8000 &` and `cd frontend && npm run dev`
2. Log in and open the chat.
3. Send a message: `My email is test@example.com and my SSN is 123-45-6789`
4. The rendered message in chat history must show `[REDACTED_EMAIL]` and `[REDACTED_SSN]`, not the original values.
5. Send a message with no sensitive content: `What is the capital of France?`
6. The message must appear unchanged.

---

## Verifying export redaction

```bash
# Using the redact endpoint directly
curl -X POST http://localhost:8000/api/voice_export/redact \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "My card is 4111 1111 1111 1111"},
      {"role": "assistant", "content": "I can help. Contact us at support@company.com"}
    ]
  }'
# Response must contain [REDACTED_PAYMENT_CARD] and [REDACTED_EMAIL]
```

---

## Environment variables

No new environment variables are introduced by this feature. Redaction patterns are compiled at import time from constants in `backend/app/voice/redaction.py`.
