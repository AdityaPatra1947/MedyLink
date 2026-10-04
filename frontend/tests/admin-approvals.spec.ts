import { test, expect, type Page, type Route } from "@playwright/test";
import type { Application, ProviderDocument } from "../lib/types";

type ProviderRole = "doctor" | "pharmacist";
const admin = { id: "synthetic-admin", account_id: "A-TEST01", name: "Test Administrator", email: "admin@example.test", role: "admin", email_verified: true };
const credential = (status = "quarantined", id = "synthetic-credential"): ProviderDocument => ({ id, name: `${id}.pdf`, kind: "credential", status });
const photo: ProviderDocument = { id: "synthetic-photo", name: "portrait.png", kind: "photo", status: "validated" };

function application(role: ProviderRole, documents: ProviderDocument[], emailVerified = true): Application {
  return {
    id: "synthetic-application", provider_id: "synthetic-provider", name: `Synthetic ${role}`,
    role, provider_email: `${role}@example.test`, email_verified: emailVerified,
    version: 1, status: "pending", reason: "", valid_until: null, is_current: true,
    registration_number: "TEST-1234", registering_body: "Synthetic register", specialty: "General practice",
    qualification: "Synthetic qualification", clinic_name: "Synthetic clinic", years_experience: 2,
    opening_hours: "09:00–17:00", practice_address: "Synthetic address", shop_name: "Synthetic pharmacy",
    shop_license: "TEST-LICENCE", shop_license_expires: "2099-12-31", contact_phone: "9000000000",
    documents, created_at: "2026-01-01T12:00:00Z", reviewed_at: null, evidence_reviewed: "", reviews: [], history: [],
  };
}

async function mockApplication(page: Page, initial: Application, failFirstApproval = false) {
  let current = structuredClone(initial);
  const state = { detailReads: 0, validations: 0, approvals: 0, unexpected: [] as string[] };
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  // Never fall through to the real database, session, email, or mutation endpoints.
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (method === "GET" && path === "/api/v1/auth/me/") return json(route, { user: admin });
    if (method === "GET" && path === "/api/v1/auth/csrf/") return json(route, { csrfToken: "synthetic-csrf" });
    if (method === "GET" && path === "/api/v1/auth/sessions/") return json(route, { results: [] });
    if (method === "GET" && path === "/api/v1/admin/audit/") return json(route, { results: [] });
    if (method === "GET" && path === "/api/v1/admin/analytics/ml/catalog/") return json(route, { synthetic: true, datasets: [], stations: [], diseases: [], lines: [], defaults: {}, suppression_threshold: 5 });
    if (method === "GET" && path === "/api/v1/admin/provider-applications/") {
      const matches = new URL(request.url()).searchParams.get("role") === current.role;
      return json(route, { results: matches ? [current] : [], next: null, previous: null, count: matches ? 1 : 0 });
    }
    if (method === "GET" && path === `/api/v1/admin/provider-applications/${current.id}/`) {
      state.detailReads++;
      return json(route, current);
    }
    const document = current.documents.find(item => path === `/api/v1/admin/provider-documents/${item.id}/validate/`);
    if (method === "POST" && document) {
      const body = request.postDataJSON();
      expect(body).toMatchObject({ safe: true, reason: "Synthetic file review only" });
      state.validations++;
      document.status = "validated";
      return json(route, document);
    }
    if (method === "POST" && path === `/api/v1/admin/provider-applications/${current.id}/approve/`) {
      state.approvals++;
      const body = request.postDataJSON();
      expect(body).toMatchObject({ evidence_reviewed: "Synthetic certificate", reason: "Synthetic approval only" });
      expect(new Date(body.valid_until).getTime()).toBeGreaterThan(Date.now());
      if (failFirstApproval && state.approvals === 1) return json(route, { detail: "Synthetic approval conflict. Please try again." }, 409);
      current = { ...current, status: "approved", valid_until: body.valid_until, reason: body.reason,
        reviews: [{ decision: "approve", reason: body.reason, evidence_reviewed: body.evidence_reviewed, valid_until: body.valid_until, reviewer_name: admin.name, created_at: new Date().toISOString() }] };
      return json(route, current);
    }
    state.unexpected.push(`${method} ${path}`);
    return json(route, { detail: "Unexpected endpoint blocked by isolated approval test." }, 501);
  });
  return state;
}

