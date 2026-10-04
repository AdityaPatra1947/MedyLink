"use client";

import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Activity, ArrowRight, BarChart3, Check, ChevronRight, CircleHelp, Compass, Database, FlaskConical, Info, Layers3, LoaderCircle, MapPin, RefreshCw, ScanSearch, ShieldCheck, SlidersHorizontal, UsersRound } from "lucide-react";
import { api, message, post } from "@/lib/api";
import type { AnalyticsCatalog, AnalyticsCluster, AnalyticsFilters, AnalyticsMetric, AnalyticsParameters, AnalyticsRun, AnalyticsSummary, ClusterResult, EvaluationResult, StationAnchor } from "@/lib/analytics-types";
import { useQuery } from "./ui";
import styles from "./admin-analytics.module.css";

const COLORS = ["#247b69", "#5486b0", "#bc8651", "#8a74ab", "#6b9154", "#b07180"];
const numberFormat = new Intl.NumberFormat("en-IN");
const shortDate = (value: string) => new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${value.slice(0, 10)}T00:00:00Z`));
const count = (value: number | null | undefined) => value == null ? "Hidden" : numberFormat.format(value);
const percent = (value: number | null | undefined) => value == null ? "Hidden" : `${(value * 100).toFixed(1)}%`;
const score = (metric?: AnalyticsMetric) => metric?.value == null ? "Unavailable" : metric.value.toFixed(3);
const reason = (value?: string | null) => value?.replaceAll("_", " ") || "There are not enough eligible observations to calculate this metric.";
const color = (cluster: number) => COLORS[Math.abs(cluster) % COLORS.length];

function queryPath(filters: AnalyticsFilters) {
  return `/admin/analytics/summary/?${new URLSearchParams({ ...filters }).toString()}`;
}

function ErrorNotice({ text, retry }: { text: string; retry?: () => void }) {
  return <div className={styles.error} role="alert"><Info size={17}/><div>{text}{retry && <div><button type="button" className={styles.subtleButton} onClick={retry}>Try again</button></div>}</div></div>;
}

function Empty({ title, children }: { title: string; children: ReactNode }) {
  return <div className={styles.empty}><ScanSearch size={28} strokeWidth={1.4}/><h4>{title}</h4><p>{children}</p></div>;
}

function PanelHead({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <div className={styles.panelHead}><div>{eyebrow && <span className={styles.eyebrow}>{eyebrow}</span>}<h3>{title}</h3>{description && <p>{description}</p>}</div>{action}</div>;
}

function Metric({ title, value, description }: { title: string; value: string; description: string }) {
  return <div className={styles.metric}><span>{title}</span><strong>{value}</strong><small>{description}</small></div>;
}

type BarRow = { key: string; label: string; value: number | null; suppressed: boolean };
function Bars({ rows, muted = false }: { rows: BarRow[]; muted?: boolean }) {
  const maximum = Math.max(1, ...rows.map(row => row.value || 0));
  if (!rows.length) return <Empty title="No recorded observations">Try a wider time window or a different area.</Empty>;
  return <div className={styles.barList}>{rows.map(row => <div className={styles.barRow} key={row.key}>
    <div className={styles.barLabel}><span>{row.label}</span><strong>{row.suppressed ? "Hidden" : count(row.value)}</strong></div>
    <div className={styles.barTrack} aria-hidden="true">{row.value != null && !row.suppressed && <span className={`${styles.barFill} ${muted ? styles.barFillMuted : ""}`} style={{ width: `${row.value / maximum * 100}%` }}/>}</div>
  </div>)}</div>;
}

function WeeklyChart({ rows }: { rows: NonNullable<AnalyticsSummary["weekly"]> }) {
  const id = useId();
  const w = 560, h = 185, left = 32, top = 16, bottom = 35;
  const maximum = Math.max(1, ...rows.map(row => row.patient_count || 0));
  const x = (i: number) => left + (rows.length < 2 ? (w - left - 15) / 2 : i / (rows.length - 1) * (w - left - 15));
  const y = (value: number) => h - bottom - value / maximum * (h - bottom - top);
  const segments: string[] = [];
  let current = "";
  rows.forEach((row, i) => {
    if (row.patient_count == null || row.suppressed) { if (current) segments.push(current); current = ""; }
    else current += `${current ? " L" : "M"}${x(i)} ${y(row.patient_count)}`;
  });
  if (current) segments.push(current);
  if (!rows.length) return <Empty title="No weekly observations">There are no recorded observations in this period.</Empty>;
  return <><svg className={styles.chartSvg} viewBox={`0 0 ${w} ${h}`} role="img" aria-labelledby={`${id}-title ${id}-desc`}>
    <title id={`${id}-title`}>Unique patients with recorded observations by week</title><desc id={`${id}-desc`}>Weekly counts may overlap. Hidden small counts appear as gaps. The data table follows the chart.</desc>
    {[0, .5, 1].map(tick => <g key={tick}><line x1={left} x2={w - 10} y1={y(maximum * tick)} y2={y(maximum * tick)} stroke="#e8eddf" strokeDasharray={tick ? "3 4" : undefined}/><text x={left - 8} y={y(maximum * tick) + 3} textAnchor="end">{Math.round(maximum * tick)}</text></g>)}
    {segments.map((segment, i) => <path key={i} d={segment} fill="none" stroke="#518b6b" strokeWidth="2.5"/>)}
    {rows.map((row, i) => <g key={row.week_start}>{row.patient_count != null && !row.suppressed && <circle className={styles.chartPoint} tabIndex={0} cx={x(i)} cy={y(row.patient_count)} r="4" fill="#578f6d" stroke="white" strokeWidth="2"><title>{shortDate(row.week_start)}: {count(row.patient_count)} patients</title></circle>}{(i % Math.max(1, Math.ceil(rows.length / 6)) === 0 || i === rows.length - 1) && <text x={x(i)} y={h - 12} textAnchor="middle">{shortDate(row.week_start)}</text>}</g>)}
  </svg><details className={styles.dataDetails}><summary>View weekly data</summary><div className={styles.tableWrap}><table><thead><tr><th>Week beginning (UTC)</th><th>Patients with observations</th></tr></thead><tbody>{rows.map(row => <tr key={row.week_start}><td>{shortDate(row.week_start)}</td><td>{row.suppressed ? "Hidden" : count(row.patient_count)}</td></tr>)}</tbody></table></div></details></>;
}

function StationMap({ stations, summary, clusters, selectedCluster, onCluster, selectedStation, onStation }: {
  stations: StationAnchor[]; summary: AnalyticsSummary; clusters: AnalyticsCluster[]; selectedCluster: number | null;
  onCluster: (value: number) => void; selectedStation: string | null; onStation: (value: string) => void;
}) {
  const id = useId();
  const w = 620, h = 470;
  const lo = Math.min(...stations.map(s => s.longitude)) - .015, hi = Math.max(...stations.map(s => s.longitude)) + .015;
  const south = Math.min(...stations.map(s => s.latitude)) - .018, north = Math.max(...stations.map(s => s.latitude)) + .018;
  const longitudeFactor = Math.cos((north + south) / 2 * Math.PI / 180);
  const scale = Math.min((w - 90) / ((hi - lo) * longitudeFactor), (h - 65) / (north - south));
  const xOffset = (w - (hi - lo) * longitudeFactor * scale) / 2;
  const yOffset = (h - (north - south) * scale) / 2;
  const project = (latitude: number, longitude: number) => ({ x: xOffset + (longitude - lo) * longitudeFactor * scale, y: yOffset + (north - latitude) * scale });
  const counts = new Map(summary.stations.map(station => [station.station_id, station]));
  const visibleClusters = clusters.filter(cluster => !cluster.suppressed && cluster.centroid && cluster.patient_count != null);
  const selected = selectedStation && counts.get(selectedStation);
  const labels = new Set(["BORIVALI", "THANE", "KALYAN", "ANDHERI", "KURLA", "VASHI", "NERUL", "PANVEL", "CSMT"]);
  const activate = (event: React.KeyboardEvent<SVGGElement>, callback: () => void) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); callback(); } };
  return <><svg className={styles.map} viewBox={`0 0 ${w} ${h}`} role="group" aria-labelledby={`${id}-title ${id}-desc`}>
    <title id={`${id}-title`}>Mumbai Metropolitan Region station-area distribution</title><desc id={`${id}-desc`}>Geographic scatter using public station anchors and rounded aggregate cluster centres. Select a station or cluster for details. There are no individual patient locations. Circle size represents count, not geographic radius.</desc>
    <defs><pattern id={`${id}-grid`} width="31" height="31" patternUnits="userSpaceOnUse"><path d="M31 0H0V31" fill="none" stroke="#e5ecde" strokeWidth=".6"/></pattern></defs><rect width={w} height={h} fill={`url(#${id}-grid)`}/>
    {[0, 1, 2, 3].map(tick => {
      const latitude = south + (north - south) * tick / 3;
      const longitude = lo + (hi - lo) * tick / 3;
      return <g key={tick} aria-hidden="true"><text x="5" y={project(latitude, lo).y + 3} style={{ fontSize: 8, fill: "#8c9a85" }}>{latitude.toFixed(2)}°N</text><text x={project(south, longitude).x} y={h - 7} textAnchor="middle" style={{ fontSize: 8, fill: "#8c9a85" }}>{longitude.toFixed(2)}°E</text></g>;
    })}
    <text x="22" y="28" style={{ fontSize: 8, letterSpacing: 1.5, fill: "#91a28b" }}>MUMBAI METROPOLITAN REGION</text>
    <path d="M583 51V27m-4 6 4-6 4 6" fill="none" stroke="#8da087" strokeWidth="1.5"/><text x="583" y="20" textAnchor="middle" style={{ fontSize: 9 }}>N</text>
    {stations.map(station => {
      const position = project(station.latitude, station.longitude), row = counts.get(station.station_id);
      const hidden = !!row?.suppressed, value = hidden ? null : row?.patient_count ?? 0;
      const active = selectedStation === station.station_id;
      const label = `${station.station_name}: ${hidden ? "count hidden" : `${count(value)} patients with observations`}`;
      return <g key={station.station_id} className={styles.mapStation} tabIndex={0} role="button" aria-label={label} aria-pressed={active} onClick={() => onStation(station.station_id)} onKeyDown={event => activate(event, () => onStation(station.station_id))}>
        <title>{label}</title><circle cx={position.x} cy={position.y} r={active ? 9 : 4 + Math.min(7, Math.sqrt(value || 0) * .6)} fill={hidden ? "#b4b7a5" : value ? "#88aa85" : "#d3dbcd"} fillOpacity={active ? 1 : .85} stroke={active ? "#244b37" : "#fff"} strokeWidth={active ? 2.5 : 1.5}/>
        {(labels.has(station.station_id) || active) && <text x={position.x + 12} y={position.y + (station.station_id === "KURLA" ? 14 : -7)} paintOrder="stroke" stroke="#f5f8f1" strokeWidth="3" strokeLinejoin="round" style={{ fontSize: active ? 11 : 9, fontWeight: active ? 700 : 400 }}>{station.station_name}</text>}
      </g>;
    })}
    {visibleClusters.map(cluster => {
      const position = project(cluster.centroid!.latitude, cluster.centroid!.longitude), active = selectedCluster === cluster.cluster;
      const radius = 16 + Math.min(11, Math.sqrt(cluster.patient_count || 0));
      return <g key={cluster.cluster} className={styles.clusterMarker} role="button" tabIndex={0} aria-label={`Cluster ${cluster.cluster + 1}, ${count(cluster.patient_count)} patients. View details.`} aria-pressed={active} onClick={() => onCluster(cluster.cluster)} onKeyDown={event => activate(event, () => onCluster(cluster.cluster))}>
        <title>Cluster {cluster.cluster + 1}: {count(cluster.patient_count)} patients</title><circle cx={position.x} cy={position.y} r={radius + 6} fill={color(cluster.cluster)} fillOpacity=".08"/><circle cx={position.x} cy={position.y} r={radius} fill={color(cluster.cluster)} fillOpacity=".88" stroke={active ? "#173e34" : "white"} strokeWidth={active ? 3 : 2}/><text x={position.x} y={position.y + 4} textAnchor="middle" style={{ fill: "white", fontSize: 12, fontWeight: 700 }}>{count(cluster.patient_count)}</text>
      </g>;
    })}
    <g transform={`translate(24,${h - 28})`}><path d={`M0 -4V0H${5 / 111.195 * scale}V-4`} fill="none" stroke="#8da087"/><text x="0" y="13" style={{ fontSize: 8 }}>5 km · approximate</text></g>
  </svg><div className={styles.mapFooter}><div className={styles.legend}><span><i className={styles.mapLegendDot}/>Station count</span><span><i className={styles.mapLegendCluster}/>Cluster aggregate</span><span><i className={styles.mapLegendSuppressed}/>Hidden count</span></div><p className={styles.footnote}>{selected ? `${selected.station_name} · ${selected.suppressed ? "Count hidden" : `${count(selected.patient_count)} patients`} · ${(selected.lines || []).join(" / ")}` : "Select a marker to inspect its aggregate. Circle sizes show patient counts, not cluster radius."}</p><p className={styles.footnote}>Public station anchors and rounded cluster centres only. Simulated catchments; no household locations or external map service.</p></div></>;
}

