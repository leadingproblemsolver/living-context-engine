# Constraint Intelligence Operating System

This document replaces comment-count optimization with a constraint-first operating model.

## Mission

Continuously detect expensive recurring operational constraints, determine which are commercially serviceable, create concrete proof that we can solve them, and convert the strongest constraints into repeatable services, tools, products, and market intelligence.

GitHub is a sensor network, not the product and not the scoreboard.

## Canonical loop

```text
DISCOVER
  -> NORMALIZE SIGNAL
  -> EXTRACT CONSTRAINT
  -> MERGE WITH EVIDENCE FAMILY
  -> SCORE CONSTRAINT VALUE
  -> SCORE INTERVENTION VALUE
  -> ROUTE ACTION
  -> BUILD PROOF
  -> MAP OFFER / PRODUCT
  -> VALIDATE WITH OPERATOR
  -> RECORD OUTCOME
  -> UPDATE POLICY
```

## Two independent scores

### Constraint value

How economically and strategically important is the underlying pain?

Weighted inputs:

- production evidence: 18%
- economic consequence: 16%
- workaround burden: 14%
- recurrence: 12%
- cross-system generality: 12%
- buyer proximity: 10%
- serviceability: 8%
- proof feasibility: 6%
- urgency: 4%

Penalties:

- commodity/known solution
- already solved upstream
- weak evidence

### Intervention value

What should we do about this particular occurrence?

A valuable constraint may still be a bad public-comment target because the thread is saturated, a fix is in progress, the issue is solved, or there is no contribution gap.

Intervention ladder:

```text
corpus_only
watch
ask_diagnostic_question
precision_comment
build_reproduction
build_patch_or_diagnostic
operator_assistance_or_offer
```

Default public action: **no comment**.

## Constraint states

```text
emerging
confirmed
saturated
validating
serviceable
proven
productizable
commoditized
deprioritized
```

The compiler currently promotes repeated strong evidence automatically from `emerging` to `confirmed` and `validating`. Later states require outcome evidence, not just more reports.

## Exploration -> exploitation gates

Continue exploration when any of these are true:

- fewer than 3 independent observations
- mechanism remains uncertain
- buyer is unclear
- severity/economic consequence is unclear
- no cross-system evidence exists

Begin exploitation when all of these are substantially true:

- at least 3 independent production examples
- the same invariant appears in at least 2 systems or materially different deployments
- an economic consequence is visible
- an identifiable buyer/operator exists
- a plausible intervention can be delivered without owning the upstream platform

Prioritize productization only when:

- at least 5 strong observations exist
- at least 2 successful interventions exist
- the same diagnostic/fix is reused
- a buyer is willing to pay or repeatedly adopt it
- the intervention can be standardized

## Proof ladder

```text
0 Evidence
1 Mechanism
2 Diagnostic
3 Reproduction
4 Mitigation
5 Patch
6 Reusable primitive
7 Productized check
8 Commercial proof
9 Repeatability
```

Most discovery work should not stop at levels 0-2. The highest-value constraint families should be deliberately pushed toward levels 4-8.

## Current root constraint taxonomy

1. Operational truth divergence
2. Ambiguous or duplicate side effects
3. Identity and credential continuity
4. Persistence and resume correctness
5. Silent delivery failure
6. State amplification and resource pressure
7. Configuration authority drift
8. Evidence freshness and stale projections
9. Tenant and request state isolation
10. Provider and adapter fidelity

The taxonomy is versioned in `config/constraint_taxonomy.json`. Create a new family only when evidence does not fit an existing root constraint without distorting it.

## Mandatory economic chain

For every high-value signal, preserve this path:

```text
technical failure
  -> workflow/operational consequence
  -> economic consequence
  -> buyer pain
  -> current compensation/workaround
```

If a credible chain cannot be constructed, lower commercial priority even if the bug is technically interesting.

## Public contribution gate

Only comment publicly when at least one of these is true:

- we can add a new causal discriminator
- we can provide a reproducible test
- we can identify missing evidence that materially narrows the search
- we can point to a precise implementation boundary
- we can provide a patch or failing test
- we can prevent a correctness/safety failure not already identified
- the operator has measurable production pain and the response creates a concrete path to resolution

Do not post generic invariant checklists into already well-diagnosed threads.

## Daily operation

1. Discover 50-200 candidate objects.
2. Filter to high-signal observations.
3. Normalize into the signal corpus.
4. Run `build_constraint_intelligence.py`.
5. Review the constraint leaderboard.
6. Select at most a small number of high intervention-value items for public interaction.
7. Spend the majority of expert effort on reproduction, code inspection, diagnostics, patches, or operator assistance.
8. Record outcomes.

Example:

```bash
python scripts/discover_github_issues.py \
  --config config/github_issue_queries.json

python scripts/build_constraint_intelligence.py \
  --input artifacts/github-review-queue.json
```

Outputs:

- `artifacts/constraint-intelligence.json` — signal-level intelligence
- `artifacts/constraint-leaderboard.json` — family-level ranking
- `artifacts/constraint-intelligence.md` — human review report

## Weekly operation

1. Rank constraint families.
2. Promote/demote saturation states using actual evidence.
3. Choose one constraint of the week.
4. Produce one concrete artifact: diagnostic, repro, patch, probe, audit template, or operator deliverable.
5. Run a buyer/operator validation test.
6. Record technical and commercial outcomes.
7. Update the targeting policy.

## Success metrics

### Intelligence

- strong signals retained
- independent confirmations
- cross-repo confirmations
- economic consequences captured
- constraints promoted from emerging -> confirmed

### Technical

- reproductions
- diagnostics
- patches/PRs
- reusable primitives
- prevented or resolved incidents

### Engagement

- substantive replies
- reporter follow-ups
- maintainer follow-ups
- requests for help

### Commercial

- operator conversations
- audits offered
- audits accepted
- paid engagements
- conversion by constraint family

### Product

- recurring checks
- reusable scripts
- repeated implementation patterns
- cross-platform applicability

Comment count is not a primary KPI.

## Provisional exploitation priorities

### 1. Runtime / operational truth

Potential deliverable: **Automation Runtime Truth Audit**

Verify that active triggers, schedules, webhook routes, queues, dependencies, and health status are backed by current serving evidence.

### 2. Side-effect integrity

Potential deliverable: **Side-Effect Integrity Audit**

Inventory consequential actions and test retry, timeout-after-commit, redelivery, duplicate scheduling, replay, external idempotency, and reconciliation behavior.

### 3. Identity / credential continuity

Potential deliverable: **Execution Identity & Credential Continuity Audit**

Verify that tenant, user, credential, scopes, secrets, and request context remain correct across interactive, scheduled, webhook, queue, background, HITL, retry, resume, and subworkflow execution.

## Architectural boundary

This intelligence layer does not change LCE's evidence claims. LCE remains a deterministic local-first operational-memory compiler with source-linked records and keyword-overlap query. Constraint classification and scoring in this pipeline are heuristic operational analysis; they are not semantic-RAG or autonomous-memory claims.
