# DriftGuard

**Define what must stay true. Check the next action or output. Get Pass, Watch, or Block—and the smallest correction required.**

DriftGuard is a constraint-control layer for consequential work. The user owns the purpose and guardrails. AI interprets semantic evidence; deterministic code owns enforcement precedence.

## What this release guarantees

- Four-field default setup: purpose, workflow, target, and observable proof of success.
- AI-assisted guardrail inference with explicit user review.
- Exact controls for criticality, enforcement, target scope, and evidence type.
- Deterministic binary, threshold, and checklist evaluation.
- Conservative semantic evaluation: missing proof is `Watch`, never `Pass`.
- A violated blocking rule always forces `Block`.
- Server-authored evaluation history with the exact constraint snapshot.
- Supabase magic-link auth, RLS, transactional saves, and per-user AI quotas.
- Local preview mode when cloud services are unavailable, labelled `rules-preview` rather than AI.

The complete non-negotiable contract is in [`RELEASE_GATES.md`](./RELEASE_GATES.md). The exact public/server environment split is in [`ENVIRONMENT.md`](./ENVIRONMENT.md), and the completed verification record is in [`RELEASE_REPORT.md`](./RELEASE_REPORT.md).

The compiler-derived operating specification is in [`docs/COMPILER_APPLICATION.md`](./docs/COMPILER_APPLICATION.md). The canonical use case, workflow, architecture, UX, scaling thresholds, brand contract, and readiness verdict live under [`docs/product/`](./docs/product/).

## Prerequisites

- Node.js 22
- npm 10+
- A Supabase project
- An OpenAI API key
- Supabase CLI commands use the pinned `supabase@2.109.0` through `npx` when needed

Use npm as the canonical package manager for this release. `package-lock.json` is committed.

### VS Code and Edge Function workspace

Open the repository root in VS Code and install the workspace-recommended **Deno** extension. The committed `.vscode/settings.json` enables Deno only for `supabase/functions`, so the frontend remains on the normal Vite/TypeScript toolchain while Edge Functions receive `Deno`, `npm:` import, and `.ts` import resolution. Reload the VS Code window once after installing the extension.

The only deployable Edge Function slugs are:

- `infer-guardrails`
- `evaluate`

`supabase/functions/_shared` is shared source, not a deployable function. The only deployable folders are `evaluate` and `infer-guardrails`. Their literal names are checked against frontend invocation constants and `supabase/config.toml`; no custom slug manifest participates in deployment.

Run the dedicated Edge checks at any time:

```bash
npm run check:edge
```

This runs pinned Deno lint/check, standalone Edge TypeScript checking, validates slug parity, and bundles every declared function.

## 1. Install and configure the frontend

```bash
npm ci
cp .env.example .env.local
```

Populate `.env.local` with exactly these two public values:

```env
VITE_SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_YOUR_ACTUAL_KEY
```

Get both values from **Supabase Dashboard → Connect** or **Project Settings → API Keys**.

These values are intentionally browser-visible. Do not put an OpenAI key, Supabase secret key, or service-role key in any `VITE_` variable.

## 2. Configure Edge Function secrets

```bash
cp supabase/functions/.env.example supabase/functions/.env.local
```

Populate it as follows:

```env
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-YOUR_ACTUAL_OPENAI_API_KEY
AI_MODEL=gpt-5.4-mini-2026-03-17
AI_RESPONSE_FORMAT=json_object
AI_REASONING_EFFORT=none
AI_TIMEOUT_MS=30000
AI_MAX_OUTPUT_TOKENS=4000
ALLOWED_ORIGINS=http://localhost:3000,https://YOUR_ACTUAL_PRODUCTION_DOMAIN
```

`ALLOWED_ORIGINS` must contain exact origins only: scheme + hostname + optional port, with no path and no trailing slash.

