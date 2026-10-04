import { spawn } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { parseEnv } from 'node:util';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const config = path.join(root, '.local/synthetic/.env');
if (!existsSync(config)) {
  console.error('Synthetic configuration is missing. See docs/ADMIN_ANALYTICS.md.');
  process.exit(1);
}
const env = { ...process.env, ...parseEnv(readFileSync(config, 'utf8')), DJANGO_SETTINGS_MODULE: 'config.synthetic_settings', PYTHONUNBUFFERED: '1' };
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const backend = path.join(root, 'backend');
const children = [];
let stopping = false;
function launch(command, args, cwd, childEnv = env) {
  const child = spawn(command, args, { cwd, env: childEnv, stdio: 'inherit' });
  children.push(child);
  child.on('error', error => { console.error(error.message); stop(1); });
  child.on('exit', code => stop(code ?? 0));
}
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  children.forEach(child => child.kill());
  setTimeout(() => process.exit(code), 300);
}
const [action, ...args] = process.argv.slice(2);
if (action === 'manage') {
  launch(python, ['manage.py', ...args], backend);
} else if (action === 'dev') {
  const port = Number(env.SYNTHETIC_FRONTEND_PORT || 3001);
  const apiPort = Number(env.SYNTHETIC_API_PORT || 8001);
  if (![port, apiPort].every(value => Number.isInteger(value) && value >= 1024 && value <= 65535) || port === apiPort) {
    console.error('Choose distinct valid synthetic frontend and API ports.');
    process.exit(1);
  }
  const origin = `http://localhost:${port}`;
  env.FRONTEND_ORIGIN = origin;
  env.CSRF_TRUSTED_ORIGINS = `${origin},http://127.0.0.1:${port}`;
  // Direct connections are retained for management commands; web requests use Neon pooling.
  if (env.SYNTHETIC_POOLED_DATABASE_URL) env.SYNTHETIC_DATABASE_URL = env.SYNTHETIC_POOLED_DATABASE_URL;
  console.log(`MedyLink SYNTHETIC DEMO: ${origin}/admin/analytics\nFictional patient data only. Ctrl+C stops both services.`);
  launch(python, ['manage.py', 'runserver', `127.0.0.1:${apiPort}`, '--noreload'], backend);
  launch(process.execPath, [path.join(root, 'frontend/node_modules/next/dist/bin/next'), 'dev', '--hostname', '127.0.0.1', '--port', String(port)], path.join(root, 'frontend'), { ...env, MEDYLINK_SYNTHETIC: 'true', API_INTERNAL_URL: `http://127.0.0.1:${apiPort}` });
} else {
  console.error('Usage: node scripts/synthetic.mjs <dev|manage> [Django arguments]');
  process.exit(1);
}
process.on('SIGINT', () => stop());
process.on('SIGTERM', () => stop());
