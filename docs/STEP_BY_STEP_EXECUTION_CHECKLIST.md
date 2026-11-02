# Step-by-Step Execution Checklist

Date: 2026-10-16

Use this checklist while developing to avoid confusion.

## Sprint 1 (Start Here)
1. Complete Phase 0 decisions and sign-off.
2. Build dashboard layout and navigation.
3. Add required windows as placeholders.
4. Add 3D panel placeholder and controls shell.
5. Review responsive behavior and empty states.

## Sprint 1 Completion Note (Current Scope)
1. Completed with scoped focus to avoid confusion.
2. Active windows are currently limited to Dashboard and Inventory.
3. Inventory flow is validated for subnet 66.162.110.0/24 host range 1-5.
4. Validation, delete confirmations, source labeling, and empty-state handling are in place.
5. Deferred windows (Incidents, Performance, Topology, Compliance, Reports) move to future phases.

## Sprint 2
1. Finalize required fields for each module.
2. Publish contract examples.
3. Map fields to tables/cards.
4. Remove extra placeholder-only noise.
5. Verify no unapproved fields are present.

## Sprint 3
1. Implement discovery and inventory backend.
2. Connect inventory and dashboard counters.
3. Add status/retry/error handling.
4. Verify discovery job lifecycle.

## Sprint 4
1. Implement monitoring and event normalization.
2. Connect event queue and alert visuals.
3. Add acknowledgement workflow.
4. Validate live update behavior.

## Sprint 5
1. Integrate real graph data.
2. Complete 2D topology interactions.
3. Implement 3D scene interactions.
4. Add path and impact analysis interactions.

## Sprint 6+
1. Add assurance and runbook workflows.
2. Add reporting/export and schedules.
3. Add RBAC, audit, performance hardening.
4. Execute release checklist.

## Gate Before Moving to Next Sprint
1. Current sprint exit criteria met.
2. Docs updated with final decisions.
3. Regressions checked on dashboard and topology pages.
