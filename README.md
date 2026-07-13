# Living Context Engine (LCE)

A local-first, single-user Python CLI that turns a filesystem corpus (docs, chats, logs,
decisions, test output) into synchronized, ranked, source-linked context -- and preserves
accepted outcomes as durable, retrievable future memory.

No database server, no required API keys, no network calls for the base workflow. See
`STATUS.md` for exactly what's proven, by what tests, and what's explicitly not attempted yet.

## Canonical loop

```
init -> doctor -> sync -> query/brief/compile -> act -> log accepted/rejected -> resync -> recover later
```

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Base install has zero third-party dependencies. Optional parser/LLM/automation backends
live in `requirements-optional.txt` and are never required for the core loop.

## Quickstart

```bash
lce init
lce sync .
lce query --text "blocker" --top-k 5
lce compile --topic "blockers" --intent blockers --format markdown
lce log --content "Adopt the fix permanently." --outcome-type decision
lce accept <record_id>      # or: lce reject <record_id>
lce sync .                  # resynchronize -- accepted outcomes reappear in future queries
```

## Commands

| Command | Purpose |
|---|---|
| `lce init` | create local state (`.lce/`), database, schema |
| `lce doctor` | honest readiness view: corpus/db/freshness/last-run/pending-records |
| `lce sync [path]` | discover, parse, chunk, extract signals, persist; scoped missing-detection |
| `lce query --text T [--intent I] [--top-k N]` | canonical retrieval hits as JSON |
| `lce brief [--text T] [--intent I]` | bounded context packet (decisions/blockers/next actions/assumptions/questions/evidence/uncertainties) |
| `lce compile --topic T [--type TYPE] [--intent I] [--format json\|markdown] [--out FILE]` | strict, source-linked compiled artifact |
| `lce log --content C --outcome-type T [--source-artifact A]` | create a `pending` continuity record |
| `lce accept RECORD_ID` / `lce reject RECORD_ID` | the only valid transitions out of `pending` |
| `lce status` | document/signal counts, recent runs, pending records |
| `lce export [--format json\|markdown] [--out FILE]` | raw state dump for backup/debugging |

Exit codes: `0` success, `1` unexpected error, `2` user error (e.g. missing database),
`3` corrupt database, `6` invalid continuity-record state transition. Nothing is ever
silently swallowed.

## How continuity works

`lce log` records a proposed outcome as `pending` -- it has no effect on retrieval yet.
`lce accept` is the only thing that writes a real file back into the corpus (under
`.lce/continuity/`, tagged with lineage and record id); `lce sync` always includes that
folder, so an accepted decision becomes ordinary, source-linked evidence in future queries,
tagged `origin=continuity (previously accepted)`. `lce reject` never writes anything back --
a rejected suggestion can never resurface as if it were current direction. Neither `sync`
nor `compile` can invoke `log`/`accept`/`reject` themselves; only a human-issued CLI command
can authorize durable memory.

## Development

```bash
pip install -e . pytest
python -m pytest -q
```

The test suite runs entirely against an isolated `tmp_path` corpus (`tests/fixtures/golden_corpus/`)
and never touches real user data.

## Explicitly out of scope (this version)

Frontend/UI, daemon/watch mode, semantic or vector retrieval, knowledge graph, multi-user
cloud sync, autonomous agent execution, heavy multimodal ingestion. See `STATUS.md` for the
full list and rationale.