function ClusterTable({ run, selected, onSelect }: { run: AnalyticsRun<ClusterResult>; selected: number | null; onSelect: (cluster: number) => void }) {
  const detail = run.result.clusters.find(cluster => cluster.cluster === selected);
  return <section className={styles.panel}><PanelHead eyebrow="Result details" title="The groups in this run" description="Local cluster IDs identify groups in this result only. Membership can change with the parameters." action={<span className={styles.methodBadge}>{run.parameters.radius_km} km · minimum {run.parameters.min_samples}</span>}/>
    {!run.result.clusters.length ? <Empty title="No spatial clusters found">The selected observations do not form a dense enough group at these settings. Noise is a valid result.</Empty> : <><div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Cluster</th><th>Patients</th><th>Station areas</th><th>Details</th></tr></thead><tbody>{run.result.clusters.map(cluster => <tr key={cluster.cluster} className={selected === cluster.cluster ? styles.selectedRow : undefined}>
      <td><button type="button" className={styles.clusterButton} onClick={() => onSelect(cluster.cluster)} aria-pressed={selected === cluster.cluster}><span className={styles.swatch} style={{ background: color(cluster.cluster) }}/>Cluster {cluster.cluster + 1}</button></td><td>{cluster.suppressed ? "Hidden" : count(cluster.patient_count)}</td><td>{cluster.suppressed ? "Suppressed" : cluster.stations.map(station => station.station_name).join(", ") || "No station breakdown"}</td><td><button type="button" className={styles.subtleButton} onClick={() => onSelect(cluster.cluster)} aria-label={`Inspect cluster ${cluster.cluster + 1}`}>Inspect <ChevronRight size={10} style={{ display: "inline", verticalAlign: "middle" }}/></button></td>
    </tr>)}</tbody></table></div>{detail && <div className={styles.clusterDetail} aria-live="polite"><h4><span className={styles.swatch} style={{ background: color(detail.cluster) }}/>Cluster {detail.cluster + 1}</h4><p>{detail.suppressed ? "This group is too small to display. Its location and station breakdown are hidden." : `${count(detail.patient_count)} distinct patients with recorded observations in this spatial group. This is a synthetic distribution, not evidence of an outbreak.`}</p>{!detail.suppressed && <div className={styles.chips}>{detail.stations.map(station => <span className={styles.chip} key={station.station_id}>{station.station_name} · {station.suppressed ? "Hidden" : count(station.patient_count)}</span>)}</div>}<dl><div><dt>Observation window (UTC)</dt><dd>{shortDate(run.filters.date_from)} – {shortDate(run.filters.date_to)}</dd></div><div><dt>Method</dt><dd>DBSCAN · Haversine distance</dd></div></dl></div>}</>}
    <details className={styles.dataDetails}><summary>Run details and method notes</summary><p className={styles.runIdentifier}>Saved run: {run.id} · {run.runtime_ms.toFixed(0)} ms · {run.reused ? "Existing saved result" : "New saved result"}</p>{run.result.notes.map((note, i) => <p className={styles.footnote} key={i}>{note}</p>)}</details>
  </section>;
}

