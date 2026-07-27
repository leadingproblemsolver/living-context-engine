# Release Checklist

## Verified in this release

- [x] Markdown/text/JSON/YAML ingestion.
- [x] project-scoped source replacement and deletion.
- [x] relative source provenance and symlink rejection.
- [x] query, timeline, context-pack, CSV/JSON export.
- [x] offline-installable deterministic wheel.
- [x] read-only API health, authentication, project listing, and exact-origin CORS behavior.
- [x] non-loopback token requirement.
- [ ] Docker/Compose runtime because no container runtime was available.
- [ ] hosted TLS/reverse-proxy deployment.
- [ ] large-corpus performance and p95/p99 latency.
- [ ] real project-source usefulness and cold-user activation.
- [ ] external backup/restore operations.

Unchecked items require a real browser, deployment environment, external integration, or human/user evidence. They are not implied by the checked offline release gates.
