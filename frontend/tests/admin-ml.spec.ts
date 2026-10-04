import { expect, test, type Page, type Route } from "@playwright/test";
import type { MLCatalog, MLFilters, MLInsights, MLMetrics, MLModelResult, MLReport, MLRun } from "../lib/ml-types";

const filters: MLFilters = { dataset_id: "mumbai_stations_v1", date_from: null, date_to: null, disease_code: "", line: "", station_id: "" };
const catalog: MLCatalog = {
  synthetic: true, suppression_threshold: 5, datasets: [{ dataset_id: filters.dataset_id, as_of: "2026-10-03", observation_start: "2024-01-01" }],
  defaults: filters, diseases: [{ disease_code: "HYPERTENSION", label: "Hypertension" }, { disease_code: "DENGUE", label: "Dengue" }], lines: ["Central", "Western"],
  stations: [{ station_id: "KURLA", station_name: "Kurla", lines: ["Central"], latitude: 19.06, longitude: 72.87 }, { station_id: "ANDHERI", station_name: "Andheri", lines: ["Western"], latitude: 19.12, longitude: 72.85 }],
};
const metrics: MLMetrics = { accuracy: .81, precision: .75, recall: .72, f1: .735, macro_f1: .78 };
const model = (id: string, name: string, delta = 0): MLModelResult => ({ id, name, cv: { mean: { ...metrics, macro_f1: .76 + delta }, std: { accuracy: .02, precision: .01, recall: .03, f1: .02, macro_f1: .02 }, folds: [metrics, metrics, metrics] }, holdout: { ...metrics, macro_f1: .77 + delta, confusion_matrix: [[70, 10], [10, 30]], examples: 120, patients: 60 } });
const report: MLReport = {
  status: "completed", target: { label: "Next recorded higher blood pressure", definition: "Next systolic >= 140 or diastolic >= 90 mmHg.", disclaimer: "Not a diagnosis." },
  data: { input_rows: 800, eligible_pairs: 600, eligible_patients: 240, class_counts: { below_threshold: 400, elevated: 200 }, interval_days: { min: 1, median: 30, max: 365 }, missing_feature_counts: { glucose: 50, adherence: 100 } },
  models: [model("logistic_regression", "Logistic regression"), model("decision_tree", "Decision tree", -.02), model("random_forest", "Random forest", .03), model("gradient_boosting", "Gradient boosting", .01)],
  baselines: [model("majority", "Always choose the most common result", -.1), model("carry_forward", "Repeat the current BP category", -.05)],
  selection: { model_id: "random_forest", model_name: "Random forest", prediction_enabled: true, gate_checks: { comparison_passed: true }, message: "Demonstration checks passed. These results are not clinically validated.", criterion: "Cross-validation macro F1", gate_policy: "Beat simple references before enabling estimates." },
  feature_importance: [{ feature: "systolic", label: "Upper blood pressure reading", importance: .08, standard_deviation: .01 }, { feature: "age", label: "Age", importance: -.01, standard_deviation: .02 }], feature_importance_method: "Held-out permutation effect on macro F1.",
  training_dates: { from: "2024-01-01", through: "2026-09-30" }, limitations: ["Synthetic data do not establish clinical accuracy."],
};
const run: MLRun = { id: "00000000-0000-4000-8000-000000000001", status: "completed", filters, created_at: "2026-10-03T07:00:00Z", started_at: "2026-10-03T07:00:01Z", finished_at: "2026-10-03T07:00:10Z", error: null, message: "Training finished.", report };
const data: MLInsights = {
  synthetic: true, filters,
  source: { patients: 240, visits: 800, reports: 60, labs: 60, adherence_logs: 365, extracted_reports: 60, unsupported_reports: 0, historically_unavailable_reports: 50, history_start: "2024-01-01", history_end: "2026-09-30", excluded: { missing_geography: 0 } },
  summary: { patients: 240, disease_counts: [{ code: "HYPERTENSION", label: "Hypertension", count: 80 }], monthly_counts: [{ month: "2024-01", count: 40 }, { month: "2026-09", count: 90 }], stations: [{ station_id: "KURLA", station_name: "Kurla", patient_count: 80 }, { station_id: "ANDHERI", station_name: "Andheri", patient_count: 160 }] },
  prediction: { eligible_patients: 240, prediction_enabled: true, counts: { elevated: 80, below_threshold: 160 }, as_of: "2026-09-30", interpretation: "Retrospective synthetic estimates; not a backtest or a live clinical forecast." },
  patient_groups: { status: "completed", eligible_patients: 240, groups: [{ group: 1, label: "Similar readings 1", patient_count: 120, suppressed: false, profile: { systolic: { mean: 125, observations: 120 }, diastolic: { mean: 82, observations: 120 } }, position: { x: -1, y: 1 }, conditions: [{ code: "HYPERTENSION", patient_count: 50 }], explanation: "These patients have similar recorded measurements." }, { group: 2, label: "Similar readings 2", patient_count: 120, suppressed: false, profile: {}, position: { x: 1, y: -1 }, conditions: [], explanation: "These patients have similar recorded measurements." }], silhouette: .21 },
  hotspots: { counts: { eligible_patients: 240, with_coordinates: 240, missing_coordinates: 0, clustered_patients: 240, noise_patients: 0, cluster_count: 1 }, clusters: [{ cluster: 0, patient_count: 240, suppressed: false, centroid: { latitude: 19.09, longitude: 72.86 }, bounds: null, stations: [{ station_id: "KURLA", station_name: "Kurla", patient_count: 80, suppressed: false }] }], notes: [] },
  model: run, training: null, notes: ["No individual patient identities are returned."],
};

