"use client";

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { AlertCircle, CalendarDays, CheckCircle2, ClipboardList, Database, FileText, FlaskConical, HeartPulse, LoaderCircle, MapPin, Pill, RefreshCw, ShieldCheck, SlidersHorizontal, UsersRound } from "lucide-react";
import { api, date, dateTime, message, post } from "@/lib/api";
import type { MLCatalog, MLFilters, MLInsights, MLModelResult, MLPatientGroups, MLReport, MLRun } from "@/lib/ml-types";
import { useQuery } from "./ui";
import { DiseasePrediction } from "./admin-disease";
import { DiseaseFilter } from "./admin-disease-filter";
import styles from "./admin-ml.module.css";

const base = "/admin/analytics/ml";
const count = (value: number | null | undefined) => value == null ? "Hidden / unavailable" : new Intl.NumberFormat("en-IN").format(value);
const percent = (value: number | null | undefined) => value == null ? "Unavailable" : `${(value * 100).toFixed(1)}%`;
const activeRun = (run: MLRun | null | undefined) => !!run && ["queued", "running"].includes(run.status);

function queryString(filters: MLFilters) {
  return new URLSearchParams(Object.entries(filters).filter((entry): entry is [string, string] => typeof entry[1] === "string" && entry[1] !== "")).toString();
}

function period(filters: MLFilters) {
  if (!filters.date_from && !filters.date_to) return "All recorded history";
  return `${filters.date_from ? date(filters.date_from) : "Earliest recorded date"} – ${filters.date_to ? date(filters.date_to) : "Latest recorded date"}`;
}

function filterDescription(filters: MLFilters, catalog: MLCatalog) {
  const codes = (filters.disease_codes || filters.disease_code || "").split(",").filter(Boolean);
  const conditions = codes.map(code => catalog.diseases.find(item => item.disease_code === code)?.label || code).join(" or ");
  return [period(filters), conditions || "All conditions", filters.line || "All lines", catalog.stations.find(item => item.station_id === filters.station_id)?.station_name || "All station areas"].join(" · ");
}

function Panel({ title, eyebrow, explanation, action, children }: { title: string; eyebrow?: string; explanation?: string; action?: ReactNode; children: ReactNode }) {
  return <section className={styles.panel}><div className={styles.panelHead}><div>{eyebrow && <span className={styles.eyebrow}>{eyebrow}</span>}<h2>{title}</h2>{explanation && <p>{explanation}</p>}</div>{action}</div>{children}</section>;
}

function Notice({ children }: { children: ReactNode }) { return <div className={styles.notice}><ShieldCheck size={17}/><div>{children}</div></div>; }
function ErrorNotice({ text, retry }: { text: string; retry?: () => void }) { return <div className={styles.error} role="alert"><AlertCircle size={17}/><div>{text}{retry && <div className="section-gap"><button type="button" className="button secondary small" onClick={retry}>Try again</button></div>}</div></div>; }
function Empty({ title, children }: { title: string; children: ReactNode }) { return <div className={styles.empty}><Database size={23}/><h3>{title}</h3><p>{children}</p></div>; }
function Stat({ label, value, explanation, icon }: { label: string; value: number | null | undefined; explanation: string; icon: ReactNode }) {
  return <div className={styles.stat}><div className={styles.statLabel}><span>{label}</span><span className={styles.statIcon} aria-hidden="true">{icon}</span></div><strong>{count(value)}</strong><small>{explanation}</small></div>;
}

function Bars({ rows }: { rows: { label: string; value: number | null; note?: string }[] }) {
  const maximum = Math.max(1, ...rows.map(row => row.value ?? 0));
  if (!rows.length) return <p className={styles.note}>No reportable counts for this selection.</p>;
  return <div className={styles.bars}>{rows.map((row, index) => <div key={`${row.label}-${index}`} className={styles.bar}><div className={styles.barLabel}><span>{row.label}</span><strong>{count(row.value)}</strong></div><div className={styles.track} aria-hidden="true">{row.value != null && <span className={styles.fill} style={{ width: `${Math.max(0, row.value) / maximum * 100}%` }}/>}</div>{row.note && <p className={styles.note}>{row.note}</p>}</div>)}</div>;
}

