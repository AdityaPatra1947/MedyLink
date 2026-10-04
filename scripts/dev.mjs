import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const next = path.join(root, 'frontend/node_modules/next/dist/bin/next');
if (!existsSync(python) || !existsSync(next)) { console.error('Install dependencies first. See README.md or run npm run setup on Windows.'); process.exit(1); }
console.log('MedyLink: http://localhost:3000\nEmail delivery follows backend/.env. Ctrl+C stops both services.');
const children = [
  spawn(python, ['manage.py', 'runserver', '127.0.0.1:8000', '--noreload'], {cwd: path.join(root, 'backend'), stdio: 'inherit', env: {...process.env, PYTHONUNBUFFERED: '1'}}),
  spawn(process.execPath, [next, 'dev', '--hostname', '127.0.0.1'], {cwd: path.join(root, 'frontend'), stdio: 'inherit'}),
];
let stopping = false;
function stop(code = 0) { if (stopping) return; stopping = true; children.forEach(c => c.kill()); setTimeout(() => process.exit(code), 300); }
children.forEach(c => { c.on('exit', code => stop(code ?? 0)); c.on('error', e => { console.error(e.message); stop(1); }); });
process.on('SIGINT', () => stop()); process.on('SIGTERM', () => stop());
