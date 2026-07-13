# DriftGuard Sociotechnical Gap-Closure Report

**Assessment date:** 2026-07-09  
**Immediate target:** credible external pilot  
**Current stage:** code-validated internal demo / staging candidate  
**Assessment basis:** repository source, successful clean install, full local validation, Cloudflare Worker smoke test, static schema/function/UI inspection, and explicitly labeled simulations.

## Executive verdict

DriftGuard is **substantially code-complete but not operationally pilot-ready**. The local release pipeline is credible: `npm ci`, `npm run validate`, and `npm run smoke:worker` passed. The remaining blockers are not general feature requests; they are truth, policy-state integrity, privacy governance, live isolation proof, semantic-quality evidence, and real-world outcome capture.

- **Code/build readiness:** 90%
- **Operational pilot readiness:** 47%
- **Production readiness:** 30%
- **Ready for:** internal demo, staging deployment, supervised non-sensitive design-partner sessions after P0 claim corrections
- **Not ready for:** unsupervised external pilot, sensitive data, production enforcement integrations, team deployment, or verified outcome/ROI claims

The repository's `pilot_ready: true` value is therefore a **P0 truth gap**, not a minor documentation issue.

## What is genuinely strong

- The three-step user path is clear and the value proposition is understandable.
- Objective binary, threshold, and checklist rules are deterministic.
- A violated blocking rule cannot be softened by the model.
- Missing semantic proof cannot produce a local semantic Pass.
- Secrets are separated from the browser; CORS, request size, timeout, and quota boundaries exist.
- RLS policies, immutable browser audit permissions, exact policy snapshots, and clean build/deploy tooling are present in source.
- The release pipeline validates types, lint, formatting, Edge parsing/bundling, schema synchronization, and the generated Cloudflare Worker.

These strengths make DriftGuard a good **pilot candidate**. They do not by themselves prove pilot safety or user value.

## Target operating standards

### Minimum usable

- One individual operator; manual plain-language or structured check.
- Non-sensitive data only unless explicit processing consent exists.
- User-approved guardrails; deterministic precedence; visibly labeled local versus cloud mode.
- Rules result in under 1 second locally; semantic result target under 30 seconds.
- Human remains responsible for the external action.
- Usefulness proof: user can complete define → approve → check without reconstructing context, and the output changes or confirms a real decision.

### Pilot-ready

- 5–10 external operators in one narrow use case.
- Two-user isolation and hosted authentication verified.
- Canonical server policy cannot be changed by evaluation payloads.
- Explicit AI/data-use consent, retention, deletion, and shared-device behavior.
- Semantic benchmark with zero critical false Passes in the pilot corpus.
- Persistent history, outcome/correction capture, support owner, failure telemetry, and visible limitations.
- Pilot success criteria: at least three evidenced useful interventions, acceptable false-block rate, repeat use, and measured time to first value.

### Operationally robust

- Idempotent evaluation API, optimistic policy concurrency, atomic audit persistence, retries, stable failure contracts, and model rollback.
- Reliable event completeness, failure alerts, incident runbooks, outcome evidence, rule/prompt/model versioning, and tested recovery.
- Documented privacy/security ownership and a verified backup/restore path.

### Scale-ready

- Organization tenancy, RBAC, delegated policy ownership, queues/concurrency controls, cost budgets, SLOs, migrations, incident rotation, and support ownership.
- Build only after pilot thresholds show repeated value and volume.

## Current-state maturity map

