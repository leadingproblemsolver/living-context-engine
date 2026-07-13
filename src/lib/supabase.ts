import { createClient } from "@supabase/supabase-js";

function clean(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

const supabaseUrl = clean(import.meta.env.VITE_SUPABASE_URL);
const supabaseKey = clean(import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY);
const placeholder = /YOUR_|REPLACE_WITH|example\.com/i;

function validateConfiguration() {
  if (!supabaseUrl && !supabaseKey) return "Supabase is not configured.";
  if (!supabaseUrl || !supabaseKey) return "Both Supabase frontend variables are required.";
  if (placeholder.test(supabaseUrl) || placeholder.test(supabaseKey)) {
    return "Replace the placeholder Supabase values in .env.local.";
  }
  try {
    const url = new URL(supabaseUrl);
    if (url.protocol !== "https:" && url.hostname !== "localhost") {
      return "VITE_SUPABASE_URL must use HTTPS outside local development.";
    }
  } catch {
    return "VITE_SUPABASE_URL is not a valid URL.";
  }
  if (!(supabaseKey.startsWith("sb_publishable_") || supabaseKey.split(".").length === 3)) {
    return "VITE_SUPABASE_PUBLISHABLE_KEY is not a publishable key or legacy anon JWT.";
  }
  return null;
}

export const supabaseConfigIssue = validateConfiguration();
export const isSupabaseConfigured = supabaseConfigIssue === null;

export const supabase = isSupabaseConfigured
  ? createClient(supabaseUrl, supabaseKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
      global: { headers: { "X-Client-Info": "driftguard-web/1.0" } },
    })
  : null;
