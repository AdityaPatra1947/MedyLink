import { expect, test, type Page, type Route } from "@playwright/test";
import type { AnalyticsCatalog, AnalyticsFilters, AnalyticsRun, AnalyticsSummary, ClusterResult, EvaluationResult } from "../lib/analytics-types";

const filters: AnalyticsFilters = { dataset_id: "mumbai_stations_v1", disease_code: "DENGUE", line: "", station_id: "", date_from: "2026-09-01", date_to: "2026-09-29" };
const catalog: AnalyticsCatalog = {
  synthetic: true, suppression_threshold: 5,
  datasets: [{ dataset_id: filters.dataset_id, as_of: "2026-09-29", observation_start: "2025-09-30", generator_version: "test", patient_count: 1000 }],
  diseases: [{ disease_code: "DENGUE", label: "Dengue" }, { disease_code: "INFLUENZA", label: "Influenza" }],
  stations: [{ station_id: "KURLA", station_name: "Kurla", lines: ["Central", "Harbour"], latitude: 19.065, longitude: 72.879 }, { station_id: "ANDHERI", station_name: "Andheri", lines: ["Western", "Harbour"], latitude: 19.117, longitude: 72.847 }, { station_id: "VASHI", station_name: "Vashi", lines: ["Harbour"], latitude: 19.063, longitude: 72.999 }],
  lines: ["Central", "Western", "Harbour"], defaults: { ...filters, radius_km: .5, min_samples: 5 },
};
const summary: AnalyticsSummary = {
  synthetic: true, dataset_id: filters.dataset_id, filters, suppression_threshold: 5,
  counts: { distinct_patients: 12, observations: 24, patient_disease_pairs: 12, missing_coordinates: 0, first_recorded_episodes_in_window: 12 },
  diseases: [{ disease_code: "DENGUE", label: "Dengue", patient_count: 12, suppressed: false }],
  stations: [{ station_id: "KURLA", station_name: "Kurla", lines: ["Central", "Harbour"], patient_count: 12, suppressed: false }],
  lines: [{ line: "Central", patient_count: 12, suppressed: false }, { line: "Harbour", patient_count: 12, suppressed: false }],
  age_bands: [{ age_band: "30s", patient_count: 8, suppressed: false }, { age_band: "40s", patient_count: null, suppressed: true }],
  weekly: [{ week_start: "2026-09-07", patient_count: 8, suppressed: false }, { week_start: "2026-09-14", patient_count: null, suppressed: true }, { week_start: "2026-09-21", patient_count: 12, suppressed: false }], notes: [],
};
const cluster: AnalyticsRun<ClusterResult> = {
  id: "00000000-0000-4000-8000-000000000001", kind: "cluster", status: "completed", reused: false, created_at: "2026-09-29T12:00:00Z", synthetic: true,
  dataset_id: filters.dataset_id, filters, parameters: { radius_km: .5, min_samples: 5 }, runtime_ms: 20, versions: { service: "test" },
  result: { counts: { eligible_patients: null, with_coordinates: null, missing_coordinates: 0, clustered_patients: 12, noise_patients: null, cluster_count: 1 }, metrics: { noise_fraction: null, silhouette: { value: null, reason: "At least two non-noise clusters are required.", coverage: null, sample_size: null } }, clusters: [{ cluster: 0, patient_count: 12, suppressed: false, centroid: { latitude: 19.065, longitude: 72.879 }, bounds: { south: 19.06, north: 19.07, west: 72.875, east: 72.885 }, stations: summary.stations }], notes: ["Synthetic spatial groups only."] },
};
const evaluation: AnalyticsRun<EvaluationResult> = {
  ...cluster, id: "00000000-0000-4000-8000-000000000002", kind: "evaluation",
  result: {
    grid: [.3, .5, .8, 1.2].flatMap(radius_km => [4, 5, 8, 12].map(min_samples => ({ radius_km, min_samples, cluster_count: 1, noise_fraction: null, silhouette: { value: null, reason: "One cluster", coverage: null } }))),
    selected: { radius_km: .5, min_samples: 5 },
    stability: { seed: 20260929, subsample_fraction: .8, perturbation_km: .03, repeats: [{ repeat: 1, shared_patients: 10, retained_fraction: .8, noise_fraction: 0, adjusted_rand_index: { value: .97, reason: null } }], mean_adjusted_rand_index: { value: .97, reason: null } },
    synthetic_pattern_recovery: { adjusted_rand_index: { value: .96, reason: null }, evaluated_patients: 12, coverage: 1, background_convention: "BACKGROUND is one reference group.", reason: null }, counts: {}, notes: [],
  },
};