| Readiness dimension                   | Score / 5 | Status   | Confidence | Evidence summary                                                                            |
| ------------------------------------- | --------: | -------- | ---------: | ------------------------------------------------------------------------------------------- |
| Outcome readiness                     |         3 | observed |        90% | Core verdict/correction implemented; no real outcome capture or semantic benchmark.         |
| User-workflow readiness               |         3 | observed |        92% | Clear three-step path; local/cloud conflict, no history, no feedback loop.                  |
| Data readiness                        |         2 | observed |        95% | Structured schema/RLS; mutable client policy, no retention/export/versioning.               |
| Model and reasoning readiness         |         2 | observed |        95% | Bounded prompts/output normalization; no labeled eval set, retry, rollout gate.             |
| Deterministic-control readiness       |         4 | observed |        96% | Block precedence and objective rules are enforced and locally tested.                       |
| Orchestration readiness               |         2 | observed |        95% | Synchronous path works; no idempotency, partial-write boundary, concurrency control.        |
| Integration readiness                 |         2 | observed |        93% | Authenticated endpoint/docs exist; no durable webhook principal or retry contract.          |
| Human-operations readiness            |         1 | observed |        98% | No support owner, incident runbook, escalation SLA, or exception workflow.                  |
| Trust and explainability readiness    |         3 | observed |        93% | Verdict trace/mode visible; local snapshot and outcome semantics overclaim.                 |
| Security/privacy/compliance readiness |         2 | observed |        94% | Secret boundaries/RLS design strong; no live isolation proof, consent, retention, deletion. |
| Failure/recovery readiness            |         2 | observed |        94% | Errors and local fallback exist; degraded mode is transient and state conflicts unresolved. |
| Observability readiness               |         2 | observed |        97% | Sanitized events exist; failures/alerts/completeness/outcomes absent.                       |
| Evaluation readiness                  |         2 | observed |       100% | Five deterministic unit tests; no Edge/RLS/semantic/E2E/adversarial suite.                  |
| Economic readiness                    |         1 | observed |        98% | Metrics are designed but costs, support minutes, and value outcomes are not measured.       |
| Adoption/distribution readiness       |         2 | inferred |        85% | Value proposition is clear; no observed activation, repeat use, buyer proof, or support.    |
| Presentation readiness                |         4 | observed |        93% | Polished, coherent UI; several claims need mode/stage qualification.                        |

**Unweighted maturity:** 46% across the compiler's sixteen dimensions. The gap between this and 90% code/build readiness is the exact distinction between software completion and operating readiness.

## Priority map

### P0 — Truth, safety, privacy, or state-integrity blockers

- **DG-G001 — Readiness documentation overstates pilot readiness**: docs/product/READINESS.yaml marks pilot_ready and deployment_ready true although hosted auth, RLS isolation, semantic quality, support, feedback, and real outcome evidence remain unverified. Closure: Change readiness to internal-demo/staging-ready; define executable gates for pilot and production.
- **DG-G004 — Evaluation completion is mislabeled as real-world outcome verification**: Every successful judgment emits OUTCOME_VERIFIED even though DriftGuard has not observed whether the user followed the correction or achieved the desired result. Closure: Rename current event and add explicit outcome-confirmation schema/endpoint.
- **DG-G008 — Snapshot-retention claims are universal but local previews are not persisted**: The landing page says every verdict retains an exact snapshot, while unsigned local preview results exist only in component memory and are lost on refresh. Closure: Add persistent mode-specific copy and a visible capability matrix; optionally retain local previews in account-scoped IndexedDB.
- **DG-G005 — AI processing, storage, and retention consent boundary is missing**: Submitted work and evidence are sent to the configured AI provider and stored in evaluations, but the product has no explicit pre-call disclosure, data classification, retention choice, or deletion control. Closure: Add data-use consent, sensitivity classification, retention policy, delete/export controls, and a local-only mode boundary.
- **DG-G002 — Evaluation can overwrite the canonical guardrail policy**: The evaluate function accepts a complete client-supplied workspace and calls save_guardrail_set before judgment. A stale, tampered, or integration-supplied payload can replace newer user-approved rules. Closure: Make evaluate accept set_id, input, expected_policy_version, and idempotency_key; load rules from DB; reject stale versions with 409.
- **DG-G006 — Tenant isolation and hosted authentication remain unverified**: RLS policies and auth checks are present, but there is no automated two-user database test or successful hosted authentication/function evidence. Closure: Add pgTAP/client integration tests for all RLS policies and complete a two-account staging test.
- **DG-G007 — Local/cloud synchronization can overwrite unsaved user state**: On sign-in, the latest cloud set automatically replaces the local workspace and is immediately written back to localStorage. Sign-out intentionally leaves that workspace visible in the browser. Closure: Namespace local data by user, preserve anonymous draft separately, detect divergence, and require choose/merge before overwrite.
- **DG-G003 — Policy refresh and evaluation audit are not atomic**: The function commits save_guardrail_set, then separately calls the model and inserts the evaluation. Failure after the save can leave a changed policy with no matching audit, while API docs call the operation transactional. Closure: Separate policy save from evaluation; add atomic record_evaluation RPC for evaluation, findings, events, idempotency, and policy-version check.

