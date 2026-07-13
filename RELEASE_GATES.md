# DriftGuard release gates

A release is deployable only when every gate below remains true. `npm run validate` checks the executable subset of this contract.

## 1. Product truth

- The product does one job: prevent consequential work from drifting outside accepted constraints.
- The first screen states the input, judgment, and corrective output without requiring product vocabulary.
- Default setup needs only purpose, workflow, target, and observable proof of success.
- Advanced controls remain optional and collapsed.

## 2. User-owned policy

- AI may propose guardrails, but a user must accept or edit them.
- AI cannot silently add, remove, rename, or weaken an accepted guardrail.
- Every evaluation uses an immutable snapshot of the guardrails supplied for that check.

## 3. Deterministic judgment precedence

- AI interprets semantic evidence only.
- Binary, threshold, and checklist rules are evaluated by deterministic code.
- A violated rule with `enforcement = block` always forces `Block`.
- Any violated or unclear active rule prevents `Pass`.
- Only a complete set of `met` findings may return `Pass`.

## 4. Evidence integrity

- Missing evidence is `unclear`; it is never treated as compliance.
- Thresholds are used only when a number and operator are explicitly configured.
- Checklists require an answer for every accepted item.
- The system returns the smallest correction for the highest-priority unresolved rule.

## 5. Audit integrity

- The browser cannot insert, update, or delete evaluation records.
- The authenticated Edge Function computes and writes the result.
- Every record stores verdict, score, findings, evaluation mode, model identity, and the exact constraint snapshot.
- Local fallback results are visibly marked `rules-preview` and are not represented as cloud-audited AI judgments.

## 6. Identity and isolation

- All application tables have Row Level Security enabled.
- Authenticated users can access only their own sets, rules, profiles, and evaluation history.
- Evaluation writes require the server-only Supabase secret key; browser roles receive read-only history access.
- Edge Functions verify the caller's Supabase access token inside the handler.

## 7. Secret boundary

- The browser receives only `VITE_SUPABASE_URL` and a publishable/anon key.
- `AI_API_KEY` exists only in Supabase Edge Function secrets.
- Populated `.env` files are ignored and absent from the release archive.
- Both current Supabase key maps and legacy keys are supported during the 2026 migration period.

## 8. LLM reliability boundary

- Model output is parsed and schema-sanitized before use.
- Unknown statuses and missing findings become `unclear`.
- User content is explicitly treated as untrusted data in both prompts.
- Calls have hard timeouts, output limits, request-size limits, and per-user quotas.
- The model snapshot is pinned; changing it requires rerunning the judgment tests.

## 9. Edge Function integrity

- Only the literal folders `evaluate` and `infer-guardrails` are deployable.
- Function folders, browser invocations, `supabase/config.toml`, and deployment commands must match that manifest.
- `_shared` remains non-deployable shared source.
- VS Code enables Deno only inside `supabase/functions`; the frontend remains in the Vite TypeScript project.
- Shared modules and every deployable function have explicit Deno/import-map configuration.
- Pinned Deno lint/check, standalone Edge TypeScript checking, slug parity, and bundling must pass before deployment.

## 10. Operational deployability

- One canonical `schema.sql` owns the entire database contract.
- A generated migration mirrors that file for `supabase db push`.
- Frontend and function environment templates are separate and complete.
- Backend deployment commands are scripted.
- Typecheck, lint, format, tests, release checks, production build, and production dependency audit pass.

## 11. Failure honesty

- Configuration errors name the missing variable.
- Server errors return a stable request ID without leaking provider or database internals.
- Cloud failure never masquerades as a persisted AI result.
- The app remains usable locally, but labels the reduced-integrity mode precisely.

## Productization and operational intelligence

- The canonical user, trigger, painful state, desired result, proof, and non-goals are versioned under `docs/product/`.
- Technical deployment readiness is not represented as live production verification.
- `operational_events` is server-authored; browser roles can read only their own events.
- Operational events contain sanitized summaries and must not duplicate raw work, evidence, secrets, or email addresses.
- Core cloud actions emit `RULE_UPDATED`, `MODEL_CALLED`, `VALIDATION_COMPLETED`, or `OUTCOME_VERIFIED` as applicable.
- Telemetry failure cannot turn a successfully stored evaluation into a failed user result.
- The Supabase all-function deploy command passes no positional names; diagnostic commands pass exactly one literal slug to avoid wrapper ambiguity.
- Team collaboration, dashboards, predictive maintenance, billing, and agent orchestration remain deferred until their documented thresholds are reached.

- The Cloudflare compatibility date is explicitly pinned and must not exceed the runtime supported by the pinned Wrangler/workerd release.

- Sample data performs no random generation, timers, network I/O, or build-time timestamp generation in Cloudflare Worker global scope.
