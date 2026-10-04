import { test, expect, type Page, type Route } from "@playwright/test";
import type { Application, Role, User } from "../lib/types";

type WorkspaceRole = "doctor" | "pharmacist" | "admin";
const orders: Record<WorkspaceRole, string[]> = { doctor: ["patients", "request", "profile", "verification", "security"], pharmacist: ["prescriptions", "dispensing", "verification", "security"], admin: ["ml", "doctors", "pharmacists", "audit", "security"] };
const labels: Record<WorkspaceRole, string[]> = { doctor: ["My patients", "Find patient", "My profile", "My verification", "Security settings"], pharmacist: ["Find prescriptions", "Dispensing history", "Shop & verification", "Security settings"], admin: ["ML insights", "Doctor approvals", "Pharmacist approvals", "Security audit", "Security settings"] };
const fixturePatient = { id: "synthetic-patient", name: "Synthetic Patient", account_id: "P-TEST01", health_id: "AT-TEST", date_of_birth: "1990-01-01", gender: "other", phone: "", address: "", blood_group: "B+", emergency_contact: "", allergy_status: "unknown" };
function fixtureApplication(role: "doctor" | "pharmacist", pending = false): Application {
  return { id: `synthetic-${role}-application`, provider_id: `synthetic-${role}`, role, name: `Synthetic ${role}`, provider_email: `${role}@example.test`, email_verified: true, version: 1, status: pending ? "pending" : "approved", reason: "Synthetic browser fixture", valid_until: "2099-01-01T00:00:00Z", is_current: true, registration_number: "TEST-123", registering_body: "Synthetic Register", specialty: "Synthetic Specialty", qualification: "Synthetic Degree", clinic_name: "Synthetic Clinic", years_experience: 2, opening_hours: "09:00–17:00", practice_address: "Synthetic address", shop_name: "Synthetic Pharmacy", shop_license: "TEST-SHOP", shop_license_expires: "2099-01-01", contact_phone: "9000000000", documents: [{ id: `synthetic-${role}-credential`, name: "synthetic.pdf", kind: "credential", status: "validated" }], created_at: "2026-09-01T00:00:00Z", reviews: [], history: [] };
}
async function mockWorkspace(page: Page, role: WorkspaceRole) {
  const user: User = { id: `synthetic-${role}`, account_id: `TEST-${role}`, name: `Synthetic ${role}`, email: `${role}@example.test`, role: role as Role, email_verified: true, phone: "9000000000" };
  const applications = { doctor: fixtureApplication("doctor", role === "admin"), pharmacist: fixtureApplication("pharmacist", role === "admin") };
  const state = { unexpected: [] as string[], errors: [] as string[], lookups: [] as string[], applicationWrites: 0 };
  page.on("pageerror", error => state.errors.push(error.message));
  await page.addInitScript(() => {
    Object.defineProperty(window, "__cameraRequests", { value: 0, writable: true });
    if (navigator.mediaDevices) Object.defineProperty(navigator.mediaDevices, "getUserMedia", { configurable: true, value: async () => {
      const state = window as unknown as { __cameraRequests: number };
      state.__cameraRequests++;
      throw new DOMException("Synthetic camera disabled", "NotAllowedError");
    } });
  });
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  // Every app API request is handled locally. No test can mutate real accounts,
  // access actual patient records, or send password-reset/verification emails.
  await page.context().route("**/api/v1/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    if (method === "GET" && path === "/api/v1/auth/me/") return json(route, { user });
    if (method === "GET" && path === "/api/v1/auth/csrf/") return json(route, { csrfToken: "synthetic-csrf" });
    if (method === "GET" && path === "/api/v1/auth/sessions/") return json(route, { results: [] });
    if (method === "GET" && path === "/api/v1/provider/application/") return json(route, { current: applications[role === "pharmacist" ? "pharmacist" : "doctor"], history: [] });
    if (method === "POST" && path === "/api/v1/provider/application/") {
      state.applicationWrites++;
      const application = applications[role === "pharmacist" ? "pharmacist" : "doctor"];
      Object.assign(application, request.postDataJSON(), { id: `synthetic-${role}-updated-application`, status: "pending", version: 2, valid_until: null, documents: [] });
      return json(route, application, 201);
    }
    if (method === "GET" && path === "/api/v1/doctor/profile/") return json(route, { user, application: applications.doctor });
    if (method === "GET" && path === "/api/v1/doctor/patients/") return json(route, { results: [fixturePatient], next: null });
    if (method === "GET" && path === "/api/v1/pharmacy/dispensing/") return json(route, { results: [], next: null });
    if (method === "GET" && path === "/api/v1/admin/audit/") return json(route, { results: [], next: null });
    if (method === "GET" && path === "/api/v1/admin/analytics/ml/catalog/") return json(route, { synthetic: true, datasets: [], stations: [], diseases: [], lines: [], defaults: {}, suppression_threshold: 5 });
    if (method === "GET" && path === "/api/v1/admin/provider-applications/") {
      const application = applications[url.searchParams.get("role") === "doctor" ? "doctor" : "pharmacist"];
      return json(route, { results: [application], next: null, count: 1 });
    }
    if (method === "GET" && path.startsWith("/api/v1/admin/provider-applications/")) {
      const application = Object.values(applications).find(item => path === `/api/v1/admin/provider-applications/${item.id}/`);
      if (application) return json(route, application);
    }
    if (method === "POST" && path === "/api/v1/provider/patients/lookup/") {
      state.lookups.push(request.postDataJSON().identifier);
      return json(route, { patient_id: fixturePatient.id, patient: fixturePatient });
    }
    if (method === "GET" && path === `/api/v1/patients/${fixturePatient.id}/clinical-summary/`) return json(route, { patient: fixturePatient, is_my_patient: false });
    if (method === "GET" && ["records", "prescriptions", "reports", "allergies", "conditions"].some(part => path === `/api/v1/patients/${fixturePatient.id}/${part}/`)) return json(route, { results: [], next: null });
    state.unexpected.push(`${method} ${path}`);
    return json(route, { detail: "Unexpected API blocked by isolated role navigation test." }, 501);
  });
  return state;
}
function section(page: Page, role: WorkspaceRole, id: string) { return page.locator(`#${role}-${id}`); }
function nav(page: Page, role: WorkspaceRole, id: string) { return page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: labels[role][orders[role].indexOf(id)], exact: true }); }
async function atSection(page: Page, role: WorkspaceRole, id: string) {
  await expect(nav(page, role, id)).toHaveAttribute("aria-current", "location");
  await expect(section(page, role, id)).toBeInViewport();
  await expect.poll(async () => section(page, role, id).evaluate(element => {
    const top = element.getBoundingClientRect().top;
    const headerBottom = document.querySelector(".topbar")?.getBoundingClientRect().bottom ?? 0;
    return top >= headerBottom - 2 && top < innerHeight * .65;
  })).toBeTruthy();
}
async function expectClean(page: Page, state: Awaited<ReturnType<typeof mockWorkspace>>) {
  expect(state.unexpected).toEqual([]);
  expect(state.errors).toEqual([]);
  expect(await page.evaluate(() => (window as unknown as { __cameraRequests: number }).__cameraRequests)).toBe(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
}

test.use({ reducedMotion: "reduce" });
for (const role of ["doctor", "pharmacist", "admin"] as const) {
  test(`${role}: every section remains mounted, navigation scrolls, and manual scrolling updates the highlight`, async ({ page }, testInfo) => {
    const state = await mockWorkspace(page, role);
    await page.goto(role === "admin" ? "/admin/doctors" : "/");
    await expect(page.locator("[data-workspace-section]")).toHaveCount(orders[role].length);
    expect(await page.locator("[data-workspace-section]").evaluateAll(elements => elements.map(element => element.getAttribute("data-workspace-section")))).toEqual(orders[role]);
    await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link")).toHaveText(labels[role]);
    for (const id of orders[role]) {
      await nav(page, role, id).click();
      await atSection(page, role, id);
      await expect(page).toHaveURL(new RegExp(role === "admin" ? `/admin/${id}$` : `#${role}-${id}$`));
    }
    const target = orders[role][1];
    await section(page, role, target).evaluate(element => {
      const headerBottom = document.querySelector(".topbar")?.getBoundingClientRect().bottom ?? 0;
      window.dispatchEvent(new WheelEvent("wheel"));
      window.scrollTo({ top: element.getBoundingClientRect().top + scrollY - headerBottom - 20, behavior: "instant" });
    });
    await atSection(page, role, target);
    if (role === "admin") await expect(page).toHaveURL(new RegExp(`/admin/${target}$`));
    await nav(page, role, orders[role][0]).click();
    await atSection(page, role, orders[role][0]);
    await page.screenshot({ path: `../.local/${role}-scroll-${testInfo.project.name}.png` });
    await expect(page.locator("[data-workspace-section]")).toHaveCount(orders[role].length);
    await expectClean(page, state);
  });
}

test("doctor: profile and lookup drafts survive navigation and section URL reloads", async ({ page }) => {
  const state = await mockWorkspace(page, "doctor");
  await page.goto("/#doctor-profile");
  await atSection(page, "doctor", "profile");
  await section(page, "doctor", "profile").getByLabel("Full name", { exact: false }).fill("Unsaved Doctor Name");
  await nav(page, "doctor", "request").click();
  await section(page, "doctor", "request").getByLabel("Account ID or health card", { exact: false }).fill("P-DRAFT1");
  await nav(page, "doctor", "profile").click();
  await expect(section(page, "doctor", "profile").getByLabel("Full name", { exact: false })).toHaveValue("Unsaved Doctor Name");
  await page.goBack();
  await atSection(page, "doctor", "request");
  await expect(section(page, "doctor", "request").getByLabel("Account ID or health card", { exact: false })).toHaveValue("P-DRAFT1");
  await page.goForward();
  await atSection(page, "doctor", "profile");
  await page.reload();
  await atSection(page, "doctor", "profile");
  await expectClean(page, state);
});

test("doctor: a submitted credential change updates the mounted profile and gates patient access", async ({ page }) => {
  const state = await mockWorkspace(page, "doctor");
  await page.goto("/");
  await expect(section(page, "doctor", "patients").getByRole("button", { name: "Open record", exact: true })).toBeVisible();
  const professional = section(page, "doctor", "profile").locator("section.panel").filter({ has: page.getByRole("heading", { name: "Professional details", exact: true }) });
  await expect(professional).toContainText("approved");
  await nav(page, "doctor", "verification").click();
  const verification = section(page, "doctor", "verification");
  await verification.getByRole("button", { name: "Submit corrected credentials", exact: true }).click();
  await verification.getByLabel("Specialty", { exact: false }).fill("Updated Synthetic Specialty");
  await verification.getByRole("checkbox").check();
  await verification.getByRole("button", { name: "Submit updated application", exact: true }).click();
  await expect(verification).toContainText("pending");
  await nav(page, "doctor", "profile").click();
  await expect(professional).toContainText("pending");
  await expect(professional).toContainText("Updated Synthetic Specialty");
  await expect(section(page, "doctor", "patients").getByRole("button", { name: "Open record", exact: true })).toHaveCount(0);
  await expect(section(page, "doctor", "patients")).toContainText("Complete your professional verification");
  await expect(section(page, "doctor", "request").getByLabel("Account ID or health card", { exact: false })).toHaveCount(0);
  await expect(section(page, "doctor", "request")).toContainText("Complete your professional verification");
  expect(state.applicationWrites).toBe(1);
  await expectClean(page, state);
});

test("pharmacist: the merged patient lookup and verification draft persist across scrolling", async ({ page }) => {
  const state = await mockWorkspace(page, "pharmacist");
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Scan QR with camera", exact: true })).toHaveCount(1);
  await section(page, "pharmacist", "prescriptions").getByLabel("Account ID or health card", { exact: false }).fill("P-DRAFT2");
  await nav(page, "pharmacist", "verification").click();
  await section(page, "pharmacist", "verification").getByRole("button", { name: "Submit corrected credentials", exact: true }).click();
  await section(page, "pharmacist", "verification").getByLabel("Pharmacy shop name", { exact: false }).fill("Unsaved Pharmacy Name");
  await nav(page, "pharmacist", "prescriptions").click();
  await expect(section(page, "pharmacist", "prescriptions").getByLabel("Account ID or health card", { exact: false })).toHaveValue("P-DRAFT2");
  await nav(page, "pharmacist", "verification").click();
  await expect(section(page, "pharmacist", "verification").getByLabel("Pharmacy shop name", { exact: false })).toHaveValue("Unsaved Pharmacy Name");
  await page.reload();
  await atSection(page, "pharmacist", "verification");
  await expectClean(page, state);
});

test("admin: approval drafts survive ML navigation, browser history, and section URL reloads", async ({ page }) => {
  const state = await mockWorkspace(page, "admin");
  await page.goto("/admin/pharmacists");
  await atSection(page, "admin", "pharmacists");
  for (const id of ["pharmacists", "doctors"]) {
    await nav(page, "admin", id).click();
    await section(page, "admin", id).getByRole("button", { name: "Review application", exact: true }).click();
    await section(page, "admin", id).getByLabel("Approval reason", { exact: false }).fill(`Unsaved ${id} decision`);
  }
  await nav(page, "admin", "ml").click();
  await atSection(page, "admin", "ml");
  await page.goBack();
  await atSection(page, "admin", "doctors");
  await expect(section(page, "admin", "doctors").getByLabel("Approval reason", { exact: false })).toHaveValue("Unsaved doctors decision");
  await page.goForward();
  await atSection(page, "admin", "ml");
  for (const id of ["pharmacists", "doctors"]) {
    await nav(page, "admin", id).click();
    await expect(section(page, "admin", id).getByLabel("Approval reason", { exact: false })).toHaveValue(`Unsaved ${id} decision`);
  }
  const evidenceIds = await page.locator('[id$="-credential-evidence"]').evaluateAll(elements => elements.map(element => element.id));
  expect(evidenceIds).toHaveLength(2);
  expect(new Set(evidenceIds).size).toBe(2);
  await nav(page, "admin", "audit").click();
  await expect(page).toHaveURL(/\/admin\/audit$/);
  await page.reload();
  await atSection(page, "admin", "audit");
  await expectClean(page, state);
});

for (const role of ["doctor", "pharmacist"] as const) {
  test(`${role}: a health-card URL opens the matching patient in the correct section without starting the camera`, async ({ page }) => {
    const state = await mockWorkspace(page, role);
    await page.goto("/health-card/synthetic-qr-token");
    const id = role === "doctor" ? "request" : "prescriptions";
    await atSection(page, role, id);
    await expect(section(page, role, id)).toContainText(fixturePatient.name);
    expect(state.lookups.length).toBeGreaterThan(0);
    expect(state.lookups.every(value => value === "synthetic-qr-token")).toBeTruthy();
    await expectClean(page, state);
  });
}
