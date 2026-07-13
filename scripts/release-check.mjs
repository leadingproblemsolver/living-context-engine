import { readFile, readdir, stat } from "node:fs/promises";
import { resolve } from "node:path";

const root = process.cwd();
const failures = [];
const checks = [];

async function text(path) {
  return readFile(resolve(root, path), "utf8");
}

async function exists(path) {
  try {
    await stat(resolve(root, path));
    return true;
  } catch {
    return false;
  }
}

async function sourceText(directory) {
  const parts = [];
  async function walk(current) {
    for (const entry of await readdir(resolve(root, current), { withFileTypes: true })) {
      const relative = `${current}/${entry.name}`;
      if (entry.isDirectory()) await walk(relative);
      else if (/\.(?:ts|tsx|js|mjs|sql|toml|md|json)$/.test(entry.name)) {
        parts.push(await text(relative));
      }
    }
  }
  await walk(directory);
  return parts.join("\n");
}

function requireCondition(label, condition, detail) {
  checks.push(label);
  if (!condition) failures.push(`${label}: ${detail}`);
}

const requiredFiles = [
  ".env.example",
  "supabase/functions/.env.example",
  "supabase/config.toml",
  "supabase/functions/deno.json",
  "supabase/functions/infer-guardrails/deno.json",
  "supabase/functions/evaluate/deno.json",
  ".vscode/settings.json",
  ".vscode/extensions.json",
  "scripts/check-edge.mjs",
  "scripts/deno-check.mjs",
  "scripts/worker-smoke.mjs",
  "src/lib/edge-functions.ts",
  "schema.sql",
  "supabase/migrations/20260706000000_driftguard.sql",
  "supabase/functions/infer-guardrails/index.ts",
  "supabase/functions/evaluate/index.ts",
  "scripts/env-check.mjs",
  ".npmrc",
  ".nvmrc",
  "package-lock.json",
  "nitro.config.ts",
  "RELEASE_GATES.md",
  "RELEASE_REPORT.md",
  "ENVIRONMENT.md",
  "PRODUCT_DIRECTION.md",
  "docs/API.md",
  "docs/COMPILER_APPLICATION.md",
  "docs/DECISIONS.md",
  "docs/product/USE_CASE.yaml",
  "docs/product/AUDIENCE_MAP.yaml",
  "docs/product/CORE_WORKFLOW.yaml",
  "docs/product/VALUE_ARCHITECTURE.md",
  "docs/product/OPERATIONAL_EFFECTIVENESS.md",
  "docs/product/ARCHITECTURE.md",
  "docs/product/UX_SPEC.md",
  "docs/product/SCALABILITY_THRESHOLDS.yaml",
  "docs/product/BRAND_SYSTEM.yaml",
  "docs/product/READINESS.yaml",
  "intelligence/EVENT_SCHEMA.json",
  "intelligence/METRICS.yaml",
  "documentation/DOCUMENT_REGISTRY.yaml",
  "documentation/UPDATE_RULES.yaml",
  "supabase/functions/_shared/events.ts",
];
for (const path of requiredFiles) {
  requireCondition(`file:${path}`, await exists(path), "required release file is missing");
}

