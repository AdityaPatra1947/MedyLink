import { test, expect, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const qrData = `data:image/png;base64,${readFileSync(join(__dirname, "fixtures", "scanner-card.png")).toString("base64")}`;
const user = { id: "synthetic-scanner-doctor", role: "doctor", account_id: "D-TEST01", name: "Synthetic Doctor", email: "doctor@example.test", email_verified: true };
const patient = { id: "synthetic-scanner-patient", name: "Synthetic QR Patient", account_id: "P-TEST01", health_id: "AT-TEST", date_of_birth: "1990-01-01", blood_group: "B+", allergy_status: "unknown" };
const application = { id: "synthetic-application", name: user.name, provider_email: user.email, role: "doctor", email_verified: true, status: "approved", is_current: true, version: 1, valid_until: "2099-01-01T00:00:00Z", registration_number: "TEST-123", registering_body: "Synthetic Register", qualification: "Synthetic Degree", specialty: "Synthetic Specialty", clinic_name: "Synthetic Clinic", contact_phone: "9000000000", practice_address: "Synthetic address", years_experience: 2, documents: [], reviews: [], history: [], created_at: "2026-09-01T00:00:00Z", reason: "" };
type CameraError = { name: string; message: string };
type CameraOptions = { errors?: CameraError[]; deferred?: boolean; holdPlayback?: boolean; playError?: CameraError; qr?: boolean };
type CameraState = { calls: number; stopped: number; streamCount: number; trackStates: string[]; errors: CameraError[]; deferred: boolean; holdPlayback: boolean; playError: CameraError | null; pendingRelease: (() => void) | null; videos: HTMLVideoElement[] };

async function mockScanner(page: Page, options: CameraOptions = {}, role: "doctor" | "pharmacist" = "doctor") {
  const scannerUser = { ...user, role };
  const scannerApplication = { ...application, role, shop_name: "Synthetic Pharmacy", shop_license: "TEST-LICENSE", shop_license_expires: "2099-01-01" };
  const state = { unexpected: [] as string[], errors: [] as string[], lookups: [] as string[] };
  page.on("pageerror", error => state.errors.push(error.message));
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  await page.context().route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (method === "GET" && path === "/api/v1/auth/me/") return json(route, { user: scannerUser });
    if (method === "GET" && path === "/api/v1/auth/csrf/") return json(route, { csrfToken: "synthetic-csrf" });
    if (method === "GET" && path === "/api/v1/auth/sessions/") return json(route, { results: [] });
    if (method === "GET" && path === "/api/v1/provider/application/") return json(route, { current: scannerApplication, history: [] });
    if (method === "GET" && path === "/api/v1/doctor/profile/") return json(route, { user: scannerUser, application: scannerApplication });
    if (method === "GET" && path === "/api/v1/doctor/patients/") return json(route, { results: [], next: null });
    if (method === "GET" && path === "/api/v1/pharmacy/dispensing/") return json(route, { results: [], next: null });
    if (method === "GET" && path === `/api/v1/patients/${patient.id}/prescriptions/`) return json(route, { results: [], next: null });
    if (method === "POST" && path === "/api/v1/provider/patients/lookup/") {
      state.lookups.push(request.postDataJSON().identifier);
      return json(route, { patient_id: patient.id, patient });
    }
    if (method === "GET" && path === `/api/v1/patients/${patient.id}/clinical-summary/`) return json(route, { patient, is_my_patient: false });
    if (method === "GET" && path === `/api/v1/patients/${patient.id}/records/`) return json(route, { results: [], next: null });
    state.unexpected.push(`${method} ${path}`);
    return json(route, { detail: "Unexpected request blocked by isolated scanner test." }, 501);
  });
  // A real canvas MediaStream exercises HTML video startup and the installed QR
  // decoder without requesting physical camera access or contacting the database.
  await page.addInitScript(({ options, qrData }) => {
    const streams: MediaStream[] = [];
    const state: CameraState = { calls: 0, stopped: 0, streamCount: 0, trackStates: [], errors: options.errors || [], deferred: !!options.deferred, holdPlayback: !!options.holdPlayback, playError: options.playError || null, pendingRelease: null, videos: [] };
    Object.defineProperty(window, "__scannerCamera", { value: state });
    Object.defineProperty(state, "trackStates", { get: () => streams.flatMap(stream => stream.getTracks().map(track => track.readyState)) });
    const originalPlay = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function () {
      if (state.playError && this instanceof HTMLVideoElement) {
        const failure = state.playError; state.playError = null;
        return Promise.reject(new DOMException(failure.message, failure.name));
      }
      if (state.holdPlayback && this instanceof HTMLVideoElement) {
        state.videos.push(this);
        return new Promise<void>(() => {});
      }
      return originalPlay.call(this);
    };
    async function createStream() {
      const canvas = document.createElement("canvas");
      canvas.width = 640; canvas.height = 480;
      const context = canvas.getContext("2d")!;
      let image: HTMLImageElement | null = null;
      if (options.qr) {
        image = new Image(); image.src = qrData;
        await image.decode();
      }
      function paint() {
        context.fillStyle = "white";
        context.fillRect(0, 0, 640, 480);
        if (image) { context.imageSmoothingEnabled = false; context.drawImage(image, 160, 80, 320, 320); }
      }
      paint();
      const stream = canvas.captureStream(12);
      const timer = window.setInterval(paint, 70);
      for (const track of stream.getTracks()) {
        const stop = track.stop.bind(track);
        track.stop = () => { if (track.readyState !== "ended") state.stopped++; stop(); window.clearInterval(timer); };
      }
      streams.push(stream); state.streamCount++;
      return stream;
    }
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", { configurable: true, value: async () => {
      state.calls++;
      const failure = state.errors.shift();
      if (failure) throw new DOMException(failure.message, failure.name);
      if (state.deferred) await new Promise<void>(resolve => { state.pendingRelease = resolve; });
      return createStream();
    } });
  }, { options, qrData });
  return state;
}
async function cameraState(page: Page) {
  return page.evaluate(() => {
    const state = (window as unknown as { __scannerCamera: CameraState }).__scannerCamera;
    return { calls: state.calls, stopped: state.stopped, streamCount: state.streamCount, trackStates: state.trackStates, waiting: !!state.pendingRelease, videos: state.videos.length };
  });
}
function nav(page: Page, name: string) { return page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name, exact: true }); }
async function openScanner(page: Page, role: "doctor" | "pharmacist" = "doctor") {
  await page.goto("/");
  await expect(nav(page, role === "doctor" ? "My patients" : "Find prescriptions")).toBeVisible();
  expect((await cameraState(page)).calls).toBe(0);
  await nav(page, role === "doctor" ? "Find patient" : "Find prescriptions").click();
  await page.getByRole("button", { name: "Scan QR with camera", exact: true }).click();
  await expect.poll(async () => (await cameraState(page)).calls).toBeGreaterThan(0);
}
function expectClean(state: Awaited<ReturnType<typeof mockScanner>>) {
  expect(state.unexpected).toEqual([]);
  expect(state.errors).toEqual([]);
}
async function expectReleased(page: Page) {
  await expect.poll(async () => (await cameraState(page)).streamCount).toBeGreaterThan(0);
  await expect.poll(async () => (await cameraState(page)).trackStates.every(value => value === "ended")).toBeTruthy();
}

