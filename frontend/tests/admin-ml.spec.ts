import { expect, test, type Page, type Route } from "@playwright/test";
import type { MLCatalog, MLDiseaseReport, MLFilters, MLInsights, MLRun } from "../lib/ml-types";

const filters: MLFilters = { dataset_id: "mumbai_stations_v1", date_from: null, date_to: null, disease_code: "", line: "", station_id: "" };
const tileImage = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGN4+f7VfwAJSQPCaELyDgAAAABJRU5ErkJggg==", "base64");
const catalog: MLCatalog = {
  synthetic: true, suppression_threshold: 5, datasets: [{ dataset_id: filters.dataset_id, as_of: "2026-10-03", observation_start: "2024-01-01" }],
  defaults: filters, diseases: [{ disease_code: "HYPERTENSION", label: "Hypertension" }, { disease_code: "DENGUE", label: "Dengue" }], lines: ["Central", "Western"],
  stations: [{ station_id: "KURLA", station_name: "Kurla", lines: ["Central"], latitude: 19.06, longitude: 72.87 }, { station_id: "ANDHERI", station_name: "Andheri", lines: ["Western"], latitude: 19.12, longitude: 72.85 }],
};
const diseaseReport: MLDiseaseReport = {
  status: "completed", models: [
    { id: "logistic_regression", name: "Logistic Regression", accuracy: .79, balance: .73 },
    { id: "decision_tree", name: "Decision Tree", accuracy: .74, balance: .69 },
    { id: "random_forest", name: "Random Forest", accuracy: .86, balance: .81 },
    { id: "knn", name: "KNN", accuracy: .76, balance: .71 },
  ].map(item => ({ id: item.id, name: item.name, cv: { mean: { accuracy: item.accuracy - .01, macro_f1: item.balance } }, holdout: { accuracy: item.accuracy, macro_f1: item.balance - .01, per_disease_recall: { DENGUE: .88, HYPERTENSION: null } } })),
  selection: { model_id: "random_forest", model_name: "Random Forest", prediction_enabled: true, message: "Synthetic demonstration checks passed." },
  split: { training_patients: 240, holdout_patients: 60 },
  feature_importance: [{ feature: "temperature", label: "Temperature", importance: .15 }, { feature: "symptom_thirst", label: "Thirst", importance: .1 }],
  training_dates: { from: "2024-01-01", through: "2026-09-30" },
  class_labels: [{ code: "DENGUE", label: "Dengue" }, { code: "HYPERTENSION", label: "Hypertension" }],
};
const diseaseRun: MLRun<MLDiseaseReport> = { id: "disease-run", task: "disease", status: "completed", filters, created_at: "2026-10-03T07:00:00Z", started_at: "2026-10-03T07:00:01Z", finished_at: "2026-10-03T07:00:10Z", error: null, message: "Training finished.", report: diseaseReport };
const data: MLInsights = {
  synthetic: true, filters,
  source: { patients: 240, visits: 800, reports: 60, labs: 60, adherence_logs: 365, extracted_reports: 60, unsupported_reports: 0, historically_unavailable_reports: 50, history_start: "2024-01-01", history_end: "2026-09-30", excluded: { missing_geography: 0 } },
  summary: { patients: 240, disease_counts: [{ code: "HYPERTENSION", label: "Hypertension", count: 80 }, { code: "DENGUE", label: "Dengue", count: 160 }], monthly_counts: [{ month: "2024-01", count: 40 }, { month: "2026-09", count: 90 }], stations: [{ station_id: "KURLA", station_name: "Kurla", patient_count: 80 }, { station_id: "ANDHERI", station_name: "Andheri", patient_count: 160 }], station_disease_counts: [{ station_id: "KURLA", station_name: "Kurla", patient_count: 80, diseases: [{ code: "HYPERTENSION", label: "Hypertension", count: 80 }, { code: "DENGUE", label: "Dengue", count: 0 }] }, { station_id: "ANDHERI", station_name: "Andheri", patient_count: 160, diseases: [{ code: "DENGUE", label: "Dengue", count: 160 }, { code: "HYPERTENSION", label: "Hypertension", count: 0 }] }] },
  patient_groups: { status: "completed", eligible_patients: 240, groups: [{ group: 1, label: "Similar readings 1", patient_count: 120, suppressed: false, profile: { systolic: { mean: 125, observations: 120 }, diastolic: { mean: 82, observations: 120 } }, position: { x: -1, y: 1 }, conditions: [{ code: "HYPERTENSION", patient_count: 50 }], explanation: "These patients have similar recorded measurements." }, { group: 2, label: "Similar readings 2", patient_count: 120, suppressed: false, profile: {}, position: { x: 1, y: -1 }, conditions: [], explanation: "These patients have similar recorded measurements." }], silhouette: .21 },
  hotspots: { counts: { eligible_patients: 240, with_coordinates: 240, missing_coordinates: 0, clustered_patients: 240, noise_patients: 0, cluster_count: 1 }, clusters: [{ cluster: 0, patient_count: 240, suppressed: false, centroid: { latitude: 19.09, longitude: 72.86 }, bounds: { south: 19.06, north: 19.12, west: 72.85, east: 72.87 }, stations: [{ station_id: "KURLA", station_name: "Kurla", patient_count: 80, suppressed: false }, { station_id: "ANDHERI", station_name: "Andheri", patient_count: 160, suppressed: false }] }], notes: [] },
  notes: ["No individual patient identities are returned."],
  disease: { model: diseaseRun, training: null, source: { patients: 240, visits: 800 }, prediction: { prediction_enabled: true, reason: "Synthetic demonstration checks passed.", counts: [{ code: "DENGUE", label: "Dengue", count: 80 }, { code: "HYPERTENSION", label: "Hypertension", count: 160 }] } },
};

