import { test, expect, type Page, type Route } from "@playwright/test";
import type { Profile, User } from "../lib/types";
import type { PatientDashboardData } from "../lib/patient-dashboard-types";

const patient: User = { id: "synthetic-user", account_id: "P-TEST01", name: "Synthetic Patient", email: "patient@example.test", role: "patient", email_verified: true };
const profile: Profile = { id: "synthetic-patient", account_id: patient.account_id, health_id: "AT-SYNTHETIC", name: patient.name, date_of_birth: "1990-01-02", gender: "prefer_not_to_say", phone: "", address: "", blood_group: "B+", emergency_contact: "", allergy_status: "unknown", photo_url: null };
const readings = [0, 1, 2].map(index => ({ record_id: `record-${index}`, recorded_at: `2026-09-${21 + index}T09:00:00Z`, author: "Synthetic Doctor", source: "Consultation" }));
const record = { id: "record-2", patient_id: profile.id, doctor_id: "synthetic-doctor", doctor_name: "Synthetic Doctor", complaint: "Synthetic consultation", diagnosis: "", notes: "Synthetic test-only notes", vitals: { blood_pressure: "124/82", glucose_mg_dl: "118" }, created_at: readings[2].recorded_at };
const report = { id: "synthetic-report", patient_id: profile.id, record_id: record.id, name: "synthetic.pdf", title: "Synthetic report", content_type: "application/pdf", size_bytes: 100, uploaded_by: { id: patient.id, name: patient.name, role: "patient" }, created_at: readings[2].recorded_at, download_url: "/api/v1/reports/synthetic-report/download/", view_url: "/api/v1/reports/synthetic-report/view/", extraction: { status: "extracted", measured_at: readings[2].recorded_at, blood_pressure: { systolic: 124, diastolic: 82, unit: "mmHg" }, blood_sugar: { value: 118, unit: "mg/dL", context: "fasting" } } };
const condition = { id: "synthetic-condition", name: "Synthetic condition", notes: "Test fixture only", source: "clinician_recorded", author_id: "synthetic-doctor", author_name: "Synthetic Doctor", created_at: readings[2].recorded_at };
const prescription = { id: "synthetic-prescription", doctor_id: "synthetic-doctor", patient: profile, doctor_name: "Synthetic Doctor", doctor_registration: "SYNTHETIC", created_at: readings[2].recorded_at, valid_until: "2099-01-01T00:00:00Z", status: "issued", notes: "Synthetic prescription", items: [{ id: "item-1", medicine: "Synthetic medicine", dosage: "Fixture instructions", instructions: "", quantity: "10", unit: "tablet", dispensed: "0", remaining: "10" }], allergies: [], allergy_status: "unknown" };
type AdherenceSummary = { percentage: number; scheduled_doses: number; taken_doses: number; days_logged: number; period_days: number };
type Lab = { id: string; name: string; value: number; unit: string; reference_low: number | null; reference_high: number | null; flag: string; measured_at: string; recorded_by_name: string; source: string; report_id: null };

function dashboardFixture(empty = false): PatientDashboardData {
  const pressure = empty ? [] : readings.map((row, index) => ({ ...row, systolic: 132 - index * 4, diastolic: 86 - index * 2, unit: "mmHg" }));
  const glucose = empty ? [] : readings.map((row, index) => ({ ...row, value: 130 - index * 6, unit: "mg/dL", context: "fasting" }));
  return {
    counts: { records: empty ? 0 : 3, active_prescriptions: empty ? 0 : 1, conditions: empty ? 0 : 1, reports: empty ? 0 : 1, report_downloads: empty ? 0 : 2 },
    latest: { blood_pressure: pressure.at(-1) ?? null, blood_sugar: glucose.at(-1) ?? null },
    trends: { blood_pressure: pressure, blood_sugar: glucose },
    health_score: null, health_score_reason: "A health score calculation policy has not been configured.",
    adherence: null as AdherenceSummary | null,
    lab_summary: { abnormal: null as number | null, total: null as number | null },
    regional_alerts: { available: false, items: [] },
    recent_notifications: empty ? [] : [{ id: `record:${record.id}`, kind: "record", title: "Consultation: Synthetic consultation", created_at: record.created_at, target_tab: "records" }, { id: `report:${report.id}`, kind: "report", title: "Report uploaded: Synthetic report", created_at: report.created_at, target_tab: "reports" }],
  };
}