function Evaluation({ evaluation, parameters, onParameters }: { evaluation: AnalyticsRun<EvaluationResult>; parameters: AnalyticsParameters; onParameters: (next: AnalyticsParameters) => void }) {
  const result = evaluation.result;
  const radii = [...new Set(result.grid.map(cell => cell.radius_km))].sort((a, b) => a - b);
  const minimums = [...new Set(result.grid.map(cell => cell.min_samples))].sort((a, b) => a - b);
  const recovery = result.synthetic_pattern_recovery;
  return <><div className={styles.evaluationGrid}><div><div className={styles.tableWrap}><table className={styles.table}><caption className={styles.footnote} style={{ textAlign: "left", marginBottom: 9 }}>Radius × minimum samples. Select a cell to use its settings.</caption><thead><tr><th>Radius</th>{minimums.map(minimum => <th key={minimum}>Min. {minimum}</th>)}</tr></thead><tbody>{radii.map(radius => <tr key={radius}><td>{radius} km</td>{minimums.map(minimum => {
    const cell = result.grid.find(value => value.radius_km === radius && value.min_samples === minimum);
    const active = radius === parameters.radius_km && minimum === parameters.min_samples;
    return <td key={minimum} className={active ? styles.selectedRow : undefined}>{cell && <button type="button" className={`${styles.subtleButton} ${styles.gridCell}`} style={{ textDecoration: "none", textAlign: "left" }} aria-pressed={active} aria-label={`Use ${radius} kilometre radius, minimum ${minimum} samples. ${count(cell.cluster_count)} clusters. Silhouette ${score(cell.silhouette)}.`} onClick={() => onParameters({ radius_km: radius, min_samples: minimum })}><strong>{count(cell.cluster_count)} groups {active && <Check size={11} style={{ display: "inline" }}/>}</strong><span>Sil. {cell.silhouette.value == null ? "N/A" : cell.silhouette.value.toFixed(3)}</span><small>Noise {percent(cell.noise_fraction)}</small>{cell.silhouette.value == null && <small>{reason(cell.silhouette.reason)}</small>}</button>}</td>;
  })}</tr>)}</tbody></table></div><p className={styles.footnote} style={{ marginTop: 11 }}>A higher silhouette alone does not identify the best setting. Compare group size, noise, coverage, and stability; then run clustering to inspect your choice.</p></div>
    <div className={styles.stability}><h4>Stability under small changes</h4><p>Mean adjusted Rand index across {result.stability.repeats.length} repeats, keeping {percent(result.stability.subsample_fraction)} of observations and perturbing coordinates by {(result.stability.perturbation_km * 1000).toFixed(0)} m.</p><strong>{score(result.stability.mean_adjusted_rand_index)}</strong><small>{result.stability.mean_adjusted_rand_index.value == null ? reason(result.stability.mean_adjusted_rand_index.reason) : "Agreement on patients shared between runs; 1 means identical grouping."}</small><p style={{ marginTop: 12 }}>Evaluated at {result.selected.radius_km} km / minimum {result.selected.min_samples}. Changing the selected grid cell does not recalculate these scores.</p><details className={styles.dataDetails}><summary>View repeat scores</summary><table><thead><tr><th>Repeat</th><th>Shared patients</th><th>ARI</th></tr></thead><tbody>{result.stability.repeats.map(repeat => <tr key={repeat.repeat}><td>{repeat.repeat}</td><td>{count(repeat.shared_patients)}</td><td>{score(repeat.adjusted_rand_index)}{repeat.adjusted_rand_index.value == null && <small>{reason(repeat.adjusted_rand_index.reason)}</small>}</td></tr>)}</tbody></table></details></div>
  </div><div className={styles.metricGrid} style={{ marginTop: 20 }}><Metric title="Synthetic pattern recovery · ARI" value={score(recovery.adjusted_rand_index)} description={recovery.adjusted_rand_index.value == null ? reason(recovery.adjusted_rand_index.reason || recovery.reason) : "Agreement with deliberately planted reference groups, assessed only after fitting. This is not diagnostic accuracy."}/><Metric title="Recovery evaluation coverage" value={percent(recovery.coverage)} description={`${count(recovery.evaluated_patients)} patients evaluated. Only matching primary-disease labels are eligible.`}/></div><p className={styles.footnote} style={{ marginTop: 12 }}>{recovery.background_convention}</p><div className={styles.notice} style={{ marginTop: 16 }}><FlaskConical size={16}/><span>The September examples are deliberately easy. High scores measure recovery of this simulation; independent seeds and harder scenarios are still needed to assess generalization.</span></div><details className={styles.dataDetails}><summary>Evaluation notes and saved run</summary><p className={styles.runIdentifier}>{evaluation.id} · {evaluation.runtime_ms.toFixed(0)} ms · {evaluation.reused ? "Saved result reused" : "New saved evaluation"}</p>{result.notes.map((note, i) => <p className={styles.footnote} key={i}>{note}</p>)}</details></>;
}

