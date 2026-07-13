import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:net";
import { resolve } from "node:path";

async function availablePort() {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new Error("Could not allocate a local smoke-test port."));
        return;
      }
      const port = address.port;
      server.close((error) => (error ? reject(error) : resolvePort(port)));
    });
  });
}

function stopProcess(child) {
  if (!child.pid || child.killed) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    return;
  }
  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    child.kill("SIGTERM");
  }
}

const root = process.cwd();
const executable = resolve(
  root,
  "node_modules",
  ".bin",
  process.platform === "win32" ? "wrangler.cmd" : "wrangler",
);
const port = await availablePort();
const child = spawn(
  executable,
  [
    "dev",
    "--config",
    ".output/server/wrangler.json",
    "--port",
    String(port),
    "--log-level",
    "error",
  ],
  {
    cwd: root,
    detached: process.platform !== "win32",
    env: { ...process.env, WRANGLER_SEND_METRICS: "false" },
    stdio: ["ignore", "pipe", "pipe"],
  },
);

let logs = "";
child.stdout.on("data", (chunk) => {
  logs += chunk.toString();
});
child.stderr.on("data", (chunk) => {
  logs += chunk.toString();
});

const deadline = Date.now() + 60_000;
let body = "";
let status = 0;
try {
  while (Date.now() < deadline) {
    if (child.exitCode !== null) break;
    try {
      const response = await fetch(`http://127.0.0.1:${port}/`);
      status = response.status;
      body = await response.text();
      if (response.ok) break;
    } catch {
      // The local runtime is still starting.
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 500));
  }

  await new Promise((resolveDelay) => setTimeout(resolveDelay, 750));
  const forbiddenRuntimeError = /Disallowed operation|runtime failed|\[ERROR\]/i.test(logs);
  if (status !== 200 || !body.includes("DriftGuard") || forbiddenRuntimeError) {
    throw new Error(
      [
        `Worker smoke test failed (HTTP ${status || "unavailable"}).`,
        forbiddenRuntimeError ? "Cloudflare runtime error detected." : "",
        logs.slice(-4000),
      ]
        .filter(Boolean)
        .join("\n"),
    );
  }
  console.log(`Cloudflare Worker smoke test passed on local port ${port}.`);
} finally {
  stopProcess(child);
}
