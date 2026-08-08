# Living Context Engine

A local-first operational-memory compiler. It turns project files into traceable decisions, blockers, actions, risks, questions, facts, and notes stored in SQLite and available through CLI, exports, context packs, or a read-only HTTP API.

## Ten-minute activation

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install .
lce ingest examples --project demo
lce query "deployment blocker" --project demo
lce timeline --project demo
lce pack "what changed and what is blocked" --project demo
```

No cloud account or API key is required for local CLI use.

## Input contract

The engine ingests Markdown, text, JSON, and YAML files. It recognizes explicit operator language such as:

```text
Decision: use a single package manager.
Blocker: production credentials are missing.
Action: run a clean deployment.
Risk: stale context may produce an unsafe decision.
Question: who owns the migration?
Evidence: the clean build passed.
```

Ordinary lines remain searchable notes. Every record preserves project, relative source path, source line, content hash, and observed timestamp. Symlink sources are rejected and source replacement is isolated by project.

## Integration surfaces

- CLI for local and CI workflows;
- SQLite database at `data/living-context.sqlite`;
- JSON/CSV export;
- source-linked Markdown and JSON context packs;
- read-only API: `/health`, `/health/ready`, `/api/status`, `/api/projects`, `/api/query`, `/api/timeline`.

Local API:

```bash
lce serve --host 127.0.0.1 --port 8790
```

Non-loopback API:

```bash
export LCE_API_TOKEN="replace-with-a-long-random-token"
lce serve --host 0.0.0.0 --port 8790
curl -H "Authorization: Bearer $LCE_API_TOKEN" http://127.0.0.1:8790/api/projects
```

## Lifecycle and deletion

```bash
lce projects
lce delete-project demo --yes
```

Project deletion is an explicit destructive operator action. The HTTP service is read-only.

## Evidence boundary

Classification is deterministic and intentionally conservative. A context pack is a source-linked retrieval artifact, not a completeness guarantee, autonomous memory, or decision-maker.

## Constraint intelligence pipeline

The repository includes a human-reviewed engineering-pain discovery and constraint-intelligence pipeline. GitHub is treated as a sensor network: strong market evidence is preserved even when a thread is a poor public-comment target.

```bash
python scripts/discover_github_issues.py \
  --config config/constraint_signal_queries.json

python scripts/build_constraint_intelligence.py \
  --input artifacts/github-review-queue.json \
  --taxonomy config/constraint_taxonomy.json
```

The compiler keeps two decisions separate:

- **constraint value** — production evidence, economic consequence, workaround burden, recurrence, cross-system generality, buyer proximity, serviceability, proof feasibility, and urgency;
- **intervention value** — whether this occurrence deserves corpus-only retention, watching, a diagnostic question, a precision comment, a reproduction, a patch/diagnostic, or operator assistance.

Default public action is **no comment**. The system is designed to move repeated evidence from discovery toward diagnostics, reproductions, patches, audits, operator validation, and reusable product primitives rather than optimize comment count.

Generated artifacts:

- `artifacts/github-review-queue.json` / `.md` — evidence-preserving discovery queue;
- `artifacts/constraint-intelligence.json` — signal-level scores and recommended interventions;
- `artifacts/constraint-leaderboard.json` — ranked constraint families;
- `artifacts/constraint-intelligence.md` — human operating report.

See [`docs/CONSTRAINT_INTELLIGENCE_OPERATING_SYSTEM.md`](docs/CONSTRAINT_INTELLIGENCE_OPERATING_SYSTEM.md) for the exploration/exploitation gates, proof ladder, public contribution policy, daily/weekly loops, success metrics, and provisional audit offers.

The original inspection details remain in [`docs/GITHUB_REVIEW_PIPELINE.md`](docs/GITHUB_REVIEW_PIPELINE.md).

See [`docs/INTEGRATION.md`](docs/INTEGRATION.md), [`docs/API.md`](docs/API.md), and [`DEPLOYABILITY_DISTRIBUTION.md`](DEPLOYABILITY_DISTRIBUTION.md).
