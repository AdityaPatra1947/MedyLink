"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Activity, ArrowRight, Bell, ClipboardList, Download, Droplets, FileText, FlaskConical, HeartPulse, X } from "lucide-react";
import { date, dateTime } from "@/lib/api";
import type { Profile, User } from "@/lib/types";
import type { PatientDashboardData, VitalReading } from "@/lib/patient-dashboard-types";
import { Empty, Panel, QueryState, Refresh, useQuery } from "./ui";
import { PatientVisits } from "./patient-visits";
import { AdherenceTracking, LabTracking } from "./patient-health-tracking";
import { HealthScoreDetails } from "./patient-score-details";
import styles from "./patient-dashboard.module.css";

type Detail = "score" | "adherence" | "labs" | "alerts" | "notifications" | "pressure" | "glucose";
const titles: Record<Detail, string> = { score: "Health score", adherence: "Medication adherence", labs: "Lab results", alerts: "Regional health alerts", notifications: "Recent notifications", pressure: "Blood pressure readings", glucose: "Blood sugar readings" };

function Dialog({ title, close, children }: { title: string; close: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog?.showModal();
    return () => { dialog?.close(); trigger?.focus(); };
  }, []);
  return <dialog ref={ref} className={styles.dialog} aria-labelledby="patient-detail-title" onCancel={event => { event.preventDefault(); close(); }}>
    <div className={styles.dialogHead}><h2 id="patient-detail-title">{title}</h2><button type="button" className="button quiet small" aria-label="Close" onClick={close}><X size={20}/></button></div>
    <div className={styles.dialogBody}>{children}</div>
  </dialog>;
}

function readingValue(reading: VitalReading, pressure: boolean) { return pressure ? `${reading.systolic}/${reading.diastolic}` : String(reading.value); }

function Trend({ readings, pressure }: { readings: VitalReading[]; pressure: boolean }) {
  const [selected, setSelected] = useState<number | null>(null);
  const name = pressure ? "Blood pressure" : "Blood sugar";
  const unit = pressure ? "mmHg" : "mg/dL";
  if (!readings.length) return <div className={styles.chartEmpty}><p>No {name.toLowerCase()} readings yet.</p><p className="progress-note">Readings appear here when your doctor records them during a consultation.</p></div>;
  const values = readings.flatMap(row => pressure ? [row.systolic!, row.diastolic!] : [row.value!]);
  const minimum = Math.min(...values), maximum = Math.max(...values);
  const padding = Math.max((maximum - minimum) * .15, 5);
  const low = Math.max(0, minimum - padding), high = maximum + padding;
  const x = (index: number) => readings.length === 1 ? 246 : 50 + index / (readings.length - 1) * 392;
  const y = (value: number) => 180 - (value - low) / (high - low) * 155;
  const selectedIndex = selected !== null && selected < readings.length ? selected : readings.length - 1;
  const active = readings[selectedIndex];
  const line = (key: "systolic" | "diastolic" | "value") => readings.map((row, index) => `${x(index)},${y(row[key]!)}`).join(" ");
  return <div>
    <p className={styles.chartIntro}>Your {readings.length === 1 ? "most recent reading" : `${readings.length} most recent readings`} · {unit}. Select a point to view its source.</p>
    <div className={styles.legend}>{pressure ? <><span><i/>Systolic</span><span><i/>Diastolic</span></> : <span><i/>Blood sugar</span>}</div>
    <svg className={styles.chart} viewBox="0 0 470 222" role="group" aria-label={`${name} trend chart`}>
      {[0, 1, 2, 3].map(index => { const value = low + (high - low) * index / 3; return <g key={index}><line x1="50" x2="442" y1={y(value)} y2={y(value)} stroke="#dce5df" strokeDasharray="3 5"/><text x="39" y={y(value) + 4} textAnchor="end">{Math.round(value)}</text></g>; })}
      <polyline points={line(pressure ? "systolic" : "value")} fill="none" stroke="#146c56" strokeWidth="2.5"/>
      {pressure && <polyline points={line("diastolic")} fill="none" stroke="#367eaa" strokeWidth="2.5"/>}
      {readings.map((row, index) => <g key={`${row.report_id || row.record_id}:${row.recorded_at}`} className={styles.point} role="button" tabIndex={0} aria-label={`${name} reading ${index + 1}: ${readingValue(row, pressure)} ${unit}, ${date(row.recorded_at)}`} aria-pressed={selectedIndex === index} onFocus={() => setSelected(index)} onMouseEnter={() => setSelected(index)} onClick={() => setSelected(index)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelected(index); } }}>
        <rect x={x(index) - 14} y={Math.min(y(pressure ? row.systolic! : row.value!), y(pressure ? row.diastolic! : row.value!)) - 14} width="28" height={Math.abs(y(pressure ? row.systolic! : row.value!) - y(pressure ? row.diastolic! : row.value!)) + 28} fill="transparent"/>
        <circle cx={x(index)} cy={y(pressure ? row.systolic! : row.value!)} r="12" fill="transparent"/>
        {pressure && <circle cx={x(index)} cy={y(row.diastolic!)} r={selectedIndex === index ? 5 : 3.5} fill="#367eaa"/>}
        <circle cx={x(index)} cy={y(pressure ? row.systolic! : row.value!)} r={selectedIndex === index ? 6 : 4} fill="#146c56"/>
      </g>)}
      <text x={readings.length === 1 ? "246" : "50"} y="209" textAnchor={readings.length === 1 ? "middle" : "start"}>{date(readings[0].recorded_at)}</text>
      {readings.length > 1 && <text x="442" y="209" textAnchor="end">{date(readings[readings.length - 1].recorded_at)}</text>}
    </svg>
    <div className={styles.selected} role="status" aria-live="polite"><strong>{readingValue(active, pressure)} {unit} · {dateTime(active.recorded_at)}</strong><p>{active.source} · {active.author}{active.context ? ` · ${active.context}` : ""}</p>{active.view_url && <a href={active.view_url} target="_blank" rel="noopener noreferrer">View source report ↗</a>}</div>
    <details className={styles.readings}><summary>View {name.toLowerCase()} readings</summary><div className="table-wrap section-gap"><table><caption>{name} readings</caption><thead><tr><th>Date</th><th>{pressure ? "Systolic / diastolic" : "Value"}</th><th>Source</th></tr></thead><tbody>{readings.map(row => <tr key={`${row.report_id || row.record_id}:${row.recorded_at}`}><td>{dateTime(row.recorded_at)}</td><td>{readingValue(row, pressure)} {unit}{row.context && <small>{row.context}</small>}</td><td>{row.author}<small>{row.source}</small>{row.view_url && <a href={row.view_url} target="_blank" rel="noopener noreferrer">View report ↗</a>}</td></tr>)}</tbody></table></div></details>
  </div>;
}

