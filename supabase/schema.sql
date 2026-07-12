-- TraceCrumb auth-free validation schema.
-- Additive by design: it does not drop or rewrite legacy authenticated workspace tables.
-- The active product path uses only the validation_* tables through the service-role Edge Function.

create extension if not exists pgcrypto;

create table if not exists public.validation_sessions (
  id uuid primary key default gen_random_uuid(),
  access_token_hash text not null unique,
  email text not null,
  email_hash text not null unique,
  source_channel text not null default 'direct',
  run_count integer not null default 0 check (run_count >= 0),
  max_runs integer not null default 10 check (max_runs between 1 and 100),
  status text not null default 'active' check (status in ('active','blocked','closed')),
  last_seen_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table if not exists public.validation_incidents (
  id uuid primary key default gen_random_uuid(),
  validation_session_id uuid not null references public.validation_sessions(id) on delete cascade,
  title text not null,
  service_name text not null,
  severity text not null check (severity in ('low','medium','high','critical')),
  symptom_text text not null,
  impact text not null,
  consequence_type text not null check (consequence_type in ('deployment','customer','rework','revenue','security','delay','other')),
  decision_deadline timestamptz,
  fingerprint jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.validation_decisions (
  id uuid primary key default gen_random_uuid(),
  validation_session_id uuid not null references public.validation_sessions(id) on delete cascade,
  incident_id uuid not null references public.validation_incidents(id) on delete cascade,
  source_channel text not null default 'direct',
  source_type text not null,
  source_name text,
  selected_branch text not null,
  supporting_evidence jsonb not null default '[]'::jsonb,
  counterevidence jsonb not null default '[]'::jsonb,
  reasoning_summary text not null,
  alternative_branches jsonb not null default '[]'::jsonb,
  unknowns jsonb not null default '[]'::jsonb,
  confidence integer not null check (confidence between 0 and 100),
  abort_conditions jsonb not null default '[]'::jsonb,
  first_action text not null,
  committed_at timestamptz not null default now(),
  commit_hash text not null unique
);

create table if not exists public.validation_reviews (
  id uuid primary key default gen_random_uuid(),
  validation_session_id uuid not null references public.validation_sessions(id) on delete cascade,
  incident_id uuid not null references public.validation_incidents(id) on delete cascade,
  decision_event_id uuid not null unique references public.validation_decisions(id) on delete cascade,
  provider text not null,
  fallback boolean not null default false,
  verdict text not null check (verdict in ('proceed','revise','escalate')),
  review jsonb not null,
  prior_decision_ids jsonb not null default '[]'::jsonb,
  latency_ms integer not null default 0 check (latency_ms >= 0),
  generated_at timestamptz not null default now()
);

create table if not exists public.validation_actions (
  id uuid primary key default gen_random_uuid(),
  validation_session_id uuid not null references public.validation_sessions(id) on delete cascade,
  decision_event_id uuid not null unique references public.validation_decisions(id) on delete cascade,
  decision_review_id uuid not null references public.validation_reviews(id) on delete cascade,
  action text not null check (action in ('proceed','revise','escalate','stop')),
  final_branch text not null,
  reason text not null,
  owner text,
  due_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.validation_outcomes (
  id uuid primary key default gen_random_uuid(),
  validation_session_id uuid not null references public.validation_sessions(id) on delete cascade,
  decision_event_id uuid not null unique references public.validation_decisions(id) on delete cascade,
  post_review_action_id uuid not null references public.validation_actions(id) on delete cascade,
  followed boolean not null,
  outcome text not null check (outcome in ('confirmed','falsified','abandoned','unknown')),
  tracecrumb_effect text not null check (tracecrumb_effect in ('changed_decision','changed_test','changed_timing','changed_participants','strengthened_decision','no_effect')),
  minutes_to_falsification integer check (minutes_to_falsification is null or minutes_to_falsification >= 0),
  actual_root_cause text,
  successful_resolution text,
  notes text,
  created_at timestamptz not null default now()
);

create table if not exists public.validation_feedback (
  id uuid primary key default gen_random_uuid(),
  validation_session_id uuid not null references public.validation_sessions(id) on delete cascade,
  decision_event_id uuid not null unique references public.validation_decisions(id) on delete cascade,
  decision_review_id uuid not null references public.validation_reviews(id) on delete cascade,
  novelty text not null check (novelty in ('novel','clarifying','already_known','irrelevant')),
  alternative_credibility text not null check (alternative_credibility in ('credible','possible','not_credible')),
  check_feasibility text not null check (check_feasibility in ('executable_now','executable_later','not_executable')),
  specificity text not null check (specificity in ('case_specific','partly_generic','generic')),
  comment text,
  created_at timestamptz not null default now()
);

create table if not exists public.validation_ai_requests (
  id uuid primary key default gen_random_uuid(),
  validation_session_id uuid references public.validation_sessions(id) on delete set null,
  decision_event_id uuid references public.validation_decisions(id) on delete set null,
  action text not null,
  provider text,
  status text not null check (status in ('started','completed','fallback','failed','rate_limited','reused')),
  latency_ms integer,
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.validation_events (
  id bigint generated always as identity primary key,
  validation_session_id uuid references public.validation_sessions(id) on delete set null,
  source_channel text not null default 'direct',
  event_type text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_validation_decisions_session_committed on public.validation_decisions(validation_session_id, committed_at desc);
create index if not exists idx_validation_requests_session_created on public.validation_ai_requests(validation_session_id, created_at desc);
create index if not exists idx_validation_requests_created on public.validation_ai_requests(created_at desc);
create index if not exists idx_validation_events_type_created on public.validation_events(event_type, created_at desc);

create or replace function public.reserve_validation_run(p_validation_session_id uuid)
returns table(run_count integer, max_runs integer)
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  update public.validation_sessions
     set run_count = validation_sessions.run_count + 1,
         last_seen_at = now()
   where id = p_validation_session_id
     and status = 'active'
     and validation_sessions.run_count < validation_sessions.max_runs
  returning validation_sessions.run_count, validation_sessions.max_runs;

  if not found then
    raise exception 'RUN_LIMIT_REACHED';
  end if;
end;
$$;

create or replace function public.release_validation_run(p_validation_session_id uuid)
returns void
language sql
security definer
set search_path = public
as $$
  update public.validation_sessions
     set run_count = greatest(0, run_count - 1),
         last_seen_at = now()
   where id = p_validation_session_id;
$$;

-- The browser never receives direct table privileges. Only the Edge Function service role reads/writes.
alter table public.validation_sessions enable row level security;
alter table public.validation_incidents enable row level security;
alter table public.validation_decisions enable row level security;
alter table public.validation_reviews enable row level security;
alter table public.validation_actions enable row level security;
alter table public.validation_outcomes enable row level security;
alter table public.validation_feedback enable row level security;
alter table public.validation_ai_requests enable row level security;
alter table public.validation_events enable row level security;

revoke all on public.validation_sessions from public, anon, authenticated;
revoke all on public.validation_incidents from public, anon, authenticated;
revoke all on public.validation_decisions from public, anon, authenticated;
revoke all on public.validation_reviews from public, anon, authenticated;
revoke all on public.validation_actions from public, anon, authenticated;
revoke all on public.validation_outcomes from public, anon, authenticated;
revoke all on public.validation_feedback from public, anon, authenticated;
revoke all on public.validation_ai_requests from public, anon, authenticated;
revoke all on public.validation_events from public, anon, authenticated;
revoke all on function public.reserve_validation_run(uuid) from public, anon, authenticated;
revoke all on function public.release_validation_run(uuid) from public, anon, authenticated;
grant execute on function public.reserve_validation_run(uuid) to service_role;
grant execute on function public.release_validation_run(uuid) to service_role;