async function mockML(page: Page, options: { role?: string; empty?: boolean; unavailable?: boolean; suppressed?: boolean; failure?: boolean; stale?: boolean; manyGroups?: boolean } = {}) {
  const state = { requests: [] as string[], writes: [] as MLFilters[], polls: 0, pageErrors: [] as string[], unexpected: [] as string[], releases: [] as (() => void)[] };
  page.on("pageerror", error => state.pageErrors.push(error.message));
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  // All API requests are mocked so tests cannot access or mutate patient data.
  await page.route("**/api/v1/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    if (path === "/api/v1/auth/me/") return json(route, { user: { id: "ml-ui-admin", account_id: "A-TESTML", name: "Course Administrator", email: "admin@example.test", role: options.role || "admin", email_verified: true } });
    if (path === "/api/v1/auth/csrf/") return json(route, { csrfToken: "ml-test-csrf" });
    if (["/api/v1/auth/sessions/", "/api/v1/admin/audit/", "/api/v1/admin/provider-applications/"].includes(path)) return json(route, { results: [], next: null });
    if (path === "/api/v1/admin/analytics/catalog/") return json(route, { ...catalog, datasets: [], stations: [] });
    if (path === "/api/v1/admin/analytics/ml/catalog/") { state.requests.push(url.search); return json(route, options.empty ? { ...catalog, datasets: [] } : catalog); }
    if (path === "/api/v1/admin/analytics/ml/insights/") {
      state.requests.push(url.search);
      const currentFilters = { ...filters, ...Object.fromEntries(url.searchParams) };
      const result = structuredClone(data);
      result.filters = currentFilters;
      if (url.searchParams.has("date_from")) result.source.patients = 60;
      if (options.stale && url.searchParams.get("date_from") === "2026-01-01") { await new Promise<void>(resolve => state.releases.push(resolve)); result.source.patients = 777; }
      if (options.unavailable) { result.model = null; result.prediction = { prediction_enabled: false, counts: null, reason: "No model has been trained." }; result.patient_groups = { status: "insufficient_data", groups: [], reason: "At least 30 patients with usable measurements are needed." }; }
      if (options.suppressed) { result.prediction.counts = { elevated: null, below_threshold: null }; result.prediction.suppressed = true; result.prediction.reason = "Small result groups are hidden."; result.model!.report!.models.forEach(value => { value.holdout.confusion_matrix = null; }); result.patient_groups.groups = [{ ...result.patient_groups.groups[0], patient_count: null, suppressed: true, profile: {}, position: null, conditions: [] }]; }
      if (options.manyGroups) result.hotspots!.clusters = Array.from({ length: 9 }, (_, index) => ({ ...data.hotspots!.clusters![0], cluster: index, patient_count: index === 8 ? null : 20, suppressed: index === 8, stations: index === 8 ? [] : data.hotspots!.clusters![0].stations }));
      return json(route, result);
    }
    if (path === "/api/v1/admin/analytics/ml/runs/" && request.method() === "POST") {
      state.writes.push(request.postDataJSON()); expect(request.headers()["x-csrftoken"]).toBe("ml-test-csrf");
      return json(route, { ...run, id: "new-run", filters: request.postDataJSON(), status: "queued", report: null, finished_at: null, message: "Waiting to compare methods." }, 202);
    }
    if (path === "/api/v1/admin/analytics/ml/runs/new-run/") {
      state.polls++;
      return json(route, { ...run, id: "new-run", filters: state.writes[0], status: options.failure ? "failed" : "completed", message: options.failure ? "Training did not finish. The previous successful model remains available." : "A new comparison is ready.", error: options.failure ? "Worker temporarily unavailable." : null });
    }
    state.unexpected.push(`${request.method()} ${path}`); return json(route, { detail: "Unexpected API request blocked by isolated ML test." }, 501);
  });
  return state;
}

