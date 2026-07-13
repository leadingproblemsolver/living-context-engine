# Value Architecture

**Status:** inferred  
**Confidence:** 90/100  
**Evidence:** `src/routes/index.tsx`, `supabase/functions/evaluate/index.ts`, `PRODUCT_DIRECTION.md`

## State transition

**Important work is guided by scattered, inconsistently applied constraints**  
→ the user defines the outcome once and accepts observable guardrails  
→ DriftGuard checks one proposed action or output against every active guardrail  
→ the user receives **Pass, Watch, or Block**, the exact reason, and the smallest safe correction  
→ the user proceeds with evidence, clarifies uncertainty, or corrects the work before damage occurs  
→ repeated evaluations create a reproducible decision record rather than repeated interpretation.

## Value contract

- **Painful before state:** The user realizes too late that work violated an important constraint.
- **Trigger:** A consequential action, output, approval, or handoff is about to occur.
- **Core mechanism:** Objective evidence is evaluated deterministically; semantic evidence is interpreted conservatively; deterministic precedence owns the final verdict.
- **Immediate output:** Pass, Watch, or Block plus one finding per guardrail.
- **Immediate user gain:** A clear next action without rereading all project context.
- **Emotional relief:** Confidence that the non-negotiables were actually checked.
- **Operational gain:** Less rework, lower decision variance, and earlier detection of missing proof.
- **Economic gain:** Avoided downstream correction cost where the guarded workflow is consequential enough.
- **Compounding value:** A reusable guardrail set and exact evaluation history reduce repeated interpretation.
- **Proof standard:** Contract tests, immutable constraint snapshots, model identity, evidence state, and eventually observed avoided failures from pilots.

## One-line value proposition

**Keep consequential work inside its real constraints without manually rechecking every requirement.**

## Claim boundary

The implementation verifies that DriftGuard can enforce its judgment contract. It does not yet prove a quantified reduction in user rework, risk, or time; those claims require pilot outcome data.
