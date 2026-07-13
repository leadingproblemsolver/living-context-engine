# DriftGuard release report

**Release date:** 2026-07-09  
**Release:** 1.0.0  
**Target:** Supabase Auth/Postgres/Edge Functions + Cloudflare module Worker

## Release decision

**Code status: deployment-ready after account-bound credentials, project linking, and production origins are supplied.**

**Production status: not yet production-verified.** No Supabase project, OpenAI account, Cloudflare account, production domain, or SMTP provider was available in this environment, so hosted authentication, RLS isolation, model calls, database migration, and external deployment cannot honestly be marked complete.

## Finalized product boundary

DriftGuard protects one decision boundary: a user or authenticated integration submits consequential work immediately before or after an important workflow step, and receives **Pass, Watch, or Block**, the exact guardrail findings, and the smallest safe correction.

- Users own and approve the active constraints.
- Deterministic rules evaluate binary, threshold, and checklist evidence.
- The model interprets semantic evidence only.
- A violated blocking rule always forces `Block`.
- Any unclear or violated rule prevents `Pass`.
- Stored cadence values are checkpoints, not claims of passive monitoring.

## Material release corrections

- Removed derived/custom Edge Function deployment metadata from the deployment path.
- Canonical aggregate deployment now passes no function names; diagnostic commands pass one literal slug.
- Kept the valid public slugs `evaluate` and `infer-guardrails` consistent across folders, config, frontend calls, and scripts.
- Made Edge dependencies explicit Deno `npm:` imports; no per-function npm installation is required.
- Scoped VS Code Deno support only to `supabase/functions`.
- Added a minimal sanitized operational event plane without duplicating raw work or evidence.
- Moved operational audit authorship to trusted server paths.
- Added canonical use-case, workflow, architecture, UX, brand, scaling-threshold, readiness, event, metric, and documentation contracts derived selectively from the project compiler.
- Pinned Nitro/Cloudflare compatibility to `2026-07-08` rather than inheriting an unsupported build date.
- Removed random UUID generation and changing timestamps from Worker module initialization.
- Added an executable generated-Worker smoke test that fails on Cloudflare global-scope/runtime errors.

## Verification completed

| Gate                                                                        | Result                                          |
| --------------------------------------------------------------------------- | ----------------------------------------------- |
| Structural release checks                                                   | 77 passed                                       |
| Judgment-contract tests                                                     | 5 passed                                        |
| Deno lint/check                                                             | 8 Edge files checked                            |
| Edge slug/folder/config/frontend parity                                     | Passed                                          |
| Edge parse and bundle                                                       | Passed for both functions                       |
| Frontend TypeScript                                                         | Passed                                          |
| ESLint                                                                      | Passed                                          |
| Prettier                                                                    | Passed                                          |
| Production Vite/Nitro build                                                 | Passed                                          |
| Cloudflare compatibility contract                                           | Pinned to `2026-07-08`                          |
| Generated Worker runtime smoke test                                         | HTTP 200, expected content, zero runtime errors |
| Frontend and backend environment preflight with non-placeholder test values | Passed                                          |
| Fresh `npm ci` from a clean source tree                                     | Passed                                          |
| npm vulnerability audit, including development dependencies                 | 0 known vulnerabilities                         |
| Canonical schema/migration synchronization                                  | Passed                                          |

Run the same full local release suite with:

```bash
npm run release:verify
```

## Structural non-negotiables enforced

- One narrow job and one three-step primary path.
- Four required intent fields; advanced policy controls remain progressively disclosed.
- User acceptance is required before inferred guardrails become policy.
- Deterministic precedence cannot be overridden by the model.
- Missing proof cannot become `Pass`.
- Evaluation audits store the exact constraint snapshot, mode, model identity, findings, and result.
- Browser roles cannot create, modify, or delete evaluation or operational-event audits.
- Every user-visible application table uses owner-scoped RLS.
- AI keys and Supabase secret keys remain server-only.
- Current Supabase publishable/secret key maps and legacy key names are supported.
- AI calls have fixed quotas, request-size limits, timeouts, output limits, and sanitized external errors.
- CORS permits only exact configured origins.
- Root `schema.sql` is canonical; the deployable migration is generated and checked against it.
- npm, Node, Supabase CLI, Wrangler, Deno, and the Cloudflare compatibility date are explicitly controlled.
- Deployment readiness is not represented as live production proof.

## Credential-bound checks still required

1. Link the intended Supabase project and apply the schema.
2. Deploy both Edge Functions and complete real inference/evaluation calls.
3. Verify owner isolation using two real authenticated users.
4. Configure production SMTP and complete a magic-link flow.
5. Deploy the Cloudflare Worker using the real frontend environment values.
6. Complete the nine-step production smoke test in `README.md`.
7. Run a bounded pilot and measure useful interventions, false blocks, false passes, and repeat use.

These are external proof requirements, not hidden repository implementation work.

## Non-blocking upstream notices

The current connected Lovable/TanStack toolchain emits maintainer notices: Vite reports that native tsconfig-path support can eventually replace `vite-tsconfig-paths`; Nitro reports an ignored internal `inlineDynamicImports` option because code splitting is enabled; and npm reports transitive `tsconfck@3.1.6` as unmaintained. None fails installation, validation, build, Worker startup, or the vulnerability audit. Replacing the wrapper would expand scope without improving the verified core workflow and is therefore deferred.
