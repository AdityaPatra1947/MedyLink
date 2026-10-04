import { test, expect } from "@playwright/test";

test("public screens hydrate with CSP and offer only public account roles", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  const response = await page.goto("/login");
  expect(response?.headers()["content-security-policy"]).toContain("'nonce-");
  await expect(page.getByRole("heading", { name: "Welcome back." })).toBeVisible();
  await page.goto("/register");
  for (const role of ["patient", "doctor", "pharmacist"]) {
    await expect(page.getByRole("link", { name: `Continue as ${role}`, exact: true })).toHaveAttribute("href", `/register/${role}`);
  }
  await expect(page.locator('a[href="/register/admin"]')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
});

test("each registration page fixes its role and preserves a responsive account step", async ({ page }) => {
  for (const role of ["patient", "doctor", "pharmacist"]) {
    await page.goto(`/register/${role}`);
    await expect(page.locator('input[name="name"]')).toBeVisible();
    await expect(page.locator('input[name="email"]')).toBeVisible();
    await expect(page.locator('input[name="password_confirm"]')).toBeVisible();
    await expect(page.locator('select[name="role"]')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  }
});

test("a card URL exposes no patient data and the privacy notice explains sharing", async ({ page }) => {
  await page.goto("/health-card/synthetic-not-a-real-card");
  await expect(page.getByText("No medical details are shown by this link.", { exact: false })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toHaveCount(0);
  await page.getByRole("button", { name: "Privacy & care" }).click();
  await expect(page.getByRole("heading", { name: "Your records. Connected care." })).toBeVisible();
  await expect(page.getByText("Previously downloaded copies cannot be recalled", { exact: false })).toBeVisible();
});


test("email verification accepts six-digit codes and old links open the code form", async ({ page }) => {
  await page.goto("/verify-email?token=retired-synthetic-token");
  await expect(page.getByText("Email verification now uses a six-digit code.", { exact: false })).toBeVisible();
  await expect(page).toHaveURL(/\/verify-email$/);
  await expect(page.locator('input[name="email"]')).toBeVisible();
  const code = page.locator('input[name="code"]');
  await expect(code).toBeVisible();
  await expect(code).toHaveAttribute("type", "text");
  await expect(code).toHaveAttribute("inputmode", "numeric");
  await expect(code).toHaveAttribute("autocomplete", "one-time-code");
  await code.fill("012345");
  await expect(code).toHaveValue("012345");
  await expect(page.getByRole("button", { name: "Confirm email address", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Verify email", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});


test("resend cooldown catches up after returning from the email tab", async ({ page }) => {
  await page.route("**/api/v1/auth/resend-verification/", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Generic synthetic response", resend_after: 60 }),
  }));
  await page.goto("/verify-email");
  await page.locator('input[name="email"]').fill("synthetic@example.test");
  await page.getByRole("button", { name: "Send code", exact: true }).click();
  await expect(page.getByRole("button", { name: /Resend code in [0-9]+s/ })).toBeDisabled();
  await page.clock.setFixedTime(new Date(Date.now() + 61_000));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("button", { name: "Resend code", exact: true })).toBeEnabled();
});