async function mockAnalytics(page: Page, empty = false, delaySeptember20 = false) {
  const state = { clusterWrites: 0, evaluations: 0, savedReads: 0, unexpected: [] as string[], pageErrors: [] as string[], releases: [] as (() => void)[] };
  page.on("pageerror", error => state.pageErrors.push(error.message));
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  // Every API call is intercepted; tests cannot read or mutate the real database.
  await page.route("**/api/v1/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    if (path === "/api/v1/auth/me/") return json(route, { user: { id: "synthetic-admin-test", account_id: "A-TEST01", name: "Synthetic Administrator", email: "admin@example.test", role: "admin", email_verified: true } });
    if (path === "/api/v1/auth/csrf/") return json(route, { csrfToken: "synthetic-token" });
    if (["/api/v1/auth/sessions/", "/api/v1/admin/audit/", "/api/v1/admin/provider-applications/"].includes(path)) return json(route, { results: [], count: 0, next: null });
    if (path === "/api/v1/admin/analytics/catalog/") return json(route, empty ? { ...catalog, datasets: [], stations: [] } : catalog);
    if (path === "/api/v1/admin/analytics/summary/") {
      const activeFilters = { ...filters, ...Object.fromEntries(url.searchParams) };
      if (delaySeptember20 && url.searchParams.get("date_to") === "2026-09-20") {
        await new Promise<void>(resolve => state.releases.push(resolve));
        return json(route, { ...summary, filters: activeFilters, counts: { ...summary.counts, distinct_patients: 777 } });
      }
      return json(route, { ...summary, filters: activeFilters });
    }
    if (path === "/api/v1/admin/analytics/cluster-runs/" && request.method() === "POST") {
      expect(request.postDataJSON()).toMatchObject({ ...filters, radius_km: .5, min_samples: 5 });
      expect(request.headers()["x-csrftoken"]).toBe("synthetic-token");
      state.clusterWrites++; return json(route, cluster, 201);
    }
    if (path === `/api/v1/admin/analytics/cluster-runs/${cluster.id}/`) { state.savedReads++; return json(route, { ...cluster, reused: true }); }
    if (path === "/api/v1/admin/analytics/evaluation-runs/" && request.method() === "POST") { state.evaluations++; return json(route, evaluation, 201); }
    state.unexpected.push(`${request.method()} ${path}`);
    return json(route, { detail: "Unexpected request blocked by isolated analytics test." }, 501);
  });
  return state;
}

test.use({ reducedMotion: "reduce" });

test("an empty deployment has a clear analytics state without fitting a model", async ({ page }) => {
  const state = await mockAnalytics(page, true);
  await page.goto("/admin/analytics");
  await expect(page.getByRole("heading", { name: "No analytics dataset is available" })).toBeVisible();
  expect(state.clusterWrites).toBe(0); expect(state.evaluations).toBe(0);
  expect(state.unexpected).toEqual([]); expect(state.pageErrors).toEqual([]);
});

test("admin can run, inspect, reload and evaluate aggregates without exposing suppressed counts", async ({ page }) => {
  const state = await mockAnalytics(page);
  await page.goto("/admin/analytics");
  const area = page.locator("#admin-analytics");
  await expect(area.getByRole("button", { name: "Run clustering", exact: true })).toBeEnabled();
  await area.getByRole("button", { name: "Run clustering", exact: true }).click();
  await expect(area.getByRole("heading", { name: "The groups in this run" })).toBeVisible();
  await expect(area.getByText("At least two non-noise clusters are required.", { exact: true })).toBeVisible();
  await expect(area.getByText("Hidden when a small count could be inferred, or unavailable for this cohort.")).toBeVisible();
  await area.getByRole("button", { name: "Reload saved result", exact: true }).click();
  await expect.poll(() => state.savedReads).toBe(1);
  await area.getByRole("button", { name: "Run evaluation", exact: true }).click();
  await expect(area.getByRole("heading", { name: "Stability under small changes" })).toBeVisible();
  await expect(area.getByText("0.960", { exact: true })).toBeVisible();
  await expect(area.getByText(/not diagnostic accuracy/i).first()).toBeVisible();
  await area.getByRole("combobox", { name: "Condition", exact: true }).selectOption("");
  await area.getByRole("button", { name: "Apply filters", exact: true }).click();
  await expect(area.getByRole("heading", { name: "The groups in this run" })).toHaveCount(0);
  await expect(area.getByRole("button", { name: "Run clustering", exact: true })).toBeDisabled();
  expect(state.clusterWrites).toBe(1); expect(state.evaluations).toBe(1);
  expect(state.unexpected).toEqual([]); expect(state.pageErrors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test("an older summary response cannot replace the current filters after resetting", async ({ page }) => {
  const state = await mockAnalytics(page, false, true);
  await page.goto("/admin/analytics");
  const area = page.locator("#admin-analytics");
  await expect(area.getByRole("button", { name: "Apply filters", exact: true })).toBeEnabled();
  await area.getByLabel("Through", { exact: true }).fill("2026-09-20");
  await area.getByRole("button", { name: "Apply filters", exact: true }).click();
  await expect.poll(() => state.releases.length).toBeGreaterThan(0);
  await area.getByRole("button", { name: "Reset demo", exact: true }).click();
  await expect(area.getByLabel("Through", { exact: true })).toHaveValue("2026-09-29");
  await expect(area.getByRole("button", { name: "Run clustering", exact: true })).toBeEnabled();
  const staleResponse = page.waitForResponse(response => response.url().includes("date_to=2026-09-20"));
  state.releases.forEach(release => release());
  await staleResponse;
  await page.evaluate(() => new Promise(requestAnimationFrame));
  await expect(area.getByText("777", { exact: true })).toHaveCount(0);
  expect(state.unexpected).toEqual([]); expect(state.pageErrors).toEqual([]);
});
