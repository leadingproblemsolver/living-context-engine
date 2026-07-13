# System Architecture

**Status:** observed  
**Confidence:** 95/100  
**Evidence:** source tree, `schema.sql`, Edge Functions, release scripts

## Experience plane

- React/TanStack single-page workspace
- localStorage fallback for unsigned/local preview
- Supabase magic-link authentication
- authenticated integration contract in `docs/API.md`

## Control plane

- user-owned guardrail definitions
- criticality, enforcement, scope, and metric type
- deterministic `Block > Watch > Pass` precedence
- body limits, exact-origin CORS, quotas, and timeouts
- human acceptance of every inferred rule

## Orchestration plane

- synchronous three-stage state flow: intent → constraints → judgment
- no background agent loop
- no passive monitoring claim
- external workflows invoke the evaluation checkpoint explicitly

## Execution plane

- deterministic binary, threshold, and checklist evaluation
- OpenAI-compatible semantic interpretation for evidence rules
- exact finding normalization
- Supabase RPC for transactional workspace save

## Data and state plane

- `profiles`
- `guardrail_sets`
- `guardrails`
- immutable `evaluations`
- sanitized `operational_events`
- internal `ai_request_usage`
- RLS owner isolation on every user-visible table

## Operational intelligence plane

- request/model latency
- model identity and token usage when provided
- rule updates
- verified evaluation outcome, verdict, score, and finding counts
- no raw work or evidence duplicated into operational events

## Packaging and distribution plane

- operator-first landing/workspace
- developer deployment and API documentation
- no buyer dashboard, team workspace, or distribution automation before pilot evidence

## Trust boundaries

1. Browser receives only Supabase URL and publishable key.
2. AI and Supabase secret keys remain in Edge Function secrets.
3. Browser may edit owned guardrails but cannot author evaluation audits or operational events.
4. Edge Functions verify authenticated users and use a server secret only for immutable writes.
5. The model receives bounded context and cannot control final verdict precedence.

## Critical synchronous path

```text
user/integration
→ authenticated Edge request
→ normalize and validate
→ deterministic objective checks
→ optional bounded semantic model call
→ deterministic verdict
→ immutable evaluation write
→ sanitized event write
→ result response
```

## Failure boundaries

- Invalid input returns a recoverable 4xx response.
- Provider timeout/rate limit returns a bounded 5xx/503 response.
- Audit persistence failure prevents a successful cloud verdict response.
- Telemetry persistence failure is logged but does not invalidate a stored evaluation.
- Local preview never claims semantic AI verification.
