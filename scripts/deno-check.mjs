import { spawnSync } from "node:child_process";

const executable = process.platform === "win32" ? "npx.cmd" : "npx";
const args = [
  "--yes",
  "deno@2.9.1",
  "lint",
  "supabase/functions/evaluate/index.ts",
  "supabase/functions/infer-guardrails/index.ts",
  "supabase/functions/_shared",
];
const result = spawnSync(executable, args, { cwd: process.cwd(), stdio: "inherit", shell: false });
if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status ?? 1);