### P1 — Core outcome and external-pilot blockers

- **DG-G010 — No actual outcome, correction acceptance, or override capture**: The system returns a correction but cannot record whether the user accepted it, changed the action, overrode the verdict, or achieved the desired result. Closure: Add evaluation_outcomes table and a minimal 'What happened?' confirmation after the workflow boundary.
- **DG-G009 — Semantic judgment quality has no realistic evaluation set**: Five tests cover only the local deterministic engine. There are no labeled semantic cases, prompt-injection cases, missing-finding cases, model-version regressions, or false-pass measurements. Closure: Create 50+ labeled cases including adversarial and ambiguous inputs; define zero critical false-Pass tolerance for pilot.
- **DG-G011 — Hosted end-to-end path is not verified**: Local install, build, Edge bundle, and Worker smoke pass; schema push, functions, SMTP magic link, provider call, and production origins have not been exercised together. Closure: Deploy staging, configure SMTP/provider/origins, execute scripted smoke, save evidence.
- **DG-G012 — API/webhook mode lacks a durable integration and idempotency contract**: The endpoint requires an expiring user access token, accepts an entire mutable workspace, and has no idempotency key or stable external event ID. The UI exposes API/webhook as an input mode. Closure: For pilot, support only browser/manual and one documented internal relay; defer generic webhooks or add scoped integration credentials and idempotency.

### P2 — Repeated-use reliability and operability gaps

- **DG-G013 — No user-visible evaluation history, audit replay, or comparison**: Evaluations are queryable by the user in the database, but the UI never loads them. The user cannot revisit a verdict, compare policy snapshots, or prove what changed. Closure: Add recent evaluations and a single evaluation detail/replay surface after outcome capture schema is stable.
- **DG-G018 — Human support, exception ownership, and incident response are unassigned**: The repo has deployment and technical docs but no named pilot support channel, response time, exception owner, model-quality reviewer, or incident runbook. Closure: Create pilot runbook, support channel, severity rules, response targets, and owner matrix.
- **DG-G015 — Operational telemetry omits failures and can silently disappear**: Operational event insertion is best-effort and only logs success-heavy events. Function exceptions return errors without FAILURE_DETECTED events, alerts, or health aggregation. Closure: Emit sanitized FAILURE_DETECTED events in catch paths, add event-delivery health metric, and define one pilot alert route.
- **DG-G017 — Cloud data deletion, export, and retention controls are absent**: Raw inputs, evidence, findings, and snapshots persist with no user-facing export/delete path, account deletion workflow, or retention job. Closure: Define pilot retention, add export and account/workspace deletion workflow, and test cascades.
- **DG-G016 — Rule versioning and concurrent-edit protection are not implemented**: Guardrails have a version column, but saves delete and recreate the list with default version 1. Guardrail sets lack a policy version/ETag and updates are last-write-wins. Closure: Add guardrail_sets.policy_version and update RPC requiring expected version; append policy_change event.
- **DG-G014 — Degraded-mode fallback is too easy to miss**: If AI/cloud evaluation fails, the browser silently substitutes local preview and shows only a short flash plus a small footer mode label. Closure: Keep result mode visible at verdict level, require acknowledgment for degraded Block/Watch, and add retry.
- **DG-G019 — Model provider retry, fallback, and rollout policy is missing**: The AI adapter makes one synchronous provider call. There is no retry for transient errors, secondary model, canary, rollback, or model/prompt evaluation gate. Closure: Add one bounded retry for 429/5xx, record prompt/model version, and require benchmark pass before model change; defer multi-provider fallback until pilot need.

### P3 — Adoption, measurement, and product-coherence gaps

- **DG-G022 — Economic and adoption metrics are designed but not operational**: Metrics YAML defines time to value, repeat use, useful intervention, and provider failure, but required client events/outcome events/cost calculations are absent. Closure: After event truth correction and outcome capture, implement a pilot report query—not a dashboard.
- **DG-G020 — Input modes and cadence are mostly labels, not configured workflows**: Prompt, checklist, metric, API, and cadence values are stored, but the in-app flow is largely the same and no scheduler/adapter is created from these settings. Closure: For pilot, retain manual + structured modes and label integration values as templates; add adapters only after a validated channel.
- **DG-G023 — Setup-time and value claims are unvalidated**: The hero claims setup in under 60 seconds and strong workflow relief without observed user timing or comparison with current workaround. Closure: Qualify as target until measured; instrument first-use timing and run 5-10 observed sessions.
- **DG-G021 — Only the latest workspace is accessible**: The database can hold multiple sets, but sign-in loads only the most recently updated set and the UI has no list, switch, duplicate, archive, or delete surface. Closure: Defer until pilot shows multi-workflow demand; then add list/switch/archive, not a dashboard.

