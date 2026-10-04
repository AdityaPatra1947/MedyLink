import { expect, test, type Page, type Route } from "@playwright/test";

const admin = {
  id: "admin-entry-fixture", account_id: "A-ENTRY1", name: "Fixture Administrator",
  email: "admin-entry@example.test", role: "admin", email_verified: true,
};
const fixturePassword = "isolated-login-fixture";

async function mockAdminEntry(page: Page, options: { signedIn?: boolean } = {}) {
  let signedIn = options.signedIn ?? true;
  const state = { requests: [] as string[], logins: 0, unexpected: [] as string[], errors: [] as string[] };
  page.on("pageerror", error => state.errors.push(error.message));
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  // These navigation checks never reach a real account, database, or mail server.
  await page.route("**/api/v1/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname, method = request.method();
    state.requests.push(`${method} ${path}`);
    if (method === "GET" && path === "/api/v1/auth/me/") return json(route, signedIn ? { user: admin } : { detail: "Fixture session is signed out." }, signedIn ? 200 : 401);
    if (method === "GET" && path === "/api/v1/auth/csrf/") return json(route, { csrfToken: "admin-entry-csrf" });
    if (method === "POST" && path === "/api/v1/auth/refresh/") return json(route, { detail: "No fixture refresh session." }, 401);
    if (method === "GET" && path === "/api/v1/ready/") return json(route, { ready: true });
    if (method === "POST" && path === "/api/v1/auth/login/") {
      expect(request.postDataJSON()).toEqual({ email: admin.email, password: fixturePassword });
      expect(request.headers()["x-csrftoken"]).toBe("admin-entry-csrf");
      signedIn = true; state.logins++;
      return json(route, { user: admin });
    }
    if (method === "GET" && path === "/api/v1/admin/analytics/ml/catalog/") return json(route, { synthetic: true, datasets: [], stations: [], diseases: [], lines: [], defaults: {}, suppression_threshold: 5 });
    if (method === "GET" && ["/api/v1/admin/provider-applications/", "/api/v1/admin/audit/", "/api/v1/auth/sessions/"].includes(path)) return json(route, { results: [], next: null });
    state.unexpected.push(`${method} ${path}`);
    return json(route, { detail: "Unexpected API request blocked by isolated admin-entry test." }, 501);
  });
  return state;
}

async function signIn(page: Page) {
  await page.getByRole("textbox", { name: /^Email address/ }).fill(admin.email);
  await page.getByLabel(/^Password/).fill(fixturePassword);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

async function expectMLWorkspace(page: Page) {
  await expect(page.getByRole("heading", { name: "ML insights", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "No ML dataset is available", exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "ML insights", exact: true })).toHaveAttribute("aria-current", "location");
  await expect(page.locator("#admin-analytics")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Population analytics", exact: true })).toHaveCount(0);
  expect(await page.locator("[data-workspace-section]").evaluateAll(elements => elements.map(element => element.getAttribute("data-workspace-section")))).toEqual(["ml", "doctors", "pharmacists", "audit", "security"]);
}

test.use({ reducedMotion: "reduce" });

test("ordinary administrator sign-in opens ML insights", async ({ page }) => {
  const state = await mockAdminEntry(page, { signedIn: false });
  await page.goto("/login");
  await signIn(page);
  await expect(page).toHaveURL(/\/admin\/ml$/);
  await expectMLWorkspace(page);
  expect(state.logins).toBe(1);
  expect(state.requests).not.toContain("GET /api/v1/admin/analytics/catalog/");
  expect(state.unexpected).toEqual([]); expect(state.errors).toEqual([]);
});

test("an authenticated administrator opening the root sees ML insights", async ({ page }) => {
  const state = await mockAdminEntry(page);
  await page.goto("/");
  await expect(page).toHaveURL(/\/admin\/ml$/);
  await expectMLWorkspace(page);
  expect(state.logins).toBe(0);
  expect(state.requests).toContain("GET /api/v1/admin/analytics/ml/catalog/");
  expect(state.requests).not.toContain("GET /api/v1/admin/analytics/catalog/");
  expect(state.unexpected).toEqual([]); expect(state.errors).toEqual([]);
});

for (const path of ["/admin", "/admin/analytics", "/#admin-analytics"]) {
  test(`legacy administrator entry ${path} opens ML without Population analytics requests`, async ({ page }) => {
    const state = await mockAdminEntry(page);
    await page.goto(path);
    await expect(page).toHaveURL(/\/admin\/ml$/);
    await expectMLWorkspace(page);
    expect(state.requests).not.toContain("GET /api/v1/admin/analytics/catalog/");
    expect(state.unexpected).toEqual([]); expect(state.errors).toEqual([]);
  });
}

for (const signedIn of [false, true]) {
  test(`the doctor approvals deep link survives ${signedIn ? "an existing session" : "sign-in"}`, async ({ page }) => {
    const state = await mockAdminEntry(page, { signedIn });
    await page.goto("/admin/doctors");
    if (!signedIn) await signIn(page);
    await expect(page).toHaveURL(/\/admin\/doctors$/);
    await expect(page.locator("#admin-doctors")).toBeInViewport();
    await expect(page.getByRole("heading", { name: "Doctor approvals", exact: true })).toBeVisible();
    await expect(page.locator("#admin-ml")).toHaveCount(1);
    await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Doctor approvals", exact: true })).toHaveAttribute("aria-current", "location");
    expect(state.logins).toBe(signedIn ? 0 : 1);
    expect(state.requests).toContain("GET /api/v1/admin/analytics/ml/catalog/");
    expect(state.unexpected).toEqual([]); expect(state.errors).toEqual([]);
  });
}

for (const path of ["/#admin-audit", "/admin/ml#admin-audit", "/admin/analytics#admin-audit"]) {
  test(`legacy section anchor ${path} keeps its destination with a clean URL`, async ({ page }) => {
    const state = await mockAdminEntry(page);
    await page.goto(path);
    await expect(page).toHaveURL(/\/admin\/audit$/);
    await expect(page.locator("#admin-audit")).toBeInViewport();
    await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Security audit", exact: true })).toHaveAttribute("aria-current", "location");
    await page.reload();
    await expect(page).toHaveURL(/\/admin\/audit$/);
    await expect(page.locator("#admin-audit")).toBeInViewport();
    expect(state.unexpected).toEqual([]); expect(state.errors).toEqual([]);
  });
}