async function mockML(page: Page, options: { role?: string; empty?: boolean; unavailable?: boolean; suppressed?: boolean; failure?: boolean; stale?: boolean; manyGroups?: boolean; diseaseGateFailed?: boolean; diseaseInsufficient?: boolean; tileFailure?: boolean; mapSuppressed?: boolean; smallUnsuppressedCount?: boolean; fullHistory?: boolean; delayInitial?: boolean } = {}) {
  const state = { requests: [] as string[], writes: [] as (MLFilters & { task?: string })[], polls: 0, pageErrors: [] as string[], unexpected: [] as string[], tileRequests: [] as string[], releases: [] as (() => void)[] };
  page.on("pageerror", error => state.pageErrors.push(error.message));
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  // Tile-service availability is checked separately. These UI tests never
  // request repeated real map tiles or send any fixture data to a third party.
  await page.route(/^https:\/\/(?:[^/]+\.)?tile\.openstreetmap\.org\//, route => {
    state.tileRequests.push(route.request().url());
    return options.tileFailure ? route.abort("failed") : route.fulfill({ status: 200, contentType: "image/png", body: tileImage });
  });
  // All API requests are mocked so tests cannot access or mutate patient data.
  await page.route("**/api/v1/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    if (path === "/api/v1/auth/me/") return json(route, { user: { id: "ml-ui-admin", account_id: "A-TESTML", name: "Course Administrator", email: "admin@example.test", role: options.role || "admin", email_verified: true } });
    if (path === "/api/v1/auth/csrf/") return json(route, { csrfToken: "ml-test-csrf" });
    if (["/api/v1/auth/sessions/", "/api/v1/admin/audit/", "/api/v1/admin/provider-applications/"].includes(path)) return json(route, { results: [], next: null });
    if (path === "/api/v1/admin/analytics/ml/catalog/") { state.requests.push(url.search); return json(route, options.empty ? { ...catalog, datasets: [] } : catalog); }
    if (path === "/api/v1/admin/analytics/ml/insights/") {
      state.requests.push(url.search);
      const currentFilters = { ...filters, ...Object.fromEntries(url.searchParams) };
      const result = structuredClone(data);
      result.filters = currentFilters;
      if (options.delayInitial) await new Promise<void>(resolve => state.releases.push(resolve));
      if (options.fullHistory) {
        const conditions = ["Dengue", "Influenza", "Hypertension", "Type 2 diabetes", "Asthma", "Anemia", "Gastroenteritis", "Hypothyroidism", "Osteoarthritis", "Malaria"];
        result.summary.disease_counts = conditions.map((label, index) => ({ code: label === "Type 2 diabetes" ? "TYPE2_DIABETES" : label.toUpperCase(), label, count: 110 + index }));
        result.summary.monthly_counts = Array.from({ length: 33 }, (_, month) => ({ month: `${2024 + Math.floor(month / 12)}-${String(month % 12 + 1).padStart(2, "0")}`, count: 120 + month }));
      }
      if (url.searchParams.has("date_from")) result.source.patients = 60;
      if (url.searchParams.get("disease_codes")) {
        result.source.patients = 70; result.source.visits = 130;
        result.summary.disease_counts = [{ code: "DENGUE", label: "Dengue", count: 20 }, { code: "HYPERTENSION", label: "Hypertension", count: 50 }];
        result.summary.station_disease_counts = [{ station_id: "KURLA", station_name: "Kurla", patient_count: 70, diseases: [{ code: "DENGUE", label: "Dengue", count: 0 }, { code: "HYPERTENSION", label: "Hypertension", count: null }] }];
        result.summary.stations = [{ station_id: "KURLA", station_name: "Kurla", patient_count: 70 }];
        result.disease!.source = { patients: 70, visits: 130 };
        result.disease!.prediction.counts = [{ code: "DENGUE", label: "Dengue", count: 20 }, { code: "HYPERTENSION", label: "Hypertension", count: 50 }];
      }
      if (url.searchParams.get("station_id") === "ANDHERI") {
        result.summary.stations = result.summary.stations.filter(station => station.station_id === "ANDHERI");
        result.summary.station_disease_counts = result.summary.station_disease_counts?.filter(station => station.station_id === "ANDHERI");
        result.source.patients = 160;
        result.disease!.source.patients = 160;
        result.hotspots!.clusters = [];
        result.hotspots!.counts = { ...result.hotspots!.counts!, eligible_patients: 160, with_coordinates: 160, clustered_patients: 0, noise_patients: 160, cluster_count: 0 };
      }
      if (options.stale && url.searchParams.get("date_from") === "2026-01-01") { await new Promise<void>(resolve => state.releases.push(resolve)); result.source.patients = 777; }
      if (options.unavailable) { result.disease!.model = null; result.disease!.prediction = { prediction_enabled: false, counts: null, reason: "No disease model has been trained." }; result.patient_groups = { status: "insufficient_data", groups: [], reason: "At least 30 patients with usable measurements are needed." }; }
      if (options.suppressed) result.patient_groups.groups = [{ ...result.patient_groups.groups[0], patient_count: null, suppressed: true, profile: {}, position: null, conditions: [] }];
      if (options.suppressed) result.disease!.prediction.counts = result.disease!.prediction.counts!.map(item => ({ ...item, count: null }));
      if (options.manyGroups) result.hotspots!.clusters = Array.from({ length: 9 }, (_, index) => ({ ...data.hotspots!.clusters![0], cluster: index, patient_count: index === 8 ? null : 20, suppressed: index === 8, centroid: index === 8 ? null : data.hotspots!.clusters![0].centroid, bounds: index === 8 ? null : data.hotspots!.clusters![0].bounds, stations: index === 8 ? [] : data.hotspots!.clusters![0].stations }));
      if (options.mapSuppressed) {
        result.summary.stations[0] = { ...result.summary.stations[0], patient_count: null, suppressed: true };
        result.summary.station_disease_counts![0] = { ...result.summary.station_disease_counts![0], patient_count: null, diseases: [{ code: "HYPERTENSION", label: "Hypertension", count: null }, { code: "DENGUE", label: "Dengue", count: 0 }] };
        result.hotspots!.clusters = [{ cluster: 8, patient_count: null, suppressed: true, centroid: null, bounds: null, stations: [] }];
      }
      // Defend against older or malformed responses that omit suppression flags.
      if (options.smallUnsuppressedCount) {
        result.summary.stations[0] = { ...result.summary.stations[0], patient_count: 3, suppressed: false };
        result.summary.station_disease_counts![0].patient_count = 3;
        result.summary.station_disease_counts![0].diseases[0].count = 3;
        result.hotspots!.clusters = [{ ...data.hotspots!.clusters![0], cluster: 8, patient_count: 3, suppressed: false }];
      }
      if (options.diseaseGateFailed) result.disease!.prediction = { prediction_enabled: false, counts: [], reason: "The method did not pass the comparison checks." };
      result.summary.patients = result.source.patients;
      return json(route, result);
    }
    if (path === "/api/v1/admin/analytics/ml/runs/" && request.method() === "POST") {
      state.writes.push(request.postDataJSON()); expect(request.headers()["x-csrftoken"]).toBe("ml-test-csrf");
      expect(request.postDataJSON().task).toBe("disease");
      return json(route, { ...diseaseRun, id: "new-disease-run", filters: request.postDataJSON(), status: "queued", report: null, finished_at: null, message: "Waiting to compare methods." }, 202);
    }
    if (path === "/api/v1/admin/analytics/ml/runs/new-disease-run/") {
      state.polls++;
      if (options.diseaseInsufficient) return json(route, { ...diseaseRun, id: "new-disease-run", filters: state.writes[0], status: "insufficient_data", message: "More usable records are needed.", report: { ...diseaseReport, status: "insufficient_data", models: [], selection: null, reason: "Selected records cover only one disease." } });
      return json(route, { ...diseaseRun, id: "new-disease-run", filters: state.writes[0], status: options.failure ? "failed" : "completed", message: options.failure ? "Disease training failed. The previous comparison is preserved." : "Disease comparison is ready.", error: options.failure ? "Worker unavailable." : null });
    }
    state.unexpected.push(`${request.method()} ${path}`); return json(route, { detail: "Unexpected API request blocked by isolated ML test." }, 501);
  });
  return state;
}

