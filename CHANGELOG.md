# Changelog

## 2.0.0 — 2026-07-31

The engine became a state-transition loop rather than a document index.

### Added

- **State layer.** Entities, claims, evidence, transitions, contradictions,
  unknowns, relationships, actions, and uncertainty snapshots, alongside the
  existing observation records in the same SQLite database.
- **Delta engine.** Every ingest compares incoming claims against current state
  and records `established` / `reinforced` / `weakened` / `revised` / `contested`
  transitions, each with the rationale and evidence behind the move.
- **Derived confidence.** Noisy-OR over evidence, damped for repeats from the
  same source, capped by method ceilings so stated intent can never reach the
  confidence of observed behaviour, and decayed by age.
- **First-class contradictions.** Conflicting values are always recorded; the
  incumbent is superseded only when new evidence clearly outweighs it.
- **Action router.** Open unknowns, conflicts, and weakly-held important claims
  compile into ranked verification tasks scored by expected uncertainty removed
  per unit of effort, with behavioural questions routed to experiments.
- **Task-scoped context packs.** `lce context "<question>"` generates a
  decision-specific pack in Markdown and JSON.
- **Uncertainty metric.** `lce metric` reports the current load and the rate at
  which it is falling.
- **Observation packets.** A documented JSON schema is the interop contract;
  `lce absorb` applies packets from any producer.
- **Prompt library.** `lce prompt extract | interview-guide | adjudicate |
  actions | decision-brief | review-delta`, each rendered against live state, so
  the whole loop works with any assistant and no API key.
- **Optional model extraction.** `pip install 'living-context-engine[llm]'` plus
  `lce ingest --llm`, using the Anthropic SDK with structured outputs.
- **Repository integration.** `lce init [--ci]` scaffolds config, a syntax
  guide, a worked example, a repo guide, and a GitHub Actions workflow;
  `lce doctor` checks readiness.
- **New read-only endpoints** for state, entities, delta, contradictions,
  unknowns, actions, metric, and context.
- `lce validate` now re-derives every claim's confidence from its evidence and
  fails on drift, unsupported claims, or orphaned claims.

### Changed

- `--project` is accepted globally and on every subcommand, and defaults to
  `.lce/config.json` or the repository directory name.
- `lce export` takes `--layer state|records`.
- Fenced code blocks are never parsed as claims, so documentation cannot teach
  the graph.
- The v1 observation layer (records, query, timeline, packs, export) is
  unchanged; existing databases migrate forward on open.

## 1.0.0 — 2026-07-27

- Separated the identity-conflicted upload from the already-finalized DriftGuard repository and implemented the distinct Living Context Engine promised by its metadata.
- Added conservative record classification, project-isolated SQLite storage, source hashes/lines/timestamps, bounded ingestion, query/timeline/context packs, exports, lifecycle deletion, and a read-only HTTP API.
- Added bearer-token protection for non-loopback serving, exact-origin CORS, Docker/Compose/CI, deterministic offline packaging, integration docs, provenance, and ownership gates.
