import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { transformSync } from 'esbuild';
import { completenessGate, fingerprint, rankPriorDecisions } from '../src/lib/decisionUtils.js';

const root = process.cwd();
const required = [
  'src/App.jsx',
  'src/branchConfig.js',
  'src/lib/decisionUtils.js',
  'src/lib/supabaseClient.js',
  'scripts/check-deploy-env.mjs',
  'supabase/schema.sql',
  'supabase/migrations/20260712090000_auth_free_validation.sql',
  'supabase/config.toml',
  'supabase/functions/ai-orchestrator/index.ts',
  'README.md',
  'WEDGE_SPEC.md',
  'FINALIZATION_REPORT.md',
  'VALIDATION_REPORT.md',
  'TRACECRUMB_SESSION_EXECUTION.yaml',
  '.env.example',
  'wrangler.jsonc',
];
for (const file of required) assert.ok(existsSync(join(root, file)), `Missing ${file}`);

const read = (file) => readFileSync(join(root, file), 'utf8');
const app = read('src/App.jsx');
const client = read('src/lib/supabaseClient.js');
const schema = read('supabase/schema.sql');
const migration = read('supabase/migrations/20260712090000_auth_free_validation.sql');
const edge = read('supabase/functions/ai-orchestrator/index.ts');
const config = read('supabase/config.toml');
const readme = read('README.md');
const wedge = read('WEDGE_SPEC.md');
const sessionYaml = read('TRACECRUMB_SESSION_EXECUTION.yaml');
const envExample = read('.env.example');
const pkg = JSON.parse(read('package.json'));
const wrangler = read('wrangler.jsonc');
const envGuard = read('scripts/check-deploy-env.mjs');

transformSync(app, { loader: 'jsx', format: 'esm', jsx: 'automatic' });
transformSync(edge, { loader: 'ts', format: 'esm' });