test.use({ reducedMotion: "reduce" });

test("the ML section defaults to all history and sends applied filters to every insight", async ({ page }) => {
  const state = await mockML(page);
  await page.goto("/admin/ml");
  const area = page.getByTestId("admin-ml");
  await expect(area.getByRole("heading", { name: "How to read this page" })).toHaveCount(0);
  await expect(area.getByRole("heading", { name: "Patterns that help you understand care." })).toHaveCount(0);
  const recordFilters = area.getByTestId("ml-record-filters");
  await expect(recordFilters.getByRole("heading", { name: "Record filters", exact: true })).toBeVisible();
  await expect(recordFilters.getByRole("button", { name: "Apply filters", exact: true })).toBeVisible();
  await expect(area.getByLabel("From date", { exact: true })).toHaveValue("");
  await expect(area.getByLabel("Through date", { exact: true })).toHaveValue("");
  await expect(area.getByText("Best in practice tests", { exact: true })).toBeVisible();
  expect(state.requests.some(query => query.includes("dataset_id=mumbai_stations_v1") && !query.includes("date_"))).toBeTruthy();
  expect(state.writes).toHaveLength(0);
  await area.getByLabel("From date", { exact: true }).fill("2025-01-01");
  await area.getByLabel("Through date", { exact: true }).fill("2026-09-30");
  await area.getByRole("button", { name: "Conditions All conditions", exact: true }).click();
  await area.getByRole("checkbox", { name: "Hypertension", exact: true }).check();
  await area.getByRole("button", { name: "Done", exact: true }).click();
  await area.getByRole("combobox", { name: "Rail line", exact: true }).selectOption("Central");
  await area.getByRole("combobox", { name: "Station area", exact: true }).selectOption("KURLA");
  await expect(area.getByRole("button", { name: "Retrain disease models", exact: true })).toBeDisabled();
  await area.getByRole("button", { name: "Apply filters", exact: true }).click();
  await expect.poll(() => state.requests.some(query => query.includes("date_from=2025-01-01") && query.includes("date_to=2026-09-30") && query.includes("station_id=KURLA") && query.includes("disease_codes=HYPERTENSION"))).toBeTruthy();
  await expect(area.getByRole("button", { name: "Retrain disease models", exact: true })).toBeEnabled();
  await expect(area.getByText("Fixed model evaluation. Exploration filters do not change these results.", { exact: true })).toBeVisible();
  await area.getByRole("button", { name: "All history", exact: true }).click();
  await expect(area.getByLabel("From date", { exact: true })).toHaveValue("");
  await expect.poll(() => state.requests.at(-1)?.includes("station_id=KURLA") && !state.requests.at(-1)?.includes("date_")).toBeTruthy();
  expect(state.unexpected).toEqual([]); expect(state.pageErrors).toEqual([]);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
  if ((page.viewportSize()?.width || 1000) <= 640) {
    await page.evaluate(() => window.scrollTo({ top: 900, behavior: "instant" }));
    await expect.poll(() => page.evaluate(() => {
      const nav = document.querySelector(".sidebar")!.getBoundingClientRect();
      const header = document.querySelector(".topbar")!.getBoundingClientRect();
      return header.top >= nav.bottom - 1;
    })).toBeTruthy();
  }
});

