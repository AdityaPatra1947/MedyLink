"use client";

import { useState } from "react";
import { Download, Eye, FileText, Paperclip, Plus, X } from "lucide-react";
import { api, date, list } from "@/lib/api";
import type { ClinicalRecord, MedicalReport, ResultPage, User } from "@/lib/types";
import { AsyncForm, Empty, Field, Panel, QueryState, Refresh, useQuery } from "./ui";
import styles from "./patient-visits.module.css";

export function PageControls({ page, next, onPage }: { page: number; next?: number | null; onPage: (page: number) => void }) {
  if (page === 1 && !next) return null;
  return <div className={styles.pagination}><button type="button" className="button secondary small" disabled={page === 1} onClick={() => onPage(page - 1)}>Previous</button><span>Page {page}</span><button type="button" className="button secondary small" disabled={!next} onClick={() => onPage(next || page + 1)}>Next</button></div>;
}

export function ReportRows({ reports, emptyText = "No reports uploaded yet." }: { reports: MedicalReport[]; emptyText?: string }) {
  if (!reports.length) return <p className={styles.noItems}>{emptyText}</p>;
  return <div className={styles.reportRows}>{reports.map(report => <article className={styles.reportRow} key={report.id}>
    <span className={styles.reportIcon}><FileText size={19} strokeWidth={1.5}/></span>
    <div className={styles.reportInfo}><h3>{report.title || report.name}</h3>{report.title && report.title !== report.name && <p>{report.name}</p>}<p>Uploaded {date(report.created_at)} · {report.size_bytes < 1024 * 1024 ? `${Math.max(1, Math.round(report.size_bytes / 1024))} KB` : `${(report.size_bytes / 1024 / 1024).toFixed(2)} MB`} · {report.uploaded_by.role === "patient" ? "Patient uploaded" : `Uploaded by ${report.uploaded_by.role === "doctor" ? "Dr. " : ""}${report.uploaded_by.name}`}</p><span className={styles.linkLabel}><Paperclip size={10}/>{report.record_id ? "Linked to a visit" : "Not linked to a visit"}</span>
      {report.extraction?.status === "extracted" && <div className={styles.reportResults}><strong>Results added to your overview</strong>{report.extraction.measured_at && <span>Measured {date(report.extraction.measured_at)}</span>}<div>{report.extraction.blood_pressure && <span>BP <b>{report.extraction.blood_pressure.systolic}/{report.extraction.blood_pressure.diastolic}</b> {report.extraction.blood_pressure.unit}</span>}{report.extraction.blood_sugar && <span>{report.extraction.blood_sugar.context === "fasting" ? "Fasting glucose" : "Blood sugar"} <b>{report.extraction.blood_sugar.value}</b> {report.extraction.blood_sugar.unit}</span>}</div></div>}
    </div>
    <div className={styles.reportActions}>
      {report.view_url && <a className="button secondary small" href={report.view_url} target="_blank" rel="noopener noreferrer" aria-label={`View ${report.title || report.name} in a new tab`}><Eye size={14}/><span>{report.content_type === "application/pdf" ? "View PDF" : "View"}</span></a>}
      <a className="button secondary small" href={report.download_url} target="_blank" rel="noopener noreferrer" aria-label={`Download ${report.title || report.name}`}><Download size={14}/><span>Download</span></a>
    </div>
  </article>)}</div>;
}

function VisitPicker({ user, patientId }: { user: User; patientId?: string }) {
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState("");
  const path = patientId ? `/patients/${patientId}/records/` : "/patients/me/records/";
  const query = useQuery<ResultPage<ClinicalRecord>>(`${path}?page=${page}`);
  const available = list(query.data).filter(record => user.role !== "doctor" || record.doctor_id === user.id);
  return <div className="substack"><label className="field"><span>Link to a visit (optional)</span><select name="record_id" value={selected} onChange={event => setSelected(event.target.value)} disabled={query.loading}><option value="">Keep as a general report</option>{available.map(record => <option value={record.id} key={record.id}>{date(record.created_at)} · Dr. {record.doctor_name} · {record.complaint}</option>)}</select><small>{user.role === "doctor" ? "You may attach a report to a consultation you authored." : "Choose the relevant consultation, or keep this report in your library."}</small></label><QueryState query={query}><PageControls page={page} next={query.data?.next} onPage={next => { setSelected(""); setPage(next); }}/></QueryState></div>;
}

export function ReportUpload({ user, patientId, recordId, onSaved }: { user: User; patientId?: string; recordId?: string; onSaved: () => void }) {
  const path = patientId ? `/patients/${patientId}/reports/` : "/patients/me/reports/";
  return <AsyncForm submit="Upload report" successText="Report uploaded." reset onSubmit={async form => {
    const body = new FormData(form);
    const file = body.get("file");
    if (!(file instanceof File) || !file.size) throw new Error("Choose a report to upload.");
    if (!/\.(pdf|jpe?g|png)$/i.test(file.name) || file.size > 10 * 1024 * 1024) throw new Error("Choose a PDF, JPEG, or PNG report up to 10 MB.");
    if (recordId) body.set("record_id", recordId);
    else if (!body.get("record_id")) body.delete("record_id");
    await api(path, { method: "POST", body });
    window.dispatchEvent(new Event("medylink:patient-health-updated"));
    onSaved();
  }}>
    <Field label="Report title (optional)" name="title" maxLength={200} placeholder="e.g. Blood test results"/>
    <Field label="Medical report" name="file" type="file" required accept=".pdf,.jpg,.jpeg,.png" hint="PDF, JPEG, or PNG, up to 10 MB. Upload only files for this patient."/>
    {recordId ? <div className={styles.uploadHint}><Paperclip size={15}/><span>This report will be attached to the selected visit.</span></div> : <VisitPicker user={user} patientId={patientId}/>}
  </AsyncForm>;
}

export function PatientReports({ user, patientId, recordId, onChanged, showHeading = true }: { user: User; patientId?: string; recordId?: string; onChanged?: () => void; showHeading?: boolean }) {
  const [page, setPage] = useState(1);
  const [uploading, setUploading] = useState(false);
  const path = patientId ? `/patients/${patientId}/reports/` : "/patients/me/reports/";
  const query = useQuery<ResultPage<MedicalReport>>(`${path}?page=${page}`);
  const reports = list(query.data);
  function reload() { query.reload(); onChanged?.(); }
  return <Panel title={showHeading ? "Medical reports" : undefined} eyebrow={showHeading ? "YOUR REPORT LIBRARY" : undefined} action={<div className="inline-actions"><Refresh onClick={reload}/><button className="button secondary small" type="button" onClick={() => setUploading(!uploading)}>{uploading ? <X size={14}/> : <Plus size={14}/>} {uploading ? "Close upload" : "Upload report"}</button></div>}>
    <p className={styles.intro}>All uploaded reports are kept here, including reports without a linked visit.</p>
    {uploading && <div className={styles.uploadBox}><ReportUpload user={user} patientId={patientId} recordId={recordId} onSaved={() => { setUploading(false); reload(); }}/></div>}
    <QueryState query={query}>{reports.length ? <ReportRows reports={reports}/> : <Empty title="Keep your reports together.">Upload laboratory results, scans, or other medical reports. You can link each file to a visit or leave it in your report library.</Empty>}</QueryState>
    <PageControls page={page} next={query.data?.next} onPage={setPage}/>
  </Panel>;
}