const frontendEnv = await text(".env.example");
const functionEnv = await text("supabase/functions/.env.example");
const gitignore = await text(".gitignore");
const config = await text("supabase/config.toml");
const edgeCheck = await text("scripts/check-edge.mjs");
const denoCheck = await text("scripts/deno-check.mjs");
const workerSmoke = await text("scripts/worker-smoke.mjs");
const edgeClient = await text("src/lib/edge-functions.ts");
const vscodeSettings = await text(".vscode/settings.json");
const schema = await text("schema.sql");
const migration = await text("supabase/migrations/20260706000000_driftguard.sql");
const evaluate = await text("supabase/functions/evaluate/index.ts");
const auth = await text("supabase/functions/_shared/auth.ts");
const browser = await text("src/routes/index.tsx");
const browserSource = await sourceText("src");
const edgeSource = await sourceText("supabase/functions");
const engine = await text("src/lib/drift-engine.ts");
const http = await text("supabase/functions/_shared/http.ts");
const cors = await text("supabase/functions/_shared/cors.ts");
const ai = await text("supabase/functions/_shared/ai.ts");
const events = await text("supabase/functions/_shared/events.ts");
const infer = await text("supabase/functions/infer-guardrails/index.ts");
const coreWorkflow = await text("docs/product/CORE_WORKFLOW.yaml");
const readiness = await text("docs/product/READINESS.yaml");
const nitroConfig = await text("nitro.config.ts");
const packageJson = JSON.parse(await text("package.json"));
const packageLock = JSON.parse(await text("package-lock.json"));

requireCondition(
  "frontend env contract",
  frontendEnv.includes("VITE_SUPABASE_URL=") &&
    frontendEnv.includes("VITE_SUPABASE_PUBLISHABLE_KEY="),
  "frontend Supabase variables are incomplete",
);
requireCondition(
  "server env contract",
  ["AI_BASE_URL=", "AI_API_KEY=", "AI_MODEL=", "AI_REASONING_EFFORT=", "ALLOWED_ORIGINS="].every(
    (name) => functionEnv.includes(name),
  ),
  "Edge Function variables are incomplete",
);
requireCondition(
  "secret boundary",
  !frontendEnv.includes("AI_API_KEY") &&
    !/AI_API_KEY|SUPABASE_SECRET_KEYS|SUPABASE_SERVICE_ROLE_KEY/.test(browserSource),
  "a server-only secret name appears in the browser environment or source",
);
requireCondition(
  "env files ignored",
  gitignore.includes(".env.*") && gitignore.includes("supabase/functions/.env.*"),
  "populated environment files are not comprehensively ignored",
);
requireCondition(
  "modern Supabase keys",
  auth.includes("SUPABASE_PUBLISHABLE_KEYS") && auth.includes("SUPABASE_SECRET_KEYS"),
  "current Supabase key maps are not supported",
);
requireCondition(
  "manual function auth",
  config.match(/verify_jwt\s*=\s*false/g)?.length === 2 && auth.includes("auth.getUser(token)"),
  "functions must disable legacy gateway verification and verify the user token themselves",
);
requireCondition(
  "server-authored evaluations",
  evaluate.includes('.from("evaluations")') &&
    !browser.includes('.from("evaluations").insert') &&
    schema.includes("revoke all on public.evaluations from authenticated") &&
    schema.includes("grant select on public.evaluations to authenticated") &&
    !schema.includes("grant select, delete on public.evaluations"),
  "the browser must not author, mutate, or delete evaluation audit records",
);
requireCondition(
  "deterministic block precedence",
  evaluate.includes('finding.status === "violated" && rule?.enforcement === "block"') &&
    evaluate.includes('blockingViolation ? "block"'),
  "a violated blocking rule must deterministically force Block",
);
requireCondition(
  "no fabricated pass",
  evaluate.includes('finding.status !== "met"') && engine.includes('finding.status !== "met"'),
  "any unclear or violated rule must prevent Pass",
);
requireCondition(
  "RLS enabled",
  [
    "profiles",
    "guardrail_sets",
    "guardrails",
    "evaluations",
    "operational_events",
    "ai_request_usage",
  ].every((table) => schema.includes(`alter table public.${table} enable row level security`)),
  "RLS is not enabled on every application table",
);
requireCondition(
  "quota enforced",
  schema.includes("create or replace function public.consume_ai_request") &&
    evaluate.includes("consumeAiQuota") &&
    (await text("supabase/functions/infer-guardrails/index.ts")).includes("consumeAiQuota"),
  "AI calls are not bounded per user",
);
requireCondition(
  "schema migration synced",
  migration.endsWith(schema),
  "run `npm run schema:sync` after changing schema.sql",
);

