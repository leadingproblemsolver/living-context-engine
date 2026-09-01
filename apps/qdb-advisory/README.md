# QDB Advisory v0

Code-first founder advisory execution loop derived from the Sophie/QDB case.

## Product boundary

This is not a mentor AI, CRM, autonomous advisor, or portfolio-intelligence product.

Closed loop:

`interaction -> evidence -> state change -> decision -> commitment/experiment -> follow-up -> outcome -> next-session brief`

AI proposes semantic structure. Code controls state. Evidence controls truth.

## v0 stack

- Next.js + TypeScript UI/API
- Vercel Workflows for durable orchestration, retries, sleeps, and human/event waits
- Supabase/Postgres as the only durable product source of truth
- Structured LLM extraction behind a strict schema
- Git branches/PRs + preview deployments

No vector DB. No RAG. No autonomous tool calling. No portfolio clustering in v0.

## v0 screens

1. Founder dashboard: current state, commitments, experiments, blockers, trajectory.
2. Session record: source interaction, evidence, decisions, commitments, experiments.
3. Advisor brief: what changed, what did not happen, unresolved commitments, state changes, and 3-5 questions requiring advisor judgment.

Portfolio intelligence is explicitly deferred until repeated real use.

## Runtime flows

### Interaction processing

`POST /api/interactions -> persist immutable interaction -> start processInteraction(interactionId)`

Workflow steps:

1. Load immutable interaction.
2. Extract bounded structured objects.
3. Reject unsupported/low-confidence objects.
4. Persist accepted observations/assumptions/decisions/commitments/experiments transactionally.
5. Rebuild/propose founder state from accepted evidence.
6. Persist a new state version.
7. Start a commitment lifecycle workflow for each new commitment with a due date.

### Commitment lifecycle

`commitment created -> durable wait -> reminder if still open -> due-date check -> founder response -> outcome evidence -> interaction workflow again`

Completion is never inferred. An open commitment whose due date has passed is displayed as overdue; its canonical status remains open until explicit evidence changes it.

### Next-session brief

v0 generates the brief on demand from immutable history + current state. Calendar-triggered generation is added only after real workflow access is earned.

## Non-negotiable invariants

- Raw interactions are immutable.
- Every extracted observation links to an interaction and a supporting source excerpt.
- The LLM cannot directly update canonical state.
- Recommendations do not become commitments without explicit acceptance.
- Missing deadlines remain null.
- Completion is never inferred.
- Founder state is disposable and reconstructable from event history.
- Duplicate interaction ingestion is idempotent.
- Cross-founder writes are impossible by construction.

## Demo dataset

Exactly one fictional founder and three sessions. The third session must prove the chain from prior commitment -> actual execution -> evidence -> state transition -> advisor brief.

## Done when

A raw session passes end-to-end with no manual database edits:

1. Interaction persisted.
2. Evidence extracted.
3. Decisions captured.
4. Explicit commitments created.
5. Previous state retrieved.
6. Evidence-supported state transition proposed.
7. Current state version updated.
8. Due commitments are visible.
9. Founder update reconciles against the prior commitment.
10. Outcome becomes new evidence.
11. State updates again.
12. Next-session brief reflects the whole chain.

Quality floor before external use:

- commitments >95% precision
- decisions >90% precision
- metrics >95% precision
- observations >90% precision
- hallucinated critical objects = 0