async function mockDashboard(page: Page, empty = false, failFirstRead = false) {
  const dashboard = dashboardFixture(empty);
  const patientProfile = { ...profile };
  const doseLogs: { id: string; date: string; scheduled_doses: number; taken_doses: number }[] = [];
  const labs: Lab[] = [];
  const state = { unexpected: [] as string[], errors: [] as string[], dashboardReads: 0, failDashboard: failFirstRead, showVisits: false, reportViews: 0, reportDownloads: 0, reportUploads: 0, doseWrites: 0, labWrites: 0, profileWrites: 0, dashboard };
  page.on("pageerror", error => state.errors.push(error.message));
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  // All API traffic is intercepted, including requests opened by links in new tabs.
  // Unrecognized requests fail locally and never reach the database or email service.
  await page.context().route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (method === "GET" && path === report.view_url) { state.reportViews++; return route.fulfill({ contentType: "text/html", body: "<title>Synthetic PDF preview</title><p>Synthetic report preview fixture</p>" }); }
    if (method === "GET" && path === report.download_url) { state.reportDownloads++; return route.fulfill({ contentType: "application/pdf", headers: { "Content-Disposition": 'attachment; filename="synthetic.pdf"' }, body: "%PDF-1.4 synthetic download fixture" }); }
    if (method === "GET" && path === "/api/v1/auth/me/") return json(route, { user: patient });
    if (method === "GET" && path === "/api/v1/auth/csrf/") return json(route, { csrfToken: "synthetic-csrf" });
    if (method === "GET" && path === "/api/v1/patients/me/") return json(route, patientProfile);
    if (method === "PATCH" && path === "/api/v1/patients/me/") { state.profileWrites++; Object.assign(patientProfile, request.postDataJSON()); return json(route, patientProfile); }
    if (method === "GET" && path === "/api/v1/patients/me/dashboard/") {
      state.dashboardReads++;
      if (state.failDashboard) return json(route, { detail: "Synthetic dashboard load failure." }, 503);
      return json(route, dashboard);
    }
    if (method === "GET" && path === "/api/v1/auth/sessions/") return json(route, { results: [{ id: "synthetic-session", current: true, created_at: readings[0].recorded_at, last_used_at: readings[2].recorded_at, expires_at: "2099-01-01T00:00:00Z", user_agent: "Synthetic browser session" }] });
    if (method === "GET" && path === "/api/v1/patients/me/dispensing/") return json(route, { results: empty ? [] : [{ id: "synthetic-dispensing", prescription_id: prescription.id, pharmacist_name: "Synthetic Pharmacist", shop_name: "Synthetic Pharmacy", patient_name: patient.name, patient_health_id: profile.health_id, created_at: readings[2].recorded_at, items: [{ medicine: "Synthetic medicine", quantity: "2", unit: "tablet" }] }], next: null });
    if (method === "GET" && path === `/api/v1/prescriptions/${prescription.id}/`) return json(route, prescription);
    if (method === "GET" && path === "/api/v1/patients/me/card/") return json(route, { patient_id: profile.id, account_id: profile.account_id, health_id: profile.health_id, name: profile.name, locator: "synthetic-qr", qr_data_url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+cG0cAAAAASUVORK5CYII=", date_of_birth: profile.date_of_birth, blood_group: profile.blood_group, photo_url: null });
    if (method === "GET" && path === "/api/v1/patients/me/records/") return json(route, { results: empty ? [] : [record], next: null });
    if (method === "GET" && path === "/api/v1/patients/me/reports/") return json(route, { results: empty ? [] : [report], next: null });
    if (method === "POST" && path === "/api/v1/patients/me/reports/") {
      state.reportUploads++;
      dashboard.counts.reports++;
      if (dashboard.latest.blood_pressure) Object.assign(dashboard.latest.blood_pressure, { systolic: 122, diastolic: 80 });
      return json(route, report, 201);
    }
    if (method === "GET" && path === "/api/v1/patients/me/prescriptions/") return json(route, { results: empty ? [] : [prescription], next: null });
    if (method === "GET" && path === "/api/v1/patients/me/visits/") return json(route, { results: state.showVisits ? [{ id: record.id, created_at: record.created_at, doctor: { id: record.doctor_id, name: record.doctor_name, qualification: "MD", specialty: "General medicine", clinic_name: "Synthetic clinic" }, record: { ...record, diagnosis: "Synthetic diagnosis for presentation testing" }, prescriptions: [prescription], reports: [report] }] : [], next: null });
    if (method === "GET" && path === `/api/v1/patients/${profile.id}/conditions/`) return json(route, { results: empty ? [] : [condition], next: null });
    if (method === "GET" && path === `/api/v1/patients/${profile.id}/allergies/`) return json(route, { results: [], next: null });
    if (method === "GET" && path === "/api/v1/patients/me/adherence/") return json(route, { results: doseLogs, summary: dashboard.adherence });
    if (method === "PUT" && path === "/api/v1/patients/me/adherence/") {
      state.doseWrites++;
      const body = request.postDataJSON();
      expect(body).toMatchObject({ scheduled_doses: 4, taken_doses: 3 });
      expect(body.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      doseLogs.splice(0, doseLogs.length, { id: "dose-1", ...body });
      dashboard.adherence = { percentage: 75, scheduled_doses: 4, taken_doses: 3, days_logged: 1, period_days: 30 };
      return json(route, doseLogs[0]);
    }
    if (method === "GET" && path === "/api/v1/patients/me/labs/") return json(route, { results: labs, next: null, summary: dashboard.lab_summary });
    if (method === "POST" && path === "/api/v1/patients/me/labs/") {
      state.labWrites++;
      const body = request.postDataJSON();
      const value = Number(body.value);
      const low = body.reference_low === null ? null : Number(body.reference_low);
      const high = body.reference_high === null ? null : Number(body.reference_high);
      const flag = high !== null && value > high ? "high" : low !== null && value < low ? "low" : low === null && high === null ? "unknown" : "normal";
      labs.unshift({ id: `lab-${state.labWrites}`, name: body.name, value, unit: body.unit, reference_low: low, reference_high: high, flag, measured_at: body.measured_at, recorded_by_name: patient.name, source: "patient", report_id: null });
      dashboard.lab_summary = { total: labs.length, abnormal: labs.some(row => row.flag !== "unknown") ? labs.filter(row => ["high", "low"].includes(row.flag)).length : null };
      return json(route, labs[0], 201);
    }
    state.unexpected.push(`${method} ${path}`);
    return json(route, { detail: "Unexpected endpoint blocked by isolated dashboard test." }, 501);
  });
  return state;
}

async function overview(page: Page) {
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Overview", exact: true }).click();
}
function expectClean(state: Awaited<ReturnType<typeof mockDashboard>>) {
  expect(state.unexpected).toEqual([]);
  expect(state.errors).toEqual([]);
}


function metric(page: Page, label: string) {
  const names: Record<string, string> = { "Health score": "Health score details", "Adherence": "Medication adherence", "Conditions": "Chronic conditions" };
  return page.getByTestId("patient-dashboard").locator(`[aria-label="${names[label] || label}"]`);
}
async function openDashboard(page: Page) {
  await page.goto("/");
  await expect(metric(page, "Active prescriptions")).toBeVisible();
}
async function closeDialog(page: Page) {
  await page.getByRole("dialog").getByRole("button", { name: /close/i }).first().click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
}

test("sidebar opens records, prescriptions, reports, QR card, and profile from one continuous page", async ({ page }, testInfo) => {
  const state = await mockDashboard(page);
  await openDashboard(page);
  await page.screenshot({ path: `../.local/patient-scroll-overview-${testInfo.project.name}.png` });
  await navigationLink(page, "records").click();
  await expect(page.getByRole("heading", { name: "Your medical timeline", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: record.complaint, exact: true })).toBeVisible();
  await overview(page);
  await navigationLink(page, "prescriptions").click();
  await expect(page.locator("#patient-prescriptions").getByRole("button", { name: "View prescription", exact: true })).toBeVisible();
  await overview(page);
  await navigationLink(page, "reports").click();
  await expect(page.locator("#patient-reports").getByRole("link", { name: "Download Synthetic report", exact: true })).toHaveAttribute("href", report.download_url);
  await overview(page);
  await navigationLink(page, "card").click();
  await expect(page.getByRole("heading", { name: "Your health card", exact: true })).toBeVisible();
  const card = page.getByRole("button", { name: "Flip health card", exact: true });
  await card.click();
  await expect(card).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("img", { name: "Health card QR code", exact: true })).toBeVisible();
  await overview(page);
  await navigationLink(page, "profile").click();
  await expect(page.getByRole("heading", { name: "Personal information", exact: true })).toBeVisible();
  await expect(page.locator('select[name="blood_group"]')).toHaveValue("B+");
  expectClean(state);
});

