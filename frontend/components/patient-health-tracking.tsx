"use client";

import { useState } from "react";
import { api, date, dateTime, post, values } from "@/lib/api";
import type { AdherenceSummary } from "@/lib/patient-dashboard-types";
import { AsyncForm, Badge, Empty, Field, QueryState, Refresh, useQuery } from "./ui";
import styles from "./patient-dashboard.module.css";

type AdherenceLog = { id: string; date: string; scheduled_doses: number; taken_doses: number };
type AdherenceResponse = { results: AdherenceLog[]; summary: AdherenceSummary | null };
type Lab = { id: string; name: string; value: number; unit: string; reference_low: number | null; reference_high: number | null; flag: string; measured_at: string; recorded_by_name: string; source: string; report_id: string | null };
type LabResponse = { results: Lab[]; next: number | null; summary: { abnormal: number | null; total: number | null } };
function localDateTime() { const now = new Date(); return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 16); }

export function AdherenceTracking({ onChanged }: { onChanged: () => void }) {
  const query = useQuery<AdherenceResponse>("/patients/me/adherence/");
  const [today] = useState(() => new Date().toISOString().slice(0, 10));
  const [earliest] = useState(() => new Date(Date.now() - 29 * 86400000).toISOString().slice(0, 10));
  const [day, setDay] = useState(today);
  const [scheduled, setScheduled] = useState<string>();
  const [taken, setTaken] = useState<string>();
  const existing = query.data?.results.find(item => item.date === day);
  const scheduledValue = scheduled ?? existing?.scheduled_doses ?? "";
  const takenValue = taken ?? existing?.taken_doses ?? "";
  return <div className="stack">
    <p className="progress-note">Track doses you actually took against the doses prescribed for each day. Your 30-day adherence is total taken ÷ total scheduled, using logged days only. A pharmacy collection is not counted as a taken dose.</p>
    <QueryState query={query}><div className="stack">
      {query.data?.summary ? <section className={styles.calculation} aria-label="Adherence calculation">
        <div className={styles.calculationResult}><strong>{query.data.summary.percentage}<small>%</small></strong><span>{query.data.summary.taken_doses} of {query.data.summary.scheduled_doses} scheduled doses across {query.data.summary.days_logged} logged days.</span></div>
        <h3>How adherence is calculated</h3>
        <p className={styles.formula}>{query.data.summary.formula || "Adherence (%) = (total doses taken ÷ total scheduled doses) × 100"}</p>
        <p className={styles.formula}>({query.data.summary.taken_doses} ÷ {query.data.summary.scheduled_doses}) × 100 = {query.data.summary.percentage}%</p>
        <p>{query.data.summary.explanation || "The calculation uses your saved dose logs in the last 30 days. Unlogged days are excluded, so this describes recorded doses only."}</p>
        {query.data.summary.period_start && query.data.summary.period_end && <p className="progress-note">{date(query.data.summary.period_start)} – {date(query.data.summary.period_end)} · {query.data.summary.days_logged} of {query.data.summary.period_days} days logged{typeof query.data.summary.missing_days === "number" ? ` · ${query.data.summary.missing_days} days unlogged` : ""}.</p>}
        <p className="notice info">Based on reported medicine intake. Blood pressure and glucose measurements alone cannot tell whether a dose was taken.</p>
        {!!query.data.summary.report_ids?.length && <details><summary className="text-button">Reports containing dose logs</summary><div className="substack section-gap">{query.data.summary.report_ids.map((id, index) => <a key={id} href={`/api/v1/reports/${id}/view/`} target="_blank" rel="noopener noreferrer">View dose diary report {index + 1} ↗</a>)}</div></details>}
      </section> : <p className="notice info">No dose logs yet. Your adherence will appear after you save a day.</p>}
      <AsyncForm submit={existing ? "Update dose log" : "Save dose log"} successText="Dose log saved." onSubmit={async form => {
        const data = values(form);
        await api("/patients/me/adherence/", { method: "PUT", body: JSON.stringify({ date: data.date, scheduled_doses: Number(data.scheduled_doses), taken_doses: Number(data.taken_doses) }) });
        setScheduled(undefined); setTaken(undefined); query.reload(); onChanged();
      }}>
        <Field label="Log date" name="date" type="date" value={day} min={earliest} max={today} required onChange={event => { setDay(event.target.value); setScheduled(undefined); setTaken(undefined); }}/>
        <div className="form-grid">
          <Field label="Scheduled doses" name="scheduled_doses" type="number" min={1} max={10000} step={1} value={scheduledValue} required onChange={event => setScheduled(event.target.value)} hint="Count individual doses from your prescription instructions."/>
          <Field label="Doses taken" name="taken_doses" type="number" min={0} max={scheduledValue || 10000} step={1} value={takenValue} required onChange={event => setTaken(event.target.value)}/>
        </div>
      </AsyncForm>
      {!!query.data?.results.length && <div><h3>Recent dose logs</h3><div className="table-wrap section-gap"><table><thead><tr><th>Date</th><th>Taken / scheduled</th><th>Update</th></tr></thead><tbody>{query.data.results.map(log => <tr key={log.id}><td>{date(log.date)}</td><td>{log.taken_doses} / {log.scheduled_doses}</td><td><button type="button" className="text-button" aria-label={`Edit dose log for ${date(log.date)}`} onClick={() => { setDay(log.date); setScheduled(undefined); setTaken(undefined); }}>Edit</button></td></tr>)}</tbody></table></div></div>}
    </div></QueryState>
  </div>;
}

