import { HttpError } from "./http.ts";

function boundedInteger(name: string, fallback: number, minimum: number, maximum: number) {
  const raw = Deno.env.get(name)?.trim();
  if (!raw) return fallback;
  const parsed = Number(raw);
  if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error(`${name} must be an integer from ${minimum} to ${maximum}`);
  }
  return parsed;
}

function configuredBaseUrl() {
  const raw = (Deno.env.get("AI_BASE_URL") ?? "https://api.openai.com/v1").trim();
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error("AI_BASE_URL must be a valid URL");
  }
  const local = ["localhost", "127.0.0.1"].includes(url.hostname);
  if (url.protocol !== "https:" && !(local && url.protocol === "http:")) {
    throw new Error("AI_BASE_URL must use HTTPS (localhost HTTP is allowed)");
  }
  if (url.search || url.hash) throw new Error("AI_BASE_URL cannot contain a query or hash");
  return raw.replace(/\/$/, "");
}

function configuredChoice(name: string, fallback: string, allowed: readonly string[]) {
  const value = (Deno.env.get(name) ?? fallback).trim().toLowerCase();
  if (!allowed.includes(value)) {
    throw new Error(`${name} must be one of: ${allowed.join(", ")}`);
  }
  return value;
}

function extractContent(payload: unknown): string {
  const data = payload as {
    choices?: Array<{ message?: { content?: string | Array<{ text?: string }> } }>;
  };
  const content = data.choices?.[0]?.message?.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return content.map((part) => part.text ?? "").join("");
  throw new Error("AI provider returned no message content");
}

function extractJson(text: string): unknown {
  const trimmed = text
    .trim()
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/, "");
  try {
    return JSON.parse(trimmed);
  } catch {
    const start = trimmed.indexOf("{");
    const end = trimmed.lastIndexOf("}");
    if (start >= 0 && end > start) return JSON.parse(trimmed.slice(start, end + 1));
    throw new Error("AI provider returned invalid JSON");
  }
}

export type AiResult = {
  data: unknown;
  provider: string;
  model: string;
  latencyMs: number;
  usage: { inputTokens: number | null; outputTokens: number | null };
};

export async function callJsonAI(system: string, user: unknown): Promise<AiResult> {
  const baseUrl = configuredBaseUrl();
  const apiKey = Deno.env.get("AI_API_KEY")?.trim();
  const model = Deno.env.get("AI_MODEL")?.trim();
  if (!apiKey) throw new Error("AI_API_KEY must be configured as an Edge Function secret");
  if (!model) throw new Error("AI_MODEL must be configured as an Edge Function secret");
  if (apiKey.length < 20) throw new Error("AI_API_KEY is implausibly short");

  const timeoutMs = boundedInteger("AI_TIMEOUT_MS", 30_000, 1_000, 55_000);
  const maxTokens = boundedInteger("AI_MAX_OUTPUT_TOKENS", 4_000, 128, 16_000);
  const responseFormat = configuredChoice("AI_RESPONSE_FORMAT", "json_object", [
    "json_object",
    "none",
  ]);
  const reasoningEffort = configuredChoice("AI_REASONING_EFFORT", "none", [
    "none",
    "low",
    "medium",
    "high",
    "xhigh",
  ]);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  const body: Record<string, unknown> = {
    model,
    max_completion_tokens: maxTokens,
    ...(reasoningEffort !== "none" || model.startsWith("gpt-5")
      ? { reasoning_effort: reasoningEffort }
      : {}),
    messages: [
      { role: "system", content: system },
      { role: "user", content: JSON.stringify(user) },
    ],
  };
  if (responseFormat !== "none") body.response_format = { type: "json_object" };

  const startedAt = Date.now();
  let response: Response;
  try {
    response = await fetch(`${baseUrl}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new HttpError("The AI provider timed out.", 504, "ai_timeout");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    const detail = await response.text();
    console.error(`AI provider error ${response.status}: ${detail.slice(0, 800)}`);
    if (response.status === 429) {
      throw new HttpError("The AI provider is rate limited. Try again shortly.", 503, "ai_busy");
    }
    throw new HttpError("The AI provider rejected the request.", 502, "ai_provider_error");
  }

  let hostname = "openai-compatible";
  try {
    hostname = new URL(baseUrl).hostname;
  } catch {
    // Keep the neutral provider label.
  }

  const payload = (await response.json()) as {
    choices?: Array<{ message?: { content?: string | Array<{ text?: string }> } }>;
    usage?: { prompt_tokens?: number; completion_tokens?: number };
  };

  return {
    data: extractJson(extractContent(payload)),
    provider: hostname,
    model,
    latencyMs: Date.now() - startedAt,
    usage: {
      inputTokens: Number.isFinite(payload.usage?.prompt_tokens)
        ? Number(payload.usage?.prompt_tokens)
        : null,
      outputTokens: Number.isFinite(payload.usage?.completion_tokens)
        ? Number(payload.usage?.completion_tokens)
        : null,
    },
  };
}
