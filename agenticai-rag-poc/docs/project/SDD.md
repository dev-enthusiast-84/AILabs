# SDD Workflow

> [← Home](README.md) · [← Project](project/PROJECT.md)

Spec-Kit Spec-Driven Development — every feature starts with a written spec committed before any implementation code.

---

## Why Spec-First?

In a codebase driven by an AI agent (Claude Code), a committed spec acts as a contract:
- The agent cannot invent requirements that were never discussed.
- Reviewers have a baseline to test the implementation against.
- Future agents resuming a feature have a record of intent.

The project constitution at `.specify/memory/constitution.md` encodes the 6 non-negotiable rules from `CLAUDE.md` (tests, OWASP, performance, docs, deployment, context snapshot) in a structured, agent-executable format. **Both files must stay in sync at all times.**

---

## Installation

```bash
pip3 install "git+https://github.com/github/spec-kit.git"
specify --version
```

The project was already bootstrapped with `specify init . --ai claude --no-git --force` — do not re-run this.

---

## The 6 Slash Commands

| Command | Purpose | Output |
|---------|---------|--------|
| `/speckit-constitution` | Create / update the project constitution | `.specify/memory/constitution.md` |
| `/speckit-specify [name]` | Write a feature specification (before any code) | `.specify/specs/[name]/spec.md` |
| `/speckit-plan` | Write the technical implementation plan | `plan.md` + `contracts/api-spec.json` |
| `/speckit-tasks` | Generate TDD-ordered task checklist | `tasks.md` (tests before implementation) |
| `/speckit-implement` | Execute task list — code + tests + docs | Checked tasks, updated docs |
| `/speckit-analyze` | Cross-artifact consistency check (optional) | Session report |

**Run spec validation before every PR:**
```bash
make spec-check    # exits 0 if all specs valid, exits 1 if any issue found
```

---

## Full Workflow

```
1. /speckit-specify [feature-name]    → spec.md (user stories, acceptance scenarios)
2. Review and approve spec.md
3. /speckit-plan                      → plan.md + api-spec.json
4. Review and approve plan.md
5. /speckit-tasks                     → tasks.md (TDD order: tests before impl)
6. /speckit-implement                 → code + tests + docs updated
7. make spec-check                    → validate all specs
8. /speckit-analyze (optional)        → confirm implementation covers all scenarios
```

**TDD task ordering rule:**
```
- [ ] T-01  Write unit tests for streaming endpoint
- [ ] T-02  Write integration tests for streaming endpoint
- [ ] I-01  Implement streaming endpoint (depends on T-01, T-02)
- [ ] I-02  Update ChatInterface to consume SSE stream (depends on T-03)
- [ ] T-03  Write Vitest tests for ChatInterface streaming
```

---

## Brownfield Back-Specs

Written for the five core capabilities that existed at onboarding time — describe what the system *does* (present tense).

| Capability | Location | Key scenarios |
|------------|----------|--------------|
| Document ingestion | `.specify/specs/document-ingestion/` | Admin uploads PDF/TXT/CSV/XLSX; guests blocked; 20 MB cap |
| RAG agent pipeline | `.specify/specs/rag-agent-pipeline/` | Planner rewrites query; Generator produces grounded answer; Validator checks faithfulness |
| JWT auth tiers | `.specify/specs/auth-tiers/` | Admin bcrypt login; guest 15-min token; write endpoints → 403 for guest |
| Content guardrails | `.specify/specs/content-guardrails/` | XSS stripped; injection blocked; filename traversal rejected |
| Settings management | `.specify/specs/settings-management/` | Admin updates key + model; guests locked after first change |

---

## Constitution Governance

Amend the constitution when: a new non-negotiable rule is adopted, the tech stack changes materially, or OWASP controls change.

**Amendment procedure:**
1. Run `/speckit-constitution` — describe the change.
2. Review the diff; bump version:
   - **PATCH** (e.g. 1.0.0 → 1.0.1): Clarification or wording fix
   - **MINOR** (e.g. 1.0.1 → 1.1.0): New section or principle added
   - **MAJOR** (e.g. 1.1.0 → 2.0.0): Principle removed or fundamentally redefined
3. Update `CLAUDE.md` to match (same commit).
4. Note the amendment in `PENDING_TASKS.md` with status `done`.

**CLAUDE.md ↔ constitution.md sync rule:** `CLAUDE.md` is human-readable; the constitution is agent-executable. Both express the same rules. Divergence is a defect — the constitution takes precedence for agent behaviour; `CLAUDE.md` for human documentation.

---

## Quick Reference

| Task | Command |
|------|---------|
| Install Spec-Kit | `pip3 install "git+https://github.com/github/spec-kit.git"` |
| Validate all specs | `make spec-check` |
| Run validation + summary | `make spec-validate` |
| Add spec to CI | `- name: Validate specs` / `run: make spec-check` in GitHub Actions |