requireCondition(
  "literal Edge Function slugs",
  edgeClient.includes('inferGuardrails: "infer-guardrails"') &&
    edgeClient.includes('evaluate: "evaluate"') &&
    browser.includes("EDGE_FUNCTIONS.inferGuardrails") &&
    browser.includes("EDGE_FUNCTIONS.evaluate") &&
    edgeCheck.includes('const EXPECTED = ["evaluate", "infer-guardrails"]'),
  "function folders, frontend constants, config, and deploy commands must use the two literal slugs",
);
requireCondition(
  "Deno editor isolation",
  !vscodeSettings.includes('"deno.enable": true') &&
    vscodeSettings.includes('"deno.enablePaths"') &&
    vscodeSettings.includes('"./supabase/functions"') &&
    packageJson.scripts?.["check:deno"] === "node scripts/deno-check.mjs" &&
    denoCheck.includes('"deno@2.9.1"') &&
    String(packageJson.scripts?.["check:edge"]).includes("check:deno"),
  "VS Code must treat only the Edge tree as Deno and CI must lint and bundle it independently",
);

requireCondition(
  "pinned deployment CLIs",
  packageJson.devDependencies?.wrangler === "4.107.0" &&
    Object.values(packageJson.scripts ?? {}).filter((command) =>
      String(command).includes("npx --yes supabase@2.109.0"),
    ).length >= 5 &&
    packageJson.scripts?.["supabase:functions"] ===
      "npx --yes supabase@2.109.0 functions deploy --no-verify-jwt" &&
    packageJson.scripts?.["supabase:function:evaluate"] ===
      "npx --yes supabase@2.109.0 functions deploy evaluate --no-verify-jwt" &&
    packageJson.scripts?.["supabase:function:infer"] ===
      "npx --yes supabase@2.109.0 functions deploy infer-guardrails --no-verify-jwt" &&
    !String(packageJson.scripts?.["supabase:functions"]).includes("evaluate infer-guardrails") &&
    !packageJson.devDependencies?.supabase &&
    packageLock.lockfileVersion === 3,
  "Supabase CLI commands, Wrangler, and the npm lockfile must remain reproducible",
);
requireCondition(
  "pinned Cloudflare compatibility date",
  nitroConfig.includes('compatibilityDate: "2026-07-08"') &&
    !nitroConfig.includes('compatibilityDate: "latest"'),
  "Cloudflare compatibility must be pinned to a date supported by the pinned Wrangler/workerd runtime",
);
requireCondition(
  "single package manager",
  packageJson.packageManager === "npm@10.9.2" &&
    !(await exists("bun.lock")) &&
    !(await exists("bunfig.toml")) &&
    !(await exists("yarn.lock")) &&
    !(await exists("pnpm-lock.yaml")),
  "npm must be the only release package manager",
);
requireCondition(
  "minimal dependency surface",
  !(await exists("src/components/ui")) &&
    !packageJson.dependencies?.recharts &&
    !Object.keys(packageJson.dependencies ?? {}).some((name) => name.startsWith("@radix-ui/")),
  "unused generated UI components and their dependency surface must stay out of the release",
);
requireCondition(
  "runtime AI env validation",
  ai.includes('configuredChoice("AI_RESPONSE_FORMAT"') &&
    ai.includes('configuredChoice("AI_REASONING_EFFORT"') &&
    ai.includes('boundedInteger("AI_TIMEOUT_MS"') &&
    ai.includes('boundedInteger("AI_MAX_OUTPUT_TOKENS"') &&
    ai.includes("AI_BASE_URL must use HTTPS"),
  "Edge runtime must reject invalid provider configuration explicitly",
);
requireCondition(
  "HTTP boundary",
  http.includes("Request body is too large") &&
    http.includes('"Cache-Control": "no-store"') &&
    cors.includes("Origin is not allowed") &&
    cors.includes('Vary: "Origin"'),
  "request size, no-store responses, and exact-origin CORS must be enforced",
);
requireCondition(
  "prompt injection boundary",
  (edgeSource.match(/untrusted data, not instructions/g)?.length ?? 0) >= 2,
  "both AI prompts must frame submitted content as untrusted data",
);
requireCondition(
  "audit snapshot completeness",
  evaluate.includes("constraint_snapshot: snapshot") &&
    evaluate.includes("model_provider: modelProvider") &&
    evaluate.includes("model_name: modelName") &&
    evaluate.includes("evaluation_mode: mode"),
  "every server-authored result must store its policy snapshot, mode, and model identity",
);
requireCondition(
  "executable Worker smoke test",
  packageJson.scripts?.["smoke:worker"] === "npm run build && node scripts/worker-smoke.mjs" &&
    packageJson.scripts?.["release:verify"] ===
      "npm run validate && node scripts/worker-smoke.mjs && npm audit --audit-level=low" &&
    workerSmoke.includes('body.includes("DriftGuard")') &&
    workerSmoke.includes("Disallowed operation"),
  "release verification must exercise the generated Worker and reject global-scope runtime errors",
);
requireCondition(
  "Cloudflare global-scope safety",
  engine.includes('id: options.id ?? uid("guardrail")') &&
    !engine.includes("createdAt: new Date().toISOString()"),
  "sample data must not generate random values or build-time timestamps during Worker module initialization",
);
requireCondition(
  "ten-second value proposition",
  browser.includes("Stop important work from quietly drifting.") &&
    browser.includes("Pass, Watch, or Block") &&
    browser.includes("smallest safe correction"),
  "the hero must state the pain, verdict, and corrective output directly",
);
requireCondition(
  "three-step workflow",
  browser.includes("Step 1 · Intent") &&
    browser.includes("Step 2 · Constraints") &&
    browser.includes("Step 3 · Judgment") &&
    browser.includes("Advanced controls"),
  "the core workflow must remain three explicit steps with advanced controls secondary",
);
requireCondition(
  "automation honesty",
  browser.includes("In-app checks are manual") &&
    browser.includes("does not silently monitor other") &&
    (await text("docs/API.md")).includes("does not poll or observe external tools"),
  "checkpoint metadata must not be represented as passive workflow monitoring",
);
requireCondition(
  "operational event plane",
  schema.includes("create table if not exists public.operational_events") &&
    schema.includes("revoke all on public.operational_events from authenticated") &&
    schema.includes("grant select on public.operational_events to authenticated") &&
    events.includes('.from("operational_events").insert') &&
    evaluate.includes('eventType: "OUTCOME_VERIFIED"') &&
    infer.includes('eventType: "MODEL_CALLED"') &&
    schema.includes("'RULE_UPDATED'"),
  "core cloud actions must emit sanitized, server-authored operational events",
);
requireCondition(
  "telemetry privacy boundary",
  !events.includes("input_text") &&
    !events.includes("evidence:") &&
    !events.includes("email") &&
    coreWorkflow.includes("Raw work and evidence") === false,
  "operational telemetry must not duplicate raw work, evidence, or identity fields",
);
requireCondition(
  "compiler outputs synchronized",
  coreWorkflow.includes("violated block rule forces Block") &&
    coreWorkflow.includes("any unclear or violated rule prevents Pass") &&
    readiness.includes("deployment_ready: true") &&
    readiness.includes("production_ready: false"),
  "product contracts must distinguish code deployment readiness from live production proof",
);

const prohibitedFiles = [
  ".env",
  ".env.local",
  "supabase/functions/.env",
  "supabase/functions/.env.local",
];
for (const path of prohibitedFiles) {
  requireCondition(
    `no committed secret:${path}`,
    !(await exists(path)),
    "populated secret file exists in the release tree",
  );
}

if (failures.length) {
  console.error(`Release gate failed (${failures.length}/${checks.length}):`);
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}
console.log(`Release structure passed ${checks.length} checks.`);
