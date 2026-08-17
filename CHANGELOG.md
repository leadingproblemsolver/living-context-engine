# Changelog

## 2.1.0 — 2026-08-17

The adoption layer: the loop from 2.0.0 wired into the places work actually
happens, behind a review gate. Seven more invariants, each answering a specific
reason tools like this get abandoned — see `docs/ADOPTION.md`.

### Added

- **Review gate (invariant 8).** Model extraction, connector pulls, and API
  writes are staged as proposals — one per claim — and applied only when a human
  accepts. `lce review [--accept|--reject|--accept-all]`, with acceptance rate
  tracked per origin so you can see which sources earn their review cost.
  `auto_apply` in config controls the policy; deterministic parsing stays direct.
- **Identity resolution (invariant 9).** `lce identity [--fix]` and `lce merge`
  find and fold entities and attributes that have split. Attribute drift is
  caught by shared word plus shared entity, because a second name for one slot
  hides the delta instead of just splitting it. The better-evidenced name
  survives; the other becomes an alias so future ingests land correctly. Every
  merge is recorded with its reason.
- **Decisions as first-class (invariant 10).** `lce decision add|link|show|close`
  and `lce decisions`. Linking a claim raises its importance floor, which feeds
  action ranking. Readiness is governed by the weakest load-bearing belief, and
  `lce metric --decision <id>` scopes the north-star metric to one call.
- **The digest (invariant 11).** `lce digest` in Markdown, Slack, HTML, or JSON,
  with `--post-slack` and an HTML dashboard at `GET /`.
- **Connectors (invariant 12).** One contract — fetch → packet → stage — with
  `csv` (including population roll-up), `github_issues`, `slack_export`, and
  `filedrop`. `lce connectors`, `lce pull [--dry-run|--reset]`, per-connector
  cursors.
- **Write API.** `POST /api/observations` with a separate `LCE_API_WRITE_TOKEN`
  (which must differ from the read token) and `Idempotency-Key` support. It
  stages; it never applies.
- **Domain profiles (invariant 13).** `lce init --profile` for
  `customer-discovery`, `product-decisions`, `security-posture`, and `hiring` —
  vocabulary, starter questions, and evidence guidance as data rather than a
  fork. The profile is injected into the extraction prompt so two teams running
  one profile produce comparable graphs.
- **MCP server.** `lce mcp` exposes 12 tools and the whole prompt library over
  stdio, so Claude Desktop, Claude Code, or Cursor can read the graph and propose
  observations. `lce mcp --print-config` prints the client block.
- **`lce why` (invariant 14).** Walks one belief back to its evidence and forward
  to what would move it — including saying explicitly when a claim has hit its
  method ceiling and no more of the same evidence will help.
- New read endpoints: `/api/decisions`, `/api/proposals`, `/api/digest`.
- `lce ingest --stage`, `lce doctor`, `lce profiles`.

### Changed

- The generated CI workflow now pulls, validates, checks identity, reports
  decision readiness, and posts the digest.
- `.lce/config.json` gains `profile` and `auto_apply`.
- Rates over sub-hour windows are no longer reported; a trend measured across
  seconds was noise dressed as a number.

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