async function openApplication(page: Page, role: ProviderRole) {
  await page.goto(role === "doctor" ? "/admin/doctors" : "/admin/pharmacists");
  await page.locator(`#admin-${role === "doctor" ? "doctors" : "pharmacists"}`).getByRole("button", { name: "Review application", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Record a decision", exact: true })).toBeVisible();
}

async function expectBlocked(page: Page) {
  const button = page.getByRole("button", { name: "Approve provider", exact: true });
  await expect(button).toBeDisabled();
  await expect(button).toHaveAttribute("aria-describedby", /-approval-blockers$/);
  await expect(page.locator('[id$="-approval-blockers"]')).toContainText("Before you can approve");
  await expect(page.getByLabel("Approval reason", { exact: false })).toHaveCount(0);
}

for (const [role, documents] of [["doctor", []], ["pharmacist", [photo]]] as [ProviderRole, ProviderDocument[]][]) {
  test(`${role}: missing credential evidence explains upload and refresh instead of an inert approval`, async ({ page }, testInfo) => {
    const state = await mockApplication(page, application(role, documents));
    await openApplication(page, role);
    await expectBlocked(page);
    const blockers = page.locator('[id$="-approval-blockers"]');
    await expect(blockers).toContainText(/no credential|credential document.*missing/i);
    await expect(blockers).toContainText(role === "doctor" ? "My verification" : "Shop & verification");
    await expect(blockers).toContainText("Credential evidence");
    await expect(blockers).toContainText("Upload evidence");
    if (role === "doctor" && testInfo.project.name === "desktop") await page.screenshot({ path: "../.local/approval-fix.png", fullPage: true });
    const beforeRefresh = state.detailReads;
    await page.getByRole("button", { name: "Refresh application", exact: true }).click();
    await expect.poll(() => state.detailReads).toBeGreaterThan(beforeRefresh);
    await expectBlocked(page);
    expect(state.approvals).toBe(0);
    expect(state.unexpected).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  });
}

for (const role of ["doctor", "pharmacist"] as const) {
  test(`${role}: review shortcut unlocks approval and errors remain visible until a successful retry`, async ({ page }) => {
    const state = await mockApplication(page, application(role, [credential(), photo]), true);
    await openApplication(page, role);
    await expectBlocked(page);
    const shortcut = page.getByRole("link", { name: "Review credential documents", exact: true });
    await expect(shortcut).toHaveAttribute("href", `#admin-${role}-synthetic-application-credential-evidence`);
    await shortcut.click();
    await expect(page).toHaveURL(/-credential-evidence$/);
    const evidence = page.locator('[id$="-credential-evidence"]');
    await expect(evidence).toBeInViewport();
    await expect(evidence.getByRole("heading", { name: "Credential evidence", exact: true })).toBeVisible();
    const headingOrder = await page.getByRole("heading", { level: 2 }).allTextContents();
    expect(headingOrder.indexOf("Credential evidence")).toBeLessThan(headingOrder.indexOf("Application details"));
    await evidence.getByText("Record file review", { exact: true }).click();
    await evidence.getByLabel("Review / malware scan reference").fill("Synthetic file review only");
    await evidence.getByRole("checkbox").check();
    await evidence.getByRole("button", { name: "Mark file reviewed and safe", exact: true }).click();
    await expect(page.getByLabel("Evidence reviewed", { exact: false })).toBeVisible();
    expect(state.validations).toBe(1);
    const decision = page.locator("section.panel").filter({ has: page.getByRole("heading", { name: "Record a decision", exact: true }) });
    await decision.getByLabel("Evidence reviewed", { exact: false }).fill("Synthetic certificate");
    await decision.getByLabel("Approval reason", { exact: false }).fill("Synthetic approval only");
    await decision.getByLabel("Verification valid until", { exact: false }).fill("2099-01-01T12:00");
    await decision.getByRole("checkbox").check();
    await decision.getByRole("button", { name: "Approve provider", exact: true }).click();
    await expect(decision.getByRole("alert")).toContainText("Synthetic approval conflict. Please try again.");
    await expect(decision.getByRole("button", { name: "Approve provider", exact: true })).toBeEnabled();
    expect(state.approvals).toBe(1);
    await decision.getByRole("button", { name: "Approve provider", exact: true }).click();
    await expect(decision.getByRole("button", { name: "Renew / restore approval", exact: true })).toBeVisible();
    await expect(page.getByText("Synthetic approval only", { exact: true }).first()).toBeVisible();
    expect(state.approvals).toBe(2);
    expect(state.unexpected).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  });
}

test("verified documents still require provider email verification", async ({ page }) => {
  const state = await mockApplication(page, application("doctor", [credential("validated")], false));
  await openApplication(page, "doctor");
  await expectBlocked(page);
  await expect(page.locator('[id$="-approval-blockers"]')).toContainText(/verif.*email|email.*verif/i);
  expect(state.approvals).toBe(0);
  expect(state.unexpected).toEqual([]);
});

test("rejected and unreviewed files remain explicit blockers", async ({ page }) => {
  const state = await mockApplication(page, application("pharmacist", [credential("rejected"), credential("quarantined", "second-credential")]));
  await openApplication(page, "pharmacist");
  await expectBlocked(page);
  const blockers = page.locator('[id$="-approval-blockers"]');
  await expect(blockers).toContainText(/1.*reject|reject.*1/i);
  await expect(blockers).toContainText(/1.*review|review.*1/i);
  await expect(page.getByRole("link", { name: "Review credential documents", exact: true })).toBeVisible();
  expect(state.approvals).toBe(0);
  expect(state.unexpected).toEqual([]);
});
