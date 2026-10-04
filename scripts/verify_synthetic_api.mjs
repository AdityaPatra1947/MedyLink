// Integration smoke test against the explicitly launched local synthetic demo.
// Uses its private fixture credentials; never logs passwords or clinical data.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const { request } = require('@playwright/test');
const baseURL = process.env.SYNTHETIC_VERIFY_URL || 'http://localhost:3001';
assert.ok(['localhost', '127.0.0.1'].includes(new URL(baseURL).hostname), 'Smoke test must target a local demo server.');
const credentials = JSON.parse(readFileSync(path.join(root, '.local/synthetic/mumbai_stations_v1/credentials.json'), 'utf8'));
assert.equal(credentials.synthetic, true);
const contexts = [];
const report = { checked_at: new Date().toISOString(), checks: [] };
async function session(role) {
  const ctx = await request.newContext({ baseURL, timeout: 120000 });
  contexts.push(ctx);
  const account = credentials.accounts.find(row => row.role === role);
  assert.ok(['@synthetic.medylink.test', '@synthetic.arogyatrack.test'].some(domain => account.email.endsWith(domain)));
  const csrf = await (await ctx.get('/api/v1/auth/csrf/')).json();
  const login = await ctx.post('/api/v1/auth/login/', { data: { email: account.email, password: account.password }, headers: { 'X-CSRFToken': csrf.csrfToken, Origin: baseURL } });
  assert.equal(login.status(), 200, `${role} login`);
  assert.equal((await login.json()).user.role, role);
  const fresh = await (await ctx.get('/api/v1/auth/csrf/')).json();
  return { ctx, headers: { 'X-CSRFToken': fresh.csrfToken, Origin: baseURL } };
}
try {
  const { ctx, headers } = await session('admin');
  const catalogResponse = await ctx.get('/api/v1/admin/analytics/catalog/');
  assert.equal(catalogResponse.status(), 200);
  const catalog = await catalogResponse.json();
  assert.equal(catalog.synthetic, true);
  assert.equal(catalog.datasets.find(row => row.dataset_id === 'mumbai_stations_v1').patient_count, 1000);
  assert.equal(catalog.stations.length, 34);
  report.checks.push('Real admin password login, synthetic catalog, 1000 patients / 34 stations');

  const filters = { dataset_id: 'mumbai_stations_v1', disease_code: 'DENGUE', line: '', station_id: '', date_from: '2026-09-01', date_to: '2026-09-29', radius_km: 0.5, min_samples: 5 };
  const denied = await ctx.post('/api/v1/admin/analytics/cluster-runs/', { data: filters });
  assert.equal(denied.status(), 403, 'Missing CSRF must fail');
  const clustered = await ctx.post('/api/v1/admin/analytics/cluster-runs/', { data: filters, headers });
  assert.ok([200, 201].includes(clustered.status()), `Cluster HTTP ${clustered.status()}`);
  const run = await clustered.json();
  assert.equal(run.result.counts.cluster_count, 3);
  assert.deepEqual(run.result.clusters.map(row => row.patient_count).sort((a, b) => a - b), [50, 50, 50]);
  // A one-person noise cell also suppresses related totals in the run envelope.
  assert.equal(run.result.counts.clustered_patients, 150);
  assert.equal(run.result.counts.noise_patients, null);
  assert.ok(Number.isFinite(run.result.metrics.silhouette.value));
  assert.ok(!JSON.stringify(run).includes('patient0001@'));
  const reused = await (await ctx.post('/api/v1/admin/analytics/cluster-runs/', { data: filters, headers })).json();
  assert.equal(reused.id, run.id);
  assert.equal(reused.reused, true);
  const saved = await ctx.get(`/api/v1/admin/analytics/cluster-runs/${run.id}/`);
  assert.equal(saved.status(), 200);
  report.dbscan = { counts: run.result.counts, metrics: run.result.metrics, stations: run.result.clusters.map(row => row.stations) };
  report.checks.push('CSRF enforcement, actual sklearn three-group Dengue fit, identical-run reuse and saved-run retrieval');

  const evaluated = await ctx.post('/api/v1/admin/analytics/evaluation-runs/', { data: filters, headers });
  assert.ok([200, 201].includes(evaluated.status()), `Evaluation HTTP ${evaluated.status()}`);
  const evaluation = await evaluated.json();
  assert.equal(evaluation.result.grid.length, 16);
  assert.equal(evaluation.result.stability.repeats.length, 3);
  assert.ok(Number.isFinite(evaluation.result.synthetic_pattern_recovery.adjusted_rand_index.value));
  report.evaluation = evaluation.result;
  report.checks.push('16-combination evaluation, seeded stability and separated synthetic truth recovery');

  const empty = await (await ctx.post('/api/v1/admin/analytics/cluster-runs/', { data: { ...filters, station_id: 'CHURCHGATE', date_from: '2026-09-29' }, headers })).json();
  assert.equal(empty.result.counts.cluster_count, 0);
  assert.equal(empty.result.metrics.silhouette.value, null);
  const invalid = await ctx.post('/api/v1/admin/analytics/cluster-runs/', { data: { ...filters, radius_km: 100 }, headers });
  assert.equal(invalid.status(), 400);
  report.checks.push('Empty cohort and invalid parameter handling');

  for (const role of ['patient', 'doctor', 'pharmacist']) {
    const other = await session(role);
    assert.equal((await other.ctx.get('/api/v1/admin/analytics/catalog/')).status(), 403, `${role} catalog denied`);
    assert.equal((await other.ctx.post('/api/v1/admin/analytics/cluster-runs/', { data: filters, headers: other.headers })).status(), 403, `${role} run denied`);
    if (role === 'patient') {
      assert.equal((await other.ctx.get('/api/v1/patients/me/')).status(), 200);
      const card = await other.ctx.get('/api/v1/patients/me/card.pdf/');
      assert.equal(card.status(), 200);
      assert.ok(card.headers()['content-type'].includes('application/pdf'));
    }
  }
  report.checks.push('Real patient/doctor/pharmacy logins denied analytics; patient profile and health card PDF available');
  writeFileSync(path.join(root, '.local/synthetic/verification.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ status: 'passed', checks: report.checks, dbscan: report.dbscan, report: '.local/synthetic/verification.json' }, null, 2));
} finally {
  await Promise.all(contexts.map(context => context.dispose()));
}
