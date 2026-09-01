create extension if not exists pgcrypto;

create table if not exists founders (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  company_name text,
  stage text,
  advisor_id uuid,
  created_at timestamptz not null default now()
);

create table if not exists interactions (
  id uuid primary key default gen_random_uuid(),
  founder_id uuid not null references founders(id) on delete cascade,
  occurred_at timestamptz not null,
  interaction_type text not null check (interaction_type in ('advisory_session','founder_update','advisor_note','follow_up_response')),
  source_type text not null,
  raw_text text not null,
  source_url text,
  source_hash text not null,
  created_at timestamptz not null default now(),
  unique (founder_id, source_hash)
);

create table if not exists observations (
  id uuid primary key default gen_random_uuid(),
  founder_id uuid not null references founders(id) on delete cascade,
  interaction_id uuid not null references interactions(id) on delete cascade,
  category text not null,
  claim text not null,
  evidence_quote text not null,
  evidence_type text not null check (evidence_type in ('reported_fact','customer_signal','behavioral_evidence','metric','advisor_observation','founder_belief')),
  confidence numeric(4,3) not null check (confidence >= 0.6 and confidence <= 1.0),
  occurred_at timestamptz not null,
  created_at timestamptz not null default now()
);

create table if not exists assumptions (
  id uuid primary key default gen_random_uuid(),
  founder_id uuid not null references founders(id) on delete cascade,
  statement text not null,
  domain text not null,
  status text not null check (status in ('untested','testing','supported','weakened','invalidated','superseded')),
  confidence numeric(4,3) not null check (confidence >= 0 and confidence <= 1.0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists decisions (
  id uuid primary key default gen_random_uuid(),
  founder_id uuid not null references founders(id) on delete cascade,
  interaction_id uuid not null references interactions(id) on delete cascade,
  decision text not null,
  rationale text,
  created_at timestamptz not null default now()
);

create table if not exists commitments (
  id uuid primary key default gen_random_uuid(),
  founder_id uuid not null references founders(id) on delete cascade,
  interaction_id uuid not null references interactions(id) on delete cascade,
  owner text not null,
  action text not null,
  success_criterion text,
  due_at timestamptz,
  status text not null default 'open' check (status in ('open','completed','blocked','abandoned','superseded')),
  completed_at timestamptz,
  blocker text,
  created_at timestamptz not null default now(),
  check ((status = 'completed' and completed_at is not null) or status <> 'completed')
);

create table if not exists experiments (
  id uuid primary key default gen_random_uuid(),
  founder_id uuid not null references founders(id) on delete cascade,
  interaction_id uuid not null references interactions(id) on delete cascade,
  hypothesis text not null,
  method text not null,
  success_threshold text,
  deadline timestamptz,
  status text not null default 'planned' check (status in ('planned','running','completed','inconclusive','cancelled')),
  result text,
  learning text,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create table if not exists founder_state (
  founder_id uuid primary key references founders(id) on delete cascade,
  state_version integer not null default 0 check (state_version >= 0),
  primary_bottleneck text,
  current_goal text,
  current_milestone text,
  icp_state text,
  problem_state text,
  wtp_state text,
  traction_state text,
  distribution_state text,
  execution_state text,
  open_questions jsonb not null default '[]'::jsonb,
  key_risks jsonb not null default '[]'::jsonb,
  last_updated_at timestamptz not null default now()
);

create index if not exists idx_interactions_founder_time on interactions(founder_id, occurred_at desc);
create index if not exists idx_observations_founder_time on observations(founder_id, occurred_at desc);
create index if not exists idx_commitments_founder_status_due on commitments(founder_id, status, due_at);
create index if not exists idx_experiments_founder_status on experiments(founder_id, status);

-- Overdue is derived, never a canonical commitment status.
create or replace view overdue_commitments as
select *
from commitments
where status = 'open' and due_at is not null and due_at < now();