const modelNames: Record<string, string> = {
  logistic_regression: "Weighted patterns", decision_tree: "A single set of decisions",
  random_forest: "Many sets of decisions", gradient_boosting: "Learning from earlier mistakes",
  majority: "Always choose the more common result", carry_forward: "Repeat the latest reading category",
};
const modelExplanations: Record<string, string> = {
  logistic_regression: "Combines the measured factors into one estimate.",
  decision_tree: "Follows a small sequence of questions about the measurements.",
  random_forest: "Combines many decision paths to make one estimate.",
  gradient_boosting: "Adds decision paths that correct earlier errors.",
};
const featureNames: Record<string, string> = { age: "Age", systolic: "Upper BP reading", diastolic: "Lower BP reading", pulse: "Pulse", temperature: "Temperature", bmi: "Body mass index", glucose: "Blood sugar", condition_count: "Recorded conditions", adherence: "Medicine-taking logs" };
const modelName = (model: { id: string; name: string }) => modelNames[model.id] || model.name;

function Prediction({ data }: { data: MLInsights }) {
  const result = data.prediction;
  return <Panel title="Estimated next-visit blood pressure" eyebrow="Group-level estimates" explanation="The target is a recorded upper reading of at least 140 mmHg or a lower reading of at least 90 mmHg at the next visit. It does not diagnose hypertension." action={<HeartPulse size={21}/> }>
    {result.prediction_enabled && result.counts ? <><div className={styles.prediction}><div><h3><i/>At or above the threshold</h3><strong>{count(result.counts.elevated)}</strong><span>Patients estimated to have a higher reading at their next recorded visit.</span></div><div><h3><i/>Below this threshold</h3><strong>{count(result.counts.below_threshold)}</strong><span>Patients estimated to have a reading below this particular threshold.</span></div></div>{result.suppressed && <Notice>{result.reason || "Small groups are hidden. These values cannot be reported safely."}</Notice>}</> : <Empty title="Estimates are not available">{result.reason || "Train a model with enough usable follow-up records. Estimates only appear if the comparison checks pass."}</Empty>}
    <p className={styles.note}>{result.interpretation || "Historical selections are retrospective estimates using the current saved model, not a test of how accurately it would have predicted the past."}</p>
    <p className={styles.note}>The next visit may be days or months later. Below this threshold does not mean a patient is healthy or needs no care.</p>
    {result.as_of && <p className={styles.footer}>Latest selected measurement: {date(result.as_of)} · {count(result.eligible_patients)} patients with usable measurements.</p>}
  </Panel>;
}