test("unavailable score and regional alerts explain missing setup; conditions stay actionable", async ({ page }) => {
  const state = await mockDashboard(page);
  await openDashboard(page);
  await metric(page, "Health score").click();
  await expect(page.getByRole("dialog")).toContainText(/not.*configured|unavailable/i);
  await closeDialog(page);
  await expect(page.getByRole("button", { name: /risk level/i })).toHaveCount(0);
  await expect(page.getByText("Risk level", { exact: true })).toHaveCount(0);
  await navigationLink(page, "profile").click();
  await expect(page.locator("#patient-profile").getByRole("heading", { name: "Chronic conditions", exact: true })).toBeVisible();
  await expect(page.locator("#patient-profile").getByText(condition.name, { exact: true })).toBeVisible();
  await overview(page);
  await page.getByRole("button", { name: /regional|outbreak|health alerts/i }).click();
  await expect(page.getByRole("dialog")).toContainText(/not.*connected|not.*configured|unavailable/i);
  await expect(page.getByRole("dialog")).not.toContainText("No outbreak alerts");
  await closeDialog(page);
  expectClean(state);
});

test("record and report notifications open the matching history", async ({ page }) => {
  const state = await mockDashboard(page);
  await openDashboard(page);
  await page.getByRole("button", { name: /notifications/i }).click();
  await page.getByRole("button", { name: /Consultation: Synthetic consultation/ }).click();
  await expect(page.getByRole("heading", { name: "Your medical timeline", exact: true })).toBeVisible();
  await overview(page);
  await page.getByRole("button", { name: /notifications/i }).click();
  await page.getByRole("button", { name: /Report uploaded: Synthetic report/ }).click();
  await expect(page.locator("#patient-reports").getByRole("link", { name: "Download Synthetic report", exact: true })).toBeVisible();
  expectClean(state);
});

