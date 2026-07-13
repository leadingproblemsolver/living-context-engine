import test from "node:test";
import assert from "node:assert/strict";
import { evaluateLocally } from "../src/lib/drift-engine.ts";

function workspace(guardrails) {
  return {
    id: "test-set",
    name: "Contract test",
    purpose: "Preserve the intended outcome",
    workflow: "Draft to release",
    target: "A defined user",
    successDefinition: "All accepted constraints are supported",
    inputMode: "prompt",
    evaluationCadence: "manual",
    guardrails,
    createdAt: new Date(0).toISOString(),
    updatedAt: new Date(0).toISOString(),
  };
}

function rule(overrides = {}) {
  return {
    id: "rule-1",
    title: "Required condition",
    description: "The required condition must be explicitly supported.",
    criticality: "critical",
    enforcement: "block",
    targetScope: "output",
    metricType: "binary",
    active: true,
    source: "user",
    ...overrides,
  };
}

const blank = {
  text: "Check this output",
  evidence: "",
  structured: { metrics: {}, binary: {}, checklist: {} },
};

test("a failed blocking binary rule forces Block", () => {
  const result = evaluateLocally(workspace([rule()]), {
    ...blank,
    structured: { ...blank.structured, binary: { "rule-1": false } },
  });
  assert.equal(result.verdict, "block");
});

test("missing proof never returns Pass, even for a preference", () => {
  const result = evaluateLocally(
    workspace([rule({ criticality: "preference", enforcement: "advise" })]),
    blank,
  );
  assert.equal(result.verdict, "watch");
});

test("a satisfied objective rule can Pass", () => {
  const result = evaluateLocally(workspace([rule()]), {
    ...blank,
    structured: { ...blank.structured, binary: { "rule-1": true } },
  });
  assert.equal(result.verdict, "pass");
  assert.equal(result.score, 100);
});

test("arbitrary prose evidence cannot fabricate a local semantic Pass", () => {
  const result = evaluateLocally(
    workspace([rule({ metricType: "evidence", enforcement: "advise" })]),
    {
      text: "The output mentions the required condition.",
      evidence: "This is long but unverified evidence.",
      structured: blank.structured,
    },
  );
  assert.equal(result.verdict, "watch");
  assert.equal(result.findings[0].status, "unclear");
});

test("threshold and checklist evidence are deterministic", () => {
  const result = evaluateLocally(
    workspace([
      rule({
        id: "threshold",
        metricType: "threshold",
        metricConfig: { operator: "gte", threshold: 90 },
      }),
      rule({
        id: "checklist",
        enforcement: "warn",
        metricType: "checklist",
        metricConfig: { checklist: ["Reviewed", "Approved"] },
      }),
    ]),
    {
      ...blank,
      structured: {
        metrics: { threshold: 92 },
        binary: {},
        checklist: { checklist: { Reviewed: true, Approved: true } },
      },
    },
  );
  assert.equal(result.verdict, "pass");
  assert.equal(
    result.findings.every((finding) => finding.status === "met"),
    true,
  );
});
