import type {
  Evaluation,
  Finding,
  Guardrail,
  GuardrailSet,
  StructuredEvidence,
  Verdict,
} from "./drift-types";

export function uid(prefix = "id") {
  return `${prefix}_${crypto.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
}

function guardrail(
  title: string,
  description: string,
  options: Partial<Guardrail> = {},
): Guardrail {
  return {
    id: options.id ?? uid("guardrail"),
    title,
    description,
    criticality: "important",
    enforcement: "warn",
    targetScope: "output",
    metricType: "evidence",
    active: true,
    source: "ai",
    ...options,
  };
}

export function inferGuardrailsLocally(input: {
  purpose: string;
  workflow: string;
  target: string;
  successDefinition: string;
  mustNotHappen: string;
}): Guardrail[] {
  const purpose = input.purpose.trim() || "Complete the work without losing the intended outcome";
  const target = input.target.trim() || "the intended user";
  const success = input.successDefinition.trim() || "the stated outcome is visibly achieved";
  const exclusions = input.mustNotHappen
    .split(/\n|;|\.(?:\s|$)/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 4);

  const inferred = [
    guardrail("Purpose remains explicit", `The next action must directly advance: ${purpose}`, {
      criticality: "critical",
      enforcement: "warn",
      targetScope: "action",
    }),
    guardrail(
      "Target value is preserved",
      `The work must create a clear benefit for ${target}, not merely produce activity.`,
      {
        criticality: "critical",
        enforcement: "block",
        targetScope: "output",
      },
    ),
    guardrail("Success is evidenced", `Completion requires observable proof that ${success}.`, {
      criticality: "important",
      enforcement: "warn",
      metricType: "evidence",
    }),
  ];

  exclusions.forEach((item) => {
    inferred.push(
      guardrail(item.replace(/^no\s+/i, "Avoid "), item, {
        criticality: "critical",
        enforcement: "block",
        source: "user",
      }),
    );
  });

  return inferred.slice(0, 7);
}

function includesAny(text: string, terms: string[]) {
  return terms.some((term) => text.includes(term));
}

function thresholdFinding(rule: Guardrail, structured: StructuredEvidence): Finding | null {
  if (rule.metricType === "threshold") {
    const threshold = rule.metricConfig?.threshold;
    const value = structured.metrics[rule.id];
    if (!Number.isFinite(threshold)) {
      return {
        guardrailId: rule.id,
        status: "unclear",
        reason: "This threshold guardrail has no configured threshold.",
        evidence: "Threshold configuration missing",
      };
    }
    if (!Number.isFinite(value)) {
      return {
        guardrailId: rule.id,
        status: "unclear",
        reason: "No numeric value was submitted for this threshold.",
        evidence: "Metric value missing",
      };
    }
    const operator = rule.metricConfig?.operator ?? "gte";
    const met =
      operator === "gte"
        ? value >= threshold!
        : operator === "lte"
          ? value <= threshold!
          : value === threshold;
    return {
      guardrailId: rule.id,
      status: met ? "met" : "violated",
      reason: met
        ? "The submitted value satisfies the configured threshold."
        : "The submitted value does not satisfy the configured threshold.",
      evidence: `${value}${rule.metricConfig?.unit ? ` ${rule.metricConfig.unit}` : ""} ${operator} ${threshold}`,
    };
  }

  if (rule.metricType === "binary") {
    const value = structured.binary[rule.id];
    if (typeof value !== "boolean") {
      return {
        guardrailId: rule.id,
        status: "unclear",
        reason: "No yes/no result was submitted for this guardrail.",
        evidence: "Binary result missing",
      };
    }
    return {
      guardrailId: rule.id,
      status: value ? "met" : "violated",
      reason: value
        ? "The required condition was confirmed."
        : "The required condition was not met.",
      evidence: value ? "Yes" : "No",
    };
  }

  if (rule.metricType === "checklist") {
    const items = rule.metricConfig?.checklist ?? [];
    if (!items.length) {
      return {
        guardrailId: rule.id,
        status: "unclear",
        reason: "This checklist guardrail has no checklist items.",
        evidence: "Checklist configuration missing",
      };
    }
    const values = structured.checklist[rule.id] ?? {};
    const answered = items.filter((item) => typeof values[item] === "boolean");
    if (answered.length !== items.length) {
      return {
        guardrailId: rule.id,
        status: "unclear",
        reason: "Not every required checklist item has been confirmed.",
        evidence: `${answered.length}/${items.length} items answered`,
      };
    }
    const failed = items.filter((item) => values[item] === false);
    return {
      guardrailId: rule.id,
      status: failed.length ? "violated" : "met",
      reason: failed.length
        ? "One or more required checklist items failed."
        : "Every required checklist item passed.",
      evidence: failed.length
        ? `Failed: ${failed.join("; ")}`
        : `${items.length}/${items.length} items passed`,
    };
  }

  return null;
}

function previewFinding(rule: Guardrail, text: string, evidence: string): Finding {
  const haystack = `${text}\n${evidence}`.toLowerCase();
  const ruleText = `${rule.title} ${rule.description}`.toLowerCase();

  if (
    includesAny(ruleText, ["confidential", "private", "customer data", "personal data"]) &&
    includesAny(haystack, ["email:", "phone:", "customer name", "private key", "password"])
  ) {
    return {
      guardrailId: rule.id,
      status: "violated",
      reason: "The input appears to contain information this guardrail excludes.",
      evidence: "Potential restricted-data marker detected",
    };
  }

  if (
    includesAny(ruleText, ["source", "verified", "evidence", "proof"]) &&
    /\b\d+(?:\.\d+)?%|\b\d+x\b/i.test(haystack) &&
    !includesAny(haystack, [
      "source:",
      "according to",
      "http",
      "estimate",
      "hypothesis",
      "measured",
    ])
  ) {
    return {
      guardrailId: rule.id,
      status: rule.enforcement === "block" ? "violated" : "unclear",
      reason: "A quantitative claim appears without visible support or qualification.",
      evidence: "Metric detected; source or qualification not detected",
    };
  }

  return {
    guardrailId: rule.id,
    status: "unclear",
    reason:
      "Local preview cannot reliably verify a semantic guardrail. Sign in for authenticated AI judgment or use a binary, threshold, or checklist rule.",
    evidence: evidence.trim()
      ? "Evidence was supplied but not semantically verified in preview mode"
      : "No semantically verified evidence",
  };
}

export function evaluateLocally(
  set: GuardrailSet,
  input: { text: string; evidence: string; structured?: StructuredEvidence },
): Evaluation {
  const active = set.guardrails.filter((rule) => rule.active);
  const structured = input.structured ?? { metrics: {}, binary: {}, checklist: {} };
  const findings = active.map(
    (rule) =>
      thresholdFinding(rule, structured) ?? previewFinding(rule, input.text, input.evidence),
  );

  const blockingViolation = findings.some((finding) => {
    const rule = active.find((item) => item.id === finding.guardrailId);
    return finding.status === "violated" && rule?.enforcement === "block";
  });
  const uncertainty = findings.some((finding) => finding.status !== "met");
  const verdict: Verdict = blockingViolation ? "block" : uncertainty ? "watch" : "pass";
  const met = findings.filter((finding) => finding.status === "met").length;
  const score = active.length ? Math.round((met / active.length) * 100) : 0;
  const firstIssue = findings.find((finding) => finding.status !== "met");
  const firstRule = active.find((rule) => rule.id === firstIssue?.guardrailId);

  return {
    verdict,
    score,
    summary:
      verdict === "pass"
        ? "No active guardrail is missing or visibly violated."
        : verdict === "block"
          ? `Stop before proceeding: ${firstRule?.title ?? "a blocking guardrail"} is violated.`
          : `Proceed only after clarifying: ${firstRule?.title ?? "one or more guardrails"}.`,
    reasoning:
      verdict === "pass"
        ? "The supplied action and evidence are consistent with the currently active constraints."
        : (firstIssue?.reason ?? "The available evidence is incomplete."),
    correction:
      verdict === "pass"
        ? "Proceed, then record the actual outcome so the next evaluation uses real evidence."
        : `Add explicit proof or revise the work so it satisfies “${firstRule?.title ?? "the flagged guardrail"}”.`,
    findings,
    evaluatedAt: new Date().toISOString(),
    mode: "rules-preview",
  };
}

export const SAMPLE_SET: GuardrailSet = {
  id: "sample",
  name: "High-trust product launch",
  purpose: "Ship a credible product page that earns qualified user action",
  workflow: "Draft → verify claims → publish → review conversion evidence",
  target: "A skeptical operator deciding whether this solves a costly workflow problem",
  successDefinition:
    "The right user understands the problem, mechanism and next step without unsupported claims",
  inputMode: "prompt",
  evaluationCadence: "before-action",
  createdAt: "2026-07-01T00:00:00.000Z",
  updatedAt: "2026-07-01T00:00:00.000Z",
  guardrails: [
    guardrail(
      "No unsupported performance claims",
      "Every metric or superiority claim must have a source, measurement, or explicit hypothesis label.",
      {
        id: "sample-1",
        criticality: "critical",
        enforcement: "block",
        source: "template",
      },
    ),
    guardrail(
      "Reader value is explicit",
      "The page must state the costly problem, the mechanism, and the user's gain in plain language.",
      {
        id: "sample-2",
        criticality: "critical",
        enforcement: "warn",
        source: "template",
      },
    ),
    guardrail(
      "No confidential customer data",
      "Examples must never expose names, emails, credentials, or private operational details.",
      {
        id: "sample-3",
        criticality: "critical",
        enforcement: "block",
        source: "template",
      },
    ),
    guardrail(
      "Success has observable evidence",
      "Record a user action, conversion event, or direct comprehension signal after publishing.",
      {
        id: "sample-4",
        criticality: "important",
        enforcement: "warn",
        source: "template",
      },
    ),
  ],
};
