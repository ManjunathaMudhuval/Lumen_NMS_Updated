# NMS_APP - Real Network Management System (NMS)

Date: 2026-10-16

This repository is planned as a real NMS platform inspired by enterprise products such as NetBrain, Netcool, and NetBox, while keeping implementation practical and modular.

## Development Principle
Build in phases to avoid confusion:
1. Build UI shell and placeholders first.
2. Add validated fields and data contracts next.
3. Connect real backend services after contracts are stable.
4. Add assurance, topology intelligence, and operations modules.

## What to Start First
Start with dashboard and window placeholders only (no full backend logic yet):
1. NOC Dashboard
2. 3D Topology View
3. Inventory View
4. Incidents/Events View
5. Performance View
6. Configuration Compliance View

After placeholders are stable, continue with real data integration in phase order.

## Documentation Map
- Master roadmap: docs/MASTER_DEVELOPMENT_PLAN.md
- Placeholder policy: docs/PLACEHOLDER_STRATEGY.md
- Phase docs: docs/phases/

## Recommended Build Order
1. Phase 0: Foundation and architecture decisions
2. Phase 1: Dashboard + placeholders
3. Phase 2: Field model and UI windows completion
4. Phase 3: Discovery and inventory backend
5. Phase 4: Monitoring/event pipeline
6. Phase 5: 3D topology and dependency mapping
7. Phase 6: Automation, assurance, reporting
8. Phase 7: Security, hardening, release

For detailed tasks and exit criteria, follow docs/MASTER_DEVELOPMENT_PLAN.md.

## Current Working Scope
1. Active views: Dashboard and Inventory.
2. Inventory test scope: subnet 66.162.110.0/24, host range 1-5.
3. Frontend is API-driven with NETCONF+YANG real-time updates.
4. Snapshot API: POST /api/inventory/netconf-yang-snapshot.
5. Push stream API: WebSocket /api/ws/inventory/netconf-yang.

## Run (Phase 2)
The backend now also serves the frontend static files on the same port, so
only ONE port needs to be reachable/forwarded.

```bash
cd /home/ad39013/NMS_APP/backend
/home/ad39013/.asdf/shims/python3 -m pip install -r requirements.txt
bash run_backend.sh start
```

Open:
1. App (frontend + API): http://127.0.0.1:8091
2. Backend health: http://127.0.0.1:8091/api/health

(A separate `python3 -m http.server` for the frontend is no longer required.)