function Comparison({ run, catalog }: { run: MLRun | null; catalog: MLCatalog }) {
  const report = run?.report;
  if (!report?.models.length) return <Panel title="Model comparison" explanation="Four different methods are compared on the same records and the same task."><Empty title="No completed comparison yet">{report?.reason || "Choose the records and use Retrain with new data. Nothing is trained just by opening this page."}</Empty></Panel>;
  const selected = report.models.find(model => model.id === report.selection?.model_id);
  const rows: { model: MLModelResult; reference?: boolean }[] = [...report.models.map(model => ({ model })), ...report.baselines.map(model => ({ model, reference: true }))];
  return <Panel title="Model comparison" eyebrow="Saved training result" explanation="Every method used the same patients and test splits. These percentages describe performance on synthetic records, not clinical reliability.">
    {selected && <div className={styles.winner}><CheckCircle2 size={24}/><div><h3>Best method in the practice tests: {modelName(selected)}</h3><p>{modelExplanations[selected.id]} Selected using balanced results across both outcomes in the practice-test rounds. The separate final test did not choose the winner.</p><p>{report.selection?.message}</p></div></div>}
    <div className={styles.range}><strong>This comparison keeps its original training selection</strong><p>{run ? filterDescription(run.filters, catalog) : "Saved training selection"}</p><p>Actual usable dates: {report.training_dates.from ? date(report.training_dates.from) : "Unavailable"} – {report.training_dates.through ? date(report.training_dates.through) : "Unavailable"}. Changing the exploration filters does not recalculate this saved comparison.</p></div>
    <div className={styles.tableWrap}><table className={styles.table}><caption className={styles.note}>All percentages give each patient equal total weight. Higher scores are better; none are the chance that a patient is ill.</caption><thead><tr><th>Method</th><th>Correct results</th><th>Higher readings found</th><th>Higher estimates correct</th><th>Practice-test balance</th><th>Final-test balance</th></tr></thead><tbody>{rows.map(({ model, reference }) => <tr key={model.id} className={selected?.id === model.id ? styles.selected : undefined}><td>{modelName(model)}<small>{reference ? "Simple reference for comparison" : modelExplanations[model.id]}</small>{selected?.id === model.id && <span className={styles.badge}>Selected method</span>}</td><td>{percent(model.holdout.accuracy)}</td><td>{percent(model.holdout.recall)}</td><td>{percent(model.holdout.precision)}</td><td>{percent(model.cv.mean.macro_f1)}</td><td>{percent(model.holdout.macro_f1)}</td></tr>)}</tbody></table></div>
    <p className={styles.note}>“Higher readings found” measures how many actual higher readings were identified. “Higher estimates correct” measures how many higher estimates were right. “Balance” combines missed readings and false alarms across both outcomes.</p>
    {selected && <><p className={styles.note}>Final test: {count(selected.holdout.patients)} separate patients and {count(selected.holdout.examples)} pairs of consecutive visits. A patient’s visits stay together so the same person is never used to both teach and test a method.</p><details className={styles.details}><summary>See correct and incorrect final-test results</summary><p>Counts below are visit pairs, before patient weighting. Rows are actual outcomes and columns are the selected method’s estimates.</p>{selected.holdout.confusion_matrix ? <div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Actual next reading</th><th>Estimated below threshold</th><th>Estimated higher reading</th></tr></thead><tbody><tr><td>Below threshold</td><td>{count(selected.holdout.confusion_matrix[0][0])} correct</td><td>{count(selected.holdout.confusion_matrix[0][1])} false alarms</td></tr><tr><td>Higher reading</td><td>{count(selected.holdout.confusion_matrix[1][0])} missed readings</td><td>{count(selected.holdout.confusion_matrix[1][1])} found readings</td></tr></tbody></table></div> : <p>These counts are hidden because at least one result group is too small.</p>}</details></>}
    <details className={styles.details}><summary>Course details: algorithms and evaluation</summary><p>Correct results = accuracy. Higher readings found = recall. Higher estimates correct = precision. Balance = macro F1, the mean of the F1 scores for both outcomes. F1 combines precision and recall; it is not a clinical probability.</p><div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Algorithm</th><th>Final-test F1</th><th>Practice-test F1</th><th>Practice-test balance variation</th></tr></thead><tbody>{report.models.map(model => <tr key={model.id}><td>{model.name}</td><td>{percent(model.holdout.f1)}</td><td>{percent(model.cv.mean.f1)}</td><td>± {(model.cv.std.macro_f1 * 100).toFixed(1)} percentage points</td></tr>)}</tbody></table></div><p>{report.split?.method}</p><p>{report.selection?.gate_policy}</p><ul>{report.limitations.map((text, index) => <li key={index}>{text}</li>)}</ul></details>
  </Panel>;
}