### P4 — Scale-only gaps

- **DG-G025 — Scale SLOs, queueing, backup/restore, and disaster recovery are unverified**: Per-user quotas and indexes exist, but there are no load tests, queue, concurrency limits, backup restore drill, SLOs, or incident rotation. Closure: Defer until pilot thresholds; first define measured triggers and perform a database restore drill before production.
- **DG-G024 — Organization tenancy, roles, and policy delegation are absent**: All data is user-owned; there is no organization, team, role, delegated administrator, shared policy, or separation of operator and policy owner. Closure: Do not build before two pilot organizations request shared policy/roles.

## Complete scored gap registry

The full machine-readable records—including severity, probability, detectability, dependency depth, closure leverage, ownership, acceptance tests, and evidence references—are in `GAP_REGISTRY.yaml`.

| Gap                                                                                  | P   | Risk | Leverage | Execution priority | Owner                     |
| ------------------------------------------------------------------------------------ | --- | ---: | -------: | -----------------: | ------------------------- |
| DG-G001 Readiness documentation overstates pilot readiness                           | P0  |  100 |     62.5 |              115.0 | product/engineering       |
| DG-G004 Evaluation completion is mislabeled as real-world outcome verification       | P0  |  100 |     41.7 |              100.4 | backend/product analytics |
| DG-G010 No actual outcome, correction acceptance, or override capture                | P1  |  125 |     20.8 |               95.8 | product+backend+frontend  |
| DG-G008 Snapshot-retention claims are universal but local previews are not persisted | P0  |   80 |     37.5 |               89.5 | product/frontend          |
| DG-G009 Semantic judgment quality has no realistic evaluation set                    | P1  |   80 |     20.8 |               77.8 | product+ML evaluation     |
| DG-G005 AI processing, storage, and retention consent boundary is missing            | P0  |   80 |     20.0 |               77.2 | product+security+backend  |
| DG-G002 Evaluation can overwrite the canonical guardrail policy                      | P0  |   80 |     15.0 |               73.8 | backend                   |
| DG-G006 Tenant isolation and hosted authentication remain unverified                 | P0  |   60 |     25.0 |               72.8 | backend/security          |
| DG-G011 Hosted end-to-end path is not verified                                       | P1  |   60 |     25.0 |               72.8 | devops/backend            |
| DG-G013 No user-visible evaluation history, audit replay, or comparison              | P2  |  100 |      9.6 |               71.7 | frontend+backend          |
| DG-G007 Local/cloud synchronization can overwrite unsaved user state                 | P0  |   60 |     12.0 |               63.6 | frontend                  |
| DG-G018 Human support, exception ownership, and incident response are unassigned     | P2  |   80 |      6.0 |               61.2 | founder/operations        |
| DG-G015 Operational telemetry omits failures and can silently disappear              | P2  |   64 |      9.6 |               57.3 | backend/operations        |
| DG-G003 Policy refresh and evaluation audit are not atomic                           | P0  |   45 |     10.0 |               56.2 | backend/database          |
| DG-G022 Economic and adoption metrics are designed but not operational               | P3  |   75 |      9.6 |               55.5 | product analytics         |
| DG-G017 Cloud data deletion, export, and retention controls are absent               | P2  |   64 |      6.0 |               54.8 | product+backend           |
| DG-G016 Rule versioning and concurrent-edit protection are not implemented           | P2  |   48 |      9.6 |               50.9 | backend/frontend          |
| DG-G012 API/webhook mode lacks a durable integration and idempotency contract        | P1  |   48 |      9.1 |               50.6 | backend/integrations      |
| DG-G014 Degraded-mode fallback is too easy to miss                                   | P2  |   48 |      9.0 |               50.5 | frontend                  |
| DG-G019 Model provider retry, fallback, and rollout policy is missing                | P2  |   48 |      4.5 |               41.1 | backend/ML operations     |
| DG-G020 Input modes and cadence are mostly labels, not configured workflows          | P3  |   45 |      6.0 |               41.0 | product/frontend          |
| DG-G023 Setup-time and value claims are unvalidated                                  | P3  |   36 |     10.0 |               40.1 | product/research          |
| DG-G021 Only the latest workspace is accessible                                      | P3  |   48 |      3.6 |               34.2 | frontend/backend          |
| DG-G025 Scale SLOs, queueing, backup/restore, and disaster recovery are unverified   | P4  |   24 |      0.6 |               22.5 | operations/architecture   |
| DG-G024 Organization tenancy, roles, and policy delegation are absent                | P4  |    9 |      0.6 |               16.5 | product/architecture      |