test.use({ reducedMotion: "reduce" });

test("the separate admin page defaults to all history and sends applied filters to every insight", async ({ page }) => {
  const state = await mockML(page);
  await page.goto("/admin/ml");
  const area = page.getByTestId("admin-ml");
  await expect(area.getByRole("heading", { name: "How to read this page" })).toBeVisible();
  await expect(area.getByLabel("From date", { exact: true })).toHaveValue("");
  await expect(area.getByLabel("Through date", { exact: true })).toHaveValue("");
  await expect(area.getByRole("heading", { name: /Best method in the practice tests/ })).toBeVisible();
  expect(state.requests.some(query => query.includes("dataset_id=mumbai_stations_v1") && !query.includes("date_"))).toBeTruthy();
  expect(state.writes).toHaveLength(0);
  await area.getByLabel("From date", { exact: true }).fill("2025-01-01");
  await area.getByLabel("Through date", { exact: true }).fill("2026-09-30");
  await area.getByRole("combobox", { name: "Condition", exact: true }).selectOption("HYPERTENSION");
  await area.getByRole("combobox", { name: "Rail line", exact: true }).selectOption("Central");
  await area.getByRole("combobox", { name: "Station area", exact: true }).selectOption("KURLA");
  await expect(area.getByRole("button", { name: "Retrain with new data", exact: true })).toBeDisabled();
  await area.getByRole("button", { name: "Apply filters", exact: true }).click();
  await expect.poll(() => state.requests.some(query => query.includes("date_from=2025-01-01") && query.includes("date_to=2026-09-30") && query.includes("station_id=KURLA") && query.includes("disease_code=HYPERTENSION"))).toBeTruthy();
  await expect(area.getByRole("button", { name: "Retrain with new data", exact: true })).toBeEnabled();
  await expect(area.getByText(/Changing the exploration filters does not recalculate this saved comparison/)).toBeVisible();
  await area.getByRole("button", { name: "All history", exact: true }).click();
  await expect(area.getByLabel("From date", { exact: true })).toHaveValue("");
  await expect.poll(() => state.requests.at(-1)?.includes("station_id=KURLA") && !state.requests.at(-1)?.includes("date_")).toBeTruthy();
  expect(state.unexpected).toEqual([]); expect(state.pageErrors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  if ((page.viewportSize()?.width || 1000) <= 640) {
    await page.evaluate(() => window.scrollTo({ top: 900, behavior: "instant" }));
    await expect.poll(() => page.evaluate(() => {
      const nav = document.querySelector(".sidebar")!.getBoundingClientRect();
      const header = document.querySelector(".topbar")!.getBoundingClientRect();
      return header.top >= nav.bottom - 1;
    })).toBeTruthy();
  }
});

test("model comparison reports real metrics and preserves the previous model after failed retraining", async ({ page }) => {
  const state = await mockML(page, { failure: true });
  await page.goto("/admin/ml");
  const area = page.getByTestId("admin-ml");
  await expect(area.getByRole("heading", { name: /Best method in the practice tests/ })).toContainText("Many sets of decisions");
  await expect(area.getByRole("columnheader", { name: "Higher readings found" })).toBeVisible();
  await expect(area.getByText("8.0 point drop", { exact: true })).toBeVisible();
  await expect(area.getByText("No demonstrated contribution", { exact: true })).toBeVisible();
  await area.getByText("See correct and incorrect final-test results", { exact: true }).click();
  await expect(area.getByRole("cell", { name: "10 missed readings", exact: true })).toBeVisible();
  await area.getByRole("button", { name: "Retrain with new data", exact: true }).click();
  await expect(area.getByRole("button", { name: "Training in progress", exact: true })).toBeDisabled();
  await expect(area.getByText("Training did not finish. The previous successful model remains available.", { exact: true })).toBeVisible();
  await expect(area.getByRole("heading", { name: /Best method in the practice tests/ })).toBeVisible();
  await expect(area.getByRole("button", { name: "Retrain with new data", exact: true })).toBeEnabled();
  expect(state.writes).toEqual([filters]); expect(state.polls).toBeGreaterThan(0);
  expect(state.unexpected).toEqual([]); expect(state.pageErrors).toEqual([]);
});

test("small groups and confusion counts remain hidden without fabricated estimates", async ({ page }) => {
  const state = await mockML(page, { suppressed: true });
  await page.goto("/admin/ml");
  const area = page.getByTestId("admin-ml");
  await expect(area.getByText("Small result groups are hidden.", { exact: true })).toBeVisible();
  await area.getByText("See correct and incorrect final-test results", { exact: true }).click();
  await expect(area.getByText("These counts are hidden because at least one result group is too small.", { exact: true })).toBeVisible();
  await expect(area.getByText("This group is too small to display its measurements or conditions.", { exact: true })).toBeVisible();
  await expect(area.getByRole("cell", { name: /missed readings/ })).toHaveCount(0);
  expect(state.pageErrors).toEqual([]); expect(state.writes).toHaveLength(0);
});

test("empty and insufficient data states never start training or show a fake score", async ({ page }) => {
  const state = await mockML(page, { unavailable: true });
  await page.goto("/admin/ml");
  const area = page.getByTestId("admin-ml");
  await expect(area.getByRole("heading", { name: "Estimates are not available", exact: true })).toBeVisible();
  await expect(area.getByText("No model has been trained.", { exact: true })).toBeVisible();
  await expect(area.getByRole("heading", { name: "No completed comparison yet", exact: true })).toBeVisible();
  await expect(area.getByRole("heading", { name: "More measurements needed", exact: true })).toBeVisible();
  expect(state.writes).toHaveLength(0); expect(state.pageErrors).toEqual([]);
});

test("no dataset shows a clear empty state", async ({ page }) => {
  const state = await mockML(page, { empty: true });
  await page.goto("/admin/ml");
  await expect(page.getByRole("heading", { name: "No ML dataset is available", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retrain with new data", exact: true })).toHaveCount(0);
  expect(state.writes).toHaveLength(0); expect(state.pageErrors).toEqual([]);
});

test("long geographic group lists start compact and all remaining groups can be expanded", async ({ page }) => {
  const state = await mockML(page, { manyGroups: true });
  await page.goto("/admin/ml");
  const area = page.getByTestId("admin-ml");
  const geo = area.locator("section").filter({ has: page.getByRole("heading", { name: "Where recorded conditions are concentrated", exact: true }) });
  await expect(geo.getByRole("heading", { name: /^Nearby recorded cases/ })).toHaveCount(6);
  await expect(geo.getByRole("heading", { name: "Nearby recorded cases 7", exact: true })).not.toBeVisible();
  const summary = geo.getByText("Show remaining 3 groups", { exact: true });
  await summary.focus();
  await page.keyboard.press("Enter");
  await expect(geo.getByRole("heading", { name: /^Nearby recorded cases/ })).toHaveCount(9);
  await expect(geo.getByRole("heading", { name: "Nearby recorded cases 9", exact: true })).toBeVisible();
  await expect(geo.getByText("This group and its location breakdown are hidden because it is too small.", { exact: true })).toBeVisible();
  await summary.click();
  await expect(geo.getByRole("heading", { name: /^Nearby recorded cases/ })).toHaveCount(6);
  expect(state.pageErrors).toEqual([]); expect(state.unexpected).toEqual([]); expect(state.writes).toHaveLength(0);
});

for (const role of ["patient", "doctor", "pharmacist"]) {
  test(`${role} cannot open the admin ML page or trigger its API calls`, async ({ page }) => {
    const state = await mockML(page, { role });
    await page.goto("/admin/ml");
    await expect(page.getByRole("heading", { name: "Administrator access required", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "ML insights", exact: true })).toHaveCount(0);
    expect(state.requests).toHaveLength(0); expect(state.writes).toHaveLength(0); expect(state.pageErrors).toEqual([]);
  });
}

test("admin navigation opens ML as a separate page and returns to existing admin sections", async ({ page }) => {
  const state = await mockML(page);
  await page.goto("/admin/analytics");
  await expect(page.getByRole("heading", { name: "No analytics dataset is available", exact: true })).toBeVisible();
  expect(state.requests).toHaveLength(0);
  await page.getByRole("link", { name: "ML insights", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/ml$/);
  await expect(page.getByTestId("admin-ml")).toBeVisible();
  await expect(page.getByRole("link", { name: "ML insights", exact: true })).toHaveAttribute("aria-current", "location");
  await page.getByRole("link", { name: "Doctor approvals", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/doctors$/);
  await expect(page.locator("#admin-doctors")).toBeInViewport();
  await expect(page.getByTestId("admin-ml")).toHaveCount(0);
  expect(state.pageErrors).toEqual([]); expect(state.unexpected).toEqual([]);
});

test("stale filtered responses cannot replace the all-history selection", async ({ page }) => {
  const state = await mockML(page, { stale: true });
  await page.goto("/admin/ml");
  const area = page.getByTestId("admin-ml");
  await expect(area.getByRole("button", { name: "Retrain with new data", exact: true })).toBeEnabled();
  await area.getByLabel("From date", { exact: true }).fill("2026-01-01");
  await area.getByRole("button", { name: "Apply filters", exact: true }).click();
  await expect.poll(() => state.releases.length).toBe(1);
  await area.getByRole("button", { name: "All history", exact: true }).click();
  state.releases.forEach(resolve => resolve());
  await expect(area.getByLabel("From date", { exact: true })).toHaveValue("");
  await expect(area.getByRole("button", { name: "Retrain with new data", exact: true })).toBeEnabled();
  await expect(area.getByText("777", { exact: true })).toHaveCount(0);
  expect(state.writes).toHaveLength(0); expect(state.pageErrors).toEqual([]);
});