Do **not** manually add the following hosted-function variables. Supabase injects them into deployed Edge Functions:

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEYS`
- `SUPABASE_SECRET_KEYS`
- legacy `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` during migration

The functions support both current and legacy key formats.

## 3. Link Supabase and deploy the backend

> **Slug invariant:** `npm run supabase:functions` deploys all local functions by passing no function names. The pinned CLI supports variadic names, but DriftGuard intentionally avoids that form because external deployment wrappers can mis-parse it. Diagnostic scripts pass exactly one literal slug.

```bash
npm run supabase:login
npm run supabase:link -- --project-ref YOUR_PROJECT_REF
npm run deploy:backend
```

`npm run deploy:backend` performs all three backend steps:

1. Synchronizes the canonical root `schema.sql` into the deployable migration.
2. Pushes the database schema, RLS policies, RPCs, grants, indexes, and quota tables.
3. Uploads Edge Function secrets and deploys every local Edge Function with one slug-free CLI command and handler-level user-token verification.

The canonical database source remains [`schema.sql`](./schema.sql). The file under `supabase/migrations/` is generated by `npm run schema:sync`; do not edit the migration directly.

### Existing project alternative

The schema is idempotent. You may paste the complete contents of `schema.sql` into the Supabase SQL Editor instead of using `db push`, then run:

```bash
npm run supabase:secrets
npm run supabase:functions
```

## 4. Configure magic-link redirects

In **Supabase Dashboard → Authentication → URL Configuration** set:

- **Site URL:** your exact production origin, for example `https://driftguard.example.com`
- **Redirect URLs:**
  - `http://localhost:3000/**`
  - your exact production origin followed by `/**`

For real external users, configure a production SMTP provider in Supabase Auth rather than relying on the default test email service.

## 5. Validate the release

```bash
npm run release:verify
```

`npm run release:verify` runs the complete release suite. Its `validate` phase runs:

- canonical schema synchronization;
- structural release gates;
- deterministic judgment-contract tests;
- pinned Deno lint/check plus standalone Edge TypeScript, slug-parity, and parse/bundle checks;
- frontend TypeScript checking;
- ESLint;
- Prettier verification;
- the full production Vite/Nitro build.

It then starts the generated Cloudflare Worker, requests the home page, rejects Worker global-scope/runtime errors, and runs the complete npm vulnerability audit.

Do not deploy when any step fails.

## 6. Run locally

Frontend only, using local preview fallback when signed out:

```bash
npm run dev
```

Full local Supabase requires Docker:

```bash
npm run supabase:local
```

The frontend is available at the Vite URL printed by the terminal. Supabase Studio and function URLs are printed by the Supabase CLI.

## 7. Deploy the web app

The existing build targets a Cloudflare module worker through Nitro.

Add the two frontend variables from `.env.local` to the production build environment, then run:

```bash
npm run deploy:web
```

This builds the production application and deploys the generated Cloudflare Worker with Wrangler. Authenticate Wrangler when prompted. The same repository can also be published through the existing Lovable project integration; use the identical two frontend environment values there.

After receiving the production URL:

1. Replace `YOUR_ACTUAL_PRODUCTION_DOMAIN` in `supabase/functions/.env.local`.
2. Re-run `npm run supabase:secrets`.
3. Add the URL to Supabase Auth redirect settings.
4. Re-run the smoke test below.

## 8. Production smoke test

1. Open the deployed URL and confirm the page renders without configuration warnings.
2. Request a magic link and complete sign-in.
3. Enter all four intent fields and infer guardrails.
4. Save the guardrail set and refresh; confirm it reloads from Supabase.
5. Add a blocking binary rule, submit `No`, and confirm the result is `Block`.
6. Submit no value for that rule and confirm the result is `Watch`, not `Pass`.
7. Submit `Yes` for every active structured rule and explicit evidence for semantic rules; confirm `Pass` is possible only when every finding is `met`.
8. In Supabase Table Editor, confirm the evaluation row includes `constraint_snapshot`, `model_name`, and `evaluation_mode`.
9. Sign in as a second test user and confirm the first user's rows are invisible.

