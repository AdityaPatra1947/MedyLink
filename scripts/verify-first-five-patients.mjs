/**
 * Read-only clinical checks of the first five synthetic patient dashboards.
 * Run after importing output/pdf/first-five-patients/manifest.json and restarting
 * the synthetic servers. Sign-in/out and report access create normal audit events;
 * downloading the five latest reports increments their download counters.
 * Never points at the normal demo server or changes clinical data.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium, expect as baseExpect } from "../frontend/node_modules/@playwright/test/index.mjs";

const expect = baseExpect.configure({ timeout: 45_000 });

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const origin = "http://localhost:3001";
const manifest = JSON.parse(await readFile(path.join(root, "output/pdf/first-five-patients/manifest.json"), "utf8"));
assert.equal(manifest.synthetic, true, "Only the synthetic report manifest is supported.");
assert.equal(manifest.patients.length, 5);
const credentials = JSON.parse(await readFile(path.join(root, ".local/synthetic/mumbai_stations_v1/credentials.json"), "utf8"));
assert.equal(credentials.synthetic, true, "Only private synthetic credentials are supported.");
const accounts = new Map(credentials.accounts.map(account => [account.source_id, account]));
const output = path.join(root, ".local/first-five-dashboard-verification");
await mkdir(output, { recursive: true });
const results = [];
const browser = await chromium.launch({ channel: "chrome", headless: true });
const failureMessage = error => String(error?.message || error).split(/\r?\n/).find(line => line.trim()) || "Unknown verification failure";

async function json(context, route) {
  try {
    const response = await context.request.get(origin + "/api/v1" + route, { timeout: 60_000 });
    assert.equal(response.status(), 200, `${route}: expected successful authenticated response`);
    return response.json();
  } catch (error) { throw new Error(`${route}: ${failureMessage(error)}`); }
}
async function allRows(context, route) {
  const rows = [];
  for (let page = 1; page <= 50; page++) {
    const response = await json(context, `${route}?page=${page}`);
    rows.push(...response.results);
    if (response.next === null || (!response.next && response.results.length < 50)) return rows;
  }
  throw new Error(`Pagination did not end for ${route}`);
}
function band(value, limits) { return limits.find(([ceiling]) => value < ceiling)[1]; }
function expectedScore(systolic, diastolic, glucose, adherence) {
  const s = band(systolic, [[90, 40], [120, 100], [130, 85], [140, 70], [160, 50], [Infinity, 25]]);
  const d = band(diastolic, [[60, 40], [80, 100], [90, 70], [100, 50], [Infinity, 25]]);
  const g = band(glucose, [[70, 30], [100, 100], [126, 70], [180, 40], [Infinity, 20]]);
  return Math.round(.3 * s + .2 * d + .3 * g + .2 * adherence);
}
async function pdf(context, url, disposition, expectedHash) {
  const response = await context.request.get(new URL(url, origin).href, { timeout: 60_000 });
  assert.equal(response.status(), 200, `${url}: response status`);
  assert.match(response.headers()["content-type"] || "", /^application\/pdf/);
  assert.match(response.headers()["content-disposition"] || "", new RegExp(`^${disposition}[; ]`));
  const bytes = await response.body();
  assert.equal(bytes.subarray(0, 5).toString(), "%PDF-");
  assert.equal(createHash("sha256").update(bytes).digest("hex"), expectedHash, "Served PDF must match the imported source document.");
}

try {
  for (const [index, fixture] of manifest.patients.entries()) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: "reduce" });
    const page = await context.newPage();
    const errors = [];
    const pendingRequests = new Set();
    let phase = "sign-in";
    page.on("pageerror", error => errors.push(error.message));
    page.on("request", request => { if (new URL(request.url()).pathname.startsWith("/api/v1/patients/")) pendingRequests.add(request); });
    page.on("requestfinished", request => pendingRequests.delete(request));
    page.on("requestfailed", request => pendingRequests.delete(request));
    page.setDefaultTimeout(30_000);
    try {
      const account = accounts.get(`PAT${String(index + 1).padStart(4, "0")}`);
      assert.ok(account?.role === "patient" && account.email && account.password, "The private credentials file must contain each mapped patient account.");
      await page.goto(origin + "/login");
      await page.locator('[name="email"]').fill(account.email);
      await page.locator('[name="password"]').fill(account.password);
      await page.getByRole("button", { name: "Sign in", exact: true }).click();
      await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
      phase = "initial dashboard and section loading";
      const expectedLatest = fixture.reports.at(-1);
      const [expectedSystolic, expectedDiastolic] = expectedLatest.blood_pressure.split("/").map(Number);
      const initialScore = expectedScore(expectedSystolic, expectedDiastolic, expectedLatest.fasting_glucose, expectedLatest.taken_doses / expectedLatest.scheduled_doses * 100);
      await expect(page.getByRole("button", { name: "Health score details", exact: true })).toContainText(String(initialScore));
      await expect.poll(() => pendingRequests.size, { timeout: 60_000, message: "Initial patient clinical requests should finish before further verification reads." }).toBe(0);

      phase = "read patient profile";
      const profile = await json(context, "/patients/me/");
      phase = "read dashboard";
      const dashboard = await json(context, "/patients/me/dashboard/");
      phase = "read adherence";
      const adherence = await json(context, "/patients/me/adherence/");
      phase = "read report library";
      const reports = await allRows(context, "/patients/me/reports/");
      phase = "read consultations";
      const records = await allRows(context, "/patients/me/records/");
      phase = "read doctor visits";
      const visits = await allRows(context, "/patients/me/visits/");
      assert.equal(profile.id, fixture.patient_id);
      assert.equal(profile.name, fixture.name);
      assert.equal(profile.account_id, fixture.account_id);
      const byId = new Map(reports.map(item => [item.id, item]));
      const clinicalById = new Map(records.map(item => [item.id, item]));
      const doctors = new Set();
      for (const expected of fixture.reports) {
        phase = `verify report ${expected.id}`;
        const report = byId.get(expected.id);
        assert.ok(report, `Missing monthly report ${expected.id}`);
        assert.equal(report.uploaded_by.role, "doctor");
        assert.equal(report.uploaded_by.name, expected.doctor);
        assert.equal(report.extraction?.status, "extracted");
        assert.equal(report.extraction.measured_at.slice(0, 10), expected.date);
        const [systolic, diastolic] = expected.blood_pressure.split("/").map(Number);
        assert.equal(report.extraction.blood_pressure.systolic, systolic);
        assert.equal(report.extraction.blood_pressure.diastolic, diastolic);
        assert.equal(report.extraction.blood_sugar.value, expected.fasting_glucose);
        const record = clinicalById.get(report.record_id);
        assert.ok(record?.complaint && record.diagnosis && record.notes, "Every monthly report requires a complete doctor-authored consultation.");
        assert.equal(record.doctor_name, expected.doctor);
        doctors.add(record.doctor_id);
        const visit = visits.find(item => item.record.id === record.id);
        assert.ok(visit?.prescriptions.length, "Monthly visit must contain its prescription.");
        for (const prescription of visit.prescriptions) {
          assert.ok(prescription.items.length);
          for (const item of prescription.items) assert.ok(item.medicine && item.dosage && item.instructions);
        }
        await pdf(context, report.view_url, "inline", expected.sha256);
      }
      assert.ok(doctors.size >= 2, "Consultations must cover different synthetic doctors.");
      phase = "verify dashboard and adherence calculations";
      assert.equal(fixture.reports.length, fixture.months);
      const latest = fixture.reports.at(-1);
      const report = byId.get(latest.id);
      const [systolic, diastolic] = latest.blood_pressure.split("/").map(Number);
      assert.equal(dashboard.latest.blood_pressure.report_id, latest.id);
      assert.equal(dashboard.latest.blood_sugar.report_id, latest.id);
      assert.equal(dashboard.latest.blood_pressure.systolic, systolic);
      assert.equal(dashboard.latest.blood_pressure.diastolic, diastolic);
      assert.equal(dashboard.latest.blood_sugar.value, latest.fasting_glucose);
      assert.ok(dashboard.trends.blood_pressure.length >= Math.min(fixture.months, 24));
      assert.ok(dashboard.trends.blood_sugar.length >= Math.min(fixture.months, 24));
      assert.equal(dashboard.counts.reports, reports.length);
      assert.equal(dashboard.counts.records, records.length);

      const summary = adherence.summary;
      assert.ok(summary && summary.scheduled_doses > 0);
      const includedLogs = adherence.results.filter(row => row.date >= summary.period_start && row.date <= summary.period_end);
      assert.equal(includedLogs.reduce((sum, row) => sum + row.taken_doses, 0), summary.taken_doses);
      assert.equal(includedLogs.reduce((sum, row) => sum + row.scheduled_doses, 0), summary.scheduled_doses);
      const actualAdherence = summary.taken_doses / summary.scheduled_doses * 100;
      assert.ok(Math.abs(summary.percentage - actualAdherence) < .051, "Displayed adherence must be rounded from actual saved dose counts.");
      assert.deepEqual(dashboard.adherence, summary);
      assert.equal(dashboard.health_score.label, "Demo health score");
      assert.equal(dashboard.health_score.value, expectedScore(systolic, diastolic, latest.fasting_glucose, actualAdherence));
      const weightSum = dashboard.health_score.components.reduce((sum, item) => sum + item.weight, 0);
      const weightedSum = dashboard.health_score.components.reduce((sum, item) => sum + item.score * item.weight, 0);
      assert.equal(Math.round(weightedSum / weightSum), dashboard.health_score.value);
      assert.ok(dashboard.health_score.formula && dashboard.health_score.disclaimer);
      await pdf(context, report.download_url, "attachment", latest.sha256);
      phase = "verify cross-patient access denial";
      const foreign = manifest.patients[(index + 1) % manifest.patients.length].reports.at(-1);
      for (const action of ["view", "download"]) {
        const denied = await context.request.get(`${origin}/api/v1/reports/${foreign.id}/${action}/`, { timeout: 60_000 });
        assert.ok([403, 404].includes(denied.status()), "Patients must not access another patient's report.");
      }
      await expect(page.getByText("Risk level", { exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Health score details", exact: true })).toContainText(String(dashboard.health_score.value));
      await expect(page.getByRole("button", { name: "Medication adherence", exact: true })).toContainText(`${summary.percentage}%`);

      if (index === 0) {
        phase = "verify score and adherence popups";
        await page.getByRole("button", { name: "Health score details", exact: true }).click();
        const scoreDialog = page.getByRole("dialog", { name: "Health score", exact: true });
        await expect(scoreDialog).toContainText(dashboard.health_score.formula);
        await expect(scoreDialog).toContainText("How your score is calculated");
        await page.screenshot({ path: path.join(output, "patient-1-score.png") });
        await page.keyboard.press("Escape");
        await page.getByRole("button", { name: "Medication adherence", exact: true }).click();
        await expect(page.getByRole("dialog")).toContainText(`(${summary.taken_doses} ÷ ${summary.scheduled_doses}) × 100 = ${summary.percentage}%`);
        await page.screenshot({ path: path.join(output, "patient-1-adherence.png") });
        await page.keyboard.press("Escape");
        await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Medical reports", exact: true }).click();
        phase = "verify PDF preview action";
        const previewLink = page.locator("#patient-reports").locator(`a[href="${report.view_url}"]`);
        await expect(previewLink).toBeVisible();
        const popupEvent = page.waitForEvent("popup");
        await previewLink.click();
        const popup = await popupEvent;
        await expect(popup).toHaveURL(new RegExp(`/reports/${latest.id}/view/$`));
        await popup.close();
        await page.screenshot({ path: path.join(output, "patient-1-reports.png") });
      }
      assert.deepEqual(errors, [], "Browser runtime errors");
      results.push({ account_id: fixture.account_id, name: fixture.name, reports_verified: fixture.months, doctors: doctors.size, health_score: dashboard.health_score.value, adherence: summary.percentage, taken_doses: summary.taken_doses, scheduled_doses: summary.scheduled_doses, latest_blood_pressure: latest.blood_pressure, latest_fasting_glucose: latest.fasting_glucose, pdf_hashes: "matched", report_access_isolation: "passed" });
      console.log(`Verified ${fixture.account_id}: ${fixture.months} reports, score ${dashboard.health_score.value}, adherence ${summary.percentage}%.`);
    } catch (error) {
      const safeError = new Error(`${fixture.account_id} during ${phase}: ${failureMessage(error)}`);
      console.error(safeError.message);
      if (pendingRequests.size) console.error(`Pending API paths: ${[...pendingRequests].map(request => new URL(request.url()).pathname).join(", ")}`);
      throw safeError;
    } finally {
      try {
        const token = await context.request.get(origin + "/api/v1/auth/csrf/", { timeout: 5_000 });
        await context.request.post(origin + "/api/v1/auth/logout/", { timeout: 5_000, headers: { "X-CSRFToken": (await token.json()).csrfToken, Origin: origin }, data: {} });
      } catch (error) { console.warn(`${fixture.account_id}: sign-out cleanup did not finish: ${failureMessage(error)}`); }
      try { await context.close(); }
      catch (error) { console.warn(`${fixture.account_id}: browser cleanup did not finish: ${failureMessage(error)}`); }
    }
  }
  await writeFile(path.join(output, "results.json"), JSON.stringify({ verified_at: new Date().toISOString(), manifest_as_of: manifest.as_of, status: "passed", patients: results }, null, 2));
  console.log("All five synthetic patient dashboards passed report, calculation, PDF, isolation, and UI checks.");
} finally {
  try { await browser.close(); }
  catch (error) { console.warn(`Browser shutdown did not finish: ${failureMessage(error)}`); }
}