test("ML insights has no blood-pressure prediction or training controls", async ({ page }) => {
  const state = await mockML(page);
  await page.goto("/admin/ml");
  const area = page.getByTestId("admin-ml");
  await expect(area.getByRole("heading", { name: "Disease prediction", exact: true })).toBeVisible();
  await expect(area.getByText("Blood pressure prediction and training", { exact: true })).toHaveCount(0);
  await expect(area.getByRole("heading", { name: "Estimated next-visit blood pressure", exact: true })).toHaveCount(0);
  await expect(area.getByRole("button", { name: "Retrain with new data", exact: true })).toHaveCount(0);
  await expect(area.getByRole("button", { name: "Retrain disease models", exact: true })).toHaveCount(1);
  await expect(area.getByRole("heading", { name: "Patients with similar measurements", exact: true })).toBeVisible();
  await expect(area.getByText("Average upper bp reading", { exact: true })).toBeVisible();
  await expect(area.getByText("125 mmHg", { exact: true })).toBeVisible();
  expect(state.writes).toHaveLength(0); expect(state.polls).toBe(0);
  expect(state.unexpected).toEqual([]); expect(state.pageErrors).toEqual([]);
});

test("small groups and disease prediction counts remain hidden without fabricated estimates", async ({ page }) => {
  const state = await mockML(page, { suppressed: true });
  await page.goto("/admin/ml");
  const area = page.getByTestId("admin-ml");
  await expect(area.getByText("This group is too small to display its measurements or conditions.", { exact: true })).toBeVisible();
  await expect(area.getByRole("region", { name: "Predictions for selected patients", exact: true }).getByText("Hidden", { exact: true })).toHaveCount(2);
  expect(state.pageErrors).toEqual([]); expect(state.writes).toHaveLength(0);
});

test("empty and insufficient data states never start training or show a fake score", async ({ page }) => {
  const state = await mockML(page, { unavailable: true });
  await page.goto("/admin/ml");
  const area = page.getByTestId("admin-ml");
  await expect(area.getByText("Estimates are not available", { exact: true })).toBeVisible();
  await expect(area.getByRole("status").getByText("No disease model has been trained.", { exact: true })).toBeVisible();
  await expect(area.getByText("No completed disease comparison yet.", { exact: true })).toBeVisible();
  await expect(area.getByRole("heading", { name: "More measurements needed", exact: true })).toBeVisible();
  expect(state.writes).toHaveLength(0); expect(state.pageErrors).toEqual([]);
});

