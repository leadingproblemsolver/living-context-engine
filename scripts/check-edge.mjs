import { readdir, readFile, stat } from "node:fs/promises";
import { resolve } from "node:path";
import { build } from "esbuild";

const root = process.cwd();
const functionsRoot = resolve(root, "supabase/functions");
const EXPECTED = ["evaluate", "infer-guardrails"];
const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

async function exists(path) {
  try {
    await stat(resolve(root, path));
    return true;
  } catch {
    return false;
  }
}

const entries = await readdir(functionsRoot, { withFileTypes: true });
const actual = entries
  .filter(
    (entry) => entry.isDirectory() && !entry.name.startsWith("_") && !entry.name.startsWith("."),
  )
  .map((entry) => entry.name)
  .sort();

for (const slug of actual) {
  if (!SLUG_PATTERN.test(slug))
    throw new Error(`Invalid Supabase Edge Function folder name: ${slug}`);
}
if (JSON.stringify(actual) !== JSON.stringify(EXPECTED)) {
  throw new Error(
    `Expected Edge Function folders ${EXPECTED.join(", ")}; found ${actual.join(", ")}.`,
  );
}

const config = await readFile(resolve(root, "supabase/config.toml"), "utf8");
const routeSource = await readFile(resolve(root, "src/routes/index.tsx"), "utf8");
const clientSource = await readFile(resolve(root, "src/lib/edge-functions.ts"), "utf8");

for (const slug of EXPECTED) {
  const entryPoint = `supabase/functions/${slug}/index.ts`;
  const denoConfig = `supabase/functions/${slug}/deno.json`;
  if (!(await exists(entryPoint))) throw new Error(`Missing ${entryPoint}`);
  if (!(await exists(denoConfig))) throw new Error(`Missing ${denoConfig}`);
  if (!config.includes(`[functions.${slug}]`))
    throw new Error(`Missing [functions.${slug}] in supabase/config.toml`);
  if (!new RegExp(`\\[functions\\.${slug}\\][\\s\\S]*?verify_jwt\\s*=\\s*false`).test(config)) {
    throw new Error(`${slug} must set verify_jwt = false in supabase/config.toml`);
  }
  if (!clientSource.includes(`"${slug}"`))
    throw new Error(`Frontend constant missing literal slug ${slug}`);

  await build({
    entryPoints: [entryPoint],
    bundle: true,
    write: false,
    platform: "neutral",
    format: "esm",
    external: ["npm:*"],
    logLevel: "silent",
  });
}

if (
  !routeSource.includes("EDGE_FUNCTIONS.inferGuardrails") ||
  !routeSource.includes("EDGE_FUNCTIONS.evaluate")
) {
  throw new Error("Frontend invokes must use EDGE_FUNCTIONS constants.");
}

console.log(`Edge Function integrity passed: ${EXPECTED.join(", ")}.`);