function AnalyticsWorkspace({ catalog, datasetId }: { catalog: AnalyticsCatalog; datasetId: string }) {
  const initial: AnalyticsFilters = {
    dataset_id: datasetId,
    disease_code: catalog.defaults.disease_code || "DENGUE", line: "", station_id: "",
    date_from: catalog.defaults.date_from || "2026-09-01", date_to: catalog.defaults.date_to || "2026-09-29",
  };
  const [draft, setDraft] = useState(initial), [filters, setFilters] = useState(initial);
  const [parameters, setParameters] = useState<AnalyticsParameters>({ radius_km: catalog.defaults.radius_km || .5, min_samples: catalog.defaults.min_samples || 5 });
  const [run, setRun] = useState<AnalyticsRun<ClusterResult> | null>(null);
  const [evaluation, setEvaluation] = useState<AnalyticsRun<EvaluationResult> | null>(null);
  const [busy, setBusy] = useState<"cluster" | "evaluation" | "reload" | null>(null), [error, setError] = useState("");
  const [selectedCluster, setSelectedCluster] = useState<number | null>(null), [selectedStation, setSelectedStation] = useState<string | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const summary = useQuery<AnalyticsSummary>(queryPath(filters));
  const conditions = useQuery<AnalyticsSummary>(queryPath({ ...filters, disease_code: "" }));
  const dirty = JSON.stringify(draft) !== JSON.stringify(filters);
  const dataset = catalog.datasets.find(value => value.dataset_id === filters.dataset_id) || catalog.datasets[0];
  const stations = catalog.stations.filter(station => !draft.line || station.lines.includes(draft.line));
  const diseaseLabel = catalog.diseases.find(disease => disease.disease_code === filters.disease_code)?.label || "All conditions";
  const setField = (key: keyof AnalyticsFilters, value: string) => setDraft(current => ({ ...current, [key]: value, ...(key === "line" ? { station_id: "" } : {}) }));
  function apply(next: AnalyticsFilters) {
    if (busy) return;
    if (next.date_from > next.date_to) { setError("The start date must be on or before the end date."); return; }
    setError(""); setFilters({ ...next }); setRun(null); setEvaluation(null); setSelectedCluster(null); setSelectedStation(null);
  }
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); apply(draft); }
  async function runAnalysis(kind: "cluster" | "evaluation") {
    if (busy) return;
    if (dirty) { setError("Apply your updated cohort filters before running an analysis."); return; }
    if (!filters.disease_code) { setError("Choose one condition and apply the filters before clustering or evaluation."); return; }
    if (!Number.isFinite(parameters.radius_km) || parameters.radius_km < .1 || parameters.radius_km > 3 || !Number.isInteger(parameters.min_samples) || parameters.min_samples < 3 || parameters.min_samples > 30) { setError("Use a radius from 0.1 to 3 km and a minimum of 3 to 30 samples."); return; }
    setError(""); setBusy(kind);
    try {
      const result = await post<AnalyticsRun<ClusterResult> | AnalyticsRun<EvaluationResult>>(`/admin/analytics/${kind === "cluster" ? "cluster" : "evaluation"}-runs/`, { ...filters, ...parameters });
      if (!alive.current) return;
      if (result.status !== "completed") throw new Error("This analysis did not complete. Please try again.");
      if (kind === "cluster") { const clusterRun = result as AnalyticsRun<ClusterResult>; setRun(clusterRun); setSelectedCluster(clusterRun.result.clusters.find(cluster => !cluster.suppressed)?.cluster ?? null); setSelectedStation(null); }
      else setEvaluation(result as AnalyticsRun<EvaluationResult>);
    } catch (caught) { if (alive.current) setError(message(caught)); }
    finally { if (alive.current) setBusy(null); }
  }
  async function reloadRun() {
    if (!run || busy) return;
    setBusy("reload"); setError("");
    try { const result = await api<AnalyticsRun<ClusterResult>>(`/admin/analytics/cluster-runs/${encodeURIComponent(run.id)}/`); if (alive.current) setRun(result); }
    catch (caught) { if (alive.current) setError(message(caught)); }
    finally { if (alive.current) setBusy(null); }
  }
  const data = summary.data;
  const visibleStations = data?.stations.filter(station => !station.suppressed && station.patient_count != null && station.patient_count > 0).length || 0;
  const selectCluster = (value: number) => { setSelectedCluster(value); setSelectedStation(null); };
  return <div className={styles.workspace}>
    <div className={styles.hero}><div><span className={styles.tag}><FlaskConical size={12}/>Synthetic data · research workspace</span><h3>Explore patterns across connected communities.</h3><p>Recorded conditions across Mumbai&apos;s station areas, with transparent clustering and evaluation.</p></div><div className={styles.heroStats}><div><strong>{count(dataset.patient_count)}</strong><span>fictional patients</span></div><div><strong>{catalog.stations.length}</strong><span>station areas</span></div></div></div>
    <section className={styles.panel}><PanelHead eyebrow="Cohort selection" title="Choose what to explore" description={`Dataset snapshot: ${shortDate(dataset.as_of)} ${dataset.as_of.slice(0, 4)} · dates use UTC calendar days.`} action={<span className={styles.iconBox}><SlidersHorizontal size={17}/></span>}/><form onSubmit={submit}><fieldset disabled={!!busy} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}><div className={styles.filters}>
      <label>Condition<select value={draft.disease_code} onChange={event => setField("disease_code", event.target.value)}><option value="">All conditions</option>{catalog.diseases.map(disease => <option key={disease.disease_code} value={disease.disease_code}>{disease.label}</option>)}</select></label>
      <label>Railway line<select value={draft.line} onChange={event => setField("line", event.target.value)}><option value="">All three lines</option>{catalog.lines.map(line => <option key={line}>{line}</option>)}</select></label>
      <label>Station area<select value={draft.station_id} onChange={event => setField("station_id", event.target.value)}><option value="">All station areas</option>{stations.map(station => <option key={station.station_id} value={station.station_id}>{station.station_name}</option>)}</select></label>
      <label>From<input type="date" required min={dataset.observation_start} max={dataset.as_of} value={draft.date_from} onChange={event => setField("date_from", event.target.value)}/></label>
      <label>Through<input type="date" required min={dataset.observation_start} max={dataset.as_of} value={draft.date_to} onChange={event => setField("date_to", event.target.value)}/></label>
    </div><div className={styles.filterFooter}><p>{dirty ? "Filters changed. Apply to update this view." : `${diseaseLabel} · ${shortDate(filters.date_from)} – ${shortDate(filters.date_to)} · ${filters.line || "All lines"}`}</p><div className={styles.actions}><button type="button" className="button quiet small" onClick={() => { setDraft(initial); setParameters({ radius_km: .5, min_samples: 5 }); apply(initial); }}>Reset demo</button><button type="submit" className="button primary small" disabled={!!busy || summary.loading}>Apply filters <ArrowRight size={13}/></button></div></div></fieldset></form></section>
    {error && <ErrorNotice text={error}/>}
    {summary.loading ? <div className={styles.skeleton} role="status" aria-label="Loading aggregate analytics"><span/><span/></div> : summary.error ? <ErrorNotice text={summary.error} retry={summary.reload}/> : data && <>
      <div className={styles.kpis}><div className={styles.kpi}><div className={styles.kpiTop}>Distinct patients<UsersRound size={16}/></div><strong>{count(data.counts.distinct_patients)}</strong><small>With recorded observations in this cohort</small></div><div className={styles.kpi}><div className={styles.kpiTop}>Recorded observations<Activity size={16}/></div><strong>{count(data.counts.observations)}</strong><small>Repeat visits can belong to one patient</small></div><div className={styles.kpi}><div className={styles.kpiTop}>Visible station areas<MapPin size={16}/></div><strong>{visibleStations}</strong><small>Areas with a reportable patient count</small></div><div className={styles.kpi}><div className={styles.kpiTop}>Missing coordinates<Compass size={16}/></div><strong>{count(data.counts.missing_coordinates)}</strong><small>Excluded from spatial clustering</small></div></div>
      {data.counts.distinct_patients === 0 ? <section className={styles.panel}><Empty title="No patients match these filters">Choose another condition, a different area, or a wider date range.</Empty></section> : <div className={styles.grid}><section className={`${styles.panel} ${styles.mapPanel}`}><PanelHead eyebrow="Geographic view" title="Station-area distribution" description={`${diseaseLabel} · ${run ? "Aggregate cluster overlay" : "Patient counts at public station anchors"}`} action={<span className={styles.iconBox}><MapPin size={17}/></span>}/><StationMap stations={catalog.stations} summary={data} clusters={run?.result.clusters || []} selectedCluster={selectedCluster} onCluster={selectCluster} selectedStation={selectedStation} onStation={value => { setSelectedStation(value); setSelectedCluster(null); }}/></section>
        <div className={styles.sideStack}><section className={styles.panel}><PanelHead eyebrow="Spatial grouping" title="Find dense groups" description="DBSCAN groups nearby observations. One patient contributes once per condition in this window." action={<span className={styles.methodBadge}>DBSCAN</span>}/><div className={styles.parameters}><label>Neighbourhood radius<input aria-label="Neighbourhood radius in kilometres" type="number" min="0.1" max="3" step="0.1" value={Number.isNaN(parameters.radius_km) ? "" : parameters.radius_km} disabled={!!busy} onChange={event => setParameters(current => ({ ...current, radius_km: event.target.valueAsNumber }))}/><small>Kilometres · 0.1 to 3</small></label><label>Minimum samples<input type="number" min="3" max="30" step="1" value={Number.isNaN(parameters.min_samples) ? "" : parameters.min_samples} disabled={!!busy} onChange={event => setParameters(current => ({ ...current, min_samples: event.target.valueAsNumber }))}/><small>Includes the point itself</small></label></div><button type="button" className="button primary wide" disabled={!!busy || dirty || !filters.disease_code || data.counts.distinct_patients === 0} onClick={() => runAnalysis("cluster")}>{busy === "cluster" ? <LoaderCircle size={15} className="spin"/> : <ScanSearch size={15}/>} {busy === "cluster" ? "Finding groups…" : "Run clustering"}</button>{!filters.disease_code && <p className={styles.footnote} style={{ marginTop: 9 }}>Select one condition to enable clustering.</p>}<div className={styles.runNote}><CircleHelp size={13}/><span>Radius connects neighbours; it does not set the maximum size of a whole cluster. Clusters are spatial groups, not disease predictions.</span></div></section>
        <section className={styles.panel}><PanelHead title={run ? "How this run performed" : "Evaluation at a glance"} description={run ? `${run.parameters.radius_km} km radius · minimum ${run.parameters.min_samples}` : "Run clustering to see computed metrics. Nothing is estimated in advance."}/>{run ? <><div className={styles.metricGrid}><Metric title="Spatial groups" value={count(run.result.counts.cluster_count)} description="Groups found at these settings"/><Metric title="Noise" value={percent(run.result.metrics.noise_fraction)} description={run.result.metrics.noise_fraction == null ? "Hidden when a small count could be inferred, or unavailable for this cohort." : "Patients not assigned to a cluster"}/><Metric title="Silhouette" value={score(run.result.metrics.silhouette)} description={run.result.metrics.silhouette.value == null ? reason(run.result.metrics.silhouette.reason) : `Geometric separation, not clinical accuracy. Scored sample: ${count(run.result.metrics.silhouette.sample_size)}.`}/><Metric title="Silhouette coverage" value={percent(run.result.metrics.silhouette.coverage)} description={run.result.metrics.silhouette.coverage == null ? "Unavailable or hidden for small-group protection." : "Share of eligible points in non-noise clusters"}/></div><button type="button" className={styles.subtleButton} style={{ marginTop: 14 }} onClick={reloadRun} disabled={!!busy}><RefreshCw size={11} style={{ display: "inline", verticalAlign: "middle", marginRight: 4 }}/>Reload saved result</button></> : <Empty title="Ready when you are">Results will include groups, noise, silhouette, and the portion of data evaluated.</Empty>}</section></div></div>}
      {busy && <div className={styles.status} role="status"><LoaderCircle className="spin" size={16}/>{busy === "evaluation" ? "Evaluating 16 parameter settings and stability repeats…" : busy === "reload" ? "Loading the saved run…" : "Calculating spatial groups and metrics…"}</div>}
      {run && <ClusterTable run={run} selected={selectedCluster} onSelect={selectCluster}/>}
      <div className={styles.equalGrid}><section className={styles.panel}><PanelHead eyebrow="Condition mix" title="Recorded conditions" description="All conditions in the same area and date window. Patients with multiple conditions can appear more than once." action={<span className={styles.iconBox}><BarChart3 size={17}/></span>}/>{conditions.loading ? <div className={styles.status} role="status"><LoaderCircle size={15} className="spin"/>Loading condition counts…</div> : conditions.error ? <ErrorNotice text={conditions.error} retry={conditions.reload}/> : <Bars rows={(conditions.data?.diseases || []).map(row => ({ key: row.disease_code, label: row.label, value: row.patient_count, suppressed: row.suppressed }))}/>}</section><section className={styles.panel}><PanelHead eyebrow="Selected cohort" title="Age distribution" description="Age at the latest recorded observation in this window. Counts are distinct patients in each displayed band." action={<span className={styles.iconBox}><UsersRound size={17}/></span>}/><Bars muted rows={data.age_bands.map(row => ({ key: row.age_band, label: row.age_band, value: row.patient_count, suppressed: row.suppressed }))}/></section></div>
      <div className={styles.equalGrid}><section className={styles.panel}><PanelHead eyebrow="Over time" title="Weekly recorded patients" description="Weeks can overlap in patient membership. These are recorded observations, not disease incidence. Hidden counts appear as gaps." action={<span className={styles.iconBox}><Activity size={17}/></span>}/><WeeklyChart rows={data.weekly || []}/></section><section className={styles.panel}><PanelHead eyebrow="Area comparison" title="Patients by station area" description="Up to eight leading areas in the selected cohort. Small counts remain hidden." action={<span className={styles.iconBox}><Layers3 size={17}/></span>}/><Bars rows={[...data.stations].sort((a, b) => (b.patient_count ?? -1) - (a.patient_count ?? -1)).slice(0, 8).map(row => ({ key: row.station_id, label: row.station_name, value: row.patient_count, suppressed: row.suppressed }))}/><details className={styles.dataDetails}><summary>View all areas and line totals</summary><div className={styles.tableWrap}><table><thead><tr><th>Station area</th><th>Patients</th></tr></thead><tbody>{data.stations.map(station => <tr key={station.station_id}><td>{station.station_name}</td><td>{station.suppressed ? "Hidden" : count(station.patient_count)}</td></tr>)}</tbody></table></div><div className={styles.chips}>{data.lines.map(line => <span className={styles.chip} key={line.line}>{line.line} · {line.suppressed ? "Hidden" : count(line.patient_count)}</span>)}</div><p className={styles.footnote} style={{ marginTop: 10 }}>Line memberships overlap at interchanges. Do not add line totals.</p></details></section></div>
      <section className={styles.panel}><PanelHead eyebrow="Compare, then interpret" title="Parameter explorer & stability" action={<span className={styles.iconBox}><FlaskConical size={17}/></span>}/><div className={styles.evaluationIntro}><p>Compare 16 radius/sample combinations, check stability under small changes, and assess recovery of deliberately planted groups. Scores are calculated on this synthetic cohort.</p><div className={styles.actions}><button type="button" className="button secondary small" disabled={!!busy || dirty || !filters.disease_code || data.counts.distinct_patients === 0} onClick={() => runAnalysis("evaluation")}>{busy === "evaluation" ? <LoaderCircle className="spin" size={14}/> : <FlaskConical size={14}/>} {busy === "evaluation" ? "Evaluating…" : evaluation ? "Re-run evaluation" : "Run evaluation"}</button></div></div>{evaluation ? <Evaluation evaluation={evaluation} parameters={parameters} onParameters={setParameters}/> : <div className={styles.metricGrid}><Metric title="Parameter grid" value="16 settings" description="Four radii × four minimum sample counts"/><Metric title="Stability check" value="3 repeats" description="Seeded subsampling with small coordinate perturbations"/></div>}</section>
      <div className={styles.notice}><ShieldCheck size={17}/><span><strong>Synthetic research view.</strong> Counts below {catalog.suppression_threshold} and related values may be hidden. Overlapping filters are not an anonymization guarantee. These results do not establish outbreaks, incidence, transmission, or diagnostic accuracy.</span></div>
    </>}
  </div>;
}

