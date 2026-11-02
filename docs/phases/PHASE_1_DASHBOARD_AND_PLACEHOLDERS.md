# Phase 1 - Dashboard and Placeholders

## Goal
Build operator dashboard and all required module windows using placeholders only.

## Steps
1. Create primary layout: sidebar, top bar, content area.
2. Add required windows:
- Dashboard
- Inventory
- Incidents/Events
- Performance
- Topology 2D
- Topology 3D
- Compliance
- Reports
3. Add placeholder cards/tables/charts in each window.
4. Add empty states with guidance and next actions.
5. Add static filters (site, device type, severity, status).

## 3D Requirement in This Phase
1. Add 3D scene container.
2. Add camera controls placeholder.
3. Add sample node/link rendering placeholder.
4. Mark data path as "real graph data in Phase 5".

## Deliverables
1. Navigable UI shell with all required windows.
2. Placeholder strategy applied consistently.
3. Zero dependency on live backend for rendering.

## Exit Criteria
1. Operators can navigate all windows.
2. Empty states are clear and actionable.
3. UI is responsive for desktop and basic tablet layout.

## Sign-off (Scoped Implementation)
1. Phase 1 is signed off with a deliberate reduced scope to avoid confusion.
2. Active views implemented now: Dashboard and Inventory.
3. Inventory includes add/filter/delete flow, inline validation messages, confirmation prompts, and source labeling.
4. Subnet test scope is locked to 66.162.110.0/24 with host range 1-5.
5. Additional operational views are deferred and will be introduced in future phases.
