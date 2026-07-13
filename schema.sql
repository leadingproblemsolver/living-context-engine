-- DriftGuard unified Supabase schema
-- Safe to run repeatedly in the SQL editor or through `supabase db push`.
-- Owns auth profiles, user guardrail sets, server-authored evaluations, RLS,
-- transactional saves, and per-user AI request quotas.

begin;

create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.guardrail_sets (
  id text primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 120),
  purpose text not null check (char_length(purpose) between 1 and 4000),
  workflow text not null default '' check (char_length(workflow) <= 4000),
  target text not null default '' check (char_length(target) <= 2000),
  success_definition text not null default '' check (char_length(success_definition) <= 4000),
  input_mode text not null default 'prompt'
    check (input_mode in ('prompt', 'checklist', 'metric', 'api')),
  evaluation_cadence text not null default 'manual'
    check (evaluation_cadence in ('manual', 'before-action', 'after-output', 'daily')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.guardrails (
  id text primary key,
  set_id text not null references public.guardrail_sets(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null check (char_length(title) between 1 and 240),
  description text not null default '' check (char_length(description) <= 2000),
  criticality text not null default 'important'
    check (criticality in ('critical', 'important', 'preference')),
  enforcement text not null default 'warn'
    check (enforcement in ('block', 'warn', 'advise')),
  target_scope text not null default 'output'
    check (target_scope in ('action', 'output', 'workflow', 'session')),
  metric_type text not null default 'evidence'
    check (metric_type in ('binary', 'threshold', 'checklist', 'evidence')),
  metric_config jsonb not null default '{}'::jsonb,
  active boolean not null default true,
  source text not null default 'user'
    check (source in ('user', 'ai', 'template')),
  version integer not null default 1 check (version > 0),
  position integer not null default 0 check (position >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.evaluations (
  id uuid primary key default gen_random_uuid(),
  set_id text not null references public.guardrail_sets(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  input_text text not null check (char_length(input_text) between 1 and 100000),
  evidence text not null default '' check (char_length(evidence) <= 50000),
  verdict text not null check (verdict in ('pass', 'watch', 'block')),
  score integer not null check (score between 0 and 100),
  summary text not null check (char_length(summary) <= 2000),
  reasoning text not null check (char_length(reasoning) <= 5000),
  correction text not null check (char_length(correction) <= 2000),
  findings jsonb not null default '[]'::jsonb,
  evaluation_mode text not null default 'ai',
  model_provider text,
  model_name text,
  constraint_snapshot jsonb not null,
  created_at timestamptz not null default now()
);

-- Minimal operational intelligence plane. Events contain identifiers, state summaries,
-- latency, and model metadata only; raw work/evidence remains in the evaluation audit.
create table if not exists public.operational_events (
  id uuid primary key default gen_random_uuid(),
  event_type text not null check (char_length(event_type) between 1 and 80),
  occurred_at timestamptz not null default now(),
  actor_type text not null
    check (actor_type in ('user', 'system', 'model', 'tool', 'human_operator')),
  user_id uuid not null references auth.users(id) on delete cascade,
  set_id text references public.guardrail_sets(id) on delete cascade,
  evaluation_id uuid references public.evaluations(id) on delete set null,
  request_id text check (request_id is null or char_length(request_id) <= 100),
  stage_id text check (stage_id is null or char_length(stage_id) <= 80),
  status text not null default 'completed'
    check (status in ('started', 'completed', 'failed')),
  latency_ms integer check (latency_ms is null or latency_ms >= 0),
  model_provider text check (model_provider is null or char_length(model_provider) <= 200),
  model_name text check (model_name is null or char_length(model_name) <= 200),
  metadata jsonb not null default '{}'::jsonb
    check (jsonb_typeof(metadata) = 'object')
);

-- Upgrade an earlier schema whose mode constraint did not include server-only rules evaluation.
alter table public.evaluations
  drop constraint if exists evaluations_evaluation_mode_check;
alter table public.evaluations
  add constraint evaluations_evaluation_mode_check
  check (evaluation_mode in ('ai', 'rules', 'rules-preview'));

-- Internal quota state. No browser role receives table privileges or RLS policies.
create table if not exists public.ai_request_usage (
  user_id uuid not null references auth.users(id) on delete cascade,
  window_kind text not null check (window_kind in ('minute', 'day')),
  window_start timestamptz not null,
  request_count integer not null default 0 check (request_count >= 0),
  updated_at timestamptz not null default now(),
  primary key (user_id, window_kind, window_start)
);

create index if not exists guardrail_sets_user_updated_idx
  on public.guardrail_sets(user_id, updated_at desc);
create index if not exists guardrails_set_position_idx
  on public.guardrails(set_id, position);
create index if not exists guardrails_user_idx
  on public.guardrails(user_id);
create index if not exists evaluations_set_created_idx
  on public.evaluations(set_id, created_at desc);
create index if not exists evaluations_user_created_idx
  on public.evaluations(user_id, created_at desc);
create index if not exists ai_request_usage_updated_idx
  on public.ai_request_usage(updated_at);
create index if not exists operational_events_user_occurred_idx
  on public.operational_events(user_id, occurred_at desc);
create index if not exists operational_events_set_occurred_idx
  on public.operational_events(set_id, occurred_at desc)
  where set_id is not null;
create index if not exists operational_events_request_idx
  on public.operational_events(request_id)
  where request_id is not null;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at
before update on public.profiles
for each row execute function public.set_updated_at();

drop trigger if exists guardrail_sets_set_updated_at on public.guardrail_sets;
create trigger guardrail_sets_set_updated_at
before update on public.guardrail_sets
for each row execute function public.set_updated_at();

drop trigger if exists guardrails_set_updated_at on public.guardrails;
create trigger guardrails_set_updated_at
before update on public.guardrails
for each row execute function public.set_updated_at();

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, email, display_name)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data ->> 'display_name', split_part(coalesce(new.email, ''), '@', 1))
  )
  on conflict (id) do update set email = excluded.email;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert or update of email on auth.users
for each row execute function public.handle_new_user();

alter table public.profiles enable row level security;
alter table public.guardrail_sets enable row level security;
alter table public.guardrails enable row level security;
alter table public.evaluations enable row level security;
alter table public.operational_events enable row level security;
alter table public.ai_request_usage enable row level security;

-- Profiles
drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own
on public.profiles for select to authenticated
using ((select auth.uid()) = id);

drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own
on public.profiles for update to authenticated
using ((select auth.uid()) = id)
with check ((select auth.uid()) = id);

-- Guardrail sets
drop policy if exists guardrail_sets_select_own on public.guardrail_sets;
create policy guardrail_sets_select_own
on public.guardrail_sets for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists guardrail_sets_insert_own on public.guardrail_sets;
create policy guardrail_sets_insert_own
on public.guardrail_sets for insert to authenticated
with check ((select auth.uid()) = user_id);

drop policy if exists guardrail_sets_update_own on public.guardrail_sets;
create policy guardrail_sets_update_own
on public.guardrail_sets for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists guardrail_sets_delete_own on public.guardrail_sets;
create policy guardrail_sets_delete_own
on public.guardrail_sets for delete to authenticated
using ((select auth.uid()) = user_id);

-- Guardrails
drop policy if exists guardrails_select_own on public.guardrails;
create policy guardrails_select_own
on public.guardrails for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists guardrails_insert_own on public.guardrails;
create policy guardrails_insert_own
on public.guardrails for insert to authenticated
with check (
  (select auth.uid()) = user_id
  and exists (
    select 1 from public.guardrail_sets s
    where s.id = set_id and s.user_id = (select auth.uid())
  )
);

drop policy if exists guardrails_update_own on public.guardrails;
create policy guardrails_update_own
on public.guardrails for update to authenticated
using ((select auth.uid()) = user_id)
with check (
  (select auth.uid()) = user_id
  and exists (
    select 1 from public.guardrail_sets s
    where s.id = set_id and s.user_id = (select auth.uid())
  )
);

drop policy if exists guardrails_delete_own on public.guardrails;
create policy guardrails_delete_own
on public.guardrails for delete to authenticated
using ((select auth.uid()) = user_id);

-- Evaluations are server-authored and immutable to browser roles. Users can read their own history.
drop policy if exists evaluations_select_own on public.evaluations;
create policy evaluations_select_own
on public.evaluations for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists evaluations_insert_own on public.evaluations;

drop policy if exists evaluations_delete_own on public.evaluations;

-- Operational events are server-authored and immutable to browser roles.
drop policy if exists operational_events_select_own on public.operational_events;
create policy operational_events_select_own
on public.operational_events for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists operational_events_insert_own on public.operational_events;
drop policy if exists operational_events_update_own on public.operational_events;
drop policy if exists operational_events_delete_own on public.operational_events;

-- Transactional source-of-truth save: one RPC writes a set and its complete ordered rule list.
create or replace function public.save_guardrail_set(payload jsonb)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  actor uuid := auth.uid();
  set_key text := nullif(trim(payload ->> 'id'), '');
  guardrail_list jsonb := coalesce(payload -> 'guardrails', '[]'::jsonb);
  item jsonb;
begin
  if actor is null then
    raise exception 'Authentication required';
  end if;
  if jsonb_typeof(coalesce(payload, '{}'::jsonb)) <> 'object' then
    raise exception 'Payload must be a JSON object';
  end if;
  if jsonb_typeof(guardrail_list) <> 'array' then
    raise exception 'Guardrails must be a JSON array';
  end if;
  if jsonb_array_length(guardrail_list) > 50 then
    raise exception 'A guardrail set may contain at most 50 rules';
  end if;

  if set_key is null then set_key := gen_random_uuid()::text; end if;
  if char_length(set_key) > 200 then raise exception 'Guardrail set id is too long'; end if;

  insert into public.guardrail_sets (
    id, user_id, name, purpose, workflow, target, success_definition,
    input_mode, evaluation_cadence
  ) values (
    set_key,
    actor,
    coalesce(nullif(trim(payload ->> 'name'), ''), 'My guardrail set'),
    coalesce(nullif(trim(payload ->> 'purpose'), ''), 'Undefined purpose'),
    coalesce(payload ->> 'workflow', ''),
    coalesce(payload ->> 'target', ''),
    coalesce(payload ->> 'success_definition', ''),
    coalesce(payload ->> 'input_mode', 'prompt'),
    coalesce(payload ->> 'evaluation_cadence', 'manual')
  )
  on conflict (id) do update set
    name = excluded.name,
    purpose = excluded.purpose,
    workflow = excluded.workflow,
    target = excluded.target,
    success_definition = excluded.success_definition,
    input_mode = excluded.input_mode,
    evaluation_cadence = excluded.evaluation_cadence
  where public.guardrail_sets.user_id = actor;

  if not exists (
    select 1 from public.guardrail_sets where id = set_key and user_id = actor
  ) then
    raise exception 'Guardrail set is not owned by the authenticated user';
  end if;

  delete from public.guardrails where set_id = set_key and user_id = actor;

  for item in select value from jsonb_array_elements(guardrail_list)
  loop
    insert into public.guardrails (
      id, set_id, user_id, title, description, criticality, enforcement,
      target_scope, metric_type, metric_config, active, source, position
    ) values (
      coalesce(nullif(trim(item ->> 'id'), ''), gen_random_uuid()::text),
      set_key,
      actor,
      coalesce(nullif(trim(item ->> 'title'), ''), 'Untitled guardrail'),
      coalesce(item ->> 'description', ''),
      coalesce(item ->> 'criticality', 'important'),
      coalesce(item ->> 'enforcement', 'warn'),
      coalesce(item ->> 'target_scope', 'output'),
      coalesce(item ->> 'metric_type', 'evidence'),
      coalesce(item -> 'metric_config', '{}'::jsonb),
      coalesce((item ->> 'active')::boolean, true),
      coalesce(item ->> 'source', 'user'),
      coalesce((item ->> 'position')::integer, 0)
    );
  end loop;

  insert into public.operational_events (
    event_type, actor_type, user_id, set_id, stage_id, status, metadata
  ) values (
    'RULE_UPDATED',
    'user',
    actor,
    set_key,
    'guardrail-definition',
    'completed',
    jsonb_build_object(
      'guardrail_count', jsonb_array_length(guardrail_list),
      'input_mode', coalesce(payload ->> 'input_mode', 'prompt'),
      'evaluation_cadence', coalesce(payload ->> 'evaluation_cadence', 'manual')
    )
  );

  return set_key;
end;
$$;

-- Fixed, atomic quotas. The browser cannot choose or raise these limits.
create or replace function public.consume_ai_request()
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  actor uuid := auth.uid();
  minute_key timestamptz := date_trunc('minute', now());
  day_key timestamptz := date_trunc('day', now());
  minute_count integer;
  day_count integer;
begin
  if actor is null then raise exception 'Authentication required'; end if;

  perform pg_advisory_xact_lock(hashtextextended(actor::text, 0));

  insert into public.ai_request_usage (user_id, window_kind, window_start, request_count)
  values (actor, 'minute', minute_key, 1)
  on conflict (user_id, window_kind, window_start)
  do update set request_count = public.ai_request_usage.request_count + 1, updated_at = now()
  returning request_count into minute_count;

  if minute_count > 20 then raise exception 'AI minute rate limit reached'; end if;

  insert into public.ai_request_usage (user_id, window_kind, window_start, request_count)
  values (actor, 'day', day_key, 1)
  on conflict (user_id, window_kind, window_start)
  do update set request_count = public.ai_request_usage.request_count + 1, updated_at = now()
  returning request_count into day_count;

  if day_count > 200 then raise exception 'AI daily rate limit reached'; end if;

  delete from public.ai_request_usage
  where user_id = actor and window_start < now() - interval '2 days';
end;
$$;

-- Explicit Data API permissions. RLS remains the real per-row boundary.
revoke all on public.profiles, public.guardrail_sets, public.guardrails,
  public.evaluations, public.operational_events, public.ai_request_usage from anon;
revoke all on public.evaluations from authenticated;
revoke all on public.operational_events from authenticated;
revoke all on public.ai_request_usage from authenticated;

grant usage on schema public to authenticated;
grant select on public.profiles to authenticated;
grant update (display_name) on public.profiles to authenticated;
grant select, insert, update, delete on public.guardrail_sets to authenticated;
grant select, insert, update, delete on public.guardrails to authenticated;
grant select on public.evaluations to authenticated;
grant select on public.operational_events to authenticated;

revoke all on function public.save_guardrail_set(jsonb) from public;
revoke all on function public.consume_ai_request() from public;
grant execute on function public.save_guardrail_set(jsonb) to authenticated;
grant execute on function public.consume_ai_request() to authenticated;

commit;
