# Phase 2 - Required Fields and Window Completion

## Goal
Finalize required field models and replace lightweight placeholders with contract-aligned UI components.

## Steps
1. Define required fields for each module.
2. Publish JSON contract examples for all modules.
3. Build real table columns and detail drawers.
4. Add field-level validation and fallback rendering.
5. Remove redundant placeholder elements.

## Deliverables
1. Approved field dictionary.
2. Contract documentation with sample payloads.
3. Contract-driven frontend rendering.

## Current Contract (Inventory Scope)
1. docs/PHASE2_INVENTORY_API_CONTRACT.md

## Exit Criteria
1. No unapproved fields in UI.
2. Required fields are visible and validated.
3. UI components are ready for backend integration.

## Phase 2 Closeout Checks (Inventory Scope)
1. Backend must not return placeholder/dummy metadata values.
2. Discovery mock may change state fields only (status/netconf/source).
3. Contract smoke script passes end-to-end against running backend.

Run smoke script:
1. Start backend on port 8788.
2. Run: backend/tools/phase2_inventory_smoke.sh
