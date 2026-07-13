import { createFileRoute } from "@tanstack/react-router";
import type { Session } from "@supabase/supabase-js";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleGauge,
  Cloud,
  Database,
  Gauge,
  Lock,
  LogOut,
  Plus,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Target,
  Trash2,
  X,
  XCircle,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { evaluateLocally, inferGuardrailsLocally, SAMPLE_SET, uid } from "../lib/drift-engine";
import { EDGE_FUNCTIONS } from "../lib/edge-functions";
import type {
  Criticality,
  Enforcement,
  Evaluation,
  EvaluationCadence,
  Guardrail,
  GuardrailSet,
  InputMode,
  MetricType,
  StructuredEvidence,
  TargetScope,
  Verdict,
} from "../lib/drift-types";
import { isSupabaseConfigured, supabase, supabaseConfigIssue } from "../lib/supabase";

export const Route = createFileRoute("/")({
  component: Index,
});

const STORAGE_KEY = "driftguard:workspace:v2";

type Stage = "define" | "guardrails" | "check";
type SetupDraft = {
  name: string;
  purpose: string;
  workflow: string;
  target: string;
  successDefinition: string;
  mustNotHappen: string;
  inputMode: InputMode;
  evaluationCadence: EvaluationCadence;
};

type DbGuardrail = {
  id: string;
  title: string;
  description: string;
  criticality: Criticality;
  enforcement: Enforcement;
  target_scope: TargetScope;
  metric_type: MetricType;
  metric_config: Guardrail["metricConfig"] | null;
  active: boolean;
  source: Guardrail["source"];
  position?: number;
};

type DbGuardrailSet = {
  id: string;
  name: string;
  purpose: string;
  workflow: string;
  target: string;
  success_definition: string;
  input_mode: InputMode;
  evaluation_cadence: EvaluationCadence;
  created_at: string;
  updated_at: string;
  guardrails?: DbGuardrail[];
};

const setupFromSet = (set: GuardrailSet): SetupDraft => ({
  name: set.name,
  purpose: set.purpose,
  workflow: set.workflow,
  target: set.target,
  successDefinition: set.successDefinition,
  mustNotHappen: set.guardrails
    .filter((item) => item.enforcement === "block")
    .map((item) => item.description)
    .join("\n"),
  inputMode: set.inputMode,
  evaluationCadence: set.evaluationCadence,
});

function loadLocalWorkspace(): GuardrailSet {
  if (typeof window === "undefined") return SAMPLE_SET;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) return SAMPLE_SET;
    const parsed = JSON.parse(stored) as GuardrailSet;
    if (!parsed?.guardrails || !Array.isArray(parsed.guardrails)) return SAMPLE_SET;
    return {
      ...SAMPLE_SET,
      ...parsed,
      inputMode: parsed.inputMode ?? "prompt",
      evaluationCadence: parsed.evaluationCadence ?? "before-action",
    };
  } catch {
    return SAMPLE_SET;
  }
}

function toGuardrail(row: DbGuardrail): Guardrail {
  return {
    id: row.id,
    title: row.title,
    description: row.description,
    criticality: row.criticality,
    enforcement: row.enforcement,
    targetScope: row.target_scope,
    metricType: row.metric_type,
    metricConfig: row.metric_config ?? undefined,
    active: row.active,
    source: row.source,
  };
}

function toSet(row: DbGuardrailSet): GuardrailSet {
  return {
    id: row.id,
    name: row.name,
    purpose: row.purpose,
    workflow: row.workflow,
    target: row.target,
    successDefinition: row.success_definition,
    inputMode: row.input_mode,
    evaluationCadence: row.evaluation_cadence,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    guardrails: [...(row.guardrails ?? [])]
      .sort((a, b) => (a.position ?? 0) - (b.position ?? 0))
      .map(toGuardrail),
  };
}

function workspaceValidationError(workspace: GuardrailSet) {
  if (
    !workspace.purpose.trim() ||
    !workspace.workflow.trim() ||
    !workspace.target.trim() ||
    !workspace.successDefinition.trim()
  ) {
    return "Purpose, workflow, target, and proof of success are required.";
  }
  const active = workspace.guardrails.filter((rule) => rule.active);
  if (!active.length) return "At least one active guardrail is required.";
  for (const rule of active) {
    if (!rule.title.trim() || !rule.description.trim()) {
      return "Every active guardrail needs a title and testable condition.";
    }
    if (rule.metricType === "threshold" && !Number.isFinite(rule.metricConfig?.threshold)) {
      return `Set a numeric threshold for “${rule.title}”.`;
    }
    if (rule.metricType === "checklist" && !(rule.metricConfig?.checklist ?? []).length) {
      return `Add at least one checklist item for “${rule.title}”.`;
    }
  }
  return null;
}

const verdictMeta: Record<
  Verdict,
  { label: string; icon: typeof CheckCircle2; className: string; plain: string }
> = {
  pass: {
    label: "Pass",
    icon: CheckCircle2,
    className: "verdict-pass",
    plain: "Safe to proceed",
  },
  watch: {
    label: "Watch",
    icon: AlertTriangle,
    className: "verdict-watch",
    plain: "Clarify before proceeding",
  },
  block: {
    label: "Block",
    icon: XCircle,
    className: "verdict-block",
    plain: "Stop and correct",
  },
};

