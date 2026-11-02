# Phase 3 - Discovery and Inventory Backend

## Goal
Implement real device discovery and inventory APIs.

## Steps
1. Implement NETCONF discovery and NETCONF+YANG value fetch workflows.
2. Store discovered data in inventory tables.
3. Expose discovery job status and inventory APIs.
4. Add retry, timeout, and partial-failure handling.
5. Connect inventory UI to real API responses.

## Deliverables
1. Discovery service with job lifecycle states.
2. Inventory persistence model.
3. API endpoints for inventory and discovery status.

## Phase 3 Bootstrap (Current Implementation)
1. Inventory is persisted in backend/data/inventory_store.json.
2. Discovery-first snapshot endpoint is available at POST /api/inventory/netconf-yang-snapshot.
3. Real-time stream endpoint is available at WebSocket /api/ws/inventory/netconf-yang.
4. Legacy metadata and mock discovery endpoints are disabled (HTTP 410) in strict real-time mode.

## Exit Criteria
1. Discovery returns real and repeatable device data.
2. Inventory window is powered by backend.
3. Error handling is visible and operator-friendly.