test("daily adherence log refreshes the dashboard using saved taken and scheduled counts", async ({ page }) => {
  const state = await mockDashboard(page);
  await openDashboard(page);
  await metric(page, "Adherence").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("No dose logs yet.");
  await dialog.getByLabel("Scheduled doses", { exact: false }).fill("4");
  await dialog.getByLabel("Doses taken", { exact: false }).fill("3");
  await dialog.getByRole("button", { name: "Save dose log", exact: true }).click();
  await expect(dialog).toContainText("75%");
  await expect(dialog.getByRole("button", { name: "Update dose log", exact: true })).toBeVisible();
  await closeDialog(page);
  await expect(metric(page, "Adherence")).toContainText("75%");
  expect(state.doseWrites).toBe(1);
  expect(state.dashboardReads).toBeGreaterThan(1);
  expectClean(state);
});

test("lab entry distinguishes unclassified results from values outside the supplied range", async ({ page }) => {
  const state = await mockDashboard(page);
  await openDashboard(page);
  await metric(page, "Abnormal lab values").click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Add lab result", exact: true }).click();
  await dialog.getByLabel("Test name", { exact: false }).fill("Synthetic test without range");
  await dialog.getByLabel("Result value", { exact: false }).fill("120");
  await dialog.getByLabel("Unit", { exact: false }).fill("mg/dL");
  await dialog.getByRole("button", { name: "Save lab result", exact: true }).click();
  await expect(dialog.getByText("unclassified", { exact: true })).toBeVisible();
  await expect(dialog).toContainText("— outside the supplied range · 1 tracked tests");
  await dialog.getByRole("button", { name: "Add lab result", exact: true }).click();
  await dialog.getByLabel("Test name", { exact: false }).fill("Synthetic test with range");
  await dialog.getByLabel("Result value", { exact: false }).fill("120");
  await dialog.getByLabel("Unit", { exact: false }).fill("mg/dL");
  await dialog.getByLabel("Reference lower limit (optional)", { exact: true }).fill("70");
  await dialog.getByLabel("Reference upper limit (optional)", { exact: true }).fill("100");
  await dialog.getByRole("button", { name: "Save lab result", exact: true }).click();
  await expect(dialog.getByText("high", { exact: true })).toBeVisible();
  await expect(dialog).toContainText("1 outside the supplied range · 2 tracked tests");
  await closeDialog(page);
  await expect(metric(page, "Abnormal lab values")).toContainText("1");
  expect(state.labWrites).toBe(2);
  expectClean(state);
});