function Index() {
  const [workspace, setWorkspace] = useState<GuardrailSet>(SAMPLE_SET);
  const [setup, setSetup] = useState<SetupDraft>(setupFromSet(SAMPLE_SET));
  const [stage, setStage] = useState<Stage>("define");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [checkText, setCheckText] = useState(
    "Publish a landing page saying teams reduce incident triage time by 43%, then ask readers to join the pilot.",
  );
  const [evidence, setEvidence] = useState("");
  const [structuredEvidence, setStructuredEvidence] = useState<StructuredEvidence>({
    metrics: {},
    binary: {},
    checklist: {},
  });
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [authOpen, setAuthOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [authSent, setAuthSent] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const workspaceRef = useRef<HTMLDivElement>(null);

  const flash = useCallback((message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 2600);
  }, []);

  useEffect(() => {
    const local = loadLocalWorkspace();
    setWorkspace(local);
    setSetup(setupFromSet(local));
  }, []);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(workspace));
  }, [workspace]);

  useEffect(() => {
    if (!supabase) return;
    void supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      if (nextSession) setAuthOpen(false);
    });
    return () => data.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    const user = session?.user;
    const client = supabase;
    if (!user || !client) return;

    let cancelled = false;
    const loadLatest = async () => {
      setBusy("load");
      const { data, error } = await client
        .from("guardrail_sets")
        .select("*, guardrails(*)")
        .eq("user_id", user.id)
        .order("updated_at", { ascending: false })
        .limit(1)
        .maybeSingle();
      if (cancelled) return;
      setBusy(null);
      if (error) {
        flash("Cloud load failed — local copy is still safe");
        return;
      }
      if (data) {
        const cloud = toSet(data as DbGuardrailSet);
        setWorkspace(cloud);
        setSetup(setupFromSet(cloud));
        flash("Cloud workspace loaded");
      }
    };

    void loadLatest();
    return () => {
      cancelled = true;
    };
  }, [flash, session?.user]);

  const completion = useMemo(() => {
    const required = [setup.purpose, setup.workflow, setup.target, setup.successDefinition];
    return Math.round((required.filter((item) => item.trim()).length / required.length) * 100);
  }, [setup]);

  const criticalCount = workspace.guardrails.filter(
    (item) => item.active && item.criticality === "critical",
  ).length;
  const blockingCount = workspace.guardrails.filter(
    (item) => item.active && item.enforcement === "block",
  ).length;

  async function sendMagicLink() {
    if (!supabase || !email.trim()) return;
    setBusy("auth");
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: window.location.origin },
    });
    setBusy(null);
    if (error) {
      flash(error.message);
      return;
    }
    setAuthSent(true);
  }

  async function signOut() {
    if (!supabase) return;
    await supabase.auth.signOut();
    setSession(null);
    flash("Signed out — local workspace remains available");
  }

  const scrollToWorkspace = () => {
    workspaceRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  async function buildGuardrails() {
    if (
      !setup.purpose.trim() ||
      !setup.workflow.trim() ||
      !setup.target.trim() ||
      !setup.successDefinition.trim()
    ) {
      flash("Add purpose, workflow, target, and proof of success first");
      return;
    }

    setBusy("infer");
    let guardrails: Guardrail[] | null = null;

    if (supabase && session) {
      const { data, error } = await supabase.functions.invoke(EDGE_FUNCTIONS.inferGuardrails, {
        body: setup,
      });
      if (!error && Array.isArray(data?.guardrails)) {
        guardrails = data.guardrails.map((item: Partial<Guardrail>) => ({
          id: item.id ?? uid("guardrail"),
          title: item.title ?? "Untitled guardrail",
          description: item.description ?? "",
          criticality: item.criticality ?? "important",
          enforcement: item.enforcement ?? "warn",
          targetScope: item.targetScope ?? "output",
          metricType: item.metricType ?? "evidence",
          metricConfig: item.metricConfig,
          active: item.active ?? true,
          source: "ai",
        }));
      }
    }

    if (!guardrails) {
      guardrails = inferGuardrailsLocally(setup);
      flash(
        session
          ? "AI was unavailable; safe local inference used"
          : "Local draft created — sign in to use AI inference",
      );
    }

    const now = new Date().toISOString();
    const next: GuardrailSet = {
      id: workspace.id === "sample" ? uid("set") : workspace.id,
      name: setup.name.trim() || "My guardrail set",
      purpose: setup.purpose.trim(),
      workflow: setup.workflow.trim(),
      target: setup.target.trim(),
      successDefinition: setup.successDefinition.trim(),
      inputMode: setup.inputMode,
      evaluationCadence: setup.evaluationCadence,
      guardrails,
      createdAt: workspace.id === "sample" ? now : workspace.createdAt,
      updatedAt: now,
    };
    setWorkspace(next);
    setBusy(null);
    setStage("guardrails");
  }

  function patchGuardrail(id: string, patch: Partial<Guardrail>) {
    setWorkspace((current) => ({
      ...current,
      updatedAt: new Date().toISOString(),
      guardrails: current.guardrails.map((item) => (item.id === id ? { ...item, ...patch } : item)),
    }));
  }

  function addGuardrail() {
    const next: Guardrail = {
      id: uid("guardrail"),
      title: "New guardrail",
      description: "State the condition that must remain true.",
      criticality: "important",
      enforcement: "warn",
      targetScope: "output",
      metricType: "evidence",
      active: true,
      source: "user",
    };
    setWorkspace((current) => ({
      ...current,
      guardrails: [...current.guardrails, next],
      updatedAt: new Date().toISOString(),
    }));
  }

  function removeGuardrail(id: string) {
    setWorkspace((current) => ({
      ...current,
      guardrails: current.guardrails.filter((item) => item.id !== id),
      updatedAt: new Date().toISOString(),
    }));
  }

  async function saveCloud() {
    const invalid = workspaceValidationError(workspace);
    if (invalid) {
      flash(invalid);
      return;
    }
    if (!supabase || !session) {
      setAuthOpen(true);
      return;
    }
    setBusy("save");
    const payload = {
      id: workspace.id,
      name: workspace.name,
      purpose: workspace.purpose,
      workflow: workspace.workflow,
      target: workspace.target,
      success_definition: workspace.successDefinition,
      input_mode: workspace.inputMode,
      evaluation_cadence: workspace.evaluationCadence,
      guardrails: workspace.guardrails.map((item, index) => ({
        id: item.id,
        title: item.title,
        description: item.description,
        criticality: item.criticality,
        enforcement: item.enforcement,
        target_scope: item.targetScope,
        metric_type: item.metricType,
        metric_config: item.metricConfig ?? {},
        active: item.active,
        source: item.source,
        position: index,
      })),
    };
    const { error } = await supabase.rpc("save_guardrail_set", { payload });
    setBusy(null);
    if (error) {
      flash(`Cloud save failed: ${error.message}`);
      return;
    }
    flash("Saved to your private cloud workspace");
  }

  async function runEvaluation() {
    const invalid = workspaceValidationError(workspace);
    if (invalid) {
      flash(invalid);
      return;
    }
    if (!checkText.trim()) {
      flash("Describe the action or output to check");
      return;
    }
    setBusy("evaluate");
    let result: Evaluation | null = null;
    let cloudError: string | null = null;

    if (supabase && session) {
      const { data, error } = await supabase.functions.invoke(EDGE_FUNCTIONS.evaluate, {
        body: {
          workspace,
          input: {
            text: checkText.trim(),
            evidence: evidence.trim(),
            ...structuredEvidence,
          },
        },
      });
      if (!error && data?.verdict) {
        result = {
          ...data,
          evaluatedAt: data.evaluatedAt ?? new Date().toISOString(),
          mode: data.mode ?? "ai",
        } as Evaluation;
      } else if (error) {
        cloudError = error.message;
      }
    }

    if (!result) {
      result = evaluateLocally(workspace, {
        text: checkText.trim(),
        evidence: evidence.trim(),
        structured: structuredEvidence,
      });
      flash(
        session
          ? `${cloudError ?? "Cloud judge unavailable"}; deterministic preview used`
          : "Rules preview used — sign in for semantic AI judgment",
      );
    }

    setEvaluation(result);
    setBusy(null);
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <Nav
        configured={isSupabaseConfigured}
        session={session}
        onOpenAuth={() => setAuthOpen(true)}
        onSignOut={signOut}
        onStart={scrollToWorkspace}
      />

      <section className="hero-shell">
        <div className="hero-grid" />
        <div className="relative mx-auto grid max-w-7xl gap-12 px-5 pb-24 pt-20 sm:px-8 lg:grid-cols-[1.02fr_.98fr] lg:items-center lg:px-10 lg:pb-28 lg:pt-28">
          <div>
            <div className="eyebrow">
              <ShieldCheck size={15} />
              Constraint control for real work
            </div>
            <h1 className="mt-6 max-w-3xl text-balance font-serif text-5xl font-semibold leading-[0.98] tracking-[-0.045em] sm:text-6xl lg:text-[74px]">
              Stop important work from quietly drifting.
            </h1>
            <p className="mt-7 max-w-2xl text-balance text-lg leading-8 text-muted-foreground sm:text-xl">
              Define what must stay true once. DriftGuard checks each decision or output against it,
              returns <strong className="text-foreground">Pass, Watch, or Block</strong>, and gives
              the smallest correction needed.
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <button className="primary-cta" onClick={scrollToWorkspace}>
                Build my guardrails
                <ArrowRight size={18} />
              </button>
              <button
                className="secondary-cta"
                onClick={() => {
                  setStage("check");
                  scrollToWorkspace();
                }}
              >
                Try the live check
              </button>
            </div>
            <div className="mt-8 flex flex-wrap gap-x-6 gap-y-3 text-sm text-muted-foreground">
              <span className="inline-flex items-center gap-2">
                <Check size={15} /> Setup in under 60 seconds
              </span>
              <span className="inline-flex items-center gap-2">
                <Check size={15} /> Human-owned constraints
              </span>
              <span className="inline-flex items-center gap-2">
                <Check size={15} /> AI never overrides a block
              </span>
            </div>
          </div>

          <HeroJudgeCard />
        </div>
      </section>

      <section className="border-y border-border/70 bg-card/45">
        <div className="mx-auto grid max-w-7xl gap-0 px-5 sm:px-8 md:grid-cols-3 lg:px-10">
          <ValueStep
            number="01"
            title="State the outcome"
            text="Describe the purpose, target user, workflow and proof of success in plain language."
          />
          <ValueStep
            number="02"
            title="Lock the constraints"
            text="Accept AI-inferred guardrails or set exact criticality, enforcement and evidence rules."
          />
          <ValueStep
            number="03"
            title="Judge every step"
            text="Paste an action or output. Get a traceable verdict and the smallest safe correction."
          />
        </div>
      </section>

      <section ref={workspaceRef} className="scroll-mt-4 px-5 py-20 sm:px-8 lg:px-10 lg:py-28">
        <div className="mx-auto max-w-7xl">
          <div className="mb-10 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="eyebrow">
                <Activity size={15} />
                Live workspace
              </div>
              <h2 className="mt-4 font-serif text-4xl font-semibold tracking-tight sm:text-5xl">
                One control loop. No configuration maze.
              </h2>
              <p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground">
                Start with four answers. Advanced controls appear only when you need exact
                enforcement, metrics or integration behavior.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill icon={Target} text={`${criticalCount} critical`} />
              <StatusPill icon={Lock} text={`${blockingCount} blocking`} />
              <button className="save-button" onClick={saveCloud} disabled={busy === "save"}>
                {busy === "save" ? (
                  <RefreshCw className="animate-spin" size={15} />
                ) : (
                  <Cloud size={15} />
                )}
                {session ? "Save cloud" : "Enable cloud sync"}
              </button>
            </div>
          </div>

          <div className="workspace-shell">
            <WorkspaceTabs stage={stage} onChange={setStage} />

            <div className="grid min-h-[650px] lg:grid-cols-[270px_1fr]">
              <WorkspaceSummary workspace={workspace} stage={stage} />

              <div className="min-w-0 p-5 sm:p-7 lg:p-10">
                {stage === "define" && (
                  <DefinePanel
                    setup={setup}
                    completion={completion}
                    advancedOpen={advancedOpen}
                    busy={busy === "infer"}
                    onChange={setSetup}
                    onToggleAdvanced={() => setAdvancedOpen((value) => !value)}
                    onBuild={buildGuardrails}
                  />
                )}

                {stage === "guardrails" && (
                  <GuardrailsPanel
                    workspace={workspace}
                    onPatch={patchGuardrail}
                    onAdd={addGuardrail}
                    onRemove={removeGuardrail}
                    onContinue={() => setStage("check")}
                  />
                )}

                {stage === "check" && (
                  <CheckPanel
                    workspace={workspace}
                    text={checkText}
                    evidence={evidence}
                    structuredEvidence={structuredEvidence}
                    evaluation={evaluation}
                    busy={busy === "evaluate"}
                    onText={setCheckText}
                    onEvidence={setEvidence}
                    onStructuredEvidence={setStructuredEvidence}
                    onRun={runEvaluation}
                    onEdit={() => setStage("guardrails")}
                  />
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      <IntegritySection />
      <InputSection />
      <Footer onStart={scrollToWorkspace} />

      {authOpen && (
        <AuthModal
          email={email}
          sent={authSent}
          busy={busy === "auth"}
          configured={isSupabaseConfigured}
          configIssue={supabaseConfigIssue}
          onEmail={setEmail}
          onSend={sendMagicLink}
          onClose={() => {
            setAuthOpen(false);
            setAuthSent(false);
          }}
        />
      )}

      {notice && <div className="toast">{notice}</div>}
    </main>
  );
}

function Nav({
  configured,
  session,
  onOpenAuth,
  onSignOut,
  onStart,
}: {
  configured: boolean;
  session: Session | null;
  onOpenAuth: () => void;
  onSignOut: () => void;
  onStart: () => void;
}) {
  return (
    <header className="sticky top-0 z-40 border-b border-border/75 bg-background/88 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8 lg:px-10">
        <button
          className="flex items-center gap-2.5"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        >
          <span className="brand-mark">
            <ShieldCheck size={18} />
          </span>
          <span className="font-serif text-xl font-semibold tracking-tight">DriftGuard</span>
        </button>
        <nav className="hidden items-center gap-7 text-sm text-muted-foreground md:flex">
          <button onClick={onStart} className="hover:text-foreground">
            How it works
          </button>
          <a href="#integrity" className="hover:text-foreground">
            Integrity
          </a>
          <a href="#inputs" className="hover:text-foreground">
            Input options
          </a>
        </nav>
        <div className="flex items-center gap-2">
          {session ? (
            <>
              <span className="hidden max-w-44 truncate text-xs text-muted-foreground sm:block">
                {session.user.email}
              </span>
              <button className="nav-button" onClick={onSignOut} aria-label="Sign out">
                <LogOut size={16} />
              </button>
            </>
          ) : (
            <button className="nav-button px-3" onClick={onOpenAuth} disabled={!configured}>
              {configured ? "Sign in" : "Local demo"}
            </button>
          )}
          <button className="nav-primary" onClick={onStart}>
            Start
          </button>
        </div>
      </div>
    </header>
  );
}

function HeroJudgeCard() {
  return (
    <div className="relative mx-auto w-full max-w-xl">
      <div className="absolute -inset-5 rounded-[32px] bg-primary/6 blur-2xl" />
      <div className="relative overflow-hidden rounded-[26px] border border-border bg-card shadow-2xl shadow-black/10">
        <div className="flex items-center justify-between border-b border-border bg-muted/45 px-5 py-4">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <CircleGauge size={17} /> Live judgment
          </div>
          <span className="status-live">
            <span /> Evaluating
          </span>
        </div>
        <div className="space-y-5 p-5 sm:p-7">
          <div className="rounded-xl border border-border bg-background p-4">
            <p className="field-label">Proposed action</p>
            <p className="mt-2 text-sm leading-6">
              Publish “cuts triage time by 43%” before the pilot data is complete.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-[140px_1fr]">
            <div className="verdict-block rounded-xl p-4">
              <XCircle size={22} />
              <p className="mt-4 text-xs font-semibold uppercase tracking-[0.16em]">Block</p>
              <p className="mt-1 text-sm font-medium">74 risk</p>
            </div>
            <div className="rounded-xl border border-border p-4">
              <p className="field-label">Why</p>
              <p className="mt-2 text-sm leading-6">
                A blocking constraint requires every performance claim to be measured, sourced or
                labeled as a hypothesis.
              </p>
            </div>
          </div>
          <div className="rounded-xl border border-primary/20 bg-primary/[0.035] p-4">
            <p className="field-label">Smallest safe correction</p>
            <p className="mt-2 text-sm font-medium leading-6">
              Replace the metric with “designed to reduce triage time” until pilot measurements are
              available.
            </p>
          </div>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>4 constraints checked · exact snapshot retained</span>
            <span className="inline-flex items-center gap-1.5">
              <BrainCircuit size={14} /> AI + deterministic precedence
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function ValueStep({ number, title, text }: { number: string; title: string; text: string }) {
  return (
    <div className="border-b border-border/70 py-8 md:border-b-0 md:border-r md:px-8 md:first:pl-0 md:last:border-r-0 md:last:pr-0">
      <p className="font-mono text-xs text-primary">{number}</p>
      <h3 className="mt-3 font-serif text-xl font-semibold">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{text}</p>
    </div>
  );
}

function WorkspaceTabs({ stage, onChange }: { stage: Stage; onChange: (stage: Stage) => void }) {
  const tabs: Array<{ id: Stage; label: string; note: string }> = [
    { id: "define", label: "Define", note: "Intent" },
    { id: "guardrails", label: "Guardrails", note: "Constraints" },
    { id: "check", label: "Check", note: "Judgment" },
  ];
  return (
    <div className="grid border-b border-border bg-muted/35 sm:grid-cols-3">
      {tabs.map((tab, index) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`workspace-tab ${stage === tab.id ? "workspace-tab-active" : ""}`}
        >
          <span className="tab-number">{index + 1}</span>
          <span className="text-left">
            <span className="block text-sm font-semibold">{tab.label}</span>
            <span className="block text-xs text-muted-foreground">{tab.note}</span>
          </span>
        </button>
      ))}
    </div>
  );
}

function WorkspaceSummary({ workspace, stage }: { workspace: GuardrailSet; stage: Stage }) {
  return (
    <aside className="border-b border-border bg-muted/20 p-5 sm:p-7 lg:border-b-0 lg:border-r">
      <p className="field-label">Active control set</p>
      <h3 className="mt-3 font-serif text-2xl font-semibold leading-tight">{workspace.name}</h3>
      <p className="mt-3 line-clamp-4 text-sm leading-6 text-muted-foreground">
        {workspace.purpose}
      </p>

      <div className="mt-7 space-y-3">
        <SummaryRow label="Target" value={workspace.target} />
        <SummaryRow label="Input" value={inputModeLabel(workspace.inputMode)} />
        <SummaryRow label="Checkpoint" value={cadenceLabel(workspace.evaluationCadence)} />
      </div>

      <div className="mt-8 border-t border-border pt-6">
        <p className="field-label">Control loop</p>
        <div className="mt-4 space-y-4">
          {[
            ["define", "Intent captured"],
            [
              "guardrails",
              `${workspace.guardrails.filter((item) => item.active).length} constraints active`,
            ],
            ["check", "Verdict + correction"],
          ].map(([id, label], index) => (
            <div key={id} className="flex items-center gap-3">
              <span className={`loop-dot ${stage === id ? "loop-dot-active" : ""}`}>
                {index + 1}
              </span>
              <span
                className={`text-sm ${stage === id ? "font-semibold" : "text-muted-foreground"}`}
              >
                {label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 line-clamp-2 text-sm font-medium">{value || "Not defined"}</p>
    </div>
  );
}

function DefinePanel({
  setup,
  completion,
  advancedOpen,
  busy,
  onChange,
  onToggleAdvanced,
  onBuild,
}: {
  setup: SetupDraft;
  completion: number;
  advancedOpen: boolean;
  busy: boolean;
  onChange: (next: SetupDraft) => void;
  onToggleAdvanced: () => void;
  onBuild: () => void;
}) {
  const patch = <K extends keyof SetupDraft>(field: K, value: SetupDraft[K]) =>
    onChange({ ...setup, [field]: value });
  return (
    <div className="mx-auto max-w-3xl">
      <PanelHeader
        kicker="Step 1 · Intent"
        title="Describe the work in plain language."
        text="These four answers are the source of truth. AI may structure them, but it cannot silently replace them."
      />

      <div className="mt-8 grid gap-5 sm:grid-cols-2">
        <Field label="Workspace name" hint="A reusable control set">
          <input
            value={setup.name}
            onChange={(event) => patch("name", event.target.value)}
            placeholder="e.g. Customer-facing launch"
          />
        </Field>
        <Field label="Purpose" hint="What outcome must this work cause?" required>
          <input
            value={setup.purpose}
            onChange={(event) => patch("purpose", event.target.value)}
            placeholder="Ship a credible page that earns qualified action"
          />
        </Field>
        <Field label="Workflow" hint="What sequence are you controlling?" required>
          <input
            value={setup.workflow}
            onChange={(event) => patch("workflow", event.target.value)}
            placeholder="Draft → verify → publish → review"
          />
        </Field>
        <Field label="Target" hint="Who or what must receive value?" required>
          <input
            value={setup.target}
            onChange={(event) => patch("target", event.target.value)}
            placeholder="A skeptical buyer deciding whether to act"
          />
        </Field>
        <div className="sm:col-span-2">
          <Field
            label="Proof of success"
            hint="What observable evidence means the purpose was achieved?"
            required
          >
            <textarea
              rows={3}
              value={setup.successDefinition}
              onChange={(event) => patch("successDefinition", event.target.value)}
              placeholder="The target user understands the problem and completes the intended next step"
            />
          </Field>
        </div>
        <div className="sm:col-span-2">
          <Field label="What must never happen?" hint="Optional. One non-negotiable per line.">
            <textarea
              rows={3}
              value={setup.mustNotHappen}
              onChange={(event) => patch("mustNotHappen", event.target.value)}
              placeholder={
                "No unsupported claims\nNo private customer information\nNo action that optimizes activity over user value"
              }
            />
          </Field>
        </div>
      </div>

      <button className="advanced-toggle" onClick={onToggleAdvanced}>
        <span className="inline-flex items-center gap-2">
          <Gauge size={16} /> Advanced control
        </span>
        <ChevronDown className={advancedOpen ? "rotate-180" : ""} size={17} />
      </button>

      {advancedOpen && (
        <div className="advanced-panel">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Input capture" hint="How work enters the judgment layer">
              <select
                value={setup.inputMode}
                onChange={(event) => patch("inputMode", event.target.value as InputMode)}
              >
                <option value="prompt">Plain-language check-in</option>
                <option value="checklist">Structured checklist</option>
                <option value="metric">Metric submission</option>
                <option value="api">API / webhook event</option>
              </select>
            </Field>
            <Field
              label="Evaluation checkpoint"
              hint="When an app or integration should submit a check"
            >
              <select
                value={setup.evaluationCadence}
                onChange={(event) =>
                  patch("evaluationCadence", event.target.value as EvaluationCadence)
                }
              >
                <option value="manual">Manual check in DriftGuard</option>
                <option value="before-action">Integration: before critical action</option>
                <option value="after-output">Integration: after each output</option>
                <option value="daily">Integration: daily workflow review</option>
              </select>
            </Field>
          </div>
          <p className="mt-5 text-sm leading-6 text-muted-foreground">
            In-app checks are manual. API or webhook integrations enforce the selected checkpoint by
            submitting the current work and evidence; DriftGuard does not silently monitor other
            tools. Exact strictness, criticality, target scope and metrics are set per guardrail in
            the next step.
          </p>
        </div>
      )}

      <div className="mt-8 flex flex-col gap-4 border-t border-border pt-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="h-2 w-28 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${completion}%` }}
            />
          </div>
          <span className="text-xs font-medium text-muted-foreground">{completion}% ready</span>
        </div>
        <button className="primary-cta" onClick={onBuild} disabled={busy}>
          {busy ? <RefreshCw className="animate-spin" size={18} /> : <Sparkles size={18} />}
          Infer my guardrails
        </button>
      </div>
    </div>
  );
}

function GuardrailsPanel({
  workspace,
  onPatch,
  onAdd,
  onRemove,
  onContinue,
}: {
  workspace: GuardrailSet;
  onPatch: (id: string, patch: Partial<Guardrail>) => void;
  onAdd: () => void;
  onRemove: (id: string) => void;
  onContinue: () => void;
}) {
  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <PanelHeader
          kicker="Step 2 · Constraints"
          title="Lock what must remain true."
          text="Criticality says how much the constraint matters. Enforcement says what the system must do when it fails."
        />
        <button className="secondary-cta shrink-0" onClick={onAdd}>
          <Plus size={17} /> Add guardrail
        </button>
      </div>

      <div className="mt-8 space-y-4">
        {workspace.guardrails.map((rule, index) => (
          <GuardrailEditor
            key={rule.id}
            rule={rule}
            index={index}
            onPatch={onPatch}
            onRemove={onRemove}
          />
        ))}
        {workspace.guardrails.length === 0 && (
          <div className="empty-state">
            <ShieldCheck size={24} />
            <h3>No guardrails yet</h3>
            <p>Add at least one condition that must remain true.</p>
          </div>
        )}
      </div>

      <div className="mt-8 flex flex-col gap-4 border-t border-border pt-6 sm:flex-row sm:items-center sm:justify-between">
        <p className="max-w-xl text-sm leading-6 text-muted-foreground">
          Precedence is deterministic: any violated blocking guardrail returns{" "}
          <strong className="text-foreground">Block</strong>, regardless of the AI score.
        </p>
        <button
          className="primary-cta"
          onClick={onContinue}
          disabled={!workspace.guardrails.length}
        >
          Run a live check <ChevronRight size={18} />
        </button>
      </div>
    </div>
  );
}

function GuardrailEditor({
  rule,
  index,
  onPatch,
  onRemove,
}: {
  rule: Guardrail;
  index: number;
  onPatch: (id: string, patch: Partial<Guardrail>) => void;
  onRemove: (id: string) => void;
}) {
  const [open, setOpen] = useState(index < 2);
  return (
    <article className={`guardrail-card ${!rule.active ? "opacity-55" : ""}`}>
      <div className="flex items-start gap-3 p-4 sm:p-5">
        <button
          className="mt-1 text-muted-foreground"
          onClick={() => setOpen((value) => !value)}
          aria-label="Toggle guardrail"
        >
          <ChevronRight className={open ? "rotate-90" : ""} size={18} />
        </button>
        <span className="guardrail-index">{String(index + 1).padStart(2, "0")}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0 flex-1">
              <input
                className="guardrail-title"
                value={rule.title}
                onChange={(event) => onPatch(rule.id, { title: event.target.value })}
              />
              {!open && (
                <p className="mt-1 line-clamp-1 text-sm text-muted-foreground">
                  {rule.description}
                </p>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <RuleBadge value={rule.criticality} />
              <RuleBadge value={rule.enforcement} />
              <button
                className={`toggle-switch ${rule.active ? "toggle-active" : ""}`}
                onClick={() => onPatch(rule.id, { active: !rule.active })}
                aria-label={rule.active ? "Disable guardrail" : "Enable guardrail"}
              >
                <span />
              </button>
            </div>
          </div>

          {open && (
            <div className="mt-5 border-t border-border pt-5">
              <Field label="Condition" hint="What must be true, observable and testable?">
                <textarea
                  rows={2}
                  value={rule.description}
                  onChange={(event) => onPatch(rule.id, { description: event.target.value })}
                />
              </Field>
              <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <Field label="Criticality" hint="Business importance">
                  <select
                    value={rule.criticality}
                    onChange={(event) =>
                      onPatch(rule.id, { criticality: event.target.value as Criticality })
                    }
                  >
                    <option value="critical">Critical</option>
                    <option value="important">Important</option>
                    <option value="preference">Preference</option>
                  </select>
                </Field>
                <Field label="Enforcement" hint="System response">
                  <select
                    value={rule.enforcement}
                    onChange={(event) =>
                      onPatch(rule.id, { enforcement: event.target.value as Enforcement })
                    }
                  >
                    <option value="block">Block</option>
                    <option value="warn">Warn</option>
                    <option value="advise">Advise</option>
                  </select>
                </Field>
                <Field label="Target scope" hint="What is judged">
                  <select
                    value={rule.targetScope}
                    onChange={(event) =>
                      onPatch(rule.id, { targetScope: event.target.value as TargetScope })
                    }
                  >
                    <option value="action">Action</option>
                    <option value="output">Output</option>
                    <option value="workflow">Workflow</option>
                    <option value="session">Session</option>
                  </select>
                </Field>
                <Field label="Metric" hint="How it is proven">
                  <select
                    value={rule.metricType}
                    onChange={(event) => {
                      const metricType = event.target.value as MetricType;
                      const metricConfig =
                        metricType === "threshold"
                          ? { operator: "gte" as const, threshold: 0, unit: "" }
                          : metricType === "checklist"
                            ? { checklist: ["Required item"] }
                            : {};
                      onPatch(rule.id, { metricType, metricConfig });
                    }}
                  >
                    <option value="evidence">Evidence</option>
                    <option value="binary">Yes / no</option>
                    <option value="threshold">Threshold</option>
                    <option value="checklist">Checklist</option>
                  </select>
                </Field>
              </div>

              {rule.metricType === "threshold" && (
                <div className="mt-4 grid gap-4 rounded-xl border border-border bg-muted/25 p-4 sm:grid-cols-3">
                  <Field label="Comparison" hint="Pass condition">
                    <select
                      value={rule.metricConfig?.operator ?? "gte"}
                      onChange={(event) =>
                        onPatch(rule.id, {
                          metricConfig: {
                            ...rule.metricConfig,
                            operator: event.target.value as "gte" | "lte" | "eq",
                          },
                        })
                      }
                    >
                      <option value="gte">At least (≥)</option>
                      <option value="lte">At most (≤)</option>
                      <option value="eq">Exactly (=)</option>
                    </select>
                  </Field>
                  <Field label="Threshold" hint="Required numeric value">
                    <input
                      type="number"
                      step="any"
                      value={rule.metricConfig?.threshold ?? ""}
                      onChange={(event) =>
                        onPatch(rule.id, {
                          metricConfig: {
                            ...rule.metricConfig,
                            threshold:
                              event.target.value === "" ? undefined : Number(event.target.value),
                          },
                        })
                      }
                    />
                  </Field>
                  <Field label="Unit" hint="Optional label">
                    <input
                      value={rule.metricConfig?.unit ?? ""}
                      onChange={(event) =>
                        onPatch(rule.id, {
                          metricConfig: { ...rule.metricConfig, unit: event.target.value },
                        })
                      }
                      placeholder="%, minutes, defects"
                    />
                  </Field>
                </div>
              )}

              {rule.metricType === "checklist" && (
                <div className="mt-4 rounded-xl border border-border bg-muted/25 p-4">
                  <Field
                    label="Required checklist items"
                    hint="One independently testable item per line"
                  >
                    <textarea
                      rows={4}
                      value={(rule.metricConfig?.checklist ?? []).join("\n")}
                      onChange={(event) =>
                        onPatch(rule.id, {
                          metricConfig: {
                            checklist: event.target.value
                              .split("\n")
                              .map((item) => item.trim())
                              .filter(Boolean)
                              .slice(0, 20),
                          },
                        })
                      }
                      placeholder={
                        "Claim has a source\nTarget user is explicit\nNo private data appears"
                      }
                    />
                  </Field>
                </div>
              )}

              <div className="mt-4 flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Source: {rule.source}</span>
                <button className="danger-link" onClick={() => onRemove(rule.id)}>
                  <Trash2 size={14} /> Delete
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </article>
  );
}

function RuleBadge({ value }: { value: string }) {
  return <span className={`rule-badge rule-${value}`}>{value}</span>;
}

function StructuredEvidenceFields({
  workspace,
  value,
  onChange,
}: {
  workspace: GuardrailSet;
  value: StructuredEvidence;
  onChange: (next: StructuredEvidence) => void;
}) {
  const rules = workspace.guardrails.filter(
    (rule) => rule.active && rule.metricType !== "evidence",
  );
  if (!rules.length) return null;

  return (
    <div className="rounded-xl border border-border bg-muted/20 p-4">
      <div className="mb-4">
        <p className="field-label">Structured proof</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          These values are enforced deterministically. AI cannot reinterpret them.
        </p>
      </div>
      <div className="space-y-4">
        {rules.map((rule) => {
          if (rule.metricType === "threshold") {
            return (
              <Field
                key={rule.id}
                label={rule.title}
                hint={`${rule.metricConfig?.operator ?? "gte"} ${rule.metricConfig?.threshold ?? "not set"} ${rule.metricConfig?.unit ?? ""}`.trim()}
              >
                <input
                  type="number"
                  step="any"
                  value={value.metrics[rule.id] ?? ""}
                  onChange={(event) => {
                    const metrics = { ...value.metrics };
                    if (event.target.value === "") delete metrics[rule.id];
                    else metrics[rule.id] = Number(event.target.value);
                    onChange({ ...value, metrics });
                  }}
                  placeholder="Enter observed value"
                />
              </Field>
            );
          }

          if (rule.metricType === "binary") {
            const current = value.binary[rule.id];
            return (
              <Field key={rule.id} label={rule.title} hint="Explicit yes/no evidence">
                <select
                  value={typeof current === "boolean" ? String(current) : ""}
                  onChange={(event) => {
                    const binary = { ...value.binary };
                    if (!event.target.value) delete binary[rule.id];
                    else binary[rule.id] = event.target.value === "true";
                    onChange({ ...value, binary });
                  }}
                >
                  <option value="">Not answered</option>
                  <option value="true">Yes — condition met</option>
                  <option value="false">No — condition failed</option>
                </select>
              </Field>
            );
          }

          const items = rule.metricConfig?.checklist ?? [];
          return (
            <div key={rule.id} className="rounded-lg border border-border bg-background p-3">
              <p className="text-sm font-semibold">{rule.title}</p>
              {items.length ? (
                <div className="mt-3 space-y-2">
                  {items.map((item) => {
                    const current = value.checklist[rule.id]?.[item];
                    return (
                      <label
                        key={item}
                        className="grid gap-2 sm:grid-cols-[1fr_170px] sm:items-center"
                      >
                        <span className="text-sm leading-5 text-muted-foreground">{item}</span>
                        <select
                          value={typeof current === "boolean" ? String(current) : ""}
                          onChange={(event) => {
                            const checklist = {
                              ...value.checklist,
                              [rule.id]: { ...(value.checklist[rule.id] ?? {}) },
                            };
                            if (!event.target.value) delete checklist[rule.id][item];
                            else checklist[rule.id][item] = event.target.value === "true";
                            onChange({ ...value, checklist });
                          }}
                        >
                          <option value="">Not checked</option>
                          <option value="true">Pass</option>
                          <option value="false">Fail</option>
                        </select>
                      </label>
                    );
                  })}
                </div>
              ) : (
                <p className="mt-2 text-xs text-amber-700">Add checklist items in Step 2.</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CheckPanel({
  workspace,
  text,
  evidence,
  structuredEvidence,
  evaluation,
  busy,
  onText,
  onEvidence,
  onStructuredEvidence,
  onRun,
  onEdit,
}: {
  workspace: GuardrailSet;
  text: string;
  evidence: string;
  structuredEvidence: StructuredEvidence;
  evaluation: Evaluation | null;
  busy: boolean;
  onText: (value: string) => void;
  onEvidence: (value: string) => void;
  onStructuredEvidence: (value: StructuredEvidence) => void;
  onRun: () => void;
  onEdit: () => void;
}) {
  return (
    <div className="mx-auto max-w-5xl">
      <PanelHeader
        kicker="Step 3 · Judgment"
        title="Check the next action before drift compounds."
        text={`This evaluation uses ${workspace.guardrails.filter((item) => item.active).length} active guardrails and stores the exact constraint snapshot with the result.`}
      />

      <div className="mt-8 grid gap-6 xl:grid-cols-[.9fr_1.1fr]">
        <div className="space-y-5">
          <Field
            label="Action, decision or output"
            hint="Paste the actual work, not a summary of your intention."
            required
          >
            <textarea
              rows={8}
              value={text}
              onChange={(event) => onText(event.target.value)}
              placeholder="Describe what you are about to do or paste the output to evaluate…"
            />
          </Field>
          <Field
            label="Evidence"
            hint="Optional but decisive: source, metric, checklist result or link."
          >
            <textarea
              rows={4}
              value={evidence}
              onChange={(event) => onEvidence(event.target.value)}
              placeholder="e.g. Source: pilot measurement from 24 incidents; reviewed 6 July 2026"
            />
          </Field>
          <StructuredEvidenceFields
            workspace={workspace}
            value={structuredEvidence}
            onChange={onStructuredEvidence}
          />
          <div className="flex flex-col gap-3 sm:flex-row">
            <button className="primary-cta flex-1 justify-center" onClick={onRun} disabled={busy}>
              {busy ? <RefreshCw className="animate-spin" size={18} /> : <Zap size={18} />}
              Judge against constraints
            </button>
            <button className="secondary-cta justify-center" onClick={onEdit}>
              Edit guardrails
            </button>
          </div>
        </div>

        {evaluation ? (
          <EvaluationCard evaluation={evaluation} workspace={workspace} />
        ) : (
          <EvaluationPlaceholder />
        )}
      </div>
    </div>
  );
}

function EvaluationCard({
  evaluation,
  workspace,
}: {
  evaluation: Evaluation;
  workspace: GuardrailSet;
}) {
  const meta = verdictMeta[evaluation.verdict];
  const VerdictIcon = meta.icon;
  return (
    <div className="evaluation-card">
      <div className={`evaluation-head ${meta.className}`}>
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em]">Verdict</p>
          <div className="mt-2 flex items-center gap-3">
            <VerdictIcon size={28} />
            <span className="font-serif text-4xl font-semibold">{meta.label}</span>
          </div>
          <p className="mt-2 text-sm font-medium">{meta.plain}</p>
        </div>
        <div className="score-ring">
          <span className="text-2xl font-semibold">{evaluation.score}</span>
          <span className="text-[10px] uppercase tracking-wider">alignment</span>
        </div>
      </div>

      <div className="space-y-5 p-5 sm:p-6">
        <div>
          <p className="field-label">Decision summary</p>
          <p className="mt-2 text-base font-semibold leading-7">{evaluation.summary}</p>
        </div>
        <div className="rounded-xl border border-border bg-muted/30 p-4">
          <p className="field-label">Why</p>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{evaluation.reasoning}</p>
        </div>
        <div className="rounded-xl border border-primary/20 bg-primary/[0.035] p-4">
          <p className="field-label">Smallest safe correction</p>
          <p className="mt-2 text-sm font-semibold leading-6">{evaluation.correction}</p>
        </div>
        <div>
          <p className="field-label">Constraint trace</p>
          <div className="mt-3 space-y-2">
            {evaluation.findings.map((finding) => {
              const rule = workspace.guardrails.find((item) => item.id === finding.guardrailId);
              return (
                <div key={finding.guardrailId} className="finding-row">
                  <FindingIcon status={finding.status} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold">{rule?.title ?? "Guardrail"}</p>
                    <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
                      {finding.reason}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <div className="flex items-center justify-between border-t border-border pt-4 text-xs text-muted-foreground">
          <span>
            {evaluation.mode === "ai"
              ? "Semantic AI + deterministic enforcement"
              : evaluation.mode === "rules"
                ? "Deterministic structured evaluation"
                : "Local deterministic preview"}
          </span>
          <span>
            {new Date(evaluation.evaluatedAt).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        </div>
      </div>
    </div>
  );
}

function FindingIcon({ status }: { status: "met" | "unclear" | "violated" }) {
  if (status === "met") return <CheckCircle2 className="mt-0.5 text-emerald-600" size={17} />;
  if (status === "violated") return <XCircle className="mt-0.5 text-red-600" size={17} />;
  return <AlertTriangle className="mt-0.5 text-amber-600" size={17} />;
}

function EvaluationPlaceholder() {
  return (
    <div className="evaluation-placeholder">
      <div className="placeholder-icon">
        <BrainCircuit size={26} />
      </div>
      <h3 className="mt-5 font-serif text-2xl font-semibold">Your judgment trace appears here.</h3>
      <p className="mt-3 max-w-sm text-center text-sm leading-6 text-muted-foreground">
        You will receive one verdict, the reason tied to exact guardrails, and the smallest
        correction needed.
      </p>
      <div className="mt-7 grid w-full max-w-sm grid-cols-3 gap-2">
        <span className="mini-verdict verdict-pass">Pass</span>
        <span className="mini-verdict verdict-watch">Watch</span>
        <span className="mini-verdict verdict-block">Block</span>
      </div>
    </div>
  );
}

function IntegritySection() {
  const items = [
    {
      icon: Lock,
      title: "Deterministic enforcement",
      text: "A violated blocking guardrail always returns Block. Model confidence cannot soften it.",
    },
    {
      icon: Database,
      title: "Exact evaluation snapshots",
      text: "Every verdict retains the constraints, evidence and model mode used at that moment.",
    },
    {
      icon: ShieldCheck,
      title: "User-owned source of truth",
      text: "AI may infer or explain constraints, but changes require explicit user acceptance.",
    },
    {
      icon: CircleGauge,
      title: "Evidence-aware judgment",
      text: "Missing proof becomes uncertainty, not a fabricated pass. Unclear work returns Watch.",
    },
  ];
  return (
    <section id="integrity" className="border-y border-border bg-ink text-paper">
      <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:px-10 lg:py-24">
        <div className="grid gap-12 lg:grid-cols-[.8fr_1.2fr]">
          <div>
            <div className="eyebrow eyebrow-dark">
              <ShieldCheck size={15} /> Technical integrity
            </div>
            <h2 className="mt-5 max-w-xl font-serif text-4xl font-semibold tracking-tight sm:text-5xl">
              AI supplies judgment. It does not own the rules.
            </h2>
            <p className="mt-5 max-w-xl text-base leading-7 text-paper/65">
              The system separates semantic interpretation from enforcement precedence, so flexible
              judgment never becomes silent policy drift.
            </p>
          </div>
          <div className="grid gap-px overflow-hidden rounded-2xl border border-white/10 bg-white/10 sm:grid-cols-2">
            {items.map((item) => {
              const Icon = item.icon;
              return (
                <div key={item.title} className="bg-ink p-6 sm:p-7">
                  <Icon className="text-paper/75" size={21} />
                  <h3 className="mt-5 font-serif text-xl font-semibold">{item.title}</h3>
                  <p className="mt-3 text-sm leading-6 text-paper/60">{item.text}</p>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}

function InputSection() {
  const modes = [
    [
      "01",
      "Plain-language check-in",
      "Best default",
      "User pastes an action, decision or output and optional evidence.",
    ],
    [
      "02",
      "Structured checklist",
      "Repeatable work",
      "Required fields remove ambiguity for recurring operational workflows.",
    ],
    [
      "03",
      "Metric submission",
      "Measured systems",
      "Thresholds, counts and pass/fail values are evaluated without interpretation.",
    ],
    [
      "04",
      "API or webhook",
      "Automated workflows",
      "Tools submit events at the exact point a decision or output is produced.",
    ],
  ];
  return (
    <section id="inputs" className="px-5 py-20 sm:px-8 lg:px-10 lg:py-28">
      <div className="mx-auto max-w-7xl">
        <div className="max-w-3xl">
          <div className="eyebrow">
            <Zap size={15} /> Consistent input
          </div>
          <h2 className="mt-5 font-serif text-4xl font-semibold tracking-tight sm:text-5xl">
            Start with one box. Expand only when repetition justifies structure.
          </h2>
          <p className="mt-5 text-base leading-7 text-muted-foreground">
            The reliable progression is manual prompt → saved checklist → metric form → event
            integration. This preserves speed without sacrificing data quality.
          </p>
        </div>
        <div className="mt-10 grid gap-4 md:grid-cols-2">
          {modes.map(([number, title, tag, text]) => (
            <article key={number} className="input-option">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-primary">{number}</span>
                <span className="rule-badge rule-important">{tag}</span>
              </div>
              <h3 className="mt-6 font-serif text-2xl font-semibold">{title}</h3>
              <p className="mt-3 text-sm leading-6 text-muted-foreground">{text}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function Footer({ onStart }: { onStart: () => void }) {
  return (
    <footer className="border-t border-border bg-card/40 px-5 py-10 sm:px-8 lg:px-10">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="brand-mark">
              <ShieldCheck size={18} />
            </span>
            <span className="font-serif text-xl font-semibold">DriftGuard</span>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            Keep execution inside the constraints that actually matter.
          </p>
        </div>
        <button className="primary-cta" onClick={onStart}>
          Build a control set <ArrowRight size={18} />
        </button>
      </div>
    </footer>
  );
}

function AuthModal({
  email,
  sent,
  busy,
  configured,
  configIssue,
  onEmail,
  onSend,
  onClose,
}: {
  email: string;
  sent: boolean;
  busy: boolean;
  configured: boolean;
  configIssue: string | null;
  onEmail: (value: string) => void;
  onSend: () => void;
  onClose: () => void;
}) {
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Sign in">
      <div className="modal-card">
        <button className="modal-close" onClick={onClose} aria-label="Close">
          <X size={18} />
        </button>
        <div className="brand-mark">
          <ShieldCheck size={18} />
        </div>
        <h2 className="mt-5 font-serif text-3xl font-semibold">Keep your guardrails synced.</h2>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          Sign in by email. Your workspace remains usable locally even when cloud sync is
          unavailable.
        </p>
        {!configured ? (
          <div className="mt-6 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950">
            {configIssue ?? "Add the Supabase values from .env.example to enable authentication."}
          </div>
        ) : sent ? (
          <div className="mt-6 rounded-xl border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-950">
            Check your inbox for the secure sign-in link.
          </div>
        ) : (
          <div className="mt-6">
            <Field label="Email" hint="No password required">
              <input
                type="email"
                value={email}
                onChange={(event) => onEmail(event.target.value)}
                placeholder="you@example.com"
                onKeyDown={(event) => event.key === "Enter" && onSend()}
              />
            </Field>
            <button
              className="primary-cta mt-4 w-full justify-center"
              onClick={onSend}
              disabled={busy || !email.trim()}
            >
              {busy ? <RefreshCw className="animate-spin" size={17} /> : <ArrowRight size={17} />}
              Send magic link
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function PanelHeader({ kicker, title, text }: { kicker: string; title: string; text: string }) {
  return (
    <div className="max-w-3xl">
      <p className="field-label text-primary">{kicker}</p>
      <h3 className="mt-3 font-serif text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h3>
      <p className="mt-3 text-sm leading-6 text-muted-foreground sm:text-base sm:leading-7">
        {text}
      </p>
    </div>
  );
}

function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label className="field-wrap">
      <span className="flex items-center justify-between gap-3">
        <span className="text-sm font-semibold">
          {label}
          {required && <span className="ml-1 text-primary">*</span>}
        </span>
        {hint && (
          <span className="hidden text-right text-[11px] text-muted-foreground sm:block">
            {hint}
          </span>
        )}
      </span>
      <span className="mt-2 block">{children}</span>
    </label>
  );
}

function StatusPill({ icon: Icon, text }: { icon: LucideIcon; text: string }) {
  return (
    <span className="status-pill">
      <Icon size={14} />
      {text}
    </span>
  );
}

function inputModeLabel(value: InputMode) {
  return {
    prompt: "Plain-language check-in",
    checklist: "Structured checklist",
    metric: "Metric submission",
    api: "API / webhook",
  }[value];
}

function cadenceLabel(value: EvaluationCadence) {
  return {
    manual: "Manual",
    "before-action": "Integration · before action",
    "after-output": "Integration · after output",
    daily: "Integration · daily review",
  }[value];
}
