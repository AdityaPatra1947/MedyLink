"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { AlertCircle, CalendarDays, ClipboardList, Database, FileText, FlaskConical, LoaderCircle, Pill, ShieldCheck, SlidersHorizontal, UsersRound } from "lucide-react";
import { api, date, message } from "@/lib/api";
import type { MLCatalog, MLFilters, MLInsights, MLPatientGroups } from "@/lib/ml-types";
import { useQuery } from "./ui";
import { DiseasePrediction } from "./admin-disease";
import { DiseaseFilter } from "./admin-disease-filter";
import { AdminGeography } from "./admin-geography";
import styles from "./admin-ml.module.css";

const base = "/admin/analytics/ml";
const count = (value: number | null | undefined) => value == null ? "Hidden / unavailable" : new Intl.NumberFormat("en-IN").format(value);

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

const featureNames: Record<string, string> = { age: "Age", systolic: "Upper BP reading", diastolic: "Lower BP reading", glucose: "Blood sugar" };

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

function Insights({ data, catalog }: { data: MLInsights; catalog: MLCatalog }) {
  return <>
    <AdminGeography data={data} catalog={catalog}/>
    <div className={styles.twoColumns}><Groups groups={data.patient_groups} catalog={catalog}/><div className="stack"><Panel title="Recorded conditions" explanation="Patients may have more than one condition, so these counts should not be added together."><Bars rows={data.summary.disease_counts.map(item => ({ label: item.label, value: item.count }))}/></Panel><Panel title="How recorded activity changes over time" explanation="Selected patient counts by month; recorded activity is not a forecast."><Bars rows={data.summary.monthly_counts.map(item => ({ label: item.month, value: item.count }))}/></Panel></div></div>
  </>;
}

function Workspace({ catalog, datasetId }: { catalog: MLCatalog; datasetId: string }) {
  const initial: MLFilters = { dataset_id: datasetId, disease_code: "", line: "", station_id: "", date_from: null, date_to: null };
  const [draft, setDraft] = useState(initial), [filters, setFilters] = useState(initial);
  const [snapshot, setSnapshot] = useState<{ key: string; value: MLInsights } | null>(null);
  const [loading, setLoading] = useState(true), [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [version, setVersion] = useState(0);
  const query = queryString(filters);
  const data = snapshot?.key === query ? snapshot.value : null;
  const dirty = JSON.stringify(draft) !== JSON.stringify(filters);

  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    setLoading(true); setLoadError("");
    api<MLInsights>(`${base}/insights/?${query}`, { signal: controller.signal }).then(value => {
      if (!current) return;
      setSnapshot({ key: query, value });
    }).catch(error => { if (current) setLoadError(message(error)); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; controller.abort(); };
  }, [query, version]);

  const setField = (key: keyof MLFilters, value: string) => setDraft(previous => ({ ...previous, [key]: key.startsWith("date_") ? value || null : value, ...(key === "line" ? { station_id: "" } : {}) }));
  function apply(next: MLFilters) {
    if (next.date_from && next.date_to && next.date_from > next.date_to) { setActionError("The start date must be on or before the end date."); return; }
    setActionError(""); setDraft(next); setFilters({ ...next });
  }
  function submitFilters(event: FormEvent<HTMLFormElement>) { event.preventDefault(); apply(draft); }
  const stations = catalog.stations.filter(station => !draft.line || station.lines.includes(draft.line));
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
