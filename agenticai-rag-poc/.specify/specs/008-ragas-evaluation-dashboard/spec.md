# Feature Specification: Ragas Evaluation Dashboard

**Feature Branch**: `008-ragas-evaluation-dashboard`  
**Created**: 2026-05-21  
**Status**: Implemented  
**Input**: User description: "Enable raga evaluation default and configurable via UI settings. Display Raga evluation dashboard on header view similar to guardrails based on raga evaluation mode ( display only when its enabled). DO not over load header with too many textual content. use icons as much possible matching Digital accessibility standrads - AA"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Admin Sees Enabled Ragas Entry Point (Priority: P1)

An administrator opens the application with Ragas evaluation enabled by default and sees a compact header icon that opens the evaluation dashboard.

**Why this priority**: The dashboard is only useful if admins can discover it without adding more header text.

**Independent Test**: Sign in as admin, call `GET /api/settings/`, assert `ragas_evaluation_enabled=true`, and confirm the header shows an accessible Ragas dashboard button.

**Acceptance Scenarios**:

1. **Given** an admin session and default settings, **When** the dashboard header renders, **Then** an icon-only Ragas dashboard button is visible with an accessible name.
2. **Given** the Ragas dashboard button is clicked, **When** the modal opens, **Then** it displays the latest scores or an empty-state message.

---

### User Story 2 - Admin Configures Ragas Visibility (Priority: P1)

An administrator can turn the Ragas dashboard on or off from Settings without restarting the app.

**Why this priority**: Operators need to control whether the evaluation affordance appears in the main workspace.

**Independent Test**: Open Settings, toggle "Ragas evaluation" off, save, and assert `POST /api/settings/` includes `ragas_evaluation_enabled=false`.

**Acceptance Scenarios**:

1. **Given** Ragas evaluation is enabled, **When** an admin turns the setting off and saves, **Then** the header Ragas button disappears after settings refresh.
2. **Given** Ragas evaluation is disabled, **When** an admin turns the setting on and saves, **Then** the header Ragas button appears again.

---

### User Story 3 - Header Stays Compact and Accessible (Priority: P2)

The header avoids extra text while preserving keyboard, screen reader, focus, and contrast support.

**Why this priority**: The header already contains role, settings, guardrails, and auth actions.

**Independent Test**: Inspect the Ragas header button at desktop and mobile widths; verify it has an accessible label, visible focus ring, and icon-only layout.

**Acceptance Scenarios**:

1. **Given** the Ragas header control is visible, **When** a keyboard user tabs to it, **Then** focus is visible and the accessible name is "Open Ragas evaluation dashboard".
2. **Given** the viewport is narrow, **When** the header renders, **Then** the Ragas control remains icon-only and does not add textual clutter.

### Edge Cases

- Guests never see the Ragas dashboard header button because the existing Ragas APIs are admin-only.
- If score loading fails, the dashboard keeps the modal open and shows a toast error instead of exposing raw server details.
- If no evaluation has been run, the dashboard shows a non-blocking empty state and still allows an admin to trigger evaluation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose a boolean `ragas_evaluation_enabled` setting in `GET /api/settings/`.
- **FR-002**: System MUST default `ragas_evaluation_enabled` to enabled.
- **FR-003**: Admin users MUST be able to update `ragas_evaluation_enabled` through `POST /api/settings/`.
- **FR-004**: The Settings UI MUST provide a switch for Ragas evaluation visibility.
- **FR-005**: The header MUST render the Ragas dashboard button only for admins when `ragas_evaluation_enabled` is true.
- **FR-006**: The Ragas header control MUST be icon-first, compact, keyboard focusable, and have an accessible name.
- **FR-007**: The dashboard MUST display the latest Ragas score metrics when available and an empty state when no scores exist.

### Key Entities

- **Runtime Setting**: `ragas_evaluation_enabled`, a boolean feature flag controlling Ragas dashboard visibility.
- **Ragas Scores**: Persisted quality metrics including faithfulness, answer relevancy, context precision, context recall, model, sample count, and evaluation timestamp.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Default admin settings response includes `ragas_evaluation_enabled=true`.
- **SC-002**: Disabling the setting removes the header dashboard entry without a page reload beyond normal React refresh.
- **SC-003**: The Ragas header button adds no visible text label at desktop or mobile sizes.
- **SC-004**: The Ragas dashboard can be opened using keyboard navigation and announces a meaningful dialog title.

## Assumptions

- Ragas evaluation remains admin-only, matching existing score and trigger endpoints.
- The setting controls UI discoverability rather than removing backend endpoints.
- Existing Ragas score storage and trigger behavior remain in place.
