https://github.com/ManjunathaMudhuval/Lumen_NMS_Updated

# Master Development Plan - Real NMS

Date: 2026-10-16
Project Root: /home/ad39013/NMS_APP

## 1. Objective
Build a production-grade Network Management System with:
- Real discovery and inventory
- Real-time monitoring and event correlation
- Topology visualization including 3D view
- Device/config/performance assurance workflows
- Reporting and operator-focused UX

This plan is intentionally phase-based and step-by-step to avoid confusion while building.

## 2. Product Modules (Target)
1. NOC Dashboard
2. Inventory and Asset Management
3. Discovery and Topology Mapping (2D + 3D)
4. Fault/Event Management
5. Performance Monitoring
6. Configuration/Compliance and Drift
7. Automation/Runbooks
8. Reports and Exports
9. User/RBAC/Audit

## 3. Core Rule for Early Development
Until Phase 2 is completed:
- Only create required placeholders.
- Do not add unnecessary fields.
- Keep schemas minimal and explicit.

## 4. Phase Summary

| Phase | Name | Primary Outcome |
|---|---|---|
| 0 | Foundation | Project skeleton, architecture, standards |
| 1 | Dashboard + Placeholder Windows | UI shell with required views and empty-safe components |
| 2 | Data Contracts + Required Fields | Finalized field model and UX completion |
| 3 | Discovery + Inventory Backend | Device discovery, inventory persistence, APIs |
| 4 | Monitoring + Event Pipeline | Telemetry ingest, alerts, event normalization |
| 5 | Topology Intelligence + 3D | Dependency graph, 3D rendering, interaction |
| 6 | Assurance + Automation + Reports | Compliance checks, runbooks, exports |
| 7 | Security + Hardening + Release | RBAC, audit, testing, production release |

## 5. Step-by-Step Execution

## Phase 0 - Foundation
Reference: docs/phases/PHASE_0_FOUNDATION.md

Steps:
1. Define architecture (frontend, backend, storage, messaging).
2. Freeze coding conventions and naming standards.
3. Define module boundaries and API style.
4. Set initial project structure and documentation folders.

Exit criteria:
1. Architecture is documented and approved.
2. Folder layout is final.
3. Team can start UI work without blockers.

## Phase 1 - Dashboard and Placeholders First
Reference: docs/phases/PHASE_1_DASHBOARD_AND_PLACEHOLDERS.md

Steps:
1. Build dashboard shell layout.
2. Add required windows as placeholders only.
3. Add placeholder cards/tables with empty-safe states.
4. Add navigation and filter shell.
5. Add basic 3D canvas window placeholder.

Exit criteria:
1. All required windows are visible and switchable.
2. No real backend dependency required to render.
3. Empty states include clear "next action" guidance.

## Phase 2 - Required Fields and Window Completion
Reference: docs/phases/PHASE_2_REQUIRED_FIELDS_AND_WINDOWS.md

Steps:
1. Finalize required field list per module.
2. Define strict JSON contracts and UI mapping.
3. Implement real form/table columns only for required fields.
4. Add validation rules and fallback rules.
5. Add versioned contract doc.

Exit criteria:
1. Each window has approved fields only.
2. No undefined field usage in UI.
3. Contracts are backend-ready and testable.

## Phase 3 - Discovery and Inventory Backend
Reference: docs/phases/PHASE_3_DISCOVERY_AND_INVENTORY.md

Steps:
1. Build discovery jobs (ICMP/SNMP/SSH where applicable).
2. Persist discovered devices/interfaces in DB.
3. Expose APIs for inventory and discovery status.
4. Add scheduler/retry/error handling.
5. Connect dashboard counters with real inventory data.

Exit criteria:
1. Discovery returns real devices.
2. Inventory APIs power UI lists.
3. Failures are visible with actionable messages.

## Phase 4 - Monitoring and Event Pipeline
Reference: docs/phases/PHASE_4_MONITORING_AND_EVENTS.md

Steps:
1. Ingest telemetry and event sources.
2. Normalize events to one common model.
3. Build thresholds and alert state model.
4. Stream updates to UI (poll or websocket).
5. Add event timeline and acknowledgement flow.

Exit criteria:
1. Real-time status updates appear in dashboard.
2. Alerts and severities are consistent.
3. Event-to-device relationship is traceable.

## Phase 5 - Topology Intelligence and 3D
Reference: docs/phases/PHASE_5_TOPOLOGY_AND_3D.md

Steps:
1. Build graph model (nodes, links, groups, metadata).
2. Implement 2D topology interactions first.
3. Implement 3D scene with camera controls.
4. Add filtering, highlighting, and path tracing.
5. Link node selection to inventory/event detail panels.

Exit criteria:
1. 3D topology loads from real graph data.
2. Operators can inspect dependencies visually.
3. Performance meets acceptable interaction latency.

## Phase 6 - Assurance, Automation, Reporting
Reference: docs/phases/PHASE_6_ASSURANCE_AUTOMATION_REPORTING.md

Steps:
1. Add config compliance and drift views.
2. Add runbook hooks and operator actions.
3. Add test/readiness scoring widgets.
4. Add report center (CSV/JSON/PDF workflows).
5. Add scheduled report generation.

Exit criteria:
1. Compliance/drift is measurable per device/site.
2. Reports are exportable and reproducible.
3. Key operations are automatable with approvals.

## Phase 7 - Security, Hardening, Release
Reference: docs/phases/PHASE_7_SECURITY_HARDENING_RELEASE.md

Steps:
1. Implement authentication and RBAC.
2. Add audit trail for critical actions.
3. Perform performance/load testing.
4. Perform accessibility and usability checks.
5. Prepare release checklist and production runbooks.

Exit criteria:
1. Security controls are enforced.
2. No critical bugs for release workflows.
3. Operational docs are complete.

## 6. Required Placeholder-First Windows (Phase 1 Scope)
Build these first as UI placeholders:
1. Executive/NOC dashboard
2. Device inventory list
3. Device detail drawer/panel
4. Incident/event queue
5. Performance metrics panel
6. Topology 2D panel
7. Topology 3D panel
8. Configuration compliance panel
9. Reports center shell

## 7. Suggested Data Domain (Minimal Required Fields)
Use these as initial required fields in Phase 2:
1. Device: id, hostname, mgmt_ip, vendor, model, site, role, status, last_seen
2. Interface: id, device_id, name, admin_state, oper_state, speed, utilization
3. Event: id, ts, severity, source, message, device_id, acknowledged
4. Link: id, src_device_id, src_if, dst_device_id, dst_if, status
5. Metric: device_id, metric_name, value, unit, ts

## 8. Definition of Done (per phase)
1. Documentation updated for the phase.
2. Demo path exists for new capabilities.
3. Basic tests pass for changed module.
4. No blocker diagnostics in changed files.
5. Handover notes written for next phase.

## 9. Delivery Rhythm (Practical)
1. Work in short sprints (3 to 5 days per phase segment).
2. Create a phase checklist and close items one by one.
3. Do not start next phase until exit criteria are met.

## 10. Immediate Next Action
Start Phase 1 implementation now:
1. Create frontend shell.
2. Build placeholder windows listed in section 6.
3. Add minimal 3D panel scaffold.
4. Keep all data mocked/static until Phase 2 contracts are signed.

## 11. Reference Reuse Input (Pre-Implementation)
Before feature coding, use the reuse analysis from the legacy AI implementation project:
1. docs/REFERENCE_REUSE_ANALYSIS_AI_IMPLEMENTATION_NETWORK_MONITERING.md
2. Apply adopt/adapt/avoid guidance to reduce technical debt.