test("no dataset shows a clear empty state", async ({ page }) => {
  const state = await mockML(page, { empty: true });
  await page.goto("/admin/ml");
  await expect(page.getByRole("heading", { name: "No ML dataset is available", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retrain disease models", exact: true })).toHaveCount(0);
  expect(state.writes).toHaveLength(0); expect(state.pageErrors).toEqual([]);
});

test("long geographic group lists start compact and all remaining groups can be expanded", async ({ page }) => {
  const state = await mockML(page, { manyGroups: true });
  await page.goto("/admin/ml");
  const geo = page.getByTestId("admin-geography");
  await expect(geo.locator('[data-testid^="nearby-group-"]:visible')).toHaveCount(6);
  await expect(geo.getByTestId("nearby-group-6")).not.toBeVisible();
  const summary = geo.getByText("Show remaining 3 groups", { exact: true });
  await summary.focus();
  await page.keyboard.press("Enter");
  await expect(geo.locator('[data-testid^="nearby-group-"]:visible')).toHaveCount(9);
  await expect(geo.getByTestId("nearby-group-8")).toBeVisible();
  await expect(geo.getByTestId("select-group-8")).toHaveCount(0);
  await summary.click();
  await expect(geo.locator('[data-testid^="nearby-group-"]:visible')).toHaveCount(6);
  expect(state.pageErrors).toEqual([]); expect(state.unexpected).toEqual([]); expect(state.writes).toHaveLength(0);
});

test("Mumbai map attribution and station markers open the recorded station details", async ({ page }) => {
  const state = await mockML(page);
  await page.goto("/admin/ml");
  const geo = page.getByTestId("admin-geography");
  await expect(geo.getByRole("region", { name: "Interactive Mumbai station map", exact: true })).toBeVisible();
  await expect(geo.getByRole("link", { name: "OpenStreetMap contributors", exact: true })).toHaveAttribute("href", /openstreetmap\.org\/copyright/);
  const marker = geo.getByRole("button", { name: "Select Kurla: 80 recorded patients", exact: true });
  await marker.focus();
  await page.keyboard.press("Enter");
  const details = geo.getByTestId("selected-station");
  await expect(details.getByRole("heading", { name: "Kurla", exact: true })).toBeVisible();
  await expect(details.getByText("80", { exact: true }).first()).toBeVisible();
  await expect(details.getByText("Recorded conditions at this station", { exact: true })).toBeVisible();
  await expect(details.getByText("Hypertension", { exact: true })).toBeVisible();
  await expect(details.getByText("0", { exact: true })).toBeVisible();
  await geo.getByRole("button", { name: "Clear map selection", exact: true }).click();
  await expect(details.getByRole("heading", { name: "Choose a station", exact: true })).toBeVisible();
  await marker.focus();
  await page.keyboard.press("Space");
  await expect(details.getByRole("heading", { name: "Kurla", exact: true })).toBeVisible();
  if (test.info().project.name === "mobile") {
    await geo.getByRole("button", { name: "Clear map selection", exact: true }).click();
    await marker.tap();
    await expect(details.getByRole("heading", { name: "Kurla", exact: true })).toBeVisible();
  }
  await expect.poll(() => state.tileRequests.length).toBeGreaterThan(0);
  expect(state.tileRequests.every(url => /^https:\/\/(?:[^/]+\.)?tile\.openstreetmap\.org\/\d+\/\d+\/\d+\.png$/.test(url))).toBeTruthy();
  expect(state.writes).toHaveLength(0); expect(state.unexpected).toEqual([]); expect(state.pageErrors).toEqual([]);
});

test("nearby groups can be selected from the map and station list remains usable", async ({ page }) => {
  const state = await mockML(page);
  await page.goto("/admin/ml");
  const geo = page.getByTestId("admin-geography");
  const groupsToggle = geo.getByRole("button", { name: "Nearby groups", exact: true });
  if (await groupsToggle.getAttribute("aria-pressed") !== "true") await groupsToggle.click();
  await geo.getByRole("button", { name: "Select nearby group 1: 240 recorded patients", exact: true }).click();
  await expect(geo.getByTestId("nearby-group-0")).toBeVisible();
  await expect(geo.getByTestId("select-group-0")).toHaveAttribute("aria-pressed", "true");
  await geo.getByRole("button", { name: "Stations", exact: true }).click();
  await expect(geo.getByTestId("select-group-0")).toHaveAttribute("aria-pressed", "false");
  await expect(geo.getByTestId("selected-station").getByRole("heading", { name: "Choose a station", exact: true })).toBeVisible();
  await geo.getByTestId("select-group-0").click();
  await expect(groupsToggle).toHaveAttribute("aria-pressed", "true");
  await expect(geo.getByTestId("select-group-0")).toHaveAttribute("aria-pressed", "true");
  await geo.getByRole("region", { name: "Conditions by station area", exact: true }).getByRole("button", { name: "View Andheri station details", exact: true }).click();
  await expect(geo.getByTestId("selected-station").getByRole("heading", { name: "Andheri", exact: true })).toBeVisible();
  await expect(geo.getByTestId("selected-station").getByText("Dengue", { exact: true })).toBeVisible();
  await groupsToggle.click();
  await expect(geo.getByTestId("selected-station").getByRole("heading", { name: "Choose a station", exact: true })).toBeVisible();
  await geo.getByRole("region", { name: "Conditions by station area", exact: true }).getByRole("button", { name: "View Andheri station details", exact: true }).click();
  await expect(geo.getByRole("button", { name: "Stations", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(geo.getByTestId("selected-station").getByRole("heading", { name: "Andheri", exact: true })).toBeVisible();
  expect(state.writes).toHaveLength(0); expect(state.unexpected).toEqual([]); expect(state.pageErrors).toEqual([]);
});

test("map fitting restores visible station locations after zooming", async ({ page }) => {
  const state = await mockML(page);
  await page.goto("/admin/ml");
  const geo = page.getByTestId("admin-geography");
  const map = geo.getByRole("region", { name: "Interactive Mumbai station map", exact: true });
  const markers = [geo.getByRole("button", { name: "Select Kurla: 80 recorded patients", exact: true }), geo.getByRole("button", { name: "Select Andheri: 160 recorded patients", exact: true })];
  const locationsFit = async () => {
    const box = await map.boundingBox();
    const locations = await Promise.all(markers.map(marker => marker.boundingBox()));
    return !!box && locations.every(location => !!location && location.x + location.width / 2 >= box.x && location.x + location.width / 2 <= box.x + box.width && location.y + location.height / 2 >= box.y && location.y + location.height / 2 <= box.y + box.height);
  };
  await expect(markers[0]).toBeVisible();
  await expect.poll(locationsFit).toBeTruthy();
  const initialViewport = page.viewportSize()!;
  await page.setViewportSize({ width: initialViewport.width > 640 ? 1024 : 430, height: initialViewport.height });
  await expect.poll(locationsFit).toBeTruthy();
  await page.setViewportSize(initialViewport);
  await expect.poll(locationsFit).toBeTruthy();
  await geo.getByRole("button", { name: "Fit visible locations", exact: true }).click();
  await expect.poll(locationsFit).toBeTruthy();
  for (let step = 0; step < 4; step++) await geo.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect.poll(locationsFit).toBeFalsy();
  await geo.getByRole("button", { name: "Fit visible locations", exact: true }).click();
  await expect.poll(locationsFit).toBeTruthy();
  await geo.getByRole("button", { name: "Reset Mumbai view", exact: true }).click();
  await expect(map).toBeVisible();
  expect(state.pageErrors).toEqual([]); expect(state.writes).toHaveLength(0);
});

test("applying station filters clears the previous map selection", async ({ page }) => {
  const state = await mockML(page);
  await page.goto("/admin/ml");
  const geo = page.getByTestId("admin-geography");
  await geo.getByRole("button", { name: "Select Kurla: 80 recorded patients", exact: true }).click();
  await expect(geo.getByTestId("selected-station").getByRole("heading", { name: "Kurla", exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "Station area", exact: true }).selectOption("ANDHERI");
  await page.getByRole("button", { name: "Apply filters", exact: true }).click();
  await expect.poll(() => state.requests.some(query => new URLSearchParams(query).get("station_id") === "ANDHERI")).toBeTruthy();
  await expect(geo.getByTestId("selected-station").getByRole("heading", { name: "Choose a station", exact: true })).toBeVisible();
  await expect(geo.getByRole("button", { name: /Select Kurla:/ })).toHaveCount(0);
  await expect(geo.getByRole("button", { name: "Select Andheri: 160 recorded patients", exact: true })).toBeVisible();
  expect(state.pageErrors).toEqual([]); expect(state.writes).toHaveLength(0); expect(state.unexpected).toEqual([]);
});

for (const smallUnsuppressedCount of [false, true]) {
test(`suppressed nearby groups reveal no location and public stations retain hidden counts (${smallUnsuppressedCount ? "missing suppression flag" : "suppressed response"})`, async ({ page }) => {
  const state = await mockML(page, { mapSuppressed: true, smallUnsuppressedCount });
  await page.goto("/admin/ml");
  const geo = page.getByTestId("admin-geography");
  await geo.getByRole("button", { name: "Nearby groups", exact: true }).click();
  await expect(geo.getByText("No nearby groups have locations that can be shown for this selection.", { exact: true })).toBeVisible();
  await expect(geo.getByRole("button", { name: /Select nearby group/ })).toHaveCount(0);
  await expect(geo.getByTestId("select-group-8")).toHaveCount(0);
  await geo.getByRole("button", { name: "Stations", exact: true }).click();
  await geo.getByRole("button", { name: "Select Kurla: small count hidden", exact: true }).click();
  const details = geo.getByTestId("selected-station");
  await expect(details.getByRole("heading", { name: "Kurla", exact: true })).toBeVisible();
  await expect(details.getByText("Hidden", { exact: true }).first()).toBeVisible();
  await expect(details.getByText("0", { exact: true })).toHaveCount(0);
  await expect(details.getByText("80", { exact: true })).toHaveCount(0);
  await expect(geo.getByTestId("nearby-group-8").getByText(/19\.|72\.|Kurla|Andheri/)).toHaveCount(0);
  expect(state.pageErrors).toEqual([]); expect(state.writes).toHaveLength(0); expect(state.unexpected).toEqual([]);
});
}

test("failed map tiles preserve station counts and selection controls", async ({ page }) => {
  const state = await mockML(page, { tileFailure: true });
  await page.goto("/admin/ml");
  const geo = page.getByTestId("admin-geography");
  await expect(geo.getByText("Map tiles could not load. Station markers and area details are still available.", { exact: true })).toBeVisible();
  await expect(geo.getByRole("heading", { name: "Conditions by station area", exact: true })).toBeVisible();
  await geo.getByRole("region", { name: "Conditions by station area", exact: true }).getByRole("button", { name: "View Kurla station details", exact: true }).click();
  await expect(geo.getByTestId("selected-station").getByRole("heading", { name: "Kurla", exact: true })).toBeVisible();
  await expect.poll(() => state.tileRequests.length).toBeGreaterThan(0);
  expect(state.pageErrors).toEqual([]); expect(state.writes).toHaveLength(0); expect(state.unexpected).toEqual([]);
});

test("map, station details and controls fit the viewport", async ({ page }) => {
  const state = await mockML(page, { fullHistory: true });
  await page.goto("/admin/ml");
  const geo = page.getByTestId("admin-geography");
  await expect(geo.getByRole("region", { name: "Interactive Mumbai station map", exact: true })).toBeVisible();
  await geo.getByRole("region", { name: "Conditions by station area", exact: true }).getByRole("button", { name: "View Kurla station details", exact: true }).click();
  await expect(geo.getByTestId("selected-station").getByRole("heading", { name: "Kurla", exact: true })).toBeVisible();
  await expect.poll(async () => {
    const mapBox = await geo.getByRole("region", { name: "Interactive Mumbai station map", exact: true }).boundingBox();
    const markerBox = await geo.getByRole("button", { name: "Select Kurla: 80 recorded patients", exact: true }).boundingBox();
    return mapBox && markerBox ? Math.hypot(markerBox.x + markerBox.width / 2 - mapBox.x - mapBox.width / 2, markerBox.y + markerBox.height / 2 - mapBox.y - mapBox.height / 2) : Infinity;
  }).toBeLessThan(4);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
  const map = await geo.getByRole("region", { name: "Interactive Mumbai station map", exact: true }).boundingBox();
  expect(map).not.toBeNull();
  expect(map!.width).toBeGreaterThan(200);
  expect(map!.height).toBeGreaterThan(200);
  expect(map!.x).toBeGreaterThanOrEqual(0);
  expect(map!.x + map!.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
  await page.mouse.move(0, 0);
  await geo.screenshot({ path: test.info().outputPath("mumbai-map-workspace.png"), style: ".topbar { visibility: hidden; }" });
  expect(state.pageErrors).toEqual([]); expect(state.writes).toHaveLength(0); expect(state.unexpected).toEqual([]);
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

test("admin navigation keeps ML filters mounted while scrolling to approvals and using browser history", async ({ page }) => {
  const state = await mockML(page);
  await page.goto("/admin/ml");
  await expect(page).toHaveURL(/\/admin\/ml$/);
  const area = page.getByTestId("admin-ml");
  await expect(area.getByText("Best in practice tests", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "ML insights", exact: true })).toHaveAttribute("aria-current", "location");
  await area.getByLabel("From date", { exact: true }).fill("2025-01-01");
  const initialRequestCount = state.requests.length;
  await page.getByRole("link", { name: "Doctor approvals", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/doctors$/);
  await expect(page.locator("#admin-doctors")).toBeInViewport();
  await expect(area).toHaveCount(1);
  await page.getByRole("link", { name: "Pharmacist approvals", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/pharmacists$/);
  await expect(page.locator("#admin-pharmacists")).toBeInViewport();
  await page.goBack();
  await expect(page).toHaveURL(/\/admin\/doctors$/);
  await expect(page.locator("#admin-doctors")).toBeInViewport();
  await page.goBack();
  await expect(page).toHaveURL(/\/admin\/ml$/);
  await expect(page.locator("#admin-ml-title")).toBeInViewport();
  await expect(area.getByLabel("From date", { exact: true })).toHaveValue("2025-01-01");
  await page.goForward();
  await expect(page).toHaveURL(/\/admin\/doctors$/);
  await expect(page.locator("#admin-doctors")).toBeInViewport();
  expect(state.requests).toHaveLength(initialRequestCount);
  expect(state.pageErrors).toEqual([]); expect(state.unexpected).toEqual([]);
});

test("an approval deep link stays aligned when the ML results above finish loading", async ({ page }) => {
  const state = await mockML(page, { delayInitial: true });
  await page.goto("/admin/doctors");
  await expect(page.locator("#admin-doctors-title")).toBeInViewport();
  await expect.poll(() => state.releases.length).toBeGreaterThan(0);
  state.releases.forEach(release => release());
  await expect(page.getByTestId("admin-ml").getByText("Best in practice tests", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/admin\/doctors$/);
  await expect(page.locator("#admin-doctors-title")).toBeInViewport();
  await expect(page.getByRole("link", { name: "Doctor approvals", exact: true })).toHaveAttribute("aria-current", "location");
  await expect.poll(() => page.locator("#admin-doctors").evaluate(element => {
    const top = element.getBoundingClientRect().top;
    const headerBottom = document.querySelector(".topbar")?.getBoundingClientRect().bottom ?? 0;
    return top >= headerBottom - 2 && top < innerHeight * .65;
  })).toBeTruthy();
  expect(state.pageErrors).toEqual([]); expect(state.unexpected).toEqual([]);
});

test("stale filtered responses cannot replace the all-history selection", async ({ page }) => {
  const state = await mockML(page, { stale: true });
  await page.goto("/admin/ml");
  const area = page.getByTestId("admin-ml");
  await expect(area.getByRole("button", { name: "Retrain disease models", exact: true })).toBeEnabled();
  await area.getByLabel("From date", { exact: true }).fill("2026-01-01");
  await area.getByRole("button", { name: "Apply filters", exact: true }).click();
  await expect.poll(() => state.releases.length).toBe(1);
  await area.getByRole("button", { name: "All history", exact: true }).click();
  state.releases.forEach(resolve => resolve());
  await expect(area.getByLabel("From date", { exact: true })).toHaveValue("");
  await expect(area.getByRole("button", { name: "Retrain disease models", exact: true })).toBeEnabled();
  await expect(area.getByText("777", { exact: true })).toHaveCount(0);
  expect(state.writes).toHaveLength(0); expect(state.pageErrors).toEqual([]);
});

test("disease prediction shows measured comparison bars and evaluation details", async ({ page }) => {
  const state = await mockML(page);
  await page.goto("/admin/ml");
  const disease = page.getByTestId("disease-prediction");
  await expect(disease.getByRole("heading", { name: "Disease prediction", exact: true })).toBeVisible();
  await expect(disease.getByRole("heading", { name: "Can we trust it?", exact: true })).toBeVisible();
  await expect(disease.getByRole("heading", { name: "Saved test results", exact: true })).toBeVisible();
  await expect(disease.getByText("All 10 diseases", { exact: true })).toBeVisible();
  await expect(disease.getByRole("heading", { name: "Algorithms compared", exact: true })).toBeVisible();
  await expect(disease.getByText("The system learns from past patient records to guess which disease a new patient most likely has.", { exact: true })).toBeVisible();
  await expect(disease.getByText("Best in practice tests", { exact: true })).toBeVisible();
  await expect(disease.getByText("86.0%", { exact: true }).first()).toBeVisible();
  const savedResults = disease.getByRole("region", { name: "Saved test results", exact: true });
  await expect(savedResults.getByText("240", { exact: true })).toBeVisible();
  await expect(savedResults.getByText("60", { exact: true })).toBeVisible();
  await expect(disease.getByText("Temperature", { exact: true })).toBeVisible();
  await expect(disease.getByText("15.0 points", { exact: true })).toBeVisible();
  await expect(disease.getByRole("heading", { name: "Predictions for selected patients", exact: true })).toBeVisible();
  await expect(disease.getByText("Current selection", { exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("ml-workspace.png") });
  await disease.screenshot({ path: test.info().outputPath("disease-panel.png") });
  await disease.getByText("Evaluation details", { exact: true }).click();
  await expect(disease.getByRole("columnheader", { name: "Practice balance", exact: true })).toBeVisible();
  await expect(disease.getByRole("heading", { name: "Cases found for each disease", exact: true })).toBeVisible();
  await expect(disease.getByText("88.0%", { exact: true })).toBeVisible();
  await expect(disease.getByText("Hidden", { exact: true })).toBeVisible();
  expect(state.writes).toHaveLength(0); expect(state.pageErrors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test("search supports multiple conditions, shared filtered counts and clearing without changing saved metrics", async ({ page }) => {
  const state = await mockML(page);
  await page.goto("/admin/ml");
  const area = page.getByTestId("admin-ml");
  await area.getByRole("button", { name: "Conditions All conditions", exact: true }).click();
  const search = area.getByRole("textbox", { name: "Search conditions", exact: true });
  await search.fill("deng");
  await area.getByRole("checkbox", { name: "Dengue", exact: true }).check();
  await expect(area.getByRole("checkbox", { name: "Hypertension", exact: true })).toHaveCount(0);
  await search.fill("hyper");
  await area.getByRole("checkbox", { name: "Hypertension", exact: true }).check();
  await area.getByRole("button", { name: "Done", exact: true }).click();
  await expect(area.getByRole("button", { name: "Remove Dengue", exact: true })).toBeVisible();
  await expect(area.getByRole("button", { name: "Retrain disease models", exact: true })).toBeDisabled();
  expect(state.requests.some(query => query.includes("disease_codes="))).toBeFalsy();
  await area.getByRole("button", { name: "Apply filters", exact: true }).click();
  await expect.poll(() => state.requests.some(query => new URLSearchParams(query).get("disease_codes") === "DENGUE,HYPERTENSION")).toBeTruthy();
  await expect(area.getByText("Dengue: 0 · Hypertension: Hidden", { exact: true }).first()).toBeVisible();
  const recorded = area.locator("section").filter({ has: page.getByRole("heading", { name: "Recorded conditions", exact: true }) });
  await expect(recorded.getByText("20", { exact: true })).toBeVisible();
  const disease = page.getByTestId("disease-prediction");
  await expect(area.getByRole("region", { name: "Selected records", exact: true }).getByText("70", { exact: true })).toBeVisible();
  await expect(disease.getByText("86.0%", { exact: true }).first()).toBeVisible();
  await expect(disease.getByRole("heading", { name: "Saved test results", exact: true })).toBeVisible();
  const savedResults = disease.getByRole("region", { name: "Saved test results", exact: true });
  await expect(savedResults.getByText("240", { exact: true })).toBeVisible();
  await expect(savedResults.getByText("60", { exact: true })).toBeVisible();
  const currentPredictions = disease.getByRole("region", { name: "Predictions for selected patients", exact: true });
  await expect(currentPredictions.getByText("20", { exact: true })).toBeVisible();
  await expect(currentPredictions.getByText("Dengue or Hypertension", { exact: true })).toBeVisible();
  await area.getByRole("button", { name: "Clear conditions", exact: true }).click();
  await area.getByRole("button", { name: "Apply filters", exact: true }).click();
  await expect.poll(() => new URLSearchParams(state.requests.at(-1)).has("disease_codes")).toBeFalsy();
  expect(state.pageErrors).toEqual([]); expect(state.writes).toHaveLength(0); expect(state.unexpected).toEqual([]);
});

test("disease estimates stay withheld when quality checks fail", async ({ page }) => {
  const state = await mockML(page, { diseaseGateFailed: true });
  await page.goto("/admin/ml");
  const disease = page.getByTestId("disease-prediction");
  await expect(disease.getByText("More evidence needed", { exact: true })).toBeVisible();
  await expect(disease.getByRole("status").getByText("The method did not pass the comparison checks.", { exact: true })).toBeVisible();
  await expect(disease.getByRole("heading", { name: "Predictions for selected patients", exact: true })).toBeVisible();
  await expect(disease.getByText("80", { exact: true })).toHaveCount(0);
  await expect(disease.getByText("160", { exact: true })).toHaveCount(0);
  await expect(disease.getByText("86.0%", { exact: true }).first()).toBeVisible();
  expect(state.writes).toHaveLength(0); expect(state.pageErrors).toEqual([]);
});

test("disease retraining sends the separate task with CSRF and preserves comparison on failure", async ({ page }) => {
  const state = await mockML(page, { failure: true });
  await page.goto("/admin/ml");
  const disease = page.getByTestId("disease-prediction");
  await disease.getByRole("button", { name: "Retrain disease models", exact: true }).click();
  await expect(disease.getByRole("button", { name: "Disease training in progress", exact: true })).toBeDisabled();
  await expect(disease.getByText("Latest training failed", { exact: true })).toBeVisible();
  await expect(disease.getByText("Disease training failed. The previous comparison is preserved.", { exact: true })).toBeVisible();
  await expect(disease.getByText("86.0%", { exact: true }).first()).toBeVisible();
  await expect(disease.getByRole("button", { name: "Retrain disease models", exact: true })).toBeEnabled();
  expect(state.writes).toEqual([{ ...filters, task: "disease" }]); expect(state.polls).toBeGreaterThan(0);
  expect(state.unexpected).toEqual([]); expect(state.pageErrors).toEqual([]);
});

test("disease training reports insufficient data without hiding the previous comparison", async ({ page }) => {
  const state = await mockML(page, { diseaseInsufficient: true });
  await page.goto("/admin/ml");
  const disease = page.getByTestId("disease-prediction");
  await disease.getByRole("button", { name: "Retrain disease models", exact: true }).click();
  await expect(disease.getByText("Not enough training data", { exact: true })).toBeVisible();
  await expect(disease.getByText("Selected records cover only one disease. Previous model remains available.", { exact: true })).toBeVisible();
  await expect(disease.getByText("Ready for demonstration", { exact: true })).toHaveCount(0);
  await expect(disease.getByText("86.0%", { exact: true }).first()).toBeVisible();
  await expect(disease.getByRole("button", { name: "Retrain disease models", exact: true })).toBeEnabled();
  expect(state.writes).toEqual([{ ...filters, task: "disease" }]);
  expect(state.pageErrors).toEqual([]); expect(state.unexpected).toEqual([]);
});

test("disease retraining completes using only the disease task", async ({ page }) => {
  const state = await mockML(page);
  await page.goto("/admin/ml");
  const disease = page.getByTestId("disease-prediction");
  await disease.getByRole("button", { name: "Retrain disease models", exact: true }).click();
  await expect(disease.getByRole("button", { name: "Disease training in progress", exact: true })).toBeDisabled();
  await expect(disease.getByRole("button", { name: "Retrain disease models", exact: true })).toBeEnabled();
  await expect(disease.getByText("Ready for demonstration", { exact: true })).toBeVisible();
  await expect(disease.getByText("86.0%", { exact: true }).first()).toBeVisible();
  expect(state.writes).toEqual([{ ...filters, task: "disease" }]);
  expect(state.polls).toBeGreaterThan(0); expect(state.requests.length).toBeGreaterThan(2);
  expect(state.unexpected).toEqual([]); expect(state.pageErrors).toEqual([]);
});
