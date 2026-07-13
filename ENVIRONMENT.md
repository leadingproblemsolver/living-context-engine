# Environment contract

DriftGuard deliberately uses two environment files because browser configuration and server secrets have different trust boundaries.

## 1. Frontend: `.env.local`

Create it from `.env.example`:

```bash
cp .env.example .env.local
```

```env
VITE_SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_REPLACE_WITH_YOUR_KEY
```

| Variable                        | Source                                                             | Exposure             | Required |
| ------------------------------- | ------------------------------------------------------------------ | -------------------- | -------- |
| `VITE_SUPABASE_URL`             | Supabase Dashboard → Project Settings → API → Project URL          | Public browser value | Yes      |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Supabase Dashboard → Project Settings → API Keys → Publishable key | Public browser value | Yes      |

Never place an AI key, a Supabase secret key, or a legacy service-role key in a `VITE_` variable.

## 2. Supabase Edge Functions: `supabase/functions/.env.local`

Create it from `supabase/functions/.env.example`:

```bash
cp supabase/functions/.env.example supabase/functions/.env.local
```

```env
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-REPLACE_WITH_YOUR_SERVER_ONLY_KEY
AI_MODEL=gpt-5.4-mini-2026-03-17
AI_RESPONSE_FORMAT=json_object
AI_REASONING_EFFORT=none
AI_TIMEOUT_MS=30000
AI_MAX_OUTPUT_TOKENS=4000
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173,https://YOUR_PRODUCTION_DOMAIN
```

| Variable               | Contract                                                                                                     | Required |
| ---------------------- | ------------------------------------------------------------------------------------------------------------ | -------- |
| `AI_BASE_URL`          | HTTPS base URL whose `/chat/completions` endpoint supports OpenAI-style messages and `max_completion_tokens` | Yes      |
| `AI_API_KEY`           | Server-only provider key; minimum sanity-checked length 20                                                   | Yes      |
| `AI_MODEL`             | Pinned model identifier used for inference and semantic evaluation                                           | Yes      |
| `AI_RESPONSE_FORMAT`   | `json_object` or `none`                                                                                      | Yes      |
| `AI_REASONING_EFFORT`  | `none`, `low`, `medium`, `high`, or `xhigh`                                                                  | Yes      |
| `AI_TIMEOUT_MS`        | Integer from 1000 to 55000                                                                                   | Yes      |
| `AI_MAX_OUTPUT_TOKENS` | Integer from 128 to 16000                                                                                    | Yes      |
| `ALLOWED_ORIGINS`      | Comma-separated exact origins; production deployment requires at least one HTTPS origin                      | Yes      |

The default values target OpenAI. An alternative gateway is valid only when it implements the exact request contract above. Set `AI_RESPONSE_FORMAT=none` when that gateway rejects `response_format`.

## 3. Supabase-provided function variables

Do not copy these into either example file. Supabase injects them into hosted Edge Functions:

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEYS`
- `SUPABASE_SECRET_KEYS`
- legacy `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` where still available

The functions accept current Supabase key maps and legacy key names. The browser never receives the secret key.

## 4. Preflight

```bash
npm run check:env
```

For staged deployment:

```bash
npm run check:env:frontend
npm run check:env:backend
```

The checks reject missing values, placeholders, invalid URLs, unsafe production origins, unsupported enumerations, and out-of-range limits before deployment begins.

## 5. Edge Function runtime and slugs

The Edge tree is a Deno workspace isolated to `supabase/functions`. VS Code settings and recommended extensions are committed under `.vscode/`. After opening the repository, install the recommended Deno extension and reload the window.

The canonical deployment slugs are literal folder names:

| Function ID       | Deployment slug    | Gateway JWT verification                    |
| ----------------- | ------------------ | ------------------------------------------- |
| `inferGuardrails` | `infer-guardrails` | Disabled; handler verifies the bearer token |
| `evaluate`        | `evaluate`         | Disabled; handler verifies the bearer token |

`_shared` is intentionally underscore-prefixed and is never deployed as a function. The root Deno configuration resolves shared imports; each deployable function also has its own `deno.json`.

Validate Deno resolution, editor/runtime types, and slug consistency with:

```bash
npm run check:edge
```

Deploy every function directory with one slug-free CLI call:

```bash
npm run supabase:functions
```

The aggregate command deliberately supplies no function names, which deploys every function directory. The diagnostic commands supply one literal slug so failures remain isolated. This avoids custom wrappers or deployment surfaces mis-parsing a multi-name command even though the pinned CLI itself supports variadic names.

## 6. Cloudflare runtime contract

`nitro.config.ts` pins the generated Worker compatibility date to `2026-07-08`. Do not replace it with `latest` or the build date. Update it deliberately only after the pinned Wrangler/workerd version starts successfully with the newer date and this test passes:

```bash
npm run smoke:worker
```
