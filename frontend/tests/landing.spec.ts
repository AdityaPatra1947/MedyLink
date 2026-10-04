import { test as base, expect, type Page } from "@playwright/test";

const test = base.extend<{ publicPage: Page }>({
  publicPage: async ({ page }, providePage) => {
    const errors: string[] = [];
    const unexpected: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    // Keep public-page checks isolated from the database and email service.
    await page.context().route("**/api/v1/**", async route => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const json = (body: unknown, status = 200) => route.fulfill({
        status, contentType: "application/json", body: JSON.stringify(body),
      });
      if (request.method() === "GET" && path === "/api/v1/auth/me/") return json({ detail: "Not signed in." }, 401);
      if (request.method() === "GET" && path === "/api/v1/auth/csrf/") return json({ csrfToken: "synthetic-csrf" });
      if (request.method() === "POST" && path === "/api/v1/auth/refresh/") return json({ detail: "No session." }, 401);
      if (request.method() === "GET" && path === "/api/v1/ready/") return json({ status: "ok" });
      unexpected.push(`${request.method()} ${path}`);
      return json({ detail: "Unexpected API request blocked by isolated landing-page test." }, 501);
    });
    await providePage(page);
    expect(unexpected).toEqual([]);
    expect(errors).toEqual([]);
  },
});

async function openLanding(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Your health story. All together." })).toBeVisible();
}

test("home has working section links and sign-in and registration entry points", async ({ publicPage: page, isMobile }) => {
  await openLanding(page);
  const navigation = page.getByRole("navigation", { name: "Main navigation", exact: true });
  const menu = page.getByRole("button", { name: "Toggle navigation", exact: true });
  if (isMobile) await menu.click();
  for (const id of ["features", "how-it-works", "for-everyone", "questions"]) {
    await expect(navigation.locator(`a[href="#${id}"]`)).toBeVisible();
    await expect(page.locator(`#${id}`)).toHaveCount(1);
  }
  await navigation.locator('a[href="#features"]').click();
  await expect(page).toHaveURL(/\/#features$/);
  if (isMobile) await expect(menu).toHaveAttribute("aria-expanded", "false");

  if (isMobile) await menu.click();
  await page.getByRole("link", { name: "Sign in", exact: true }).first().click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Welcome back.", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "MedyLink home", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Your health story. All together." })).toBeVisible();
  if (isMobile) await menu.click();
  await page.getByRole("link", { name: "Get started", exact: true }).filter({ visible: true }).first().click();
  await expect(page).toHaveURL(/\/register$/);
  for (const role of ["patient", "doctor", "pharmacist"]) {
    await expect(page.getByRole("link", { name: `Continue as ${role}`, exact: true })).toHaveAttribute("href", `/register/${role}`);
  }
  await expect(page.locator('a[href="/register/admin"]')).toHaveCount(0);
});

test("role choices explain each experience and lead to the matching registration", async ({ publicPage: page }) => {
  await openLanding(page);
  const roles = [
    { name: "Patients", role: "patient", article: "a" },
    { name: "Doctors", role: "doctor", article: "a" },
    { name: "Pharmacists", role: "pharmacist", article: "a" },
  ];
  for (const selected of roles) {
    const button = page.getByRole("button", { name: selected.name, exact: true });
    await button.click();
    await expect(button).toHaveAttribute("aria-pressed", "true");
    for (const other of roles.filter(role => role !== selected)) {
      await expect(page.getByRole("button", { name: other.name, exact: true })).toHaveAttribute("aria-pressed", "false");
    }
    const link = page.getByRole("link", { name: `Create ${selected.article} ${selected.role} account`, exact: true });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", `/register/${selected.role}`);
  }
  await page.getByRole("link", { name: "Create a pharmacist account", exact: true }).click();
  await expect(page).toHaveURL(/\/register\/pharmacist$/);
  await expect(page.locator('input[name="email"]')).toBeVisible();
  await expect(page.locator('input[name="password_confirm"]')).toBeVisible();
  await expect(page.locator('select[name="role"]')).toHaveCount(0);
});

test("record-access answers expand and mobile navigation supports Escape", async ({ publicPage: page, isMobile }) => {
  await openLanding(page);
  if (isMobile) {
    const menu = page.getByRole("button", { name: "Toggle navigation", exact: true });
    await expect(menu).toHaveAttribute("aria-expanded", "false");
    await menu.click();
    await expect(menu).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("Escape");
    await expect(menu).toHaveAttribute("aria-expanded", "false");
  }
  const summary = page.locator("summary").filter({ hasText: "Who can access my medical records?" });
  const disclosure = page.locator("details").filter({ has: summary });
  await expect(disclosure).not.toHaveAttribute("open", "");
  await summary.click();
  await expect(disclosure).toHaveAttribute("open", "");
  await expect(disclosure).toContainText(/approved doctors/i);
  await expect(disclosure).toContainText(/pharmac/i);
  await summary.click();
  await expect(disclosure).not.toHaveAttribute("open", "");
});

test("small screens remain readable and reduced-motion preferences stop animation", async ({ publicPage: page }) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openLanding(page);
  for (const id of ["features", "how-it-works", "for-everyone", "questions"]) {
    await page.locator(`#${id}`).scrollIntoViewIfNeeded();
    await expect(page.locator(`#${id}`)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  }
  const clippedText = await page.locator("main h1, main p").evaluateAll(elements => elements.flatMap(element => {
    const bounds = element.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return [];
    const contents = document.createRange();
    contents.selectNodeContents(element);
    const boxes = [bounds, ...contents.getClientRects()];
    return boxes.some(box => box.left < -1 || box.right > window.innerWidth + 1)
      ? [element.textContent?.trim().slice(0, 80)] : [];
  }));
  expect(clippedText).toEqual([]);
  const movingAnimations = await page.evaluate(() => document.getAnimations().filter(animation => {
    const duration = animation.effect?.getComputedTiming().duration;
    return animation.playState === "running" && typeof duration === "number" && duration > 1;
  }).length);
  expect(movingAnimations).toBe(0);
});

test("direct section links survive a delayed session check and reload", async ({ publicPage: page }) => {
  await page.route("**/api/v1/auth/me/", async route => {
    await new Promise(resolve => setTimeout(resolve, 300));
    await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Not signed in." }) });
  });
  const expectQuestionsAtTop = async () => {
    await expect(page).toHaveURL(/\/#questions$/);
    await expect(page.locator("#questions")).toBeInViewport();
    await expect.poll(() => page.locator("#questions").evaluate(element => {
      const section = element.getBoundingClientRect();
      const header = document.querySelector("header[data-landing-header]")?.getBoundingClientRect();
      return Boolean(header && section.top >= header.bottom - 1 && section.top < window.innerHeight / 2);
    })).toBe(true);
  };
  await page.goto("/#questions");
  await expectQuestionsAtTop();
  // Force a different position so reload cannot pass through browser restoration alone.
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await page.reload();
  await expectQuestionsAtTop();
});
