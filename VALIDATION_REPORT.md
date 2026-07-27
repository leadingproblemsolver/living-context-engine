# Validation Report

## Release purpose

Dependency-free local-first context ingestion, search, timeline, export, and source-linked context-pack service.

## Result

- **Automated tests:** 14/14 Pytest tests passed
- **Release validation:** Source compilation, repository validation, two byte-identical wheel builds, offline wheel installation, CLI ingest/query/timeline/pack/export/projects/delete smoke workflow, and authenticated read-only API smoke checks passed.
- **Release status:** offline-verified release candidate

## Verified

- Markdown/text/JSON/YAML ingestion
- project-scoped source replacement and deletion
- relative source provenance and symlink rejection
- query, timeline, context-pack, CSV/JSON export
- offline-installable deterministic wheel
- read-only API health, authentication, project listing, and exact-origin CORS behavior
- non-loopback token requirement

## Not verified

- Docker/Compose runtime because no container runtime was available
- hosted TLS/reverse-proxy deployment
- large-corpus performance and p95/p99 latency
- real project-source usefulness and cold-user activation
- external backup/restore operations

## Claim boundary

This report establishes deterministic local behavior and the stated release contracts only. It does not establish production scale, adoption, business impact, or independent human ownership. See `AI_HUMAN_PROVENANCE.md`, `PORTFOLIO_EVIDENCE.md`, and `HUMAN_OWNERSHIP_SPRINTS.md`.
