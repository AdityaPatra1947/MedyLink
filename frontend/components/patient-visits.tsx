"use client";

import { useState } from "react";
import { ArrowRight, ChevronDown, Download, FileText, Paperclip, Plus, Stethoscope } from "lucide-react";
import { date, dateTime, list } from "@/lib/api";
import type { PatientVisit, ResultPage, User } from "@/lib/types";
import { Badge, Empty, Panel, QueryState, Refresh, useQuery } from "./ui";
import { PrescriptionDetail } from "./clinical";
import { PageControls, PatientReports, ReportRows, ReportUpload } from "./patient-reports";
import styles from "./patient-visits.module.css";

export function PatientVisits({ user, preview = false, navigate, showReportLibrary = true, showHeading = true, showNavigation = true }: { user: User; preview?: boolean; navigate?: (tab: string) => void; showReportLibrary?: boolean; showHeading?: boolean; showNavigation?: boolean }) {
  const [page, setPage] = useState(1);
  const [selectedPrescription, setSelectedPrescription] = useState<string>();
  const [uploadVisit, setUploadVisit] = useState<string>();
  const [libraryVersion, setLibraryVersion] = useState(0);
  const query = useQuery<ResultPage<PatientVisit>>(`/patients/me/visits/?page=${page}`);
  const visits = preview ? list(query.data).slice(0, 3) : list(query.data);
  function uploaded() { setUploadVisit(undefined); query.reload(); setLibraryVersion(value => value + 1); }
  if (selectedPrescription) return <PrescriptionDetail id={selectedPrescription} user={user} onBack={() => setSelectedPrescription(undefined)}/>;
  return <div className="stack"><Panel title={showHeading ? preview ? "Recent doctor visits" : "Your doctor visits" : undefined} eyebrow={showHeading ? "YOUR CARE HISTORY" : undefined} action={preview ? <button type="button" className="text-button" onClick={() => navigate?.("visits")}>View all visits</button> : <Refresh onClick={query.reload}/>}>
    <QueryState query={query}>{visits.length ? <div className={styles.visitList}>{visits.map(visit => <article className={styles.visit} key={visit.id}>
      <div className={styles.visitHeading}><span className={styles.doctorIcon}><Stethoscope size={21} strokeWidth={1.5}/></span><div className={styles.doctorInfo}><h3>Dr. {visit.doctor.name}</h3><p>{[visit.doctor.specialty, visit.doctor.clinic_name].filter(Boolean).join(" · ") || visit.doctor.qualification || "Consultation"}</p></div><time dateTime={visit.created_at}>{date(visit.created_at)}</time></div>
      <div className={styles.visitSummary}><div><p className={styles.label}>{visit.record.correction_of ? "LINKED CORRECTION" : "SYMPTOMS / REASON FOR VISIT"}</p><h4>{visit.record.complaint}</h4>{visit.record.diagnosis && <p className={styles.diagnosis}><strong>Diagnosis:</strong> {visit.record.diagnosis}</p>}</div><div className={styles.attachments}><span><FileText size={12}/>{visit.prescriptions.length} prescription{visit.prescriptions.length === 1 ? "" : "s"}</span><span><Paperclip size={12}/>{visit.reports.length} report{visit.reports.length === 1 ? "" : "s"}</span></div></div>
      <details className={styles.visitDetails}><summary>View visit details<ChevronDown size={14}/></summary><div className={styles.detailsContent}>
        <div className={styles.notes}><span className={styles.label}>DOCTOR’S EXAMINATION AND CARE PLAN · {dateTime(visit.created_at)}</span>{visit.record.notes ? <p>{visit.record.notes}</p> : <p className="muted">No additional consultation notes.</p>}{visit.record.correction_reason && <p><strong>Correction reason:</strong> {visit.record.correction_reason}</p>}{Object.keys(visit.record.vitals || {}).length > 0 && <div className={styles.vitals}>{Object.entries(visit.record.vitals).map(([key, value]) => <span key={key}><strong>{key.replaceAll("_", " ")}</strong>{String(value)}</span>)}</div>}</div>
        <div className={styles.detailSection}><h4>Prescriptions from this visit</h4>{visit.prescriptions.length ? visit.prescriptions.map(prescription => <div key={prescription.id} className={styles.prescription}><div className={styles.prescriptionHead}><div><strong>{date(prescription.created_at)}</strong><p>{prescription.items.map(item => item.medicine).join(", ")}</p></div><Badge>{prescription.status}</Badge></div><ul className={styles.prescriptionMedicines}>{prescription.items.map(item => <li key={item.id}><strong>{item.medicine}</strong><p>{item.dosage}</p>{item.instructions && <p>{item.instructions}</p>}<p>Prescribed: {item.quantity} {item.unit}</p></li>)}</ul>{prescription.notes && <p className="wrap-text section-gap">{prescription.notes}</p>}<div className={styles.prescriptionActions}><button className="text-button" type="button" onClick={() => setSelectedPrescription(prescription.id)}>View prescription<ArrowRight size={12}/></button><a className="text-button" href={`/api/v1/prescriptions/${prescription.id}/pdf/`} target="_blank" rel="noreferrer"><Download size={12}/>Download PDF</a></div></div>) : <p className={styles.noItems}>No prescriptions linked to this visit. Your complete prescription history is available in Prescriptions.</p>}</div>
        <div className={styles.detailSection}><div className={styles.reportHeading}><h4>Reports for this visit</h4><button className="text-button" type="button" onClick={() => setUploadVisit(uploadVisit === visit.id ? undefined : visit.id)}><Plus size={12}/>{uploadVisit === visit.id ? "Close upload" : "Add report"}</button></div><ReportRows reports={visit.reports} emptyText="No reports linked to this visit."/>{uploadVisit === visit.id && <div className={styles.uploadBox}><ReportUpload user={user} recordId={visit.record.id} onSaved={uploaded}/></div>}</div>
      </div></details>
    </article>)}</div> : <Empty title="Your next visit starts your story.">Consultations recorded by your doctors will appear here with their prescriptions and any reports attached to the visit.</Empty>}</QueryState>
    {!preview && <PageControls page={page} next={query.data?.next} onPage={setPage}/>}
    {!preview && navigate && showNavigation && <><p className={styles.noItems}>Older prescriptions and reports may not have a linked visit. They remain available in your complete history below.</p><div className={styles.historyLinks}><button type="button" className="text-button" onClick={() => navigate("prescriptions")}>All prescriptions<ArrowRight size={13}/></button><button type="button" className="text-button" onClick={() => navigate("reports")}>All reports<ArrowRight size={13}/></button><button type="button" className="text-button" onClick={() => navigate("records")}>Medical timeline<ArrowRight size={13}/></button></div></>}
  </Panel>{!preview && showReportLibrary && <PatientReports key={libraryVersion} user={user} onChanged={query.reload}/>}</div>;
}
