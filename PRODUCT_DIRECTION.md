# DriftGuard — Final Product Direction

## The inelastic job

**Prevent a costly action or output from quietly violating the purpose and constraints the user already cares about.**

DriftGuard is not another task manager, habit tracker or generic AI reviewer. It is a **constraint-control layer** placed at the decision boundary of important work.

> Define what must stay true. Submit the next action or output. Receive Pass, Watch or Block, the exact reason, and the smallest safe correction.

The value becomes inelastic when drift produces expensive rework, credibility damage, compliance exposure, customer harm or a false sense of progress.

## Initial wedge

Target users are operators doing ambiguous but consequential work where the intended outcome is clear enough to state, yet easy to lose during execution:

- founders and product operators shipping claims, releases and experiments;
- content or communications teams protecting trust and approval constraints;
- technical operators following incident, change or deployment boundaries;
- consultants and educators checking deliverables against explicit success conditions.

The product remains workflow-agnostic, but the first message is concrete: **stop preventable rework before the action is taken.**

## Vocabulary

| Concept                     | Precise term | Meaning                                  |
| --------------------------- | ------------ | ---------------------------------------- |
| Why the work exists         | Purpose      | The outcome the workflow must cause      |
| Who/what must receive value | Target       | The beneficiary or controlled object     |
| How much a rule matters     | Criticality  | Critical, Important or Preference        |
| What happens when it fails  | Enforcement  | Block, Warn or Advise                    |
| What is being judged        | Target scope | Action, Output, Workflow or Session      |
| How it is proven            | Metric type  | Binary, Threshold, Checklist or Evidence |
| Result of a check           | Verdict      | Pass, Watch or Block                     |

“Vitality” is intentionally not used. **Criticality** is more operationally precise.

## Sub-60-second default workflow

1. **Purpose:** What outcome must this work cause?
2. **Workflow:** What sequence is being controlled?
3. **Target:** Who or what must receive value?
4. **Proof of success:** What observable evidence means the outcome occurred?
5. Optional: What must never happen?
6. AI proposes 3–7 testable guardrails.
7. User accepts or edits them.
8. User submits the next action/output and optional evidence.
9. System returns verdict, trace and correction.

Advanced controls stay collapsed until the user needs exact enforcement or an explicit integration checkpoint.

## Judgment contract

AI performs semantic interpretation only. Deterministic code owns policy precedence.

1. Evaluate every active guardrail against the submitted work and evidence.
2. Missing evidence is `unclear`, never an assumed pass.
3. Any `violated` guardrail with `enforcement = block` forces `Block`.
4. Otherwise, a violation or material uncertainty forces `Watch`.
5. Only fully supported work returns `Pass`.
6. Return the smallest concrete correction for the highest-priority issue.
7. Store the exact constraint snapshot with every verdict.

AI cannot silently create constraints, override a block, or mutate an accepted guardrail set.

## Consistent user-input progression

Use the least structured option that still creates reliable evidence:

1. **Plain-language check-in** — fastest default for new or irregular workflows.
2. **Structured checklist** — required fields for repeated workflows.
3. **Metric submission** — objective thresholds and counts.
4. **API/webhook event** — evaluation when an external tool or automation explicitly submits the current work and evidence at a workflow boundary.

Do not begin with passive surveillance or dozens of integrations. First prove which decision boundary users repeatedly care enough to check.

## Expansion path

Expand only after repeated use identifies a stable workflow:

- reusable guardrail templates;
- guardrail version history and approval roles;
- scheduled or event-triggered evaluation;
- Slack, email, browser and workflow-tool capture;
- team escalation for blocked actions;
- outcome feedback that tests whether guardrails predict real success;
- domain-specific judgment packs.

The expansion invariant is unchanged: **more capture methods and intelligence, not more ambiguity about who owns the constraints.**

## Hero copy

**Stop important work from quietly drifting.**

Define what must stay true once. DriftGuard checks each decision or output against it, returns **Pass, Watch or Block**, and gives the smallest correction needed.

Primary CTA: **Build my guardrails**

## Product boundaries

Do not turn DriftGuard into:

- a general project-management suite;
- an autonomous agent that changes policy;
- a vague “AI alignment score” without evidence;
- a monitoring dashboard before a repeated decision boundary exists;
- a compliance product that invents legal obligations.

The product wins by making one high-value judgment loop exceptionally clear, traceable and hard to bypass.

## Productization stop condition

The current release stops at a deployable, operator-first, pilot-ready constraint-control loop. The next valid expansion input is observed behavior: repeated use, useful interventions, false blocks, false Passes, support burden, and requests for shared policy. Do not expand into general project management, team governance, passive monitoring, predictive systems, or agent orchestration before those signals cross the thresholds in `docs/product/SCALABILITY_THRESHOLDS.yaml`.