## Dependency graph

```text
Correct readiness / persistence / outcome claims (G001, G004, G008)
  ├─> clean pilot metrics and buyer proof (G022, G023)
  └─> truthful onboarding and support

Canonical server policy + versioning (G002, G016)
  └─> atomic/idempotent evaluation (G003)
       ├─> safe API/webhook integration (G012)
       ├─> reliable history/replay (G013)
       └─> outcome/correction linkage (G010)

Privacy consent + retention (G005, G017)
  └─> external pilot eligibility

Live RLS/auth proof (G006) + local/cloud conflict safety (G007)
  └─> hosted end-to-end pilot path (G011)

Semantic benchmark (G009) + model rollout/fallback (G019)
  └─> credible core-result quality

Outcome capture (G010) + truthful events (G004) + failure telemetry (G015)
  └─> useful-intervention evidence and economic measurement (G022)

Pilot evidence
  ├─> multiple-workspace decision (G021)
  ├─> team tenancy/RBAC decision (G024)
  └─> scale/SLO/queue investment (G025)
```

## Critical preflight questions and safe defaults

| Question                                                             | Why it changes execution                                       | Default assumption                                    | Risk of default                                          |
| -------------------------------------------------------------------- | -------------------------------------------------------------- | ----------------------------------------------------- | -------------------------------------------------------- |
| Is the immediate target an external pilot or production?             | Changes required proof, support, and risk gates.               | External pilot.                                       | Production controls could otherwise be underbuilt.       |
| What data may be sent to the LLM and stored?                         | Changes consent, provider, retention, and local-only behavior. | Non-sensitive business text only.                     | Users may submit unauthorized confidential data.         |
| Is Block advisory or must an integration technically stop execution? | Changes API semantics and ownership.                           | Advisory verdict; external workflow owns enforcement. | Users may assume DriftGuard itself prevented the action. |
| Which integration caller is supported in the pilot?                  | Changes authentication and idempotency design.                 | Browser/manual plus one controlled internal relay.    | Generic webhook claims remain unsupported.               |
| What is the acceptable critical false-Pass rate?                     | Changes semantic evaluation and pilot safety.                  | Zero critical false Passes in the labeled pilot set.  | A weaker default undermines the core promise.            |

## Sociotechnical responsibility matrix

| Stage              | User                                        | AI                          | Deterministic system                             | External tool                | Decision owner         | Failure/support owner | Verification owner         |
| ------------------ | ------------------------------------------- | --------------------------- | ------------------------------------------------ | ---------------------------- | ---------------------- | --------------------- | -------------------------- |
| Define intent      | States purpose, target, success, exclusions | May propose guardrails      | Validates schema/limits                          | None                         | User                   | Product support       | User                       |
| Approve policy     | Reviews/edits/accepts                       | No authority to accept      | Persists canonical version and conflict checks   | Supabase DB                  | User                   | Engineering           | System + user              |
| Submit check       | Provides work/evidence or integration event | Interprets semantic rules   | Evaluates objective rules and verdict precedence | Supabase Edge/AI provider    | User/integration owner | Operations            | System                     |
| Act on verdict     | Proceeds, corrects, or overrides            | Recommends correction only  | Must not execute external action by default      | User workflow/integration    | Human user             | Workflow owner        | Human user                 |
| Confirm outcome    | Records what happened and evidence          | May summarize               | Links outcome to evaluation                      | Optional source system       | Human user/lead        | Pilot operator        | Human or external evidence |
| Recover failure    | Retries or contacts support                 | None                        | Preserves input, identifies mode/error           | Provider/Supabase/Cloudflare | Operations             | Named support owner   | Operations                 |
| Change model/rules | Approves policy or release                  | Produces candidate behavior | Runs regression gates and versions change        | CI/provider                  | Product owner          | Engineering           | Evaluation reviewer        |