// Product and access boundary.
assert.match(readme, /no password, magic link, OAuth provider, or Supabase Auth dependency/i);
assert.match(readme, /10 server-enforced live review runs/i);
assert.match(wedge, /Ten server-enforced live runs/i);
assert.match(app, /Start your 10-run validation/i);
assert.match(app, /No password, identity provider, or Supabase Auth record is created/i);
assert.doesNotMatch(app, /supabase\.auth|signInAnonymously|signInWithOtp|updateUser|signOut\(/);
assert.doesNotMatch(client, /persistSession:\s*true|autoRefreshToken:\s*true|detectSessionInUrl:\s*true/);
assert.match(client, /persistSession:\s*false/);

// Browser uses one function boundary, not direct product-table access.
assert.match(app, /supabase\.functions\.invoke/);
assert.doesNotMatch(app, /supabase\.from\(|supabase\.rpc\(/);
assert.match(app, /register_guest/);
assert.match(app, /session_status/);
assert.match(app, /history/);
assert.match(app, /save_action/);
assert.match(app, /save_outcome/);
assert.match(app, /save_feedback/);

// Mechanism improvements.
assert.match(app, /Strongest contradiction/);
assert.match(app, /Credible alternative cause/);
assert.match(app, /Cheapest falsification check/);
assert.match(app, /Decision boundary/);
assert.match(app, /const \[action, setAction\] = useState\(''\)/);
assert.match(app, /consequence_type/);
assert.match(app, /decision_deadline/);
assert.match(app, /unknowns/);
assert.match(app, /tracecrumb_effect/);
assert.match(app, /alternative_credibility/);
assert.match(app, /check_feasibility/);
assert.match(app, /specificity/);
assert.match(app, /Copy brief/);
assert.match(app, /Download Markdown/);
assert.match(app, /Download JSON/);

// Active auth-free data model and atomic quota.
for (const table of ['validation_sessions', 'validation_incidents', 'validation_decisions', 'validation_reviews', 'validation_actions', 'validation_outcomes', 'validation_feedback', 'validation_ai_requests', 'validation_events']) {
  assert.match(schema, new RegExp(`create table if not exists public\\.${table}`));
  assert.match(schema, new RegExp(`alter table public\\.${table} enable row level security`));
  assert.match(schema, new RegExp(`revoke all on public\\.${table} from public, anon, authenticated`));
}
assert.match(schema, /max_runs integer not null default 10/);
assert.match(schema, /email_hash text not null unique/);
assert.match(schema, /access_token_hash text not null unique/);
assert.match(schema, /reserve_validation_run/);
assert.match(schema, /run_count < validation_sessions\.max_runs/);
assert.match(schema, /RUN_LIMIT_REACHED/);
assert.match(schema, /release_validation_run/);
assert.equal(schema, migration, 'Canonical schema and active migration must be byte-identical');
assert.doesNotMatch(schema, /auth\.users|auth\.uid\(|org_members|profiles_select_own/);

// Trusted function controls access and provider calls without Supabase Auth.
assert.match(config, /verify_jwt\s*=\s*false/);
assert.match(edge, /SUPABASE_SERVICE_ROLE_KEY/);
assert.match(edge, /access_token_hash/);
assert.match(edge, /email_hash/);
assert.match(edge, /reserve_validation_run/);
assert.match(edge, /MAX_VALIDATION_RUNS/);
assert.match(edge, /DAILY_REVIEW_LIMIT/);
assert.match(edge, /DAILY_SIGNUP_LIMIT/);
assert.match(edge, /ALLOWED_ORIGINS/);
assert.match(edge, /ABUSE_HASH_SECRET/);
assert.match(edge, /\/v1\/responses/);
assert.match(edge, /type: "json_schema"/);
assert.match(edge, /strict: true/);
assert.match(edge, /store: false/);
assert.match(edge, /deterministicFallback/);
assert.match(edge, /No live telemetry was queried/);
assert.match(edge, /not a root-cause finding/);
assert.doesNotMatch(edge, /auth\.getUser|SUPABASE_ANON_KEY|org_members|auth\.users/);
assert.doesNotMatch(app, /OPENAI_API_KEY|SUPABASE_SERVICE_ROLE_KEY|ABUSE_HASH_SECRET/);

// Deployment contract.
assert.match(envExample, /VITE_SUPABASE_URL/);
assert.match(envExample, /VITE_SUPABASE_PUBLISHABLE_KEY/);
assert.doesNotMatch(envExample, /OPENAI_API_KEY|SERVICE_ROLE|ABUSE_HASH_SECRET/);
assert.match(envGuard, /VITE_SUPABASE_URL/);
assert.match(envGuard, /VITE_SUPABASE_PUBLISHABLE_KEY/);
assert.doesNotMatch(envGuard, /VITE_SITE_URL/);
assert.match(wrangler, /"directory"\s*:\s*"\.\/dist"/);
assert.equal(pkg.scripts.ship, 'npm run test && npm run build');
assert.match(pkg.scripts['deploy:cloudflare'], /wrangler deploy/);

// Session logistics explicitly separate technical and human work.
assert.match(sessionYaml, /technical_applicable:/);
assert.match(sessionYaml, /human_sociotechnical:/);
assert.match(sessionYaml, /distribution_and_validation:/);
assert.match(sessionYaml, /weight:\s*0\./);
assert.match(sessionYaml, /do_not_proceed_unless/);

// Completeness gate.
const incomplete = completenessGate({ selected_branch: 'Check database', supporting_evidence: '', first_action: '', abort_conditions: '', confidence: 90, impact: '', symptom_text: '', reasoning_summary: '' });
assert.equal(incomplete.pass, false);
assert.ok(incomplete.failures.length >= 6);

const complete = completenessGate({
  selected_branch: 'Check database pool saturation',
  supporting_evidence: 'connection wait rising',
  counterevidence: 'database CPU normal',
  alternative_branches: 'upstream dependency',
  reasoning_summary: 'Connection wait rose before saturation.',
  first_action: 'inspect active and waiting connections',
  abort_conditions: 'pool wait normal',
  symptom_text: 'checkout requests waiting for database connections',
  impact: 'checkout is blocked for customers',
  confidence: 60,
});
assert.equal(complete.pass, true);

// Prior-decision matching remains deterministic and bounded.
const current = { service_name: 'checkout', severity: 'critical', fingerprint: fingerprint('checkout connection pool wait rising') };
const ranked = rankPriorDecisions(current, [{ id: 'd1', incidents: { service_name: 'checkout', severity: 'critical', fingerprint: fingerprint('checkout pool wait exhausted') } }], 5);
assert.equal(ranked[0].id, 'd1');
assert.ok(ranked[0].match_score > 0.35);

console.log('SHIP TESTS OK: auth-free 10-run validation, trusted API boundary, decision-impact loop, and deployment contracts');