function Metric({ label, value, note, icon, onClick }: { label: string; value: ReactNode; note: string; icon: ReactNode; onClick?: () => void }) {
  const content = <><span className={styles.metricTop}>{label}{icon}</span><strong>{value}</strong><small>{note}</small></>;
  return onClick ? <button type="button" className={styles.metric} aria-label={label} onClick={onClick}>{content}</button> : <div className={styles.metric} role="group" aria-label={label}>{content}</div>;
}

export function PatientDashboard({ profile, user, navigate, showVisits = true }: { profile: Profile; user: User; navigate: (tab: string) => void; showVisits?: boolean }) {
  const query = useQuery<PatientDashboardData>("/patients/me/dashboard/");
  const reloadDashboard = query.reload;
  useEffect(() => {
    window.addEventListener("medylink:patient-health-updated", reloadDashboard);
    return () => window.removeEventListener("medylink:patient-health-updated", reloadDashboard);
  }, [reloadDashboard]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const data = query.data;
  function go(tab: string) { setDetail(null); navigate(tab); }
  const pressure = data?.latest.blood_pressure, glucose = data?.latest.blood_sugar;
  return <div className="stack" data-testid="patient-dashboard">
    <div className={styles.toolbar}><p>Your health overview, based on your saved records.</p><div className="inline-actions"><button type="button" className="button secondary small" onClick={() => setDetail("notifications")}><Bell size={16}/>Recent notifications</button><Refresh onClick={query.reload}/></div></div>
    <QueryState query={query}>{data && <>
      <div className={styles.summaryGrid}>
        <Panel className={styles.summaryPanel}>
          <div className={styles.scoreRow}><button type="button" className={styles.score} aria-label="Health score details" onClick={() => setDetail("score")}><strong>{data.health_score?.value ?? "—"}</strong><small>{data.health_score ? "out of 100" : "Not available"}</small></button><div className={styles.scoreInfo}><h2>Health score</h2><p>{data.health_score ? data.health_score.label : "Your score appears when a calculation policy and the required health data are available."}</p>{data.health_score?.disclaimer && <small className={styles.scoreDisclaimer}>Custom demo score · not a clinical assessment</small>}</div></div>
          <div className={styles.summaryActions}><button type="button" aria-label="Medication adherence" onClick={() => setDetail("adherence")}><span>Adherence</span><strong>{data.adherence ? `${data.adherence.percentage}%` : "Not available"}</strong><small className={styles.metricHint}>View calculation</small></button><div role="group" aria-label="Chronic conditions"><span>Active conditions</span><strong>{data.counts.conditions}</strong></div></div>
        </Panel>
        <div className={styles.identityGrid}>
          <div className={styles.identity} role="group" aria-label="Patient ID"><span>Patient ID</span><strong>{profile.account_id}</strong><small>Your permanent account identity</small></div>
          <div className={styles.identity} role="group" aria-label="Blood group"><span><Droplets size={15}/>Blood group</span><strong>{profile.blood_group && profile.blood_group !== "unknown" ? profile.blood_group : "Unknown"}</strong></div>
          <button type="button" className={styles.alert} aria-label="Regional health alerts" onClick={() => setDetail("alerts")}><Bell size={21}/><span><strong>Health alerts in your region</strong><small>{data.regional_alerts.available ? data.regional_alerts.items.length ? `${data.regional_alerts.items.length} alerts available` : "No current alerts in the connected feed" : "Regional alert feed not connected"}</small></span><ArrowRight size={16}/></button>
        </div>
      </div>
      <div className={styles.metrics}>
        <Metric label="Medical records" value={data.counts.records} note="Consultations in your history" icon={<FileText size={18}/>}/>
        <Metric label="Active prescriptions" value={data.counts.active_prescriptions} note="Valid, with medicine remaining" icon={<ClipboardList size={18}/>}/>
        <Metric label="Latest blood pressure" value={pressure ? readingValue(pressure, true) : "—"} note={pressure ? `mmHg · ${date(pressure.recorded_at)}` : "No readings recorded"} icon={<HeartPulse size={18}/>} onClick={() => setDetail("pressure")}/>
        <Metric label="Blood sugar" value={glucose?.value ?? "—"} note={glucose ? `mg/dL · ${date(glucose.recorded_at)}` : "No readings recorded"} icon={<Activity size={18}/>} onClick={() => setDetail("glucose")}/>
        <Metric label="Abnormal lab values" value={data.lab_summary.abnormal ?? "—"} note={data.lab_summary.total === null ? "No tracked tests yet" : `${data.lab_summary.total} tracked tests · review results`} icon={<FlaskConical size={18}/>} onClick={() => setDetail("labs")}/>
        <Metric label="Report downloads" value={data.counts.report_downloads} note={`${data.counts.reports} reports available`} icon={<Download size={18}/>}/>
      </div>
      <div className={styles.charts}><Panel title="Blood pressure" action={<HeartPulse size={19}/>}><Trend readings={data.trends.blood_pressure} pressure/></Panel><Panel title="Blood sugar" action={<Activity size={19}/>}><Trend readings={data.trends.blood_sugar} pressure={false}/></Panel></div>
    </>}</QueryState>
    {showVisits && <PatientVisits user={user} preview navigate={go}/>}
    {detail && <Dialog title={titles[detail]} close={() => setDetail(null)}>
      {detail === "score" && <>{data?.health_score ? <HealthScoreDetails score={data.health_score}/> : <><p>Health score is not available.</p><p>{data?.health_score_reason || "A calculation policy and the required health measurements are needed before a score can be calculated."}</p></>}</>}
      {detail === "adherence" && <AdherenceTracking onChanged={query.reload}/>}
      {detail === "labs" && <LabTracking onChanged={query.reload}/>}
      {detail === "pressure" && <Trend readings={data?.trends.blood_pressure ?? []} pressure/>}
      {detail === "glucose" && <Trend readings={data?.trends.blood_sugar ?? []} pressure={false}/>}
      {detail === "alerts" && <>{!data?.regional_alerts.available ? <><p>A regional health alert feed is not connected yet.</p><p>The dashboard cannot currently confirm whether there are outbreaks or alerts in your area.</p></> : data.regional_alerts.items.length ? data.regional_alerts.items.map(alert => <article key={alert.id} className="substack"><h3>{alert.title}</h3><p>{alert.description}</p><small>{alert.region} · {dateTime(alert.published_at)}</small><a href={alert.source_url} target="_blank" rel="noopener noreferrer">Read the original health alert ↗</a></article>) : <p>No current alerts were returned by the connected feed.</p>}</>}
      {detail === "notifications" && <>{data?.recent_notifications.length ? <div>{data.recent_notifications.map(item => <article key={item.id} className={styles.notification}><div><strong>{item.title}</strong><small>{dateTime(item.created_at)}</small></div><button type="button" className="button secondary small" aria-label={`View ${item.title}`} onClick={() => go(item.target_tab)}>View {item.kind === "record" ? "record" : item.kind === "report" ? "report" : "prescription"}</button></article>)}</div> : <Empty title="No recent notifications.">New consultations, prescriptions, and uploaded reports will appear here.</Empty>}</>}
    </Dialog>}
  </div>;
}
