# Content Guardrails

> [← Home](README.md) · [Security Reference](SECURITY.md)

Configurable content policies applied to every query (input) and every answer (output).

---

## How It Works

```
User query
   ▼
[safety.py — bleach XSS strip, basic injection regex]
   ▼
[Guardrail Engine — INPUT pass]
   ├── Block rules   → HTTP 400 "Query blocked by content policy."
   ├── Flag rules    → logged server-side; query continues
   └── Redact rules  → text modified in-place; query continues
   ▼
[LangGraph Agent Pipeline]
   ▼
[Guardrail Engine — OUTPUT pass]
   ├── Block rules   → answer replaced with "Response blocked by content policy."
   ├── Redact rules  → PII replaced in answer before returning to client
   └── Flag rules    → logged server-side; answer returned unchanged
   ▼
Client receives (possibly redacted) answer
```

Processing order per pass: **block → redact → flag**. A blocking rule short-circuits immediately.

---

## Rule Types, Actions, and Targets

| Type | How it matches | Configured with |
|------|---------------|-----------------|
| `word` | Whole-word match (`\b`), case-insensitive | List of words |
| `topic` | Substring match, case-insensitive | List of keyword phrases |
| `regex` | Full regex with `re.IGNORECASE` | Pattern string + optional replacement |

**Actions:** `block` (rejects request, returns error) · `redact` (replaces matched text with `replacement`) · `flag` (logs violation server-side, text unchanged)

**Targets:** `input` · `output` · `both`

---

## Built-In Rules

Cannot be deleted (only toggled on/off by admins).

**Input rules:**

| ID | Name | Type | Action | Default |
|----|------|------|--------|:-------:|
| `prompt-injection` | Prompt Injection | regex | block | **ON** |
| `sql-injection` | SQL Injection | regex | block | **ON** |
| `input-pii-email` | Input PII — Email | regex | flag | **ON** |
| `input-profanity` | Input Profanity | word | block | OFF |

**Output rules:**

| ID | Name | Type | Action | Default |
|----|------|------|--------|:-------:|
| `output-pii-email` | Output PII — Email | regex | redact | **ON** |
| `output-pii-phone` | Output PII — Phone | regex | redact | **ON** |
| `output-ssn` | Output PII — SSN | regex | redact | **ON** |
| `output-credit-card` | Output PII — Credit Card | regex | redact | **ON** |
| `output-ai-disclaimer` | AI Self-Identification | regex | flag | **ON** |

**Both-direction rules (off by default):**

| ID | Name | Type | Action | Default |
|----|------|------|--------|:-------:|
| `violence-harmful` | Violence / Harmful Content | topic | block | OFF |
| `adult-content` | Adult Content | topic | block | OFF |

---

## Managing Rules via the UI

1. Log in as **admin** → click the **Guardrails** button (shield icon) in the header.
2. The **Rules** tab lists all rules with type, target, action, and severity badges.
3. Toggle switch to enable/disable a rule instantly.
4. **Trash** icon deletes a user-created rule (built-ins show a lock icon).
5. **Add Rule** opens the inline form to create a custom rule.
6. **Test** tab to paste text and see which rules fire before a real query.

> Guests can view rules in read-only mode; write actions are admin-only.

## Managing Rules via the API

```bash
# List all rules
curl -s http://localhost:8000/api/guardrails/ -H "Authorization: Bearer $TOKEN" | jq .

# Enable or disable a rule
curl -s -X PATCH http://localhost:8000/api/guardrails/output-ai-disclaimer \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"enabled": false}'

# Create a custom word-based block rule
curl -s -X POST http://localhost:8000/api/guardrails/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Competitor Block","type":"word","target":"input","action":"block","severity":"medium","words":["rivalcorp"]}'

# Delete a user-created rule (built-in rules return 400)
curl -s -X DELETE http://localhost:8000/api/guardrails/<rule-id> \
  -H "Authorization: Bearer $TOKEN"

# Test text against all active rules
curl -s -X POST http://localhost:8000/api/guardrails/check \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"text": "My email is alice@example.com", "target": "output"}' | jq .
# → { "allowed": true, "modified_text": "My email is [EMAIL REDACTED]", "flagged": false }
```

---

## Rule Schema

```json
{
  "id":          "stable ID (fixed for built-ins; UUID for user rules)",
  "name":        "string (2–80 chars)",
  "description": "string",
  "type":        "word | topic | regex",
  "target":      "input | output | both",
  "action":      "block | flag | redact",
  "severity":    "low | medium | high",
  "enabled":     true,
  "builtin":     false,
  "words":       ["list", "of", "words"],
  "keywords":    ["keyword phrase"],
  "pattern":     "regex string (type=regex only)",
  "replacement": "[REDACTED] (type=regex + action=redact only)"
}
```