function Groups({ groups, catalog }: { groups: MLPatientGroups; catalog: MLCatalog }) {
  const visible = groups.groups.filter(group => !group.suppressed && group.position);
  const xs = visible.map(group => group.position!.x), ys = visible.map(group => group.position!.y);
  const minX = Math.min(0, ...xs), maxX = Math.max(1, ...xs), minY = Math.min(0, ...ys), maxY = Math.max(1, ...ys);
  const x = (value: number) => 55 + (value - minX) / Math.max(1, maxX - minX) * 410;
  const y = (value: number) => 210 - (value - minY) / Math.max(1, maxY - minY) * 165;
  return <Panel title="Patients with similar measurements" eyebrow="Health patterns" explanation="Each patient contributes their latest usable reading in the selected history. Groups describe similar measurements, not the same diagnosis or treatment." action={<UsersRound size={21}/> }>
    {groups.status !== "completed" ? <Empty title="More measurements needed">{groups.reason || "There are not enough usable measurements to describe patient groups."}</Empty> : <>
      {visible.length > 1 && <><svg className={styles.map} viewBox="0 0 520 250" role="img" aria-label="Similar-patient group centres; only aggregate group positions are shown"><line x1="30" x2="490" y1="223" y2="223" stroke="#d5e0cf"/><line x1="30" x2="30" y1="25" y2="223" stroke="#d5e0cf"/>{visible.map(group => <g key={group.group}><circle cx={x(group.position!.x)} cy={y(group.position!.y)} r={Math.min(28, 10 + Math.sqrt(group.patient_count || 0))} fill="#7bac8c" fillOpacity=".6" stroke="#477759" strokeWidth="1.5" tabIndex={0}><title>{group.label}: {count(group.patient_count)} patients</title></circle><text x={x(group.position!.x)} y={y(group.position!.y) + 4} textAnchor="middle">{group.group}</text><text x={x(group.position!.x)} y={y(group.position!.y) + 43} textAnchor="middle">{group.label}</text></g>)}</svg><p className={styles.note}>Nearby group centres share more measured characteristics. The axes combine several measurements; they are not a health score. No individual patient points are shown.</p></>}
      <div className={styles.groups}>{groups.groups.map(group => <article key={group.group} className={styles.group}><div className={styles.groupHead}><h3>{group.label}</h3><strong>{group.suppressed ? "Hidden" : count(group.patient_count)}</strong></div><p>{group.suppressed ? "This group is too small to display its measurements or conditions." : group.explanation}</p>{!group.suppressed && <><dl>{["systolic", "diastolic", "glucose", "age"].filter(key => group.profile[key]?.mean != null).map(key => <div key={key}><dt>Average {featureNames[key].toLowerCase()}</dt><dd>{group.profile[key].mean}{key === "systolic" || key === "diastolic" ? " mmHg" : key === "glucose" ? " mg/dL" : " years"}</dd></div>)}</dl>{!!group.conditions.length && <p>Recorded conditions: {group.conditions.map(item => `${catalog.diseases.find(disease => disease.disease_code === item.code)?.label || item.code} (${count(item.patient_count)})`).join(" · ")}. A patient may have more than one condition.</p>}</>}</article>)}</div>
      <details className={styles.details}><summary>How these groups were formed</summary><p>Grouping compares measurements after putting them on a common scale. Missing values are filled using the selected group’s middle values for this grouping exercise only.</p><p>Course method: K-Means. The two-dimensional chart uses PCA and shows group centres only. Group separation: {groups.silhouette == null ? "Unavailable" : groups.silhouette.toFixed(3)}; this is not diagnostic accuracy.</p></details>
    </>}
  </Panel>;
}

