# Release Checklist

## Verified in this release

- [x] State primitives: entities, claims, evidence, transitions, contradictions,
      unknowns, relationships, actions, metrics.
- [x] Claims without evidence rejected; evidence idempotent across re-ingestion.
- [x] Confidence derived from evidence, damped for correlated repeats, capped by
      method ceiling, decayed by age — and re-derivable by `lce validate`.
- [x] Transition classification with recorded rationale, and supersession only
      past the evidence margin.
- [x] Contradictions recorded, resolvable, and acceptable as genuine splits.
- [x] Task-scoped context packs in Markdown and JSON.
- [x] Action ranking with expected-gain projection using the same confidence
      maths as the graph.
- [x] Uncertainty metric and snapshot history.
- [x] Observation packet schema, `lce absorb`, and the prompt library.
- [x] Repository scaffolding (`lce init [--ci]`), config resolution, `lce doctor`.
- [x] Project-scoped source replacement, deletion, and isolation.
- [x] Relative source provenance and symlink rejection.
- [x] Offline-installable deterministic wheel with the `llm` extra declared.
- [x] Read-only API across both layers, non-loopback token requirement, and
      exact-origin CORS behaviour.
- [ ] Model-assisted extraction against a live API.
- [ ] Extraction quality against a labelled corpus.
- [ ] Docker/Compose runtime because no container runtime was available.
- [ ] Hosted TLS/reverse-proxy deployment.
- [ ] Large-corpus performance and p95/p99 latency.
- [ ] Cold-user activation and real decision impact.
- [ ] External backup/restore operations.

Unchecked items require a live API key, a labelled corpus, a deployment
environment, or human evidence. They are not implied by the checked offline
gates.