export function AdminAnalytics() {
  const [requestedDataset, setRequestedDataset] = useState("");
  const catalog = useQuery<AnalyticsCatalog>(`/admin/analytics/catalog/${requestedDataset ? `?dataset_id=${encodeURIComponent(requestedDataset)}` : ""}`);
  if (catalog.loading) return <div className={styles.status} role="status"><LoaderCircle size={18} className="spin"/>Loading the analytics workspace…</div>;
  if (catalog.error) return <ErrorNotice text={catalog.error} retry={catalog.reload}/>;
  if (!catalog.data?.datasets.length || !catalog.data.stations.length) return <section className={styles.panel}><Empty title="No analytics dataset is available">Import the approved synthetic dataset to enable cohort summaries, station-area maps, and clustering.</Empty><div style={{ textAlign: "center" }}><button type="button" className="button secondary small" onClick={catalog.reload}><Database size={14}/>Check for a dataset</button></div></section>;
  const datasetId = requestedDataset || catalog.data.defaults.dataset_id || catalog.data.datasets[0].dataset_id;
  return <>{catalog.data.datasets.length > 1 && <label className="field" style={{ maxWidth: 400, marginBottom: 18 }}><span>Analytics dataset</span><select value={datasetId} onChange={event => setRequestedDataset(event.target.value)}>{catalog.data.datasets.map(dataset => <option key={dataset.dataset_id} value={dataset.dataset_id}>{dataset.dataset_id}</option>)}</select></label>}<AnalyticsWorkspace key={datasetId} catalog={catalog.data} datasetId={datasetId}/></>;
}
