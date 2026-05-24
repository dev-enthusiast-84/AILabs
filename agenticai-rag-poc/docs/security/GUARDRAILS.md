# Content Guardrails

> [← Home](README.md) · [Security Reference](security/SECURITY.md)

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

## Rule Persistence

Custom rules are stored in-memory and reset on server restart. Built-in rules are re-seeded automatically on every startup from a hardcoded list in `guardrails/store.py`. There is no database backend for guardrail rules — if you need custom rules to survive restarts, re-create them via the API after each startup or add them to `_default_rules()` in the store.

## Rule Lifecycle

1. **Create** (`POST /api/guardrails/`) — new user-defined rule is added to the in-memory store and enabled by default.
2. **Toggle** (`PATCH /api/guardrails/{id}` with `{"enabled": false/true}`) — enable or disable any rule. Built-in rules may only have `enabled` patched; all other fields are immutable.
3. **Delete** (`DELETE /api/guardrails/{id}`) — removes a user-defined rule until the next server restart. Built-in rules cannot be deleted; attempting to do so returns HTTP 400.

## Guest Restrictions

Guests may call `GET /api/guardrails/` and `GET /api/guardrails/{id}` to view rules in read-only mode. `POST`, `PATCH`, and `DELETE` on guardrail endpoints require admin role (HTTP 403 otherwise).

---

## Managing Rules via the UI

1. Log in as **admin** → click the **Guardrails** button (shield icon) in the header.
2. The **Rules** tab lists all rules with type, target, action, and severity badges.
3. Toggle switch to enable/disable a rule instantly.
4. **Trash** icon deletes a user-created rule (built-ins show a lock icon).
5. **Add Rule** opens the inline form to create a custom rule.
6. **Test** tab to paste text and see which rules fire before a real query.

> Guests can view rules in read-only mode; write actions are admin-only.

For curl examples and the full rule JSON schema → [Guardrails API Reference](security/GUARDRAILS-API.md).
```