function Geography({ data, catalog }: { data: MLInsights; catalog: MLCatalog }) {
  const hotspots = data.hotspots;
  const stations = data.summary.stations;
  const known = catalog.stations.filter(station => stations.some(row => row.station_id === station.station_id));
  const lon = known.map(station => station.longitude), lat = known.map(station => station.latitude);
  const west = Math.min(...lon), east = Math.max(...lon), south = Math.min(...lat), north = Math.max(...lat);
  const px = (longitude: number) => 50 + (longitude - west) / Math.max(.01, east - west) * 420;
  const py = (latitude: number) => 250 - (latitude - south) / Math.max(.01, north - south) * 205;
  const groups = hotspots?.clusters || [];
  const groupCards = (items: typeof groups) => items.map(group => <article className={styles.group} key={group.cluster}><div className={styles.groupHead}><h3>Nearby recorded cases {group.cluster + 1}</h3><strong>{group.suppressed ? "Hidden" : count(group.patient_count)}</strong></div><p>{group.suppressed ? "This group and its location breakdown are hidden because it is too small." : group.stations.map(station => `${station.station_name}: ${count(station.patient_count)}`).join(" · ") || "Nearby observations form this geographic group."}</p></article>);
  return <Panel title="Where recorded conditions are concentrated" eyebrow="Area patterns" explanation="The same area, condition, and date filters apply here. These are recorded patient counts, not disease rates or confirmed outbreaks." action={<MapPin size={21}/> }>
    {known.length ? <><svg className={styles.map} viewBox="0 0 520 295" role="img" aria-label="Station-area map showing aggregate patient counts"><text x="20" y="25">North ↑</text>{known.map(station => { const row = stations.find(item => item.station_id === station.station_id)!; const hidden = row.suppressed || row.patient_count == null; return <g key={station.station_id}><circle cx={px(station.longitude)} cy={py(station.latitude)} r={hidden ? 5 : Math.min(18, 4 + Math.sqrt(row.patient_count || 0))} fill={hidden ? "#b5c5aa" : "#4f9274"} fillOpacity=".75" stroke="#fff" strokeWidth="1.5" tabIndex={0}><title>{station.station_name}: {hidden ? "small count hidden" : `${count(row.patient_count)} patients`}</title></circle>{known.length <= 8 && <text x={px(station.longitude)} y={py(station.latitude) + 28} textAnchor="middle">{station.station_name}</text>}</g>; })}</svg><div className={styles.legend}><span><i/>Recorded patients at station areas</span><span><i/>Hidden small count</span></div><p className={styles.note}>Public station positions represent simulated areas. This map does not show home addresses or individual patients.</p></> : <Empty title="No locations available">There are no station areas with usable location information in this selection.</Empty>}
    <div className={styles.groups}>{groups.length ? groupCards(groups.slice(0, 6)) : <p className={styles.note}>{hotspots?.reason || "No dense geographic groups were found for this selection."}</p>}</div>
    {groups.length > 6 && <details className={styles.details}><summary>Show remaining {groups.length - 6} groups</summary><p>All {groups.length} groups remain available. The first six are shown above; these are the remaining groups from the same selection.</p><div className={`${styles.groups} ${styles.moreGroups}`}>{groupCards(groups.slice(6))}</div></details>}
    {!!data.summary.station_disease_counts?.length && <div className={styles.stationCounts}><h3>Conditions by station area</h3><div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Station area</th><th>Patients</th><th>Recorded conditions</th></tr></thead><tbody>{data.summary.station_disease_counts.slice(0, 6).map(station => <tr key={station.station_id}><td>{station.station_name}</td><td>{station.patient_count == null ? "Hidden" : count(station.patient_count)}</td><td>{station.diseases.map(item => `${item.label}: ${item.count == null ? "Hidden" : count(item.count)}`).join(" · ") || "None recorded"}</td></tr>)}</tbody></table></div><p className={styles.note}>Counts of 1–4 are hidden; 0 means no recorded cases. Patients can have more than one condition.</p></div>}
    <details className={styles.details}><summary>View all area counts and grouping details</summary><div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Station area</th><th>Recorded patients</th><th>Conditions</th></tr></thead><tbody>{stations.map(station => <tr key={station.station_id}><td>{station.station_name}</td><td>{station.suppressed ? "Hidden" : count(station.patient_count)}</td><td>{data.summary.station_disease_counts?.find(item => item.station_id === station.station_id)?.diseases.map(item => `${item.label}: ${item.count == null ? "Hidden" : count(item.count)}`).join(" · ") || "Unavailable"}</td></tr>)}</tbody></table></div><p>Course method: DBSCAN groups nearby observations. {count(hotspots?.counts?.missing_coordinates)} selected patients lack coordinates. {count(hotspots?.counts?.noise_patients)} were outside dense groups.</p>{hotspots?.notes?.map((note, index) => <p key={index}>{note}</p>)}</details>
  </Panel>;
}

function Importance({ report }: { report: MLReport | null | undefined }) {
  const maximum = Math.max(.01, ...(report?.feature_importance || []).map(feature => feature.importance));
  return <Panel title="Which measurements helped the method?" eyebrow="Understanding the method" explanation="Each measurement is shuffled in the separate test data. A larger drop in the balanced score suggests the saved method used that measurement more. This does not show medical causes.">
    {report?.feature_importance.length ? <div className={styles.bars}>{report.feature_importance.slice(0, 8).map(feature => <div key={feature.feature} className={styles.bar}><div className={styles.barLabel}><span>{feature.label}</span><strong>{feature.importance > 0 ? `${(feature.importance * 100).toFixed(1)} point drop` : "No demonstrated contribution"}</strong></div><div className={styles.track} aria-hidden="true"><span className={styles.fill} style={{ width: `${Math.max(0, feature.importance) / maximum * 100}%` }}/></div></div>)}</div> : <Empty title="No fitted method to explain yet">Measurement contributions appear after a completed training comparison.</Empty>}
    <p className={styles.note}>Drops are percentage points in the balanced test score, not percentages of medical importance. These results belong to the saved training run and stay unchanged when you explore a different group.</p>
    {report?.feature_importance_method && <details className={styles.details}><summary>How measurement contributions were checked</summary><p>{report.feature_importance_method}</p></details>}
  </Panel>;
}

