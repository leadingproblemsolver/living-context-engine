# Architecture

Five primitives, one loop.

```
ingestion  →  extraction  →  state graph  →  delta engine  →  action router
   files        packets        SQLite         transitions      ranked tasks
   packets                     evidence       contradictions
   models                      confidence
```

## 1. Ingestion (`extract.py`, `observe.py`)

Resolves a path into `(file, source reference)` pairs, rejects symlinks, bounds
size and count. Every file produces two things:

- **Observation records** — one per line, deterministically classified, stored
  with project, relative path, line number, content hash, and timestamp. This is
  the searchable substrate; it never becomes belief.
- **An observation packet** — the structured statements the file actually makes,
  parsed from the line syntax, read from JSON, or produced by a model.

## 2. Extraction

`observe.packet_from_text` is a deterministic line parser. `llm.extract_packet`
is an optional model call using the same prompt that `lce prompt extract`
prints. Both emit the schema in `observe.OBSERVATION_SCHEMA`, and both are
validated before anything is written: a claim without evidence is rejected at
the boundary.

## 3. State graph (`store.py`, `models.py`)

SQLite, one file, ten state tables alongside the observation layer:

| Table | Holds |
| --- | --- |
| `observations` | Source provenance and content hash |
| `entities` | The things claims are about |
| `claims` | `(entity, attribute, value)` with confidence, status, importance |
| `evidence` | Verbatim support, one row per independent observation |
| `transitions` | Every state change, with the reason it happened |
| `contradictions` | Conflicting active claims, open or resolved |
| `unknowns` | Open questions with impact and blocked decision |
| `relationships` | Typed edges between entities |
| `actions` | Ranked verification tasks and their status |
| `metrics` | Uncertainty snapshots over time |

Identity is deterministic: an entity is `(project, kind, normalised name)`, a
claim is `(project, entity, attribute, normalised value)`, and a piece of
evidence is `(claim, source, locator, excerpt, actor)`. That last one is why
re-ingesting an unchanged file cannot inflate confidence.

Confidence is never stored independently of its evidence — it is recomputed from
the evidence rows on every change, and `lce validate` re-derives all of it to
prove the two have not drifted apart.

## 4. Delta engine (`delta.py`)

The core. For each incoming claim:

1. Insert evidence idempotently. If nothing new arrived and the claim already
   existed, stop — no transition, because nothing changed.
2. Recompute confidence from all evidence on the claim.
3. Compare against the other active claims in the same `(entity, attribute)`
   slot:
   - no competitor → `established`
   - same value → `reinforced` (or `weakened`)
   - different value → always record a contradiction, then either `revised`
     (the new effective confidence exceeds the incumbent's by the supersession
     margin, and the old claim is marked superseded) or `contested` (both stay
     active, the conflict stays open)
4. Write the transition with a rationale naming the evidence and the numbers
   behind the move.

Multi-valued attributes (`name[]`) skip conflict detection entirely.

## 5. Action router (`actions.py`)

Compiles uncertainty into work. Three sources:

- open unknowns
- open contradictions
- active claims that are important but weakly held or ageing

Each gets a method — interview, experiment, desk research, instrumentation, ask
an expert, reconcile — chosen from the shape of the question. Behavioural
questions escalate to experiments because interviews cannot settle them, and
decision entities are excluded, since a decision is an act rather than a belief
awaiting verification.

Expected confidence gain is computed by running the *same* confidence function
over the evidence the method would produce, so a proposal's projected value and
the engine's real arithmetic can never disagree. Priority is

```
impact × uncertainty × expected_gain × linkage ÷ √effort_days
```

## Context assembly (`context.py`)

`build_context` scores every entity and claim against the task's terms, always
including decisions, constraints, and risks, and returns the matched state plus
the transitions, contradictions, unknowns, and actions in scope, with
deduplicated citations. Two questions against the same graph produce two
different packs.

## The metric (`store.uncertainty`)

```
uncertainty = Σ impact(open unknowns)
            + Σ importance × (1 − effective confidence) over active claims
            + Σ severity(open contradictions)
```

Snapshotted on every mutation. `lce metric` reports the current load and the
rate at which it is falling, which is the only number the engine exists to move.

## Layering and compatibility

The v1 observation layer (records, query, timeline, packs, export) is unchanged
and still works on its own. The state layer sits on top of it in the same
database; `lce ingest` drives both. Existing databases migrate forward on open —
the state tables are created empty and fill as sources are re-ingested.