## API/workflow integration

The authenticated function contract, headers, structured evidence shape, and response format are documented in [`docs/API.md`](./docs/API.md). The app itself performs checks only when the user submits them. “Before action,” “after output,” and “daily” are integration checkpoints: an external workflow must call the evaluation endpoint with the work and evidence at that point. DriftGuard does not claim passive monitoring without such an integration.

## Architecture boundary

```text
Browser
  ├─ public Supabase URL + publishable key
  ├─ localStorage preview workspace
  └─ authenticated calls
       ↓
Supabase
  ├─ Auth: magic links and user sessions
  ├─ Postgres: RLS-protected sets, rules, immutable evaluations, and sanitized operational events
  ├─ RPC: transactional set save + atomic AI quotas
  └─ Edge Functions
       ├─ verify user bearer token
       ├─ read server-only AI secrets
       ├─ evaluate objective rules deterministically
       ├─ use AI only for semantic interpretation
       ├─ apply deterministic Pass/Watch/Block precedence
       └─ write the audit record with a server secret
```

## Core files

- `ENVIRONMENT.md` — exact variable names, sources, trust boundaries, and accepted values.
- `RELEASE_REPORT.md` — verified gates and credential-bound production checks.
- `schema.sql` — complete database contract.
- `supabase/config.toml` — function auth deployment configuration.
- `supabase/functions/deno.json` — shared-module Deno/import-map configuration.
- `supabase/functions/*/deno.json` — per-function Deno configuration for deployment and editor resolution.
- `supabase/functions/.env.example` — exact server-only LLM configuration.
- `supabase/functions/infer-guardrails/` — guarded AI inference.
- `supabase/functions/evaluate/` — hybrid deterministic/semantic judgment and audit persistence.
- `src/lib/drift-engine.ts` — deterministic local preview and contract tests.
- `nitro.config.ts` — pinned Cloudflare compatibility contract.
- `scripts/worker-smoke.mjs` — executable generated-Worker runtime regression test.
- `RELEASE_GATES.md` — structural non-negotiables.
- `PRODUCT_DIRECTION.md` — wedge, vocabulary, and expansion boundaries.
- `docs/product/USE_CASE.yaml` — canonical trigger, user, pain, proof, and non-goals.
- `docs/product/CORE_WORKFLOW.yaml` — complete stage and handoff contract.
- `docs/product/READINESS.yaml` — evidence-based deployment and production verdict.
- `intelligence/EVENT_SCHEMA.json` — sanitized operational event contract.
- `documentation/UPDATE_RULES.yaml` — documentation synchronization rules.

## Deliberate boundaries

DriftGuard is not a general project manager, autonomous policy setter, passive surveillance system, or invented compliance authority. It becomes valuable at a specific decision boundary where violating accepted constraints creates rework, credibility damage, customer harm, or operational risk.

## Edge deployment diagnostics

The canonical deployment uses no function-name argument, which deploys every folder under `supabase/functions`:

```bash
npm run supabase:link -- --project-ref YOUR_PROJECT_REF
npm run supabase:functions
```

To isolate a function-specific failure, deploy exactly one literal slug:

```bash
npm run supabase:function:evaluate
npm run supabase:function:infer
```

The normal path intentionally does **not** force `--use-api`. If local bundling fails because Docker or the local bundler is unavailable, use the explicit server-side API path for diagnosis:

```bash
npm run supabase:functions:api
```

For a raw trace:

```bash
npx --yes supabase@2.109.0 functions deploy evaluate --no-verify-jwt --debug
npx --yes supabase@2.109.0 functions deploy infer-guardrails --no-verify-jwt --debug
```

The Edge import `npm:@supabase/supabase-js@2.110.0` is resolved by Deno/Supabase at bundle time. It is intentionally not installed inside each function folder.