function Insights({ data, catalog }: { data: MLInsights; catalog: MLCatalog }) {
  return <>
    <div className={styles.twoColumns}><Groups groups={data.patient_groups} catalog={catalog}/><Geography data={data} catalog={catalog}/></div>
    <div className={styles.twoColumns}><Panel title="Recorded conditions" explanation="Patients may have more than one condition, so these counts should not be added together."><Bars rows={data.summary.disease_counts.map(item => ({ label: item.label, value: item.count }))}/></Panel><Panel title="How recorded activity changes over time" explanation="Selected patient counts by month; recorded activity is not a forecast."><Bars rows={data.summary.monthly_counts.map(item => ({ label: item.month, value: item.count }))}/></Panel></div>
  </>;
}

function Workspace({ catalog, datasetId }: { catalog: MLCatalog; datasetId: string }) {
  const initial: MLFilters = { dataset_id: datasetId, disease_code: "", line: "", station_id: "", date_from: null, date_to: null };
  const [draft, setDraft] = useState(initial), [filters, setFilters] = useState(initial);
  const [snapshot, setSnapshot] = useState<{ key: string; value: MLInsights } | null>(null);
  const [loading, setLoading] = useState(true), [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState(""), [pollError, setPollError] = useState("");
  const [version, setVersion] = useState(0), [submitting, setSubmitting] = useState(false);
  const [training, setTraining] = useState<MLRun | null>(null);
  const [bpOpen, setBpOpen] = useState(false);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const query = queryString(filters);
  const data = snapshot?.key === query ? snapshot.value : null;
  const dirty = JSON.stringify(draft) !== JSON.stringify(filters);
  const trainingId = activeRun(training) ? training!.id : null;

  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    setLoading(true); setLoadError("");
    api<MLInsights>(`${base}/insights/?${query}`, { signal: controller.signal }).then(value => {
      if (!current) return;
      setSnapshot({ key: query, value });
      if (value.training) setTraining(previous => !activeRun(previous) || previous?.id === value.training?.id ? value.training : previous);
    }).catch(error => { if (current) setLoadError(message(error)); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; controller.abort(); };
  }, [query, version]);

  useEffect(() => {
    if (!trainingId) return;
    let current = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const run = await api<MLRun>(`${base}/runs/${encodeURIComponent(trainingId!)}/`);
        if (!current) return;
        setTraining(run); setPollError("");
        if (!activeRun(run)) { setVersion(value => value + 1); return; }
      } catch (error) { if (current) setPollError(`Could not check training progress. ${message(error)} Retrying automatically.`); }
      if (current) timer = setTimeout(poll, 3000);
    }
    timer = setTimeout(poll, 1500);
    return () => { current = false; clearTimeout(timer); };
  }, [trainingId]);

  const setField = (key: keyof MLFilters, value: string) => setDraft(previous => ({ ...previous, [key]: key.startsWith("date_") ? value || null : value, ...(key === "line" ? { station_id: "" } : {}) }));
  function apply(next: MLFilters) {
    if (next.date_from && next.date_to && next.date_from > next.date_to) { setActionError("The start date must be on or before the end date."); return; }
    setActionError(""); setDraft(next); setFilters({ ...next });
  }
  function submitFilters(event: FormEvent<HTMLFormElement>) { event.preventDefault(); apply(draft); }
  async function retrain() {
    if (submitting || trainingId || dirty) return;
    setSubmitting(true); setActionError(""); setPollError("");
    try {
      const run = await post<MLRun>(`${base}/runs/`, filters);
      if (!alive.current) return;
      setTraining(run);
      if (!activeRun(run)) setVersion(value => value + 1);
    } catch (error) { if (alive.current) setActionError(message(error)); }
    finally { if (alive.current) setSubmitting(false); }
  }
  const stations = catalog.stations.filter(station => !draft.line || station.lines.includes(draft.line));
  const readiness = training?.report?.data || data?.model?.report?.data;
  const selectedConditions = (filters.disease_codes || filters.disease_code || "").split(",").filter(Boolean).map(code => catalog.diseases.find(item => item.disease_code === code)?.label || code);
  return <div className={styles.workspace} data-testid="admin-ml">
    <section className={styles.filterPanel} aria-labelledby="ml-filters-heading" data-testid="ml-record-filters">
      <div className={styles.filterHeading}><div className={styles.filterTitle}><span className={styles.sectionIcon} aria-hidden="true"><SlidersHorizontal size={18}/></span><div><h2 id="ml-filters-heading">Record filters</h2><p>Choose conditions, locations and dates.</p></div></div><span className={styles.tag}><FlaskConical size={13} aria-hidden="true"/>Synthetic data</span></div>
      <form onSubmit={submitFilters}><div className={styles.filters}>
        <DiseaseFilter options={catalog.diseases} selected={(draft.disease_codes || draft.disease_code || "").split(",").filter(Boolean)} onChange={codes => setDraft(previous => ({ ...previous, disease_code: "", disease_codes: codes.join(",") }))}/>
        <label>Rail line<select value={draft.line} onChange={event => setField("line", event.target.value)}><option value="">All lines</option>{catalog.lines.map(line => <option key={line}>{line}</option>)}</select></label>
        <label>Station area<select value={draft.station_id} onChange={event => setField("station_id", event.target.value)}><option value="">All station areas</option>{stations.map(station => <option key={station.station_id} value={station.station_id}>{station.station_name}</option>)}</select></label>
        <label>From date<input type="date" value={draft.date_from || ""} onChange={event => setField("date_from", event.target.value)}/></label>
        <label>Through date<input type="date" value={draft.date_to || ""} onChange={event => setField("date_to", event.target.value)}/></label>
      </div><div className={styles.filterFooter}><p className={dirty ? styles.pendingSelection : styles.appliedSelection}><i aria-hidden="true"/>{dirty ? "Unapplied changes — apply filters to update the results." : filterDescription(filters, catalog)}</p><div className={styles.actions}><button type="button" className="button secondary small" onClick={() => apply({ ...draft, date_from: null, date_to: null })}><CalendarDays size={15} aria-hidden="true"/>All history</button><button type="submit" className="button primary small">Apply filters</button></div></div></form>
    </section>
    {actionError && <ErrorNotice text={actionError}/>}
    {loadError && <ErrorNotice text={loadError} retry={() => setVersion(value => value + 1)}/>}
    {loading && <div className={styles.loadingPanel}><div className={styles.status} role="status"><LoaderCircle size={17} className="spin"/>{data ? "Updating the selected insights…" : "Reading the selected records…"}</div>{!data && <div className={styles.skeletonGrid} aria-hidden="true">{[0, 1, 2, 3].map(item => <div key={item}><i/><b/><span/></div>)}</div>}</div>}
    {data && <>
      <section aria-labelledby="ml-selected-records-heading" className={styles.selectionOverview}><div className={styles.selectionHeading}><h2 id="ml-selected-records-heading">Selected records</h2><span>Updates with your filters</span></div><div className={styles.readiness}><Stat label="Patients in this selection" value={data.source.patients} explanation="Each person counted once." icon={<UsersRound size={18}/>}/><Stat label="Recorded visits" value={data.source.visits} explanation="Consultations and report observations." icon={<ClipboardList size={18}/>}/><Stat label="Uploaded reports" value={data.source.reports} explanation="Files in the selected records." icon={<FileText size={18}/>}/><Stat label="Recorded dose days" value={data.source.adherence_logs} explanation="Days with medicine intake logs." icon={<Pill size={18}/>}/></div></section>
      <DiseasePrediction data={data.disease} filters={filters} dirty={dirty} fallbackPatients={data.source.patients} selectedConditions={selectedConditions} onRefresh={() => setVersion(value => value + 1)}/>
      <details className={styles.bpSection} open={bpOpen} onToggle={event => setBpOpen(event.currentTarget.open)}><summary>Blood pressure prediction and training</summary><div className={styles.bpContents}>
      <Panel title="Keep the learning data up to date" eyebrow="Training" explanation="Training compares four methods on the same task. A failed run keeps the previous successful model available." action={<button type="button" className="button primary small" disabled={submitting || !!trainingId || dirty || data.source.patients === 0} onClick={() => void retrain()}>{submitting || trainingId ? <LoaderCircle size={15} className="spin"/> : <RefreshCw size={15}/>} {submitting ? "Starting training…" : trainingId ? "Training in progress" : "Retrain with new data"}</button>}>
        <p className={styles.note}>Available selected history: {data.source.history_start ? date(data.source.history_start) : "No start date"} – {data.source.history_end ? date(data.source.history_end) : "No end date"}. {count(data.source.labs)} structured lab results.</p>
        {dirty && <p className={styles.note}>Apply the filters before starting a training run.</p>}
        {training && <div className={styles.range} role="status"><strong>{activeRun(training) ? "Training in progress" : training.status === "completed" ? "Training completed" : training.status === "insufficient_data" ? "More usable records needed" : "Training did not complete"}</strong><p>{training.message || training.error || "The saved model remains available while this run is checked."}</p><p>Run selection: {filterDescription(training.filters, catalog)}</p>{training.finished_at && <p>Finished {dateTime(training.finished_at)}</p>}</div>}
        {pollError && <ErrorNotice text={pollError}/>}
        {training?.report?.reason && <p className={styles.note}>{training.report.reason}</p>}
        <details className={styles.details}><summary>Data readiness and omitted records</summary><p>Training needs at least 100 usable pairs of consecutive visits from 50 patients, including at least 10 patients for each outcome. Measurements entered after their recorded date are excluded from historical training to avoid using information that was unavailable at the time.</p><ul><li>Reports with supported structured results: {count(data.source.extracted_reports)}</li><li>Other report formats: {count(data.source.unsupported_reports)}</li><li>Reports entered after their measurement date: {count(data.source.historically_unavailable_reports)}</li>{Object.entries(data.source.excluded || {}).map(([key, value]) => <li key={key}>{key === "unmapped_patients" ? "Patients without a mapped area" : key === "missing_geography" ? "Patients without usable coordinates" : key.replaceAll("_", " ")}: {count(value)}</li>)}</ul>{readiness && <><p>Last run’s usable training data: {count(readiness.eligible_pairs)} visit pairs from {count(readiness.eligible_patients)} patients. This belongs to that run’s saved selection.</p><ul>{Object.entries(readiness.missing_feature_counts).map(([key, value]) => <li key={key}>Missing {featureNames[key]?.toLowerCase() || key.replaceAll("_", " ")}: {count(value)}</li>)}</ul></>}</details>
      </Panel>
      <Prediction data={data}/><Comparison run={data.model} catalog={catalog}/><Importance report={data.model?.report}/>
      </div></details>
      {data.source.patients === 0 ? <Empty title="No patients match this selection">Choose a wider date range or clear an area or condition filter. No results are invented for an empty group.</Empty> : <Insights data={data} catalog={catalog}/>}
      {!!data.notes.length && <details className={`${styles.panel} ${styles.details}`}><summary>Data and privacy notes</summary><ul>{data.notes.map((note, index) => <li key={index}>{note}</li>)}</ul></details>}
      <Notice>Predictions support decisions and are not a diagnosis. These methods are evaluated on synthetic data and have not been clinically validated. Small groups are hidden to reduce identification risk; this does not guarantee anonymity.</Notice>
    </>}
  </div>;
}

