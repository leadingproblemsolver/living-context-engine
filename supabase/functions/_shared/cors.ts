import { HttpError } from "./http.ts";

function configuredOrigins() {
  return new Set(
    (Deno.env.get("ALLOWED_ORIGINS") ?? "http://localhost:3000,http://localhost:5173")
      .split(",")
      .map((value) => value.trim().replace(/\/$/, ""))
      .filter(Boolean),
  );
}

export function corsHeadersFor(req: Request) {
  const origin = req.headers.get("origin")?.replace(/\/$/, "") ?? "";
  const allowed = configuredOrigins();

  if (origin && !allowed.has(origin)) {
    throw new HttpError("Origin is not allowed.", 403, "origin_not_allowed");
  }

  return {
    "Access-Control-Allow-Origin": origin || [...allowed][0] || "http://localhost:3000",
    "Access-Control-Allow-Headers":
      "authorization, x-client-info, apikey, content-type, x-request-id",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}
