# GitHub inspection and review pipeline

The objective is not to broadcast Living Context Engine into unrelated threads. The objective is to find active engineering problems where LCE's implemented mechanisms are directly relevant, contribute a useful answer, and create a legitimate reason for an engineer to inspect the repository.

## Conversion path

```text
LCE capability
  -> precise pain language
  -> live open GitHub issue
  -> deterministic qualification
  -> human technical review
  -> value-first response
  -> optional contextual repository reference
  -> repository inspection
  -> useful feedback, issue, PR, or star
```

A star is a downstream signal, not the primary action. The controllable target is a qualified repository inspection by a relevant engineer.

## Run locally

```bash
python scripts/discover_github_issues.py
```

Optional controls:

```bash
python scripts/discover_github_issues.py \
  --created-after 2026-05-01 \
  --per-query 30 \
  --min-score 60
```

Outputs:

- `artifacts/github-review-queue.json` for processing and measurement;
- `artifacts/github-review-queue.md` for human review.

The scheduled GitHub Action runs twice weekly and uploads both files as a workflow artifact. It does not post comments.

## Qualification model

The score is deliberately simple and inspectable:

| Component | Maximum | What it represents |
|---|---:|---|
| Relevance | 40 | Exact LCE capability language found in the issue |
| Intent | 25 | The author is actively seeking a fix, workaround, or architecture |
| Recency | 15 | The problem is current enough to engage |
| Validation | 10 | Other humans have engaged with the issue |
| Spam penalty | -20 | Bot, stale, duplicate, invalid, or beginner-task noise |

The score is a queueing heuristic, not evidence that LCE solves the issue.

## Mandatory human gate

Before responding to any issue:

1. Read the complete issue and all comments.
2. Confirm the problem remains unresolved.
3. Inspect linked code, logs, reproductions, and maintainer guidance.
4. Write the useful part first: diagnosis, workaround, schema, or runnable example.
5. Remove the LCE reference if it is not necessary to the answer.
6. Never repeat the same promotional wording across repositories.

## Value-first response structure

Use this order:

1. **Observed failure:** restate the concrete mechanism, not the product category.
2. **Immediate help:** provide a specific fix, data shape, command sequence, or diagnostic.
3. **Boundary:** state what the proposed fix does not guarantee.
4. **Optional reference:** mention LCE only when its implemented behavior directly covers the recurring pattern.
5. **Verification request:** ask whether the proposed mechanism matches the maintainer's constraints.

Example skeleton:

```text
The failure looks less like "missing AI memory" and more like replacement without source provenance: the resumed state cannot show which file/line produced each claim.

A minimal fix is to persist records as {project, source_path, source_line, observed_at, content_hash, kind, text}, replace records only within the same project/source boundary, and build the handoff from those records rather than from a free-form summary.

That gives traceability, but it does not prove the context pack is complete or make decisions autonomously.

I maintain Living Context Engine, which implements this exact local-first pattern with SQLite, source-linked records, CLI queries, context packs, and a read-only API. The schema/approach above is usable independently of the project.
```

## Inspection readiness gate

Do not increase outreach volume until the repository passes these checks:

- the README communicates the mechanism and evidence boundary in under two minutes;
- activation works from a clean Python environment;
- examples produce inspectable output;
- tests pass on the default branch;
- repository topics and description use the same pain language as the query matrix;
- issue templates invite reproducible failures and integration requests;
- the first contribution path is explicit;
- generated outreach can be traced to a query, issue, reviewer decision, and outcome.

## Weekly operating target

Start with a small controlled batch:

- review the top 10 queue entries;
- select at most 3 where direct technical help is possible;
- post no more than 3 fully individualized responses;
- ask 2 relevant engineers for blunt repository inspection;
- record inspections, substantive replies, issues opened, PRs, and stars;
- change query terms only from observed false positives and real conversations.

This prevents optimizing for low-quality impressions while the repository and message are still being calibrated.
