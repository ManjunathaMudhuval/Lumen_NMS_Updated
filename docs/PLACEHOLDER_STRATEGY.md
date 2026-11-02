# Placeholder Strategy (Before Full Development)

Date: 2026-10-16

## Purpose
Use placeholders only where required to establish structure without overbuilding fields or backend logic too early.

## Rules
1. Placeholder must represent a real planned module.
2. Placeholder must show future data intent (title, short description, empty state).
3. Avoid fake complex business logic in placeholders.
4. Avoid adding fields that are not approved in Phase 2 data contracts.
5. Every placeholder must include a "next integration step" note.

## Required Placeholder Types
1. Window-level placeholders (whole module page)
2. Component-level placeholders (card, chart, table)
3. Action placeholders (disabled buttons with tooltip, e.g. "Enabled in Phase 4")

## Placeholder Content Template
- Module title
- Purpose sentence
- Planned data source
- Empty-state guidance
- Owner phase

Example:
- Title: Event Correlation Queue
- Purpose: Shows normalized active events for operator triage.
- Planned data source: monitoring event pipeline API
- Empty state: No events yet. Connect event source in Phase 4.
- Owner phase: Phase 4

## Avoid These Mistakes
1. Adding 50+ columns before contract approval.
2. Building backend APIs for undefined fields.
3. Styling placeholders as final production components.
4. Creating one-off field names inconsistent with domain model.

## Transition from Placeholder to Real Module
1. Lock required fields in Phase 2.
2. Add API contract and sample payload.
3. Replace placeholder with real component using contract mapping.
4. Add tests for empty/partial/full payloads.
