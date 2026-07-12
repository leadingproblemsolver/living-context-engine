import React, { useEffect, useMemo, useState } from 'react';
import { supabase, AI_FUNCTION_NAME, isSupabaseConfigured } from './lib/supabaseClient.js';
import { BRANCH } from './branchConfig.js';
import { buildMarkdownRecord, completenessGate, fingerprint, rankPriorDecisions, toLines } from './lib/decisionUtils.js';

const DRAFT_KEY = 'tracecrumb-active-incident-draft';
const TOKEN_KEY = 'tracecrumb-validation-token-v1';
const MAX_RUNS = 10;

const EMPTY_FORM = {
  title: '', service_name: '', severity: 'high', symptom_text: '', impact: '', consequence_type: 'customer', decision_deadline: '',
  source_type: 'human', source_name: '', selected_branch: '', supporting_evidence: '', counterevidence: '', reasoning_summary: '',
  alternative_branches: '', confidence: 50, abort_conditions: '', first_action: '', unknowns: '',
};

const SAMPLE_FORM = {
  title: 'Checkout latency spike after deploy', service_name: 'payments-api', severity: 'high',
  symptom_text: 'Error rate jumped. 5xx responses are concentrated on POST /charge. Queue depth is rising.',
  impact: 'EU customers are unable to complete checkout.', consequence_type: 'customer', decision_deadline: '',
  source_type: 'human', source_name: 'Incident responder',
  selected_branch: 'The latest payments-api deploy caused the checkout failures, so we should roll it back.',
  supporting_evidence: 'Failures began 14 minutes after deploy\n5xx errors are concentrated on POST /charge\nRedis CPU is high',
  counterevidence: 'Auth dependency is stable\nEU-only impact may point to regional routing or configuration\nRedis CPU could be retry amplification rather than root cause',
  reasoning_summary: 'The deploy is the most recent correlated change, but the regional pattern and Redis signal need to be separated before rollback.',
  alternative_branches: 'EU routing or configuration mismatch\nRedis saturation from retry amplification\nQueue consumer slowdown',
  confidence: 70,
  abort_conditions: 'Previous version shows the same latency and 5xx pattern\nEU-only failures correlate with routing or configuration instead of build version',
  first_action: 'Compare one failing EU charge path with one healthy region and inspect Redis latency, command volume, and retries for the same window.',
  unknowns: 'Whether EU and non-EU traffic use identical routing configuration.',
};

const WORKED_EXAMPLE = {
  incident: { title: 'Checkout 5xx spike after deploy', service_name: 'payments-api', severity: 'high', symptom_text: 'POST /charge 5xx increased 14 minutes after deployment. Redis CPU is high. Queue depth is rising. Auth dependency is stable.', impact: 'EU customers cannot complete checkout.', consequence_type: 'customer' },
  decision: { id: 'worked-decision', source_type: 'human', source_name: 'Incident responder', selected_branch: 'Roll back the latest payments-api deployment.', supporting_evidence: ['Failure started 14 minutes after deploy', 'POST /charge is the affected path', 'Redis CPU is high'], counterevidence: ['Only EU traffic is failing', 'Auth is stable', 'Redis CPU may be caused by retries'], reasoning_summary: 'The deploy is the most recent correlated change.', alternative_branches: ['EU routing/configuration mismatch', 'Redis retry amplification', 'Queue consumer slowdown'], confidence: 70, first_action: 'Compare EU and non-EU charge paths before rollback; inspect Redis latency and retry rate.', abort_conditions: ['The previous version shows the same failure pattern', 'Failures correlate with EU routing rather than build version'], unknowns: ['Whether routing configuration differs by region'], committed_at: 'Before review', commit_hash: 'worked-example' },
  review: { verdict: 'revise', strongest_supporting_evidence: ['The timing after deploy is real and should be checked.'], missing_or_weak_evidence: ['EU-only failure does not cleanly fit a global deploy regression.', 'Redis CPU may be a downstream retry effect.'], counter_hypothesis: 'A regional routing/configuration path is failing and causing charge retries, which makes Redis look like the primary cause.', cheapest_falsification_check: 'Compare the failing EU route with a healthy region and verify whether the same build behaves differently before rollback.', premature_closure_risk: 'Rollback may consume time while the discriminating signal is regional behavior.', branch_abort_conditions: ['EU and non-EU traffic use the same build but only EU fails', 'Rollback does not reduce queue depth within five minutes'], rationale: 'Revise the next move: check the regional path before a full rollback.', prior_decisions_used: [], limitations: ['Worked example only; no live telemetry was queried.'] },
  reviewRow: { provider: 'worked example', fallback: false, latency_ms: 0 },
  postReviewAction: { action: 'revise', final_branch: 'Check EU routing/configuration and Redis retry amplification before rollback.', reason: 'The regional pattern does not fit a global deploy regression strongly enough to justify immediate rollback.' },
  outcome: { followed: true, outcome: 'confirmed', minutes_to_falsification: 4, actual_root_cause: 'EU routing sent charge traffic through a stale configuration path, causing retries and Redis pressure.', successful_resolution: 'Corrected the EU route config, drained the queue, and left the deployment in place.', tracecrumb_effect: 'changed_test' },
};

