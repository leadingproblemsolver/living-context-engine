import { defineNitroConfig } from "nitro/config";

// Pin the Workers runtime contract instead of inheriting the build date.
// Update deliberately only after the pinned Wrangler/workerd version supports it.
export default defineNitroConfig({
  compatibilityDate: "2026-07-08",
});
