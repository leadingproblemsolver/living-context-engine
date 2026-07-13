export class HttpError extends Error {
  constructor(
    message: string,
    public readonly status = 400,
    public readonly code = "bad_request",
  ) {
    super(message);
  }
}

export function requestId(req: Request) {
  return req.headers.get("x-request-id")?.slice(0, 100) || crypto.randomUUID();
}

export function jsonResponse(body: unknown, status: number, headers: Record<string, string>) {
  return Response.json(body, {
    status,
    headers: { ...headers, "Cache-Control": "no-store" },
  });
}

export function errorResponse(error: unknown, headers: Record<string, string>, id: string) {
  const known = error instanceof HttpError;
  const status = known ? error.status : 500;
  const code = known ? error.code : "internal_error";
  const message = known ? error.message : "The request could not be completed.";

  if (!known || status >= 500) console.error(`[${id}]`, error);

  return jsonResponse({ error: { code, message, requestId: id } }, status, headers);
}

export async function readJson(req: Request, maxBytes = 160_000): Promise<unknown> {
  const declared = Number(req.headers.get("content-length") ?? 0);
  if (declared > maxBytes) throw new HttpError("Request body is too large.", 413, "body_too_large");

  const text = await req.text();
  if (new TextEncoder().encode(text).byteLength > maxBytes) {
    throw new HttpError("Request body is too large.", 413, "body_too_large");
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new HttpError("Request body must be valid JSON.", 400, "invalid_json");
  }
}

export function requirePost(req: Request) {
  if (req.method !== "POST") throw new HttpError("Method not allowed.", 405, "method_not_allowed");
}