export function AdminML() {
  const [datasetId, setDatasetId] = useState("");
  const catalog = useQuery<MLCatalog>(`${base}/catalog/${datasetId ? `?dataset_id=${encodeURIComponent(datasetId)}` : ""}`);
  if (catalog.loading) return <div className={styles.status} role="status"><LoaderCircle size={18} className="spin"/>Loading ML insights…</div>;
  if (catalog.error) return <ErrorNotice text={catalog.error} retry={catalog.reload}/>;
  if (!catalog.data?.datasets.length) return <Panel title="No ML dataset is available"><Empty title="Add a synthetic dataset to begin">Insights appear when the configured synthetic dataset contains records. Training will not start automatically.</Empty><button type="button" className="button secondary small section-gap" onClick={catalog.reload}>Check for data</button></Panel>;
  const selected = datasetId || catalog.data.defaults.dataset_id || catalog.data.datasets[0].dataset_id;
  return <>{catalog.data.datasets.length > 1 && <label className={styles.dataset}>Synthetic dataset<select value={selected} onChange={event => setDatasetId(event.target.value)}>{catalog.data.datasets.map(dataset => <option key={dataset.dataset_id} value={dataset.dataset_id}>{dataset.dataset_id}</option>)}</select></label>}<Workspace key={selected} catalog={catalog.data} datasetId={selected}/></>;
}