test("empty dashboard keeps absent observations unknown and does not invent reassuring data", async ({ page }) => {
  const state = await mockDashboard(page, true);
  await openDashboard(page);
  await expect(metric(page, "Medical records")).toContainText("0");
  await expect(metric(page, "Active prescriptions")).toContainText("0");
  await expect(metric(page, "Health score")).not.toContainText("100");
  await expect(metric(page, "Adherence")).not.toContainText("0%");
  await expect(page.getByText("No outbreak alerts in your region", { exact: true })).toHaveCount(0);
  await metric(page, "Abnormal lab values").click();
  await expect(page.getByRole("dialog")).toContainText("No structured lab results yet.");
  await closeDialog(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  expectClean(state);
});


test("vital chart points work by click and keyboard and expose dated reading tables", async ({ page }) => {
  const state = await mockDashboard(page);
  await openDashboard(page);
  const dashboard = page.getByTestId("patient-dashboard");
  const pressure = dashboard.getByRole("button", { name: /^Blood pressure reading 1:/ });
  await pressure.click();
  await expect(dashboard.getByRole("status").filter({ hasText: "132/86" })).toBeVisible();
  const glucose = dashboard.getByRole("button", { name: /^Blood sugar reading 2:/ });
  await glucose.focus();
  await glucose.press("Enter");
  await expect(dashboard.getByRole("status").filter({ hasText: "124" })).toBeVisible();
  await dashboard.getByText("View blood pressure readings", { exact: true }).click();
  const pressureTable = dashboard.getByRole("table", { name: "Blood pressure readings", exact: true });
  await expect(pressureTable).toBeVisible();
  await expect(pressureTable.getByRole("row")).toHaveCount(4);
  await expect(pressureTable).toContainText("Synthetic Doctor");
  await dashboard.getByText("View blood sugar readings", { exact: true }).click();
  const glucoseTable = dashboard.getByRole("table", { name: "Blood sugar readings", exact: true });
  await expect(glucoseTable).toBeVisible();
  await expect(glucoseTable).toContainText("fasting");
  await metric(page, "Latest blood pressure").click();
  await expect(page.getByRole("dialog", { name: "Blood pressure readings", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await metric(page, "Blood sugar").click();
  await expect(page.getByRole("dialog", { name: "Blood sugar readings", exact: true })).toBeVisible();
  await closeDialog(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  expectClean(state);
});

test("dashboard load failure offers a retry without showing fabricated summaries", async ({ page }) => {
  const state = await mockDashboard(page, false, true);
  await page.goto("/");
  await expect(page.getByRole("alert").filter({ hasText: "Synthetic dashboard load failure." })).toBeVisible();
  await expect(metric(page, "Active prescriptions")).toHaveCount(0);
  state.failDashboard = false;
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(metric(page, "Active prescriptions")).toBeVisible();
  expect(state.dashboardReads).toBeGreaterThan(1);
  expectClean(state);
});


test("single and unchanged vital series stay selectable with finite chart coordinates", async ({ page }) => {
  const state = await mockDashboard(page);
  state.dashboard.trends.blood_pressure.splice(1);
  state.dashboard.latest.blood_pressure = state.dashboard.trends.blood_pressure[0];
  for (const row of state.dashboard.trends.blood_sugar) row.value = 118;
  await openDashboard(page);
  const dashboard = page.getByTestId("patient-dashboard");
  await expect(dashboard.getByRole("button", { name: /^Blood pressure reading/ })).toHaveCount(1);
  await dashboard.getByRole("button", { name: /^Blood pressure reading 1:/ }).click();
  const glucose = dashboard.getByRole("button", { name: /^Blood sugar reading 3:/ });
  await glucose.focus();
  await glucose.press("Space");
  await expect(glucose).toHaveAttribute("aria-pressed", "true");
  const coordinates = await dashboard.getByRole("group", { name: /trend chart$/ }).locator("polyline").evaluateAll(elements => elements.map(element => element.getAttribute("points")));
  expect(coordinates).toHaveLength(3);
  for (const points of coordinates) expect(points).not.toMatch(/NaN|Infinity|undefined/);
  expectClean(state);
});

test("configured metrics disclose their calculation and alert source instead of hiding the inputs", async ({ page }) => {
  const state = await mockDashboard(page);
  state.dashboard.health_score = { value: 70, label: "Synthetic test score", method: "Synthetic browser-test policy (test)", calculated_at: readings[2].recorded_at, components: [{ key: "systolic", label: "Synthetic pressure component", value: 124, score: 70, weight: 1 }] };
  state.dashboard.regional_alerts = { available: true, items: [{ id: "synthetic-alert", title: "Synthetic alert fixture", description: "Only an isolated browser-test fixture.", region: "Synthetic region", source_url: "https://example.test/synthetic-alert", published_at: readings[2].recorded_at }] };
  await openDashboard(page);
  await expect(metric(page, "Health score")).toContainText("70");
  await metric(page, "Health score").click();
  await expect(page.getByRole("dialog")).toContainText("Synthetic browser-test policy (test)");
  await expect(page.getByRole("dialog")).toContainText("Synthetic pressure component");
  await closeDialog(page);
  await page.getByRole("button", { name: "Regional health alerts", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("link", { name: /Read the original health alert/ })).toHaveAttribute("href", "https://example.test/synthetic-alert");
  await closeDialog(page);
  expectClean(state);
});

test("health score and adherence show weighted arithmetic, source reports, and no risk level", async ({ page }, testInfo) => {
  const state = await mockDashboard(page);
  state.dashboard.health_score = {
    value: 84, label: "Demo health score", method: "synthetic-bp-glucose-v1", calculated_at: readings[2].recorded_at,
    formula: "round(0.30 × systolic + 0.20 × diastolic + 0.30 × glucose + 0.20 × adherence)",
    explanation: "The latest supported monthly report supplies blood pressure and fasting glucose; the last 30 days of recorded doses supply adherence.",
    disclaimer: "This synthetic demonstration score is not a clinically validated medical assessment.",
    components: [
      { key: "systolic", label: "Systolic blood pressure", value: 118, unit: "mmHg", score: 100, weight: .3, formula: "90–119 mmHg → 100 points", explanation: "Custom demonstration bands.", source_report_id: report.id, source_report_title: report.title, measured_at: readings[2].recorded_at },
      { key: "diastolic", label: "Diastolic blood pressure", value: 82, unit: "mmHg", score: 70, weight: .2 },
      { key: "glucose", label: "Fasting glucose", value: 110, unit: "mg/dL", score: 70, weight: .3 },
      { key: "adherence", label: "Medication adherence", value: 95, unit: "%", score: 95, weight: .2 },
    ],
  };
  state.dashboard.adherence = { percentage: 95, scheduled_doses: 60, taken_doses: 57, days_logged: 30, period_days: 30, period_start: "2026-09-01", period_end: "2026-09-30", missing_days: 0, source: "dose_logs", formula: "Adherence = taken ÷ scheduled × 100", explanation: "Counts come from the dose diary in the uploaded report and saved patient logs." };
  await openDashboard(page);
  await expect(page.getByText("Custom demo score · not a clinical assessment", { exact: true })).toBeVisible();
  await expect(page.getByText("Risk level", { exact: true })).toHaveCount(0);
  await metric(page, "Health score").focus();
  await page.keyboard.press("Enter");
  let dialog = page.getByRole("dialog", { name: "Health score", exact: true });
  await expect(dialog).toContainText("round((100 × 0.3 + 70 × 0.2 + 70 × 0.3 + 95 × 0.2) ÷ 1) = 84");
  await expect(dialog).toContainText("90–119 mmHg → 100 points");
  await expect(dialog).toContainText("not a clinically validated medical assessment");
  await expect(dialog.getByRole("link", { name: /View source report: Synthetic report/ })).toHaveAttribute("href", report.view_url);
  await page.screenshot({ path: `../.local/patient-health-score-${testInfo.project.name}.png` });
  await page.keyboard.press("Escape");
  await expect(metric(page, "Health score")).toBeFocused();
  await metric(page, "Adherence").click();
  dialog = page.getByRole("dialog", { name: "Medication adherence", exact: true });
  await expect(dialog).toContainText("(57 ÷ 60) × 100 = 95%");
  await expect(dialog).toContainText("30 of 30 days logged · 0 days unlogged");
  await expect(dialog).toContainText("Blood pressure and glucose measurements alone cannot tell whether a dose was taken");
  await closeDialog(page);
  expectClean(state);
});

test("reports expose extracted results and working view and download actions", async ({ page }) => {
  const state = await mockDashboard(page);
  await openDashboard(page);
  await navigationLink(page, "reports").click();
  const library = page.locator("#patient-reports");
  await expect(library).toContainText("Results added to your overview");
  await expect(library).toContainText("124/82");
  await expect(library).toContainText("118 mg/dL");
  const previewEvent = page.waitForEvent("popup");
  await library.getByRole("link", { name: "View Synthetic report in a new tab", exact: true }).click();
  const preview = await previewEvent;
  await expect(preview).toHaveURL(new RegExp(`${report.view_url}$`));
  await expect(preview.getByText("Synthetic report preview fixture", { exact: true })).toBeVisible();
  await preview.close();
  const downloadEvent = page.waitForEvent("download");
  await library.getByRole("link", { name: "Download Synthetic report", exact: true }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("synthetic.pdf");
  expect(await download.failure()).toBeNull();
  expect(state.reportViews).toBe(1);
  expect(state.reportDownloads).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  expectClean(state);
});

test("visit details retain the doctor's symptoms, diagnosis, care plan, and full prescription", async ({ page }, testInfo) => {
  const state = await mockDashboard(page);
  state.showVisits = true;
  await openDashboard(page);
  await navigationLink(page, "visits").click();
  const visits = page.locator("#patient-visits");
  await expect(visits).toContainText("SYMPTOMS / REASON FOR VISIT");
  await expect(visits).toContainText("Diagnosis: Synthetic diagnosis for presentation testing");
  await visits.getByText("View visit details", { exact: true }).click();
  await expect(visits).toContainText("Synthetic test-only notes");
  await expect(visits).toContainText("Fixture instructions");
  await expect(visits).toContainText("Prescribed: 10 tablet");
  await expect(visits.getByRole("link", { name: "View Synthetic report in a new tab", exact: true })).toBeVisible();
  await page.screenshot({ path: `../.local/patient-report-visit-${testInfo.project.name}.png` });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  expectClean(state);
});

test("saving a report refreshes the mounted overview and extracted readings", async ({ page }) => {
  const state = await mockDashboard(page);
  await openDashboard(page);
  await expect(metric(page, "Latest blood pressure")).toContainText("124/82");
  await navigationLink(page, "reports").click();
  const library = page.locator("#patient-reports");
  await library.getByRole("button", { name: "Upload report", exact: true }).click();
  await library.getByLabel("Medical report", { exact: false }).setInputFiles({ name: "synthetic-upload.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 isolated browser upload fixture") });
  await library.locator("form").getByRole("button", { name: "Upload report", exact: true }).click();
  await expect(metric(page, "Latest blood pressure")).toContainText("122/80");
  await expect(metric(page, "Report downloads")).toContainText("2 reports available");
  expect(state.reportUploads).toBe(1);
  expect(state.dashboardReads).toBeGreaterThan(1);
  expectClean(state);
});


const sectionOrder = ["overview", "card", "records", "visits", "reports", "prescriptions", "dispensing", "profile", "security"];
const sectionLabels: Record<string, string> = { overview: "Overview", card: "Health card", records: "Medical records", visits: "Recent visits", reports: "Medical reports", prescriptions: "Prescriptions", dispensing: "Dispensing history", profile: "My profile", security: "Security settings" };

function navigationLink(page: Page, id: string) {
  return page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: sectionLabels[id], exact: true });
}
async function expectSectionPosition(page: Page, id: string) {
  await expect(navigationLink(page, id)).toHaveAttribute("aria-current", "location");
  await expect(page.locator(`[data-patient-section="${id}"]`)).toBeInViewport();
  // A section merely existing in the long document is not evidence of navigation.
  // Its start must be in the viewport, below the sticky navigation/header.
  await expect.poll(async () => page.locator(`#patient-${id}`).evaluate(element => {
    const top = element.getBoundingClientRect().top;
    const header = document.querySelector(".topbar")?.getBoundingClientRect();
    return top >= (header?.bottom ?? 0) - 2 && top < innerHeight * .65;
  })).toBeTruthy();
}

test.describe("patient continuous scrolling workspace", () => {
  test.use({ reducedMotion: "reduce" });

  test("sidebar is the single section navigator while summaries and data actions remain available", async ({ page }) => {
    const state = await mockDashboard(page);
    await openDashboard(page);
    await expect(page.locator('a[href^="#patient-"]')).toHaveCount(sectionOrder.length);
    const dashboard = page.getByTestId("patient-dashboard");
    for (const label of ["Medical records", "Active prescriptions", "Report downloads", "Blood group", "Chronic conditions", "Show QR card", "View medical records"]) {
      await expect(dashboard.getByRole("button", { name: label, exact: true })).toHaveCount(0);
    }
    await expect(page.locator("#patient-overview > .page-heading").getByRole("button")).toHaveCount(0);
    await expect(metric(page, "Medical records")).toContainText("3");
    await expect(metric(page, "Active prescriptions")).toContainText("1");
    await expect(metric(page, "Report downloads")).toContainText("2");
    await expect(page.getByRole("heading", { name: "Medical reports", exact: true })).toHaveCount(1);
    await expect(page.getByRole("heading", { name: "Prescriptions", exact: true })).toHaveCount(1);
    await expect(page.getByRole("button", { name: "Upload photo", exact: true })).toHaveCount(1);
    await expect(page.locator("#patient-visits").getByRole("button", { name: /^(All prescriptions|All reports|Medical timeline)$/ })).toHaveCount(0);
    await expect(metric(page, "Health score")).toHaveRole("button");
    await expect(metric(page, "Adherence")).toHaveRole("button");
    await expect(metric(page, "Abnormal lab values")).toHaveRole("button");
    expectClean(state);
  });

  test("all sections stay in order and every sidebar link jumps to its section", async ({ page }, testInfo) => {
    const state = await mockDashboard(page);
    await openDashboard(page);
    await expect(page.locator("[data-patient-section]")).toHaveCount(sectionOrder.length);
    const ids = await page.locator("[data-patient-section]").evaluateAll(elements => elements.map(element => element.getAttribute("data-patient-section")));
    expect(ids).toEqual(sectionOrder);
    await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link")).toHaveText(sectionOrder.map(id => sectionLabels[id]));
    for (const id of sectionOrder) {
      await expect(navigationLink(page, id)).toHaveAttribute("href", `#patient-${id}`);
      await navigationLink(page, id).click();
      await expectSectionPosition(page, id);
      await expect(page).toHaveURL(new RegExp(`#patient-${id}$`));
      await expect(page.locator("[data-patient-section]")).toHaveCount(sectionOrder.length);
    }
    await expect(page.locator("#patient-dispensing")).toContainText("Synthetic Pharmacy");
    await expect(page.locator("#patient-security")).toContainText("Synthetic browser session");
    await page.screenshot({ path: `../.local/patient-scroll-security-${testInfo.project.name}.png` });
    await navigationLink(page, "card").click();
    await expectSectionPosition(page, "card");
    await page.screenshot({ path: `../.local/patient-scroll-card-${testInfo.project.name}.png` });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    expectClean(state);
  });

  test("manual scrolling updates the sidebar highlight without hiding other sections", async ({ page }) => {
    const state = await mockDashboard(page);
    await openDashboard(page);
    for (const id of ["reports", "profile", "records"]) {
      await page.locator(`#patient-${id}`).evaluate(element => {
        const headerBottom = document.querySelector(".topbar")?.getBoundingClientRect().bottom ?? 0;
        window.scrollTo({ top: element.getBoundingClientRect().top + scrollY - headerBottom - 16, behavior: "instant" });
      });
      await expectSectionPosition(page, id);
      await expect(page.getByRole("navigation", { name: "Main navigation" }).locator('[aria-current="location"]')).toHaveCount(1);
    }
    const viewport = page.viewportSize()!;
    await page.mouse.move(viewport.width * .8, viewport.height * .6);
    await page.mouse.wheel(0, 100000);
    await expect(navigationLink(page, "security")).toHaveAttribute("aria-current", "location");
    await page.mouse.wheel(0, -100000);
    await expect(navigationLink(page, "overview")).toHaveAttribute("aria-current", "location");
    await expect(page.locator("[data-patient-section]")).toHaveCount(sectionOrder.length);
    expectClean(state);
  });

  test("section navigation preserves profile drafts, report uploads, and prescription details", async ({ page }) => {
    const state = await mockDashboard(page);
    await openDashboard(page);
    await navigationLink(page, "profile").click();
    await expectSectionPosition(page, "profile");
    await page.locator("#patient-profile").getByLabel("Phone number", { exact: true }).fill("9876543210");
    await navigationLink(page, "reports").click();
    await page.locator("#patient-reports").getByRole("button", { name: "Upload report", exact: true }).click();
    await page.locator("#patient-reports").getByLabel("Report title (optional)", { exact: true }).fill("Unsaved report draft");
    await navigationLink(page, "prescriptions").click();
    await page.locator("#patient-prescriptions").getByRole("button", { name: "View prescription", exact: true }).click();
    await expect(page.locator("#patient-prescriptions")).toContainText("Synthetic prescription");
    await overview(page);
    await navigationLink(page, "records").click();
    await expectSectionPosition(page, "records");
    await overview(page);
    await navigationLink(page, "card").click();
    await expectSectionPosition(page, "card");
    await navigationLink(page, "profile").click();
    await expect(page.locator("#patient-profile").getByLabel("Phone number", { exact: true })).toHaveValue("9876543210");
    await navigationLink(page, "reports").click();
    await expect(page.locator("#patient-reports").getByLabel("Report title (optional)", { exact: true })).toHaveValue("Unsaved report draft");
    await navigationLink(page, "prescriptions").click();
    await expect(page.locator("#patient-prescriptions").getByRole("button", { name: "Back to prescriptions", exact: true })).toBeInViewport();
    expect(state.doseWrites).toBe(0);
    expect(state.labWrites).toBe(0);
    expectClean(state);
  });

  test("saved profile changes update the mounted health card without resetting its flip state", async ({ page }) => {
    const state = await mockDashboard(page);
    await openDashboard(page);
    await navigationLink(page, "card").click();
    const card = page.getByRole("button", { name: "Flip health card", exact: true });
    await expect(card).toContainText("B+");
    await card.click();
    await expect(card).toHaveAttribute("aria-pressed", "true");
    await navigationLink(page, "profile").click();
    await page.locator('#patient-profile select[name="blood_group"]').selectOption("O+");
    await page.locator("#patient-profile").getByRole("button", { name: "Save profile", exact: true }).click();
    await expect(page.locator("#patient-profile")).toContainText("Profile updated.");
    await expect(card).toContainText("O+");
    await navigationLink(page, "card").click();
    await expect(card).toHaveAttribute("aria-pressed", "true");
    await card.click();
    await expect(card.getByText("O+", { exact: true })).toBeInViewport();
    expect(state.profileWrites).toBe(1);
    expectClean(state);
  });

  test("direct section URLs, reload, and browser history restore the chosen section", async ({ page }) => {
    const state = await mockDashboard(page);
    await page.goto("/#patient-reports");
    await expectSectionPosition(page, "reports");
    await navigationLink(page, "card").click();
    await expectSectionPosition(page, "card");
    await navigationLink(page, "profile").click();
    await expectSectionPosition(page, "profile");
    await page.goBack();
    await expectSectionPosition(page, "card");
    await page.goForward();
    await expectSectionPosition(page, "profile");
    await page.reload();
    await expectSectionPosition(page, "profile");
    expectClean(state);
  });
});