export function LabTracking({ onChanged }: { onChanged: () => void }) {
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [measurementTime] = useState(localDateTime);
  const query = useQuery<LabResponse>(`/patients/me/labs/?page=${page}`);
  return <div className="stack">
    <p className="progress-note">Results extracted from supported reports appear here with the recorded reference range. You can also add a result manually. Flags compare the value with that supplied range; results without a range remain unclassified.</p>
    <div className="inline-actions"><button type="button" className="button secondary small" onClick={() => setAdding(!adding)}>{adding ? "Close lab form" : "Add lab result"}</button><Refresh onClick={query.reload}/></div>
    {adding && <AsyncForm submit="Save lab result" successText="" onSubmit={async form => {
      const data = values(form);
      await post("/patients/me/labs/", { name: data.name, value: data.value, unit: data.unit, reference_low: data.reference_low === "" ? null : data.reference_low, reference_high: data.reference_high === "" ? null : data.reference_high, measured_at: new Date(data.measured_at).toISOString() });
      setAdding(false); setPage(1); query.reload(); onChanged();
    }}>
      <Field label="Test name" name="name" required maxLength={120} placeholder="As printed on your lab report"/>
      <div className="form-grid"><Field label="Result value" name="value" type="number" step="any" required/><Field label="Unit" name="unit" required maxLength={40} placeholder="For example, mg/dL"/></div>
      <div className="form-grid"><Field label="Reference lower limit (optional)" name="reference_low" type="number" step="any"/><Field label="Reference upper limit (optional)" name="reference_high" type="number" step="any"/></div>
      <Field label="Measured at" name="measured_at" type="datetime-local" required defaultValue={measurementTime} max={localDateTime()}/>
      <p className="progress-note">Results keep their original entry. Check the value, unit, date, and reference range before saving.</p>
    </AsyncForm>}
    <QueryState query={query}>{query.data?.results.length ? <div>
      <p className="progress-note">{query.data.summary.abnormal ?? "—"} outside the supplied range · {query.data.summary.total ?? "—"} tracked tests. The summary uses the latest result for each test and unit.</p>
      {query.data.results.map(result => <article className="list-row" key={result.id}><div className="row-content"><h3>{result.name} <Badge>{result.flag === "unknown" ? "unclassified" : result.flag}</Badge></h3><p><strong>{result.value} {result.unit}</strong> · {dateTime(result.measured_at)}</p><p>Reference range: {result.reference_low ?? "not supplied"} – {result.reference_high ?? "not supplied"} {result.unit}</p><p className="row-meta">Recorded by {result.recorded_by_name} · {result.source === "patient" ? "Patient reported" : "Doctor recorded"}</p></div></article>)}
    </div> : <Empty title="No structured lab results yet.">Add results from a report to track their values and reference ranges.</Empty>}</QueryState>
    {(page > 1 || query.data?.next) && <div className="inline-actions"><button type="button" className="button secondary small" disabled={page === 1 || query.loading} onClick={() => setPage(page - 1)}>Previous lab results</button><span>Page {page}</span><button type="button" className="button secondary small" disabled={!query.data?.next || query.loading} onClick={() => setPage(page + 1)}>Next lab results</button></div>}
  </div>;
}
