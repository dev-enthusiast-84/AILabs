# Guardrails API Reference

> [← Home](README.md) · [← Security](security/SECURITY.md) · [Guardrails](security/GUARDRAILS.md)

curl examples and rule schema for managing guardrail rules via the REST API.

---

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