## Functionality–presentability matrix

| Capability                                  | Functional state                                 | Presentation                     | Claim allowed now                |
| ------------------------------------------- | ------------------------------------------------ | -------------------------------- | -------------------------------- |
| Local manual rules preview                  | working                                          | polished                         | Yes, explicitly as local preview |
| Cloud semantic evaluation                   | working in code; hosted unverified               | polished                         | Qualified only                   |
| Deterministic Block precedence              | verified locally                                 | understandable                   | Yes                              |
| Exact evaluation snapshot                   | working for successful cloud evaluations only    | polished                         | Qualified by mode                |
| Private per-user cloud data                 | implemented in schema; live isolation unverified | polished                         | Qualified pending two-user test  |
| API/webhook checks                          | partial authenticated endpoint                   | understandable                   | Only for browser/internal relay  |
| Before-action/after-output/daily monitoring | metadata/integration contract only               | polished                         | No automation claim              |
| Real outcome verification                   | nonexistent                                      | implicitly claimed by event name | No                               |
| Evaluation history                          | stored but hidden                                | hidden                           | No user-facing history claim     |
| Operational intelligence                    | partial success telemetry                        | hidden                           | Qualified                        |
| Team/company governance                     | nonexistent                                      | not presented                    | No                               |

## Ordered closure plan

### Phase 0 — Truth and boundary correction

**Gaps:** DG-G001, DG-G004, DG-G008, DG-G005
**Exit criterion:** Claims, events, and data handling no longer imply unearned capability.

### Phase 1 — Canonical core path

**Gaps:** DG-G002, DG-G003, DG-G016
**Exit criterion:** Evaluation cannot mutate policy; persistence is versioned, atomic, and testable.

### Phase 2 — Security and quality proof

**Gaps:** DG-G006, DG-G007, DG-G009, DG-G011
**Exit criterion:** Staging path, isolation, sync, and semantic quality are evidenced.

### Phase 3 — Pilot reliability

**Gaps:** DG-G010, DG-G012, DG-G014, DG-G015, DG-G017, DG-G018, DG-G019, DG-G013
**Exit criterion:** Users can recover, inspect history, confirm outcomes, and obtain support.

### Phase 4 — Evidence generation

**Gaps:** DG-G022, DG-G023
**Exit criterion:** Run 5–10 real operators and calculate useful intervention, false-pass/block, repeat-use, latency, cost, and support.

### Phase 5 — Validated workflow expansion

**Gaps:** DG-G020, DG-G021
**Exit criterion:** Only implement modes/workspace management justified by observed repeat use.

### Phase 6 — Scale

**Gaps:** DG-G024, DG-G025
**Exit criterion:** Only after thresholds and organizational demand.

### Phase 7 — Presentation refinement

**Exit criterion:** Polish only verified capabilities and publish evidence-backed claims.

## Immediate execution board

1. Correct `pilot_ready`, snapshot, and `OUTCOME_VERIFIED` claims.
2. Stop evaluation from accepting/persisting client-owned policy; load by `set_id + policy_version`.
3. Add atomic/idempotent evaluation persistence.
4. Add explicit AI data-use/retention consent and local/cloud conflict handling.
5. Add automated two-user RLS tests and deploy staging.
6. Build the semantic benchmark and run it against the pinned model/prompt.
7. Add real outcome/correction/override capture.
8. Add persistent degraded mode, failure events, support ownership, and minimal history.
9. Run the bounded pilot; stop building and collect evidence.

## Residual risks after pilot readiness

- Model interpretation remains probabilistic; critical decisions still require human accountability.
- Browser/manual use does not technically enforce external actions unless the integrating workflow honors Block.
- AI-provider and Supabase availability remain external dependencies.
- Team tenancy, RBAC, billing, queueing, disaster recovery, and enterprise compliance remain deferred.
- A successful pilot in one workflow does not validate every domain or constraint type.

## Stop condition

After P0–P2 acceptance tests pass, stop implementation expansion and run the pilot. The next constraint must become observed user behavior, false-pass/false-block evidence, useful interventions, repeat use, and support burden—not additional architecture.
