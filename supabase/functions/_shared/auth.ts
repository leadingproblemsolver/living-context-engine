import { createClient, type SupabaseClient, type User } from "npm:@supabase/supabase-js@2.110.0";
import { HttpError } from "./http.ts";

function namedKeyMap(name: string): string | null {
  const raw = Deno.env.get(name);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Record<string, string>;
    return parsed.default || Object.values(parsed).find(Boolean) || null;
  } catch {
    throw new Error(`${name} is not valid JSON`);
  }
}

function publicKey() {
  return namedKeyMap("SUPABASE_PUBLISHABLE_KEYS") ?? Deno.env.get("SUPABASE_ANON_KEY") ?? "";
}

function secretKey() {
  return namedKeyMap("SUPABASE_SECRET_KEYS") ?? Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
}

function projectUrl() {
  const value = Deno.env.get("SUPABASE_URL");
  if (!value) throw new Error("SUPABASE_URL is unavailable in the Edge Function environment");
  return value;
}

export type AuthContext = {
  user: User;
  client: SupabaseClient;
  token: string;
};

export async function requireUser(req: Request): Promise<AuthContext> {
  const authorization = req.headers.get("Authorization") ?? "";
  const match = authorization.match(/^Bearer\s+(.+)$/i);
  if (!match) throw new HttpError("Authentication required.", 401, "authentication_required");

  const key = publicKey();
  if (!key) throw new Error("No Supabase publishable or legacy anon key is available");

  const token = match[1];
  const client = createClient(projectUrl(), key, {
    global: { headers: { Authorization: `Bearer ${token}` } },
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
  });

  // This network-verifies the bearer token against this project's Auth service.
  const { data, error } = await client.auth.getUser(token);
  if (error || !data.user) {
    throw new HttpError("Authentication required.", 401, "authentication_required");
  }

  return { user: data.user, client, token };
}

export function adminClient() {
  const key = secretKey();
  if (!key) throw new Error("No Supabase secret or legacy service-role key is available");
  return createClient(projectUrl(), key, {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
  });
}

export async function consumeAiQuota(client: SupabaseClient) {
  const { error } = await client.rpc("consume_ai_request");
  if (!error) return;
  if (/rate limit/i.test(error.message)) {
    throw new HttpError("AI request limit reached. Try again later.", 429, "rate_limited");
  }
  throw new Error(`Could not enforce AI request quota: ${error.message}`);
}
