import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const mode = process.argv[2] ?? "all";
if (!new Set(["frontend", "backend", "all"]).has(mode)) {
  console.error("Usage: node scripts/env-check.mjs frontend|backend|all");
  process.exit(2);
}

async function load(path) {
  let content = "";
  try {
    content = await readFile(resolve(path), "utf8");
  } catch {
    // Hosting platforms may supply values directly through process.env.
  }
  const values = {};
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const index = line.indexOf("=");
    if (index < 1) continue;
    values[line.slice(0, index).trim()] = line
      .slice(index + 1)
      .trim()
      .replace(/^['"]|['"]$/g, "");
  }
  return { ...values, ...process.env };
}

const placeholder = /(YOUR_|REPLACE_WITH|example\.com|YOUR_ACTUAL|YOUR_PROJECT)/i;
const failures = [];
function requireValue(env, name) {
  const value = String(env[name] ?? "").trim();
  if (!value) failures.push(`${name} is missing`);
  else if (placeholder.test(value)) failures.push(`${name} still contains a placeholder`);
  return value;
}
function validUrl(value, name, { local = false, allowPath = false } = {}) {
  try {
    const url = new URL(value);
    if (
      url.protocol !== "https:" &&
      !(local && url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname))
    ) {
      failures.push(`${name} must use HTTPS${local ? " (localhost HTTP is allowed)" : ""}`);
    }
    if ((!allowPath && url.pathname !== "/") || url.search || url.hash)
      failures.push(
        `${name} must be ${allowPath ? "a base URL without a query or hash" : "an origin URL without a path, query, or hash"}`,
      );
    return url;
  } catch {
    failures.push(`${name} is not a valid URL`);
    return null;
  }
}

if (mode === "frontend" || mode === "all") {
  const env = await load(".env.local");
  const url = requireValue(env, "VITE_SUPABASE_URL");
  const key = requireValue(env, "VITE_SUPABASE_PUBLISHABLE_KEY");
  if (url) validUrl(url, "VITE_SUPABASE_URL", { local: true });
  if (key && !(key.startsWith("sb_publishable_") || key.split(".").length === 3)) {
    failures.push(
      "VITE_SUPABASE_PUBLISHABLE_KEY is not a modern publishable key or legacy anon JWT",
    );
  }
}

if (mode === "backend" || mode === "all") {
  const env = await load("supabase/functions/.env.local");
  const baseUrl = requireValue(env, "AI_BASE_URL");
  const apiKey = requireValue(env, "AI_API_KEY");
  requireValue(env, "AI_MODEL");
  const origins = requireValue(env, "ALLOWED_ORIGINS");
  if (baseUrl) validUrl(baseUrl, "AI_BASE_URL", { allowPath: true });
  if (apiKey && apiKey.length < 20) failures.push("AI_API_KEY is implausibly short");

  const format = String(env.AI_RESPONSE_FORMAT ?? "json_object").toLowerCase();
  if (!new Set(["json_object", "none"]).has(format))
    failures.push("AI_RESPONSE_FORMAT must be json_object or none");
  const effort = String(env.AI_REASONING_EFFORT ?? "none").toLowerCase();
  if (!new Set(["none", "low", "medium", "high", "xhigh"]).has(effort)) {
    failures.push("AI_REASONING_EFFORT must be none, low, medium, high, or xhigh");
  }
  const timeout = Number(env.AI_TIMEOUT_MS ?? 30000);
  if (!Number.isInteger(timeout) || timeout < 1000 || timeout > 55000)
    failures.push("AI_TIMEOUT_MS must be an integer from 1000 to 55000");
  const maxTokens = Number(env.AI_MAX_OUTPUT_TOKENS ?? 4000);
  if (!Number.isInteger(maxTokens) || maxTokens < 128 || maxTokens > 16000)
    failures.push("AI_MAX_OUTPUT_TOKENS must be an integer from 128 to 16000");

  let productionOrigin = false;
  for (const item of origins
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean)) {
    const url = validUrl(item, `ALLOWED_ORIGINS entry ${item}`, { local: true });
    if (url?.protocol === "https:" && !["localhost", "127.0.0.1"].includes(url.hostname))
      productionOrigin = true;
  }
  if (origins && !productionOrigin)
    failures.push(
      "ALLOWED_ORIGINS must include at least one HTTPS production origin before backend deployment",
    );
}

if (failures.length) {
  console.error("Environment preflight failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}
console.log(`${mode} environment preflight passed.`);