test.use({ reducedMotion: "reduce" });

for (const error of [
  { name: "NotAllowedError", message: "Permission denied", expected: "Camera permission was denied." },
  { name: "NotFoundError", message: "Requested device not found", expected: "No camera was found." },
  { name: "NotReadableError", message: "Could not start video source", expected: "The camera is unavailable or in use by another app." },
]) {
  test(`scanner explains ${error.name} without treating every failure as permission denial`, async ({ page }) => {
    const state = await mockScanner(page, { errors: [error] });
    await openScanner(page);
    await expect(page.locator("#doctor-request").getByRole("alert")).toContainText(error.expected);
    await expect(page.getByRole("button", { name: "Retry camera", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Close scanner", exact: true }).click();
    await expect(page.getByRole("button", { name: "Close scanner", exact: true })).toHaveCount(0);
    expectClean(state);
  });
}

test("system-level denial provides Windows guidance and Retry camera can recover", async ({ page }) => {
  const state = await mockScanner(page, { errors: [{ name: "NotAllowedError", message: "Permission denied by system" }] });
  await openScanner(page);
  await expect(page.locator("#doctor-request").getByRole("alert")).toContainText("Camera access was denied by your operating system.");
  await expect(page.locator("#doctor-request")).toContainText(/Windows|Privacy.*security/i);
  await page.getByRole("button", { name: "Retry camera", exact: true }).click();
  await expect.poll(async () => (await cameraState(page)).streamCount).toBe(1);
  await expect(page.locator('#doctor-request video')).toBeVisible();
  await expect(page.locator("#doctor-request").getByRole("alert")).toHaveCount(0);
  await page.getByRole("button", { name: "Close scanner", exact: true }).click();
  await expectReleased(page);
  expectClean(state);
});

test("a video playback failure is reported and cleaned up instead of being silently ignored", async ({ page }) => {
  const state = await mockScanner(page, { playError: { name: "NotReadableError", message: "Synthetic playback failure" } });
  await openScanner(page);
  await expect(page.locator("#doctor-request").getByRole("alert")).toContainText("The camera is unavailable or in use by another app.");
  await expectReleased(page);
  await page.getByRole("button", { name: "Retry camera", exact: true }).click();
  await expect.poll(async () => (await cameraState(page)).streamCount).toBe(2);
  await expect(page.locator("#doctor-request").getByRole("alert")).toHaveCount(0);
  await page.getByRole("button", { name: "Close scanner", exact: true }).click();
  await expectReleased(page);
  expectClean(state);
});

for (const role of ["doctor", "pharmacist"] as const) {
  test(`${role}: a synthetic camera scans a QR card, opens its patient once, and releases the stream`, async ({ page }) => {
    const state = await mockScanner(page, { qr: true }, role);
    await openScanner(page, role);
    const section = `#${role}-${role === "doctor" ? "request" : "prescriptions"}`;
    await expect(page.locator(section)).toContainText(patient.name, { timeout: 15000 });
    expect(state.lookups).toEqual(["synthetic-camera-card"]);
    await expectReleased(page);
    await expect(page.getByRole("button", { name: "Close scanner", exact: true })).toHaveCount(0);
    expectClean(state);
  });
}

test("leaving the scanner section stops its camera and reopening starts a fresh stream", async ({ page }) => {
  const state = await mockScanner(page);
  await openScanner(page);
  await expect(page.locator('#doctor-request video')).toBeVisible();
  await nav(page, "My profile").click();
  await expectReleased(page);
  await expect(page.locator('#doctor-request video')).toHaveCount(0);
  await nav(page, "Find patient").click();
  expect((await cameraState(page)).streamCount).toBe(1);
  await page.getByRole("button", { name: "Scan QR with camera", exact: true }).click();
  await expect.poll(async () => (await cameraState(page)).streamCount).toBe(2);
  await page.getByRole("button", { name: "Close scanner", exact: true }).click();
  await expectReleased(page);
  expectClean(state);
});

test("closing while camera permission is pending also stops the late stream", async ({ page }) => {
  const state = await mockScanner(page, { deferred: true });
  await openScanner(page);
  await expect.poll(async () => (await cameraState(page)).waiting).toBeTruthy();
  await page.getByRole("button", { name: "Close scanner", exact: true }).click();
  await page.evaluate(() => {
    const camera = (window as unknown as { __scannerCamera: CameraState }).__scannerCamera;
    camera.deferred = false; camera.pendingRelease?.();
  });
  await expectReleased(page);
  expectClean(state);
});

test("closing before the video playing event still releases the acquired camera", async ({ page }) => {
  const state = await mockScanner(page, { holdPlayback: true });
  await openScanner(page);
  await expect.poll(async () => (await cameraState(page)).videos).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Close scanner", exact: true }).click();
  await expectReleased(page);
  expectClean(state);
});

test("a visible scan button opens the scanner even while the previous section is highlighted", async ({ page }) => {
  const state = await mockScanner(page);
  const viewport = page.viewportSize()!;
  await page.setViewportSize({ width: viewport.width, height: 1600 });
  await page.goto("/");
  await expect(nav(page, "My patients")).toHaveAttribute("aria-current", "location");
  const button = page.getByRole("button", { name: "Scan QR with camera", exact: true });
  await expect(button).toBeInViewport();
  expect((await cameraState(page)).calls).toBe(0);
  await button.click();
  await expect.poll(async () => (await cameraState(page)).streamCount).toBe(1);
  await expect(page.locator('#doctor-request video')).toBeVisible();
  await expect(nav(page, "My patients")).toHaveAttribute("aria-current", "location");
  // The lookup remains inactive before and after this scroll, so only its
  // visibility observer can release this camera (the active prop stays false).
  await page.evaluate(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "instant" }));
  await expect(nav(page, "Security settings")).toHaveAttribute("aria-current", "location");
  await expectReleased(page);
  await expect(page.getByRole("button", { name: "Close scanner", exact: true })).toHaveCount(0);
  expectClean(state);
});
