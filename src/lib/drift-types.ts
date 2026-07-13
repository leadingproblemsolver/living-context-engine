export type Criticality = "critical" | "important" | "preference";
export type Enforcement = "block" | "warn" | "advise";
export type TargetScope = "action" | "output" | "workflow" | "session";
export type MetricType = "binary" | "threshold" | "checklist" | "evidence";
export type Verdict = "pass" | "watch" | "block";
export type InputMode = "prompt" | "checklist" | "metric" | "api";
export type EvaluationCadence = "manual" | "before-action" | "after-output" | "daily";

export type Guardrail = {
  id: string;
  title: string;
  description: string;
  criticality: Criticality;
  enforcement: Enforcement;
  targetScope: TargetScope;
  metricType: MetricType;
  metricConfig?: {
    operator?: "gte" | "lte" | "eq";
    threshold?: number;
    unit?: string;
    checklist?: string[];
  };
  active: boolean;
  source: "user" | "ai" | "template";
};

export type GuardrailSet = {
  id: string;
  name: string;
  purpose: string;
  workflow: string;
  target: string;
  successDefinition: string;
  inputMode: InputMode;
  evaluationCadence: EvaluationCadence;
  guardrails: Guardrail[];
  createdAt: string;
  updatedAt: string;
};

export type Finding = {
  guardrailId: string;
  status: "met" | "unclear" | "violated";
  reason: string;
  evidence: string;
};

export type Evaluation = {
  verdict: Verdict;
  score: number;
  summary: string;
  reasoning: string;
  correction: string;
  findings: Finding[];
  evaluatedAt: string;
  mode: "ai" | "rules" | "rules-preview";
};

export type StructuredEvidence = {
  metrics: Record<string, number>;
  binary: Record<string, boolean>;
  checklist: Record<string, Record<string, boolean>>;
};
