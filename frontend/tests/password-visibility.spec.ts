import { test, expect, type Page, type Route } from "@playwright/test";

async function mockPublicApi(page: Page, mutation?: (route: Route, pathname: string) => Promise<void>) {
  await page.route("**/api/v1/**", async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === "/api/v1/auth/csrf/") {
      await route.fulfill({ json: { csrfToken: "synthetic-csrf-token" } });
    } else if (pathname === "/api/v1/ready/") {
      await route.fulfill({ json: { status: "ready" } });
    } else if (route.request().method() === "POST" && mutation) {
      await mutation(route, pathname);
    } else {
      await route.fulfill({ status: 403, json: { detail: "Not signed in (test fixture)." } });
    }
  });
}

test("sign-in visibility works with mouse and keyboard without changing credentials or submitting", async ({ page }) => {
  const requests: unknown[] = [];
  let finishLogin: (() => void) | undefined;
  await mockPublicApi(page, async (route, pathname) => {
    if (pathname !== "/api/v1/auth/login/") {
      await route.fulfill({ status: 403, json: { detail: "Unexpected test request." } });
      return;
    }
    requests.push(route.request().postDataJSON());
    await new Promise<void>(resolve => { finishLogin = resolve; });
    await route.fulfill({ status: 401, json: { detail: "Synthetic sign-in response." } });
  });
  try {
    await page.goto("/login");
    const input = page.locator('input[name="password"]');
    await expect(input).toHaveAttribute("type", "password");
    await expect(input).toHaveAttribute("autocomplete", "current-password");
    await page.locator('input[name="email"]').fill("fixture@example.test");
    await input.fill("Synthetic-example-123!");
    await page.getByRole("button", { name: "Show password", exact: true }).click();
    await expect(input).toHaveAttribute("type", "text");
    await expect(input).toHaveValue("Synthetic-example-123!");
    await page.getByRole("button", { name: "Hide password", exact: true }).click();
    await expect(input).toHaveAttribute("type", "password");
    await page.getByRole("button", { name: "Show password", exact: true }).focus();
    await page.keyboard.press("Space");
    await expect(input).toHaveAttribute("type", "text");
    expect(requests).toEqual([]);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect.poll(() => requests).toEqual([{ email: "fixture@example.test", password: "Synthetic-example-123!" }]);
    await expect(input).toBeDisabled();
    await expect(page.getByRole("button", { name: "Hide password", exact: true })).toBeDisabled();
    finishLogin?.();
    await expect(page.getByRole("alert").filter({ hasText: "Synthetic sign-in response." })).toBeVisible();
    await expect(input).toBeEnabled();
  } finally {
    finishLogin?.();
  }
});

for (const role of ["patient", "doctor", "pharmacist"]) {
  test(`${role} registration toggles password fields independently and preserves entered values between steps`, async ({ page }) => {
    await mockPublicApi(page);
    await page.goto(`/register/${role}`);
    const password = page.locator('input[name="password"]');
    const confirmation = page.locator('input[name="password_confirm"]');
    await expect(password).toHaveAttribute("type", "password");
    await expect(confirmation).toHaveAttribute("type", "password");
    await expect(password).toHaveAttribute("minlength", "10");
    await expect(password).toHaveAttribute("autocomplete", "new-password");
    await page.locator('input[name="name"]').fill("Synthetic Example");
    await page.locator('input[name="email"]').fill("fixture@example.test");
    await password.fill("Synthetic-example-123!");
    await confirmation.fill("Synthetic-example-123!");
    await page.getByRole("button", { name: "Show password", exact: true }).click();
    await expect(password).toHaveAttribute("type", "text");
    await expect(confirmation).toHaveAttribute("type", "password");
    await page.getByRole("button", { name: "Show confirm password", exact: true }).click();
    await expect(confirmation).toHaveAttribute("type", "text");
    await expect(password).toHaveValue("Synthetic-example-123!");
    await expect(confirmation).toHaveValue("Synthetic-example-123!");
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await page.getByRole("button", { name: "Back", exact: true }).click();
    await expect(password).toHaveValue("Synthetic-example-123!");
    await expect(confirmation).toHaveValue("Synthetic-example-123!");
    await expect(password).toHaveAttribute("type", "password");
    await expect(confirmation).toHaveAttribute("type", "password");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  });
}

test("password reset visibility preserves the token, validation, and submitted password", async ({ page }) => {
  const requests: unknown[] = [];
  await mockPublicApi(page, async (route, pathname) => {
    if (pathname === "/api/v1/auth/reset-password/") {
      requests.push(route.request().postDataJSON());
      await route.fulfill({ json: { detail: "Password reset (test fixture)." } });
    } else {
      await route.fulfill({ status: 403, json: { detail: "Unexpected test request." } });
    }
  });
  await page.goto("/reset-password?token=synthetic-reset-token");
  const password = page.locator('input[name="password"]');
  await expect(password).toHaveAttribute("type", "password");
  await expect(password).toHaveAttribute("minlength", "10");
  await expect(password).toHaveAttribute("autocomplete", "new-password");
  await password.fill("Synthetic-example-123!");
  await page.getByRole("button", { name: "Show new password", exact: true }).click();
  await expect(password).toHaveAttribute("type", "text");
  expect(requests).toEqual([]);
  await page.getByRole("button", { name: "Reset password", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Password reset. You can now sign in");
  expect(requests).toEqual([{ password: "Synthetic-example-123!", token: "synthetic-reset-token" }]);
});

test("local sign-in opens the separate demo workspace without transferring credentials", async ({ page }) => {
  await mockPublicApi(page);
  const navigations: { url: string; method: string; body: string | null }[] = [];
  await page.route("http://localhost:3001/login", async route => {
    navigations.push({ url: route.request().url(), method: route.request().method(), body: route.request().postData() });
    await route.fulfill({ contentType: "text/html", body: "<!doctype html><html lang=\"en\"><body><h1>Demo sign-in fixture</h1></body></html>" });
  });
  await page.goto("http://localhost:3000/login");
  await page.locator('input[name="email"]').fill("fixture@example.test");
  await page.locator('input[name="password"]').fill("Synthetic-example-123!");
  const demoLink = page.getByRole("link", { name: "Open demo sign in" });
  await expect(demoLink).toHaveAttribute("href", "http://localhost:3001/login");
  await demoLink.click();
  await expect(page).toHaveURL("http://localhost:3001/login");
  await expect(page.getByRole("heading", { name: "Demo sign-in fixture" })).toBeVisible();
  expect(navigations).toEqual([{ url: "http://localhost:3001/login", method: "GET", body: null }]);
});
