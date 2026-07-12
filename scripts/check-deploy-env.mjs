import { loadEnv } from 'vite';

const mode = process.env.NODE_ENV || 'production';
const env = { ...loadEnv(mode, process.cwd(), ''), ...process.env };
const required = [
  'VITE_SUPABASE_URL',
  'VITE_SUPABASE_PUBLISHABLE_KEY',
];

const missing = required.filter((key) => {
  const value = String(env[key] || '').trim();
  return !value || /YOUR_|REPLACE_ME|example\.supabase/i.test(value);
});

if (missing.length) {
  console.error(`Configured production build blocked. Set: ${missing.join(', ')}`);
  console.error('Use `npm run build` only for the worked-example/static preview.');
  process.exit(1);
}

for (const key of ['VITE_SUPABASE_URL']) {
  try {
    const url = new URL(env[key]);
    if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Unsupported protocol');
  } catch {
    console.error(`${key} must be a valid http(s) URL.`);
    process.exit(1);
  }
}

console.log('Deployment environment OK: public frontend configuration is present.');
