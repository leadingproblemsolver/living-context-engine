# Architectural Decisions

## ADR-001 — Deterministic verdict authority

The model may interpret semantic evidence but may not decide the final verdict or score. A violated blocking rule always forces Block, and any non-met rule prevents Pass.

## ADR-002 — User ownership of policy

Inferred guardrails are proposals. The user accepts, edits, disables, or deletes them before they become the active policy set.

## ADR-003 — One Supabase control/data boundary

Supabase provides authentication, Postgres, RLS, RPCs, quotas, and Edge Functions. This minimizes integration and maintenance overhead for the current stage.

## ADR-004 — No passive-monitoring claim

Cadence values describe checkpoints. DriftGuard checks external work only when a user or integration submits it.

## ADR-005 — Deploy all Edge Functions without positional names

The canonical all-function deployment is `supabase functions deploy --no-verify-jwt`. Although the pinned CLI supports multiple function names, external deployment wrappers may expose only one slug field or mis-handle variadic arguments. The aggregate command therefore passes none; diagnostic commands pass one literal slug.

## ADR-006 — Sanitized operational intelligence

Operational events retain identifiers, status, latency, model identity, token counts, verdict summaries, and finding counts. Raw work and evidence remain only in the evaluation audit to avoid unnecessary duplication.

## ADR-007 — Stop at pilot readiness

Team workspaces, billing, dashboards, predictive maintenance, and autonomous orchestration are deferred until observed usage crosses explicit thresholds.

## ADR-008 — Pin and smoke-test the Cloudflare runtime contract

Nitro must not inherit the build date as the Worker compatibility date. `nitro.config.ts` pins a date supported by the pinned Wrangler/workerd release, and `npm run smoke:worker` must render the generated Worker without global-scope I/O or random-value errors.
