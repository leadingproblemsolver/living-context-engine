import type { SupabaseClient } from "npm:@supabase/supabase-js@2.110.0";

export type OperationalEvent = {
  eventType: string;
  actorType: "user" | "system" | "model" | "tool" | "human_operator";
  userId: string;
  setId?: string | null;
  evaluationId?: string | null;
  requestId?: string | null;
  stageId?: string | null;
  status?: "started" | "completed" | "failed";
  latencyMs?: number | null;
  modelProvider?: string | null;
  modelName?: string | null;
  metadata?: Record<string, unknown>;
};

export async function recordOperationalEvents(client: SupabaseClient, events: OperationalEvent[]) {
  if (!events.length) return;

  const { error } = await client.from("operational_events").insert(
    events.map((event) => ({
      event_type: event.eventType,
      actor_type: event.actorType,
      user_id: event.userId,
      set_id: event.setId ?? null,
      evaluation_id: event.evaluationId ?? null,
      request_id: event.requestId ?? null,
      stage_id: event.stageId ?? null,
      status: event.status ?? "completed",
      latency_ms: event.latencyMs ?? null,
      model_provider: event.modelProvider ?? null,
      model_name: event.modelName ?? null,
      metadata: event.metadata ?? {},
    })),
  );

  // Telemetry must never turn a valid user result into a failed result.
  if (error) console.error(`Operational event persistence failed: ${error.message}`);
}
