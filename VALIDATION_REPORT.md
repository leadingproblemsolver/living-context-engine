# Validation Report

## Release purpose

A dependency-free local reality delta compiler: observations in, traceable state
with provenance and confidence out, plus detected changes, first-class
contradictions, open unknowns, ranked verification actions, task-scoped context
packs, and an uncertainty metric over time.

## Result

- **Automated tests:** 44/44 Pytest tests passed, organised by the invariant each protects
- **Release validation:** source compilation, repository validation, wheel build
  and offline install, full CLI loop against the bundled discovery corpus
  (`init` → `ingest` → `state` → `delta` → `contradictions` → `actions` →
  `context` → `metric` → `prompt` → `doctor` → `validate`), and read-only HTTP
  state-layer checks passed
- **Release status:** offline-verified release candidate

## Verified

- Prose produces no belief; only explicit statements become state
- Claims without evidence are rejected at the ingestion boundary
- Evidence is idempotent — re-ingesting an unchanged source cannot inflate
  confidence, and produces no transition
- Confidence is derived, not stored independently: `lce validate` re-derives all
  of it from evidence and fails on drift
- Repeated observations from one actor move belief less than independent ones
- Method ceilings hold: 50 interviews cannot exceed the interview ceiling, and a
  single transaction can carry a claim above it
- Stronger new evidence revises a belief and supersedes the old claim; an evenly
  matched conflict keeps both claims active and opens a contradiction
- Multi-valued attributes accumulate instead of manufacturing conflict
- Fenced code blocks in documentation are never parsed as claims
- Two different questions produce two different context packs
- Open unknowns, open contradictions, and weak important claims each produce
  ranked actions; behavioural questions route to experiments
- Uncertainty falls when a question is answered and when evidence accumulates
- Projects are isolated across state and observation layers, including deletion
- Read-only HTTP state, unknown, action, metric, and context endpoints, and the
  project requirement on state-layer endpoints
- Offline-installable deterministic wheel with the optional `llm` extra declared

## Not verified

- Extraction quality against a labelled real corpus
- Model-assisted extraction (`--llm`) against a live API, and its accuracy
- Whether the ranked actions measurably shorten a real decision
- Docker/Compose runtime, because no container runtime was available
- Hosted TLS/reverse-proxy deployment
- Large-corpus performance and p95/p99 latency
- Cold-user activation and multi-week team usefulness
- External backup/restore operations

## Claim boundary

This report establishes deterministic local behaviour and the stated contracts
only. Confidence values are bookkeeping over evidence strength, independence,
and age — they are not probabilities that a claim is true, and the graph is only
as honest as the source `kind` an operator assigns. Nothing here establishes
production scale, adoption, or business impact. See `AI_HUMAN_PROVENANCE.md`,
`PORTFOLIO_EVIDENCE.md`, and `HUMAN_OWNERSHIP_SPRINTS.md`.
