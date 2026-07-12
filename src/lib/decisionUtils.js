const STOP = new Set([
  'the','and','for','with','this','that','from','into','when','then','have','been','were','will',
  'not','are','our','was','has','but','they','you','your','service','incident','check','first',
]);

export function toLines(value, limit = 12) {
  return String(value || '')
    .split(/\n|,|;/)
    .map((x) => x.trim())
    .filter(Boolean)
    .slice(0, limit);
}

export function fingerprint(value, limit = 24) {
  return Array.from(new Set(
    String(value || '')
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, ' ')
      .split(/\s+/)
      .filter((word) => word.length > 3 && !STOP.has(word)),
  )).slice(0, limit);
}

export function jaccard(a = [], b = []) {
  const A = new Set(a);
  const B = new Set(b);
  if (!A.size || !B.size) return 0;
  let intersection = 0;
  A.forEach((item) => { if (B.has(item)) intersection += 1; });
  return intersection / new Set([...A, ...B]).size;
}

export function rankPriorDecisions(current, rows = [], limit = 5) {
  const fp = current.fingerprint || fingerprint([
    current.title,
    current.service_name,
    current.symptom_text,
    current.supporting_evidence,
    current.selected_branch,
  ].join(' '));

  return rows
    .map((row) => {
      const incident = row.incidents || {};
      const lexical = jaccard(fp, incident.fingerprint || []);
      const service = current.service_name && incident.service_name === current.service_name ? 0.35 : 0;
      const severity = current.severity && incident.severity === current.severity ? 0.05 : 0;
      return { ...row, match_score: Math.min(1, lexical * 0.6 + service + severity) };
    })
    .filter((row) => row.match_score > 0.05)
    .sort((a, b) => b.match_score - a.match_score)
    .slice(0, limit);
}

export function completenessGate(decision) {
  const evidence = toLines(decision.supporting_evidence);
  const counter = toLines(decision.counterevidence);
  const alternatives = toLines(decision.alternative_branches);
  const aborts = toLines(decision.abort_conditions);
  const failures = [];

  if (!decision.symptom_text?.trim()) failures.push('No directly observed state recorded.');
  if (!decision.selected_branch?.trim()) failures.push('No current theory recorded.');
  if (!evidence.length) failures.push('No supporting signals recorded.');
  if (!decision.reasoning_summary?.trim()) failures.push('No assumptions or reasoning recorded.');
  if (!decision.impact?.trim()) failures.push('No consequence if wrong recorded.');
  if (!decision.first_action?.trim()) failures.push('No first action recorded.');
  if (!aborts.length) failures.push('No switch condition recorded.');
  if (Number(decision.confidence) >= 80 && !counter.length) failures.push('High confidence without a signal that does not fit.');
  if (Number(decision.confidence) >= 80 && !alternatives.length) failures.push('High confidence without another plausible explanation.');

  const score = Math.max(0, 100 - failures.length * 18);
  return {
    pass: failures.length === 0,
    score,
    failures,
  };
}

export function buildMarkdownRecord(record) {
  const d = record.decision;
  const r = record.review || {};
  const a = record.postReviewAction || {};
  const o = record.outcome || {};
  const bullets = (items) => (items?.length ? items.map((x) => `- ${typeof x === 'string' ? x : JSON.stringify(x)}`).join('\n') : '- None recorded');

  return `# TraceCrumb Incident Decision Record\n\n` +
    `## Incident\n` +
    `- Title: ${record.incident?.title || 'Untitled'}\n` +
    `- Service: ${record.incident?.service_name || 'Unknown'}\n` +
    `- Severity: ${record.incident?.severity || 'Unknown'}\n` +
    `- Impact: ${record.incident?.impact || 'Not recorded'}\n` +
    `- Consequence type: ${record.incident?.consequence_type || 'Not recorded'}\n` +
    `- Decision deadline: ${record.incident?.decision_deadline || 'Not recorded'}\n\n` +
    `## What was happening\n${record.incident?.symptom_text || 'Not recorded'}\n\n` +
    `## Current theory saved before review\n${d.selected_branch}\n\n` +
    `## Evidence supporting the theory\n${bullets(d.supporting_evidence)}\n\n` +
    `## Assumptions making the theory plausible\n${d.reasoning_summary || 'Not recorded'}\n\n` +
    `## Signals that did not fit\n${bullets(d.counterevidence)}\n\n` +
    `## Known unknowns\n${bullets(d.unknowns)}\n\n` +
    `## Other plausible explanations\n${bullets(d.alternative_branches)}\n\n` +
    `## Action the team was about to take\n${d.first_action}\n\n` +
    `## Switch direction if\n${bullets(d.abort_conditions)}\n\n` +
    `## Review result\n` +
    `- Recommended next move: ${r.verdict || 'Not reviewed'}\n` +
    `- What does not fit: ${(r.missing_or_weak_evidence || []).join('; ') || '—'}\n` +
    `- Another plausible explanation: ${r.counter_hypothesis || '—'}\n` +
    `- Fastest way to prove it wrong: ${r.cheapest_falsification_check || '—'}\n` +
    `- Why: ${r.rationale || '—'}\n\n` +
    `## Next move recorded after review\n` +
    `- Choice: ${a.action || 'Not recorded'}\n` +
    `- Action: ${a.final_branch || '—'}\n` +
    `- Reason: ${a.reason || '—'}\n\n` +
    `## Outcome\n` +
    `- Followed: ${o.followed ?? '—'}\n` +
    `- Outcome: ${o.outcome || 'Not recorded'}\n` +
    `- Minutes to proof/disproof: ${o.minutes_to_falsification ?? '—'}\n` +
    `- Actual root cause: ${o.actual_root_cause || '—'}\n` +
    `- Resolution: ${o.successful_resolution || '—'}\n` +
    `- TraceCrumb effect: ${o.tracecrumb_effect || '—'}\n` +
    `- Notes: ${o.notes || '—'}\n\n` +
    `## Record metadata\n` +
    `- Decision source: ${d.source_type}${d.source_name ? ` — ${d.source_name}` : ''}\n` +
    `- Committed at: ${d.committed_at || ''}\n` +
    `- Commit hash: ${d.commit_hash || ''}\n`;
}