function getInitialTheme() {
  if (typeof window === 'undefined') return 'dark';
  const saved = window.localStorage.getItem('tracecrumb-theme');
  if (saved === 'light' || saved === 'dark') return saved;
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function ThemeToggle() {
  const [theme, setTheme] = useState(getInitialTheme);
  useEffect(() => { document.documentElement.dataset.theme = theme; window.localStorage.setItem('tracecrumb-theme', theme); }, [theme]);
  return <button className="secondary" type="button" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</button>;
}

function localDateTimeToIso(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function getSourceChannel() {
  if (typeof window === 'undefined') return 'direct';
  return new URLSearchParams(window.location.search).get('source_channel') || 'direct';
}

function getGuestToken() {
  if (typeof window === 'undefined') return '';
  let token = window.localStorage.getItem(TOKEN_KEY);
  if (token) return token;
  const bytes = new Uint8Array(32);
  window.crypto.getRandomValues(bytes);
  token = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  window.localStorage.setItem(TOKEN_KEY, token);
  return token;
}

async function callApi(action, payload = {}) {
  if (!isSupabaseConfigured) throw new Error('Deployment is missing VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY.');
  const { data, error } = await supabase.functions.invoke(AI_FUNCTION_NAME, {
    body: { branch: 'first60', action, guest_token: getGuestToken(), payload },
  });
  if (error) {
    let message = error.message || 'Request failed';
    try {
      const body = await error.context?.json?.();
      if (body?.error) message = body.error;
    } catch (_) {}
    throw new Error(message);
  }
  if (!data?.ok) throw new Error(data?.error || 'Request failed');
  return data;
}

async function logEvent(eventType, metadata = {}) {
  try { await callApi('log_event', { source_channel: getSourceChannel(), event_type: eventType, metadata }); } catch (_) {}
}

function ProcessStrip({ active = 0 }) {
  const steps = ['Save theory', 'Stress-test', 'Choose move', 'Record result'];
  return <div className="process-strip" aria-label="TraceCrumb workflow">{steps.map((step, index) => <React.Fragment key={step}><div className={`process-step ${index <= active ? 'is-active' : ''}`}><span>{index + 1}</span>{step}</div>{index < steps.length - 1 ? <b aria-hidden="true">→</b> : null}</React.Fragment>)}</div>;
}

function TrustRow() { return <div className="trust-row"><span>No production access</span><span>No root-cause claim</span><span>10 server-enforced runs</span></div>; }

function AuditPreview({ compact = false }) {
  return <section className={`audit-preview ${compact ? 'audit-preview-compact' : ''}`}><div className="audit-preview-head"><span className="kicker">Worked example</span><span className="pill">No telemetry queried</span></div><div className="preview-line"><small>Your current theory</small><strong>The deploy caused checkout failures.</strong></div><div className="preview-grid"><div><small>Strongest contradiction</small><p>Only EU traffic is failing while the same build serves other regions.</p></div><div><small>Cheapest falsification check</small><p>Compare EU routing/configuration with one healthy region before rollback.</p></div></div><div className="preview-verdict"><span>Recommended move</span><strong>REVISE</strong><span className="pill">4 min check</span></div></section>;
}

function LandingPage({ onStart, onResume, hasSession, error }) {
  useEffect(() => { logEvent('landing_view'); }, []);
  return <main className="landing-shell"><nav className="landing-nav"><div className="brand-mark"><span className="brand-dot" /><span>{BRANCH.product}</span><small>{BRANCH.productDescriptor}</small></div><div className="row"><ThemeToggle />{hasSession ? <button className="secondary" onClick={onResume}>Resume validation</button> : null}</div></nav><section className="landing-hero"><div className="landing-hero-copy"><div className="kicker">{BRANCH.kicker}</div><p className="landing-tagline">{BRANCH.tagline}</p><h1>{BRANCH.headline}</h1><p className="landing-copy">{BRANCH.subheadline}</p><div className="landing-actions"><button type="button" onClick={onStart}>{hasSession ? 'Continue your 10-run validation' : 'Start your 10-run validation'}</button><a className="button-link secondary" href="?demo=1&source_channel=landing" onClick={() => logEvent('demo_opened')}>See a worked example</a></div><p className="field-help">One email, no password, no magic link. Your 10-run validation workspace is bound to this browser.</p>{error ? <p className="loss" role="alert">{error}</p> : null}<TrustRow /><ProcessStrip active={1} /></div><AuditPreview /></section><section className="landing-grid"><div className="card"><span className="kicker">Problem</span><h3>{BRANCH.landing.problemTitle}</h3><p>{BRANCH.landing.problemBody}</p></div><div className="card"><span className="kicker">Mechanism</span><h3>{BRANCH.landing.solutionTitle}</h3><p>{BRANCH.landing.solutionBody}</p></div><div className="card"><span className="kicker">Return</span><h3>{BRANCH.landing.proofTitle}</h3><p>{BRANCH.landing.proofBody}</p></div></section></main>;
}

function SignupPanel({ onRegistered, onBack }) {
  const [email, setEmail] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try { const data = await callApi('register_guest', { email: email.trim(), source_channel: getSourceChannel() }); await logEvent('validation_signup_completed'); onRegistered(data.session); }
    catch (err) { setError(err.message || String(err)); } finally { setBusy(false); }
  }
  return <div className="auth-wrap"><div className="auth-top row"><button className="secondary" onClick={onBack}>← Landing</button><ThemeToggle /></div><div className="auth card"><div className="kicker">10-run validation access</div><h2>Start without an account system</h2><p>Enter an email so we can attribute validation evidence. No password, identity provider, or Supabase Auth record is created.</p><form className="form-grid" onSubmit={submit}><label>Email<input required type="email" autoComplete="email" maxLength="254" value={email} onChange={(e) => setEmail(e.target.value)} /></label><div className="boundary"><strong>Access boundary</strong><p>This browser stores a random access token. Export important records before clearing browser storage.</p></div>{error ? <p className="loss" role="alert">{error}</p> : null}<button disabled={busy}>{busy ? 'Opening validation workspace…' : `Start ${MAX_RUNS} demo runs`}</button></form></div></div>;
}

function WorkedExample() { useEffect(() => { logEvent('demo_view'); }, []); return <main className="container demo-page"><div className="header"><div className="brand"><span className="kicker">Worked example — not a live investigation</span><h1>{BRANCH.productDescriptor}</h1><p>Example data only. No production system, telemetry, database write, or AI provider is queried.</p></div><div className="row"><a className="button-link secondary" href="/">Back</a><a className="button-link" href="/?start=1&source_channel=demo">Run your own check</a></div></div><ProcessStrip active={3} /><OutcomeDelta record={WORKED_EXAMPLE} /><DecisionRecord record={WORKED_EXAMPLE} /></main>; }

function OutcomeDelta({ record }) { if (!record?.postReviewAction) return null; return <section className="outcome-delta card"><div><span className="kicker">Before review</span><strong>{record.decision.selected_branch}</strong></div><b>→</b><div><span className="kicker">After review</span><strong>{record.postReviewAction.final_branch}</strong></div><b>→</b><div><span className="kicker">Outcome</span><strong>{record.outcome ? `${record.outcome.outcome} in ${record.outcome.minutes_to_falsification ?? '—'} min` : 'Pending'}</strong></div></section>; }

function BulletList({ items, empty = 'None recorded.' }) { return items?.length ? <ul>{items.map((item, index) => <li key={index}>{typeof item === 'string' ? item : item.reason || JSON.stringify(item)}</li>)}</ul> : <p>{empty}</p>; }

function ProviderStatus({ record }) { const row = record.reviewRow || {}; if (row.fallback) return <div className="fallback-warning"><strong>Provider review unavailable.</strong> The run was preserved, but the content below is a deterministic record-quality fallback.</div>; if (row.provider) return <div className="provider-ok"><strong>Incident-specific checkpoint completed.</strong> Provider: {row.provider}{row.latency_ms ? ` · ${(row.latency_ms / 1000).toFixed(1)}s` : ''}</div>; return <div className="provider-ok"><strong>Worked example.</strong> Fixed sample output.</div>; }

function ReviewPanel({ record }) {
  const review = record.review; if (!review) return null; const fallback = Boolean(record.reviewRow?.fallback); const verdict = fallback ? 'review unavailable' : String(review.verdict || 'revise');
  return <section className="review-panel"><ProviderStatus record={record} /><div className="review-verdict"><span className="kicker">Decision checkpoint</span><strong className={fallback ? 'warn' : review.verdict === 'proceed' ? 'ok' : 'warn'}>{verdict.toUpperCase()}</strong></div><div className="review-grid"><div><h3>1. Strongest contradiction</h3><BulletList items={review.missing_or_weak_evidence} empty="No material contradiction identified." /></div><div><h3>2. Credible alternative cause</h3><p>{fallback ? 'Not generated by the deterministic fallback.' : review.counter_hypothesis || 'Not established.'}</p></div><div><h3>3. Cheapest falsification check</h3><p>{review.cheapest_falsification_check || record.decision.first_action || 'Not established.'}</p></div><div><h3>4. Decision boundary</h3><BulletList items={review.branch_abort_conditions || record.decision.abort_conditions} empty={review.premature_closure_risk || 'No boundary recorded.'} />{review.premature_closure_risk ? <p><strong>Closure risk:</strong> {review.premature_closure_risk}</p> : null}</div></div><details className="optional-fields"><summary>Supporting evidence and rationale</summary><div className="optional-fields-body"><h3>What supports the theory</h3><BulletList items={review.strongest_supporting_evidence} /><p><strong>Why:</strong> {review.rationale || 'No rationale returned.'}</p></div></details><p className="scope-warning">Scope: redacted submitted record only. No live telemetry, root-cause proof, or remediation execution.</p></section>;
}

function Provenance({ record }) { const row = record.reviewRow || {}; return <div className="provenance"><span className="pill">Saved before review</span><span className="pill">Source: {record.decision.source_type}{record.decision.source_name ? ` / ${record.decision.source_name}` : ''}</span><span className="pill">Review: {row.fallback ? 'fallback' : row.provider || 'worked example'}</span>{record.decision.commit_hash ? <span className="pill hash">Hash: {record.decision.commit_hash.slice(0, 12)}…</span> : null}</div>; }

function DecisionRecord({ record, onPostReviewAction, onOutcome, saving }) {
  const [action, setAction] = useState(''); const [finalBranch, setFinalBranch] = useState(record.postReviewAction?.final_branch || ''); const [reason, setReason] = useState(''); const [owner, setOwner] = useState(''); const [dueAt, setDueAt] = useState('');
  const [outcome, setOutcome] = useState(''); const [followed, setFollowed] = useState('true'); const [minutes, setMinutes] = useState(''); const [rootCause, setRootCause] = useState(''); const [resolution, setResolution] = useState(''); const [effect, setEffect] = useState(''); const [notes, setNotes] = useState('');
  function download(kind) { const content = kind === 'json' ? JSON.stringify(record, null, 2) : buildMarkdownRecord(record); const blob = new Blob([content], { type: kind === 'json' ? 'application/json' : 'text/markdown' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `tracecrumb-${record.incident?.title || 'decision-record'}.${kind === 'json' ? 'json' : 'md'}`.replace(/[^a-z0-9.]+/gi, '-').toLowerCase(); link.click(); URL.revokeObjectURL(url); }
  async function copyBrief() { await navigator.clipboard.writeText(buildMarkdownRecord(record)); logEvent('decision_brief_copied'); }
  return <div className="record-stack"><section className="card locked-record"><div className="record-header"><div><span className="kicker">Saved incident record</span><h2>{record.incident?.title}</h2><p>{record.incident?.service_name} · {record.incident?.severity} · {record.incident?.consequence_type || 'other'} consequence</p></div><div className="row"><button className="secondary" onClick={copyBrief}>Copy brief</button><button className="secondary" onClick={() => download('md')}>Download Markdown</button><button className="secondary" onClick={() => download('json')}>Download JSON</button></div></div><Provenance record={record} /><div className="decision-branch"><span>Current theory</span>{record.decision.selected_branch}</div><div className="decision-grid"><div><h3>Directly observed state</h3><p>{record.incident?.symptom_text}</p></div><div><h3>Directly observed evidence</h3><BulletList items={record.decision.supporting_evidence} /></div><div><h3>Assumptions making it plausible</h3><p>{record.decision.reasoning_summary || 'None recorded.'}</p></div><div><h3>Signals that do not fit</h3><BulletList items={record.decision.counterevidence} /></div><div><h3>Known unknowns</h3><BulletList items={record.decision.unknowns} /></div><div><h3>Action about to be taken</h3><p>{record.decision.first_action}</p></div></div></section><section className="card"><ReviewPanel record={record} /></section>
  {onPostReviewAction && !record.postReviewAction ? <section className="card"><span className="kicker">Mandatory next move</span><h2>Choose explicitly—nothing is preselected</h2><div className="form-grid"><label>Choice<select required value={action} onChange={(e) => setAction(e.target.value)}><option value="">Select…</option><option value="proceed">Proceed unchanged</option><option value="revise">Run the check or revise the theory</option><option value="escalate">Escalate for another review</option><option value="stop">Stop this action</option></select></label><label>Exact next move<input required value={finalBranch} onChange={(e) => setFinalBranch(e.target.value)} /></label><div className="two-col"><label>Owner<input value={owner} onChange={(e) => setOwner(e.target.value)} /></label><label>Due at<input type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} /></label></div><label>Why this move?<textarea required value={reason} onChange={(e) => setReason(e.target.value)} /></label><button disabled={saving || !action || !reason.trim() || !finalBranch.trim()} onClick={() => onPostReviewAction({ action, final_branch: finalBranch, reason, owner, due_at: localDateTimeToIso(dueAt) })}>{saving ? 'Saving…' : 'Save explicit next move'}</button></div></section> : null}
  {record.postReviewAction ? <section className="card compact"><span className="kicker">Next move saved</span><h3>{record.postReviewAction.action.toUpperCase()}</h3><p><strong>Action:</strong> {record.postReviewAction.final_branch}</p><p>{record.postReviewAction.reason}</p></section> : null}
  {onOutcome && record.postReviewAction && !record.outcome ? <section className="card"><span className="kicker">Close the loop</span><h2>What actually happened?</h2><div className="form-grid"><label>Was the saved move followed?<select value={followed} onChange={(e) => setFollowed(e.target.value)}><option value="true">Yes</option><option value="false">No</option></select></label><label>Outcome<select required value={outcome} onChange={(e) => setOutcome(e.target.value)}><option value="">Select…</option><option value="confirmed">Confirmed</option><option value="falsified">Falsified</option><option value="abandoned">Abandoned</option><option value="unknown">Unknown</option></select></label><label>TraceCrumb effect<select required value={effect} onChange={(e) => setEffect(e.target.value)}><option value="">Select…</option><option value="changed_decision">Changed decision</option><option value="changed_test">Changed test</option><option value="changed_timing">Changed timing</option><option value="changed_participants">Changed participants</option><option value="strengthened_decision">Strengthened decision</option><option value="no_effect">No effect</option></select></label><label>Minutes to proof/disproof<input min="0" type="number" value={minutes} onChange={(e) => setMinutes(e.target.value)} /></label><label>Actual root cause<textarea value={rootCause} onChange={(e) => setRootCause(e.target.value)} /></label><label>Resolution<textarea value={resolution} onChange={(e) => setResolution(e.target.value)} /></label><label>Notes<textarea value={notes} onChange={(e) => setNotes(e.target.value)} /></label><button disabled={saving || !outcome || !effect} onClick={() => onOutcome({ followed: followed === 'true', outcome, tracecrumb_effect: effect, minutes_to_falsification: minutes ? Number(minutes) : null, actual_root_cause: rootCause, successful_resolution: resolution, notes })}>{saving ? 'Saving…' : 'Save outcome'}</button></div></section> : null}
  {record.outcome ? <section className="card compact"><span className="kicker">Outcome recorded</span><h3>{record.outcome.outcome?.toUpperCase()}</h3><p>{record.outcome.tracecrumb_effect?.replaceAll('_', ' ')} · {record.outcome.actual_root_cause || record.outcome.notes || 'Outcome saved.'}</p></section> : null}</div>;
}

function ReviewFeedback({ record, onSave, saving }) {
  const existing = record.feedback; const [novelty, setNovelty] = useState(''); const [credibility, setCredibility] = useState(''); const [feasibility, setFeasibility] = useState(''); const [specificity, setSpecificity] = useState(''); const [comment, setComment] = useState('');
  if (!record.review || existing) return existing ? <section className="card compact"><span className="kicker">Feedback recorded</span><p>{existing.novelty} · {existing.alternative_credibility} · {existing.check_feasibility} · {existing.specificity}</p></section> : null;
  return <section className="card feedback-card"><span className="kicker">Evidence quality</span><h2>Separate novelty from executability</h2><div className="form-grid"><label>Novelty<select required value={novelty} onChange={(e) => setNovelty(e.target.value)}><option value="">Select…</option><option value="novel">Novel</option><option value="clarifying">Clarifying</option><option value="already_known">Already known</option><option value="irrelevant">Irrelevant</option></select></label><label>Alternative cause credibility<select required value={credibility} onChange={(e) => setCredibility(e.target.value)}><option value="">Select…</option><option value="credible">Credible enough to investigate</option><option value="possible">Possible but weak</option><option value="not_credible">Not credible</option></select></label><label>Falsification check feasibility<select required value={feasibility} onChange={(e) => setFeasibility(e.target.value)}><option value="">Select…</option><option value="executable_now">Executable now</option><option value="executable_later">Executable later</option><option value="not_executable">Not executable</option></select></label><label>Specificity<select required value={specificity} onChange={(e) => setSpecificity(e.target.value)}><option value="">Select…</option><option value="case_specific">Case-specific</option><option value="partly_generic">Partly generic</option><option value="generic">Generic</option></select></label><label>What was missing or most useful?<textarea maxLength="1000" value={comment} onChange={(e) => setComment(e.target.value)} /></label><button disabled={saving || !novelty || !credibility || !feasibility || !specificity} onClick={() => onSave({ novelty, alternative_credibility: credibility, check_feasibility: feasibility, specificity, comment })}>{saving ? 'Saving…' : 'Save feedback'}</button></div></section>;
}

function ReadinessChecklist({ gate }) { return <div className={`gate-status ${gate.pass ? 'gate-pass' : 'gate-fail'}`}><strong>{gate.pass ? 'Ready to review' : 'Add the missing pieces'}</strong>{gate.failures.length ? <BulletList items={gate.failures} /> : <p>The record is specific enough to save and review.</p>}</div>; }

function DecisionGate({ validationSession, onSessionUpdate }) {
  const [form, setForm] = useState(() => { try { return { ...EMPTY_FORM, ...(JSON.parse(sessionStorage.getItem(DRAFT_KEY) || '{}')) }; } catch (_) { return EMPTY_FORM; } });
  const [history, setHistory] = useState([]); const [record, setRecord] = useState(null); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const gate = useMemo(() => completenessGate(form), [form]);
  useEffect(() => { sessionStorage.setItem(DRAFT_KEY, JSON.stringify(form)); }, [form]);
  async function loadHistory() { const data = await callApi('history'); setHistory(data.records || []); }
  useEffect(() => { loadHistory().catch((err) => setError(err.message)); }, [validationSession.id]);
  async function submit(event) {
    event.preventDefault(); if (!gate.pass) return setError(gate.failures.join(' ')); setBusy(true); setError(''); setRecord(null);
    try {
      const normalized = { ...form, decision_deadline: localDateTimeToIso(form.decision_deadline), supporting_evidence: toLines(form.supporting_evidence), counterevidence: toLines(form.counterevidence), alternative_branches: toLines(form.alternative_branches), abort_conditions: toLines(form.abort_conditions), unknowns: toLines(form.unknowns), confidence: Number(form.confidence), fingerprint: fingerprint([form.title, form.service_name, form.symptom_text, form.supporting_evidence, form.selected_branch].join(' ')) };
      const priorIds = rankPriorDecisions(normalized, history.map((x) => ({ ...x.decision, id: x.decision.id, incidents: x.incident, decision_outcomes: x.outcome ? [x.outcome] : [] })), 5).map((item) => item.id);
      const data = await callApi('review', { form: normalized, prior_decision_ids: priorIds, source_channel: getSourceChannel() });
      setRecord(data.record); onSessionUpdate(data.session); setForm(EMPTY_FORM); sessionStorage.removeItem(DRAFT_KEY); logEvent('first_value_reached', { provider: data.record.reviewRow.provider, verdict: data.record.review.verdict, fallback: data.record.reviewRow.fallback }); await loadHistory();
    } catch (err) { setError(err.message || String(err)); } finally { setBusy(false); }
  }
  async function saveAction(payload) { setBusy(true); setError(''); try { const data = await callApi('save_action', { decision_event_id: record.decision.id, review_id: record.reviewRow.id, ...payload }); setRecord({ ...record, postReviewAction: data.action }); logEvent('post_review_action', { action: payload.action }); await loadHistory(); } catch (err) { setError(err.message); } finally { setBusy(false); } }
  async function saveOutcome(payload) { setBusy(true); setError(''); try { const data = await callApi('save_outcome', { decision_event_id: record.decision.id, action_id: record.postReviewAction.id, ...payload }); setRecord({ ...record, outcome: data.outcome }); logEvent('outcome_recorded', { outcome: payload.outcome, tracecrumb_effect: payload.tracecrumb_effect }); await loadHistory(); } catch (err) { setError(err.message); } finally { setBusy(false); } }
  async function saveFeedback(payload) { setBusy(true); setError(''); try { const data = await callApi('save_feedback', { decision_event_id: record.decision.id, review_id: record.reviewRow.id, ...payload }); setRecord({ ...record, feedback: data.feedback }); logEvent('review_feedback', payload); await loadHistory(); } catch (err) { setError(err.message); } finally { setBusy(false); } }
  const remaining = Math.max(0, validationSession.max_runs - validationSession.run_count);
  return <><section className="app-intro card"><div><span className="kicker">Validation run budget</span><h2>{remaining} of {validationSession.max_runs} runs remain</h2><p>Each submitted checkpoint consumes one server-enforced run, including a deterministic fallback. Drafting and worked examples do not consume runs.</p><ProcessStrip active={record ? (record.postReviewAction ? 2 : 1) : 0} /></div><div className="boundary"><strong>Human boundary</strong><p>Use a real decision with a real owner and consequence. Redact credentials, secrets, and customer PII. The tool challenges a theory; the responder remains accountable.</p></div></section><div className="grid gate-grid"><section className="card"><div className="form-heading"><div><span className="kicker">Step 1 — commit before review</span><h2>Stress-test a live decision before it becomes expensive to reverse.</h2></div><button className="secondary" type="button" onClick={() => setForm(SAMPLE_FORM)}>Load worked input</button></div><form className="form-grid" onSubmit={submit}><label>What is happening?<textarea required maxLength="2400" value={form.symptom_text} onChange={(e) => setForm({ ...form, symptom_text: e.target.value })} /></label><label>Current theory<textarea required maxLength="1200" value={form.selected_branch} onChange={(e) => setForm({ ...form, selected_branch: e.target.value })} /></label><label>Directly observed evidence<textarea required maxLength="2400" value={form.supporting_evidence} onChange={(e) => setForm({ ...form, supporting_evidence: e.target.value })} /></label><label>Assumptions making it plausible<textarea required maxLength="1600" value={form.reasoning_summary} onChange={(e) => setForm({ ...form, reasoning_summary: e.target.value })} /></label><label>Action you are about to take<textarea required maxLength="1000" value={form.first_action} onChange={(e) => setForm({ ...form, first_action: e.target.value })} /></label><label>What would force a switch?<textarea required maxLength="1600" value={form.abort_conditions} onChange={(e) => setForm({ ...form, abort_conditions: e.target.value })} /></label><div className="two-col"><label>Consequence type<select value={form.consequence_type} onChange={(e) => setForm({ ...form, consequence_type: e.target.value })}><option value="deployment">Deployment</option><option value="customer">Customer</option><option value="rework">Rework</option><option value="revenue">Revenue</option><option value="security">Security</option><option value="delay">Delay</option><option value="other">Other</option></select></label><label>Decision deadline<input type="datetime-local" value={form.decision_deadline} onChange={(e) => setForm({ ...form, decision_deadline: e.target.value })} /></label></div><label>Consequence if wrong<textarea required maxLength="1200" value={form.impact} onChange={(e) => setForm({ ...form, impact: e.target.value })} /></label><details className="optional-fields"><summary>Add context</summary><div className="form-grid optional-fields-body"><div className="two-col"><label>Incident title<input maxLength="180" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label><label>Service<input maxLength="100" value={form.service_name} onChange={(e) => setForm({ ...form, service_name: e.target.value })} /></label></div><label>Signals that do not fit<textarea maxLength="2400" value={form.counterevidence} onChange={(e) => setForm({ ...form, counterevidence: e.target.value })} /></label><label>Other plausible explanations<textarea maxLength="1600" value={form.alternative_branches} onChange={(e) => setForm({ ...form, alternative_branches: e.target.value })} /></label><label>Known unknowns<textarea maxLength="1600" value={form.unknowns} onChange={(e) => setForm({ ...form, unknowns: e.target.value })} /></label><label>Confidence: {form.confidence}%<input type="range" min="0" max="100" step="5" value={form.confidence} onChange={(e) => setForm({ ...form, confidence: Number(e.target.value) })} /></label></div></details><ReadinessChecklist gate={gate} />{error ? <p className="loss" role="alert">{error}</p> : null}<button disabled={busy || !gate.pass || remaining <= 0}>{remaining <= 0 ? '10-run limit reached' : busy ? 'Saving and reviewing…' : 'Commit theory → run checkpoint'}</button></form></section><section className="card current-record"><span className="kicker">Output contract</span><h2>Four decision-changing cards</h2><p>Strongest contradiction, credible alternative cause, cheapest falsification check, and decision boundary.</p><AuditPreview compact /></section></div>{record ? <DecisionRecord record={record} onPostReviewAction={saveAction} onOutcome={saveOutcome} saving={busy} /> : null}{record ? <ReviewFeedback record={record} onSave={saveFeedback} saving={busy} /> : null}<section className="card history"><span className="kicker">This browser’s validation evidence</span><h2>Prior checkpoints</h2>{history.length === 0 ? <p>No completed runs yet.</p> : <div className="list">{history.map((item) => <button className="item history-item" key={item.decision.id} onClick={() => setRecord(item)}><div className="row"><strong>{item.incident.title}</strong><span className="pill">{item.review ? 'Reviewed' : 'Pending'}</span><span className="pill">{item.postReviewAction ? item.postReviewAction.action : 'Action pending'}</span></div><p>{item.decision.selected_branch}</p><small>{new Date(item.decision.committed_at).toLocaleString()}</small></button>)}</div>}</section></>;
}

function Header({ validationSession, onBack }) { const remaining = Math.max(0, validationSession.max_runs - validationSession.run_count); return <header className="header"><div className="brand"><span className="kicker">{BRANCH.kicker}</span><h1>{BRANCH.product}</h1><p>{BRANCH.promise}</p></div><div className="row"><ThemeToggle /><span className="pill">{validationSession.email}</span><span className="pill">{remaining}/{validationSession.max_runs} runs left</span><button className="secondary" onClick={onBack}>Landing</button></div></header>; }

export default function App() {
  const params = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : new URLSearchParams(); const isDemo = params.get('demo') === '1'; const wantsStart = params.get('start') === '1';
  const [validationSession, setValidationSession] = useState(null); const [screen, setScreen] = useState(wantsStart ? 'signup' : 'landing'); const [loading, setLoading] = useState(true); const [error, setError] = useState('');
  useEffect(() => { (async () => { if (!isSupabaseConfigured) { setLoading(false); return; } try { const data = await callApi('session_status'); if (data.session) { setValidationSession(data.session); if (wantsStart) setScreen('app'); } } catch (_) {} finally { setLoading(false); } })(); }, []);
  if (isDemo) return <WorkedExample />;
  if (loading) return <div className="container"><div className="card">Loading…</div></div>;
  if (screen === 'landing') return <LandingPage hasSession={Boolean(validationSession)} onStart={() => setScreen(validationSession ? 'app' : 'signup')} onResume={() => setScreen('app')} error={error} />;
  if (screen === 'signup') return <SignupPanel onBack={() => setScreen('landing')} onRegistered={(session) => { setValidationSession(session); setScreen('app'); }} />;
  if (!validationSession) return <LandingPage hasSession={false} onStart={() => setScreen('signup')} onResume={() => {}} error={error} />;
  return <main className="container"><Header validationSession={validationSession} onBack={() => setScreen('landing')} />{error ? <div className="card"><p className="loss">{error}</p></div> : null}<DecisionGate validationSession={validationSession} onSessionUpdate={setValidationSession} /></main>;
}
