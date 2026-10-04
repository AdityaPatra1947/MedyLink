// Real browser smoke test for the local synthetic demo; no API stubs.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const { chromium, expect: baseExpect } = require('@playwright/test');
const expect = baseExpect.configure({ timeout: 60000 });
const origin = process.env.SYNTHETIC_VERIFY_URL || 'http://localhost:3001';
assert.ok(['localhost', '127.0.0.1'].includes(new URL(origin).hostname));
const credentials = JSON.parse(readFileSync(path.join(root, '.local/synthetic/mumbai_stations_v1/credentials.json'), 'utf8'));
assert.equal(credentials.synthetic, true);
const admin = credentials.accounts.find(row => row.role === 'admin');
const browser = await chromium.launch({ channel: 'chrome', headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  page.setDefaultTimeout(120000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${origin}/admin/analytics`);
  await page.getByLabel('Email address').fill(admin.email);
  await page.getByLabel(/^Password/).fill(admin.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Station-area distribution', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Run clustering', exact: true })).toBeEnabled();
  const clusterResponse = page.waitForResponse(response => response.url().includes('/analytics/cluster-runs/') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Run clustering', exact: true }).click();
  const run = await (await clusterResponse).json();
  assert.equal(run.result.counts.cluster_count, 3);
  await expect(page.getByRole('heading', { name: 'The groups in this run', exact: true })).toBeVisible();
  await page.locator('#admin-analytics-title').scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(root, '.local/synthetic/analytics-desktop.png'), fullPage: false });
  const evaluationResponse = page.waitForResponse(response => response.url().includes('/analytics/evaluation-runs/') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Run evaluation', exact: true }).click();
  const evaluation = await (await evaluationResponse).json();
  assert.equal(evaluation.result.grid.length, 16);
  await expect(page.getByRole('button', { name: 'Re-run evaluation', exact: true })).toBeEnabled();
  await page.getByRole('heading', { name: 'Parameter explorer & stability', exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(root, '.local/synthetic/analytics-evaluation.png'), fullPage: false });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Desktop overflow');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('#admin-analytics-title').scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(root, '.local/synthetic/analytics-mobile.png'), fullPage: false });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile overflow');
  await page.getByRole('combobox', { name: 'Station area', exact: true }).selectOption('CHURCHGATE');
  await page.getByLabel('From', { exact: true }).fill('2026-09-29');
  await page.getByRole('button', { name: 'Apply filters', exact: false }).click();
  await expect(page.getByRole('heading', { name: 'No patients match these filters', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Reset demo', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Run clustering', exact: true })).toBeEnabled();
  assert.deepEqual(errors, []);
  console.log('PASS: real admin UI login; DBSCAN map and cluster details; 16-setting evaluation; desktop/mobile no overflow; empty filters; reset; no browser exceptions. Screenshots saved privately in .local/synthetic/.');
} finally {
  await browser.close();
}
