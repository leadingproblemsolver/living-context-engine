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
- [x] Review gate: staged proposals, per-claim granularity, acceptance rates per
      origin, and no state change until accepted.
- [x] Identity resolution for entities and attributes, proposed rather than
      applied, with recorded merges and forward-routing aliases.
- [x] Decisions with links, weakest-link readiness, and decision-scoped
      uncertainty.
- [x] Connector contract with cursors, roll-up, and per-connector error
      isolation; csv, github_issues, slack_export, filedrop.
- [x] Staged write endpoint with a separate write token and idempotency keys.
- [x] MCP server: handshake, 12 tools, prompt library, staged proposals, tool
      errors.
- [x] Digest in Markdown, Slack, HTML, JSON, plus the HTML dashboard.
- [x] Domain profiles as data, including the shorter security half-life.
- [ ] Model-assisted extraction against a live API.
- [ ] Live GitHub and Slack pulls, and Slack webhook delivery.
- [ ] A real MCP client session.
- [ ] Review throughput at volume — whether the gate stays cheaper than the
      errors it prevents.
- [ ] Extraction quality against a labelled corpus.
- [ ] Docker/Compose runtime because no container runtime was available.
- [ ] Hosted TLS/reverse-proxy deployment.
- [ ] Large-corpus performance and p95/p99 latency.
- [ ] Cold-user activation and real decision impact.
- [ ] External backup/restore operations.

Unchecked items require a live API key, a labelled corpus, a deployment
environment, or human evidence. They are not implied by the checked offline
gates.
