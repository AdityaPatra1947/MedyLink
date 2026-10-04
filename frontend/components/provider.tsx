"use client";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowRight, Camera, Check, LoaderCircle, Plus, ShieldCheck, UserRound } from "lucide-react";
import { api, date, list, message, post, values } from "@/lib/api";
import type { Application, Profile, ResultPage, User } from "@/lib/types";
import { AsyncForm, Badge, Empty, Feedback, Field, Panel, QueryState, Refresh, Textarea, useQuery } from "./ui";
import { ApplicationDetails, ReviewHistory } from "./application-details";
import { PageControls, PatientReports } from "./patient-reports";
import { DoctorProfile } from "./doctor-profile";
import { Security } from "./security";
import { HealthCardScanner } from "./health-card-scanner";
import styles from "./doctor-workspace.module.css";
import { DispensingHistory, Entries, Prescriptions, Records } from "./clinical";

function identifier(raw: string) { try { return new URL(raw).pathname.split("/").filter(Boolean).pop() || raw.trim(); } catch { return raw.trim(); } }
type PatientIdentity = Pick<Profile, "id" | "name" | "health_id" | "account_id" | "date_of_birth">;
function PatientLookup({ user, navigate, initialIdentifier = "", active = true, showHeading = true, showNavigation = true, onPatientAdded }: { user: User; navigate: (tab: string) => void; initialIdentifier?: string; active?: boolean; showHeading?: boolean; showNavigation?: boolean; onPatientAdded?: () => void }) {
  const [value, setValue] = useState(initialIdentifier);
  const [scan, setScan] = useState(false);
  const [selected, setSelected] = useState<PatientIdentity>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const request = useRef(0);
  const lookupContainer = useRef<HTMLDivElement>(null);
  useEffect(() => { if (!active) setScan(false); }, [active]);
  useEffect(() => {
    if (!scan || !lookupContainer.current) return;
    // The lookup may be visible before its heading reaches the scrollspy line.
    // Allow an explicit camera click there, but release it when it leaves view.
    const observer = new IntersectionObserver(([entry]) => { if (!entry.isIntersecting) setScan(false); });
    observer.observe(lookupContainer.current);
    return () => observer.disconnect();
  }, [scan]);
  const lookup = useCallback(async (raw: string) => {
    const current = ++request.current;
    const key = identifier(raw);
    setValue(key); setError(""); setScan(false); setPending(true);
    try {
      const result = await post<{ patient_id: string; patient: PatientIdentity }>("/provider/patients/lookup/", { identifier: key });
      if (request.current === current) setSelected({ ...result.patient, id: result.patient_id });
    } catch (error) { if (request.current === current) setError(message(error)); }
    finally { if (request.current === current) setPending(false); }
  }, []);
  useEffect(() => {
    if (initialIdentifier) void lookup(initialIdentifier);
    return () => { request.current += 1; };
  }, [initialIdentifier, lookup]);
  if (selected) return user.role === "doctor"
    ? <DoctorPatientWorkspace patientId={selected.id} user={user} navigate={navigate} onBack={() => setSelected(undefined)} showNavigation={showNavigation} onPatientAdded={onPatientAdded}/>
    : <div className="stack"><button className="page-back" onClick={() => setSelected(undefined)}><ArrowLeft size={15}/>Find another patient</button><Panel title={selected.name}><p className="muted">{selected.account_id || selected.health_id}</p></Panel><Prescriptions key={selected.id} path={`/patients/${selected.id}/prescriptions/`} user={user}/></div>;
  return <div className="grid-main" ref={lookupContainer}><Panel title={showHeading ? user.role === "doctor" ? "Find a patient" : "Find patient prescriptions" : undefined}>
    <p className="progress-note">Enter the patient’s short account ID or scan the QR code on their health card. Existing health IDs also work.</p>
    <form className="form" onSubmit={event => { event.preventDefault(); if (!pending) void lookup(value); }}>
      <Field label="Account ID or health card" name="identifier" required value={value} disabled={pending} onChange={event => setValue(event.target.value)} placeholder="P-7K4M2Q or scan a health card"/>
      <Feedback error={error}/>
      <button className="button primary" type="submit" disabled={pending}>{pending ? <LoaderCircle size={16} className="spin"/> : <ArrowRight size={16}/>} {pending ? "Opening patient record…" : "Find patient"}</button>
    </form>
    <div className="divider-label">Or scan a card</div><div className="inline-actions"><button className="button secondary" type="button" disabled={pending} onClick={() => setScan(true)}><Camera size={16}/>Scan QR with camera</button></div>
    {scan && <HealthCardScanner onScan={text => { void lookup(text); }} onClose={() => setScan(false)}/>}
  </Panel><Panel title="Connected care"><div className="security-hint"><ShieldCheck size={21}/><p>{user.role === "doctor" ? "View the patient’s complete history, including consultations and reports from other doctors. Add a new consultation or upload a report while earlier records keep their original author and content." : "View prescribed medicines and allergy information, then record quantities handed over. Full clinical notes and reports are reserved for doctors and the patient."}</p></div>{user.role === "doctor" && <p className="progress-note section-gap">After opening a record, choose Add patient to keep them in My patients for the next visit.</p>}</Panel></div>;
}
function ApplicationForm({ user, current, onSaved }: {user: User; current?: Application | null; onSaved: () => void}) {
  return <AsyncForm submit={current ? "Submit updated application" : "Submit for verification"} successText="" onSubmit={async form => {
    const data = values(form);
    await post("/provider/application/",{...data,years_experience:data.years_experience === "" ? null : data.years_experience});
    onSaved();
  }}>
    <div className="form-grid">
      <Field label="Professional registration number" name="registration_number" required defaultValue={current?.registration_number} maxLength={100}/>
      <Field label="Registering body / jurisdiction" name="registering_body" required defaultValue={current?.registering_body} maxLength={150}/>
      <Field label="Contact phone" name="contact_phone" type="tel" required defaultValue={current?.contact_phone} maxLength={30}/>
      {user.role === "doctor" && <>
        <Field label="Qualification" name="qualification" required defaultValue={current?.qualification} maxLength={150}/>
        <Field label="Specialty" name="specialty" required defaultValue={current?.specialty} maxLength={150}/>
        <Field label="Clinic / hospital name" name="clinic_name" defaultValue={current?.clinic_name} maxLength={180}/>
        <Field label="Years of experience" name="years_experience" type="number" min="0" max="80" step="1" defaultValue={current?.years_experience ?? ""}/>
      </>}
    </div>
    <Textarea label="Practice / shop address" name="practice_address" required defaultValue={current?.practice_address}/>
    {user.role === "pharmacist" && <>
      <Field label="Pharmacy shop name" name="shop_name" required defaultValue={current?.shop_name} maxLength={180}/>
      <div className="form-grid">
        <Field label="Shop licence number" name="shop_license" required defaultValue={current?.shop_license} maxLength={100}/>
        <Field label="Shop licence valid until" name="shop_license_expires" type="date" required defaultValue={current?.shop_license_expires || ""}/>
      </div>
      <Field label="Opening hours" name="opening_hours" defaultValue={current?.opening_hours} maxLength={300} placeholder="For example, Monday–Saturday, 9 am–7 pm"/>
    </>}
    <label className="checkbox"><input type="checkbox" required/><span>I confirm these details are accurate. An updated submission requires a new review before you can continue providing care.</span></label>
    {current && <p className="progress-note">Previous submissions and files remain in your history. Upload the credential evidence for this new submission after saving.</p>}
  </AsyncForm>;
}
function ProviderFiles({ application, photo = false, reload }: {application:Application;photo?:boolean;reload?:()=>void}) {
  const files=application.documents.filter(document => photo ? document.kind === "photo" : document.kind !== "photo");
  const photoLabel=application.role==="pharmacist" ? "Shop photo" : "Profile photo";
  return <Panel title={photo ? photoLabel+" (optional)" : "Credential evidence"}>
    <p className="progress-note">{photo ? "A JPEG or PNG image, up to 2 MB. Your private photo is separate from the documents used to verify your credentials." : "PDF, JPEG, or PNG, up to 5 MB each. These private files are reviewed by an administrator."}</p>
    {files.length ? files.map(document => <div className="list-row" key={document.id}><div><a href={`/api/v1/provider-documents/${document.id}/download/`} target="_blank" rel="noreferrer" className="text-button">{document.name}</a><p><Badge>{document.status}</Badge></p></div></div>) : <p className="muted">{photo ? "No photo submitted." : "No credential documents submitted."}</p>}
    {application.status === "pending" && reload && <div className="section-gap"><AsyncForm submit={photo ? "Upload photo" : "Upload evidence"} successText="File uploaded for review." reset onSubmit={async form => {
      const data=new FormData(form);data.set("kind",photo ? "photo" : "credential");
      await api("/provider/application/documents/",{method:"POST",body:data});reload();
    }}><Field label={photo ? photoLabel : "Credential document"} name="file" type="file" accept={photo ? ".jpg,.jpeg,.png" : ".pdf,.jpg,.jpeg,.png"} required/></AsyncForm></div>}
  </Panel>;
}
type ApplicationData = { current: Application | null; history: Application[] };
type ApplicationQuery = { data: ApplicationData | null; loading: boolean; error: string; reload: () => void };
function Verification({ user, sharedQuery }: {user: User; sharedQuery?: ApplicationQuery}) {
  const ownQuery=useQuery<ApplicationData>(sharedQuery ? null : "/provider/application/");
  const query=sharedQuery || ownQuery;
  const current=query.data?.current; const [editing,setEditing]=useState(false);
  return <QueryState query={query}><div className="grid-main"><div className="stack">
    <Panel title={current ? "Your current application" : "Submit your credentials"} action={current && <Badge>{current.status}</Badge>}>
      {current && !editing ? <><ApplicationDetails application={current}/>{current.status === "suspended" ? <p className="notice info section-gap">Your verification is suspended. Contact your administrator for review and reapproval.</p> : <button className="button secondary section-gap" onClick={() => setEditing(true)}>Submit corrected credentials</button>}</> : <ApplicationForm user={user} current={current} onSaved={() => {setEditing(false);query.reload();}}/>}
    </Panel>
    {current && <Panel title="Review history"><ReviewHistory reviews={current.reviews}/></Panel>}
    {!!query.data?.history.filter(item=>item.id!==current?.id).length && <Panel title="Previous submissions">{query.data.history.filter(item=>item.id!==current?.id).map(application => <details className="section-gap" key={application.id}><summary className="text-button">Version {application.version} · {date(application.created_at)} · {application.status}</summary><div className="stack section-gap"><ApplicationDetails application={application}/><ReviewHistory reviews={application.reviews}/>{application.documents.map(document=><a key={document.id} className="text-button" href={`/api/v1/provider-documents/${document.id}/download/`} target="_blank" rel="noreferrer">{document.kind === "photo" ? "Photo: " : "Credential: "}{document.name}</a>)}</div></details>)}</Panel>}
  </div><div className="stack">
    {current ? <><ProviderFiles application={current} reload={query.reload}/><ProviderFiles application={current} photo reload={query.reload}/></> : <Panel title="Credential evidence"><Empty title="Submit details first.">You can upload your evidence after the application has been created.</Empty></Panel>}
    <Panel title="A review before access"><div className="security-hint"><ShieldCheck size={20}/><p>Verify your email and submit professional credentials for manual review. Only approved providers may access patient information. No SMS verification is required.</p></div></Panel>
  </div></div></QueryState>;
}
function DoctorPatientWorkspace({ patientId, user, navigate, onBack, showNavigation = true, onPatientAdded }: { patientId: string; user: User; navigate: (tab: string) => void; onBack: () => void; showNavigation?: boolean; onPatientAdded?: () => void }) {
  const [section, setSection] = useState("records");
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const summary = useQuery<{ patient: Profile; is_my_patient: boolean }>(`/patients/${patientId}/clinical-summary/`);
  const isSaved = saved || summary.data?.is_my_patient;
  async function addPatient() {
    if (saving || isSaved) return;
    setSaving(true); setSaveError("");
    try { await post(`/doctor/patients/${patientId}/`); setSaved(true); onPatientAdded?.(); }
    catch (error) { setSaveError(message(error)); }
    finally { setSaving(false); }
  }
  return <div><button className="page-back" onClick={onBack}><ArrowLeft size={15}/>Back to patients</button><QueryState query={summary}>{summary.data && <>
    <Panel><div className={styles.patientHeading}><div><p className="eyebrow">PATIENT RECORD</p><h2>{summary.data.patient.name}</h2><p className={styles.patientMeta}>{summary.data.patient.account_id || summary.data.patient.health_id} · Born {date(summary.data.patient.date_of_birth)}</p><p className={styles.patientMeta}>Allergy status: {summary.data.patient.allergy_status?.replaceAll("_", " ") || "Unknown"} · Blood group: {summary.data.patient.blood_group || "Unknown"}</p></div><div className={styles.patientActions}>{isSaved ? <span className={styles.saved} role="status"><Check size={15}/>Added to My patients</span> : <button className="button primary" type="button" disabled={saving} onClick={() => void addPatient()}>{saving ? <LoaderCircle size={15} className="spin"/> : <Plus size={15}/>} {saving ? "Adding patient…" : "Add patient"}</button>}{showNavigation && <button className="text-button" type="button" onClick={() => { onBack(); navigate("patients"); }}>View My patients<ArrowRight size={13}/></button>}</div></div><Feedback error={saveError}/><p className={styles.historyNote}>History from every doctor is available here. Finalized consultations and uploaded reports are preserved; add a new consultation for today’s care.</p></Panel>
    <div className="tabs section-gap">{[["records", "Clinical timeline"], ["prescriptions", "Prescriptions"], ["reports", "Medical reports"], ["summary", "Allergies & conditions"]].map(([id, label]) => <button key={id} className={`tab ${section === id ? "active" : ""}`} onClick={() => setSection(id)}>{label}</button>)}</div>
    {section === "records" ? <Records path={`/patients/${patientId}/records/`} patientId={patientId} user={user}/> : section === "prescriptions" ? <Prescriptions path={`/patients/${patientId}/prescriptions/`} patientId={patientId} user={user}/> : section === "reports" ? <PatientReports user={user} patientId={patientId}/> : <div className="grid-two"><Entries patientId={patientId} kind="allergies" user={user}/><Entries patientId={patientId} kind="conditions" user={user}/></div>}
  </>}</QueryState></div>;
}
function DoctorPatients({ user, navigate, refreshVersion = 0, showHeading = true, showNavigation = true, onPatientAdded }: { user: User; navigate: (tab: string) => void; refreshVersion?: number; showHeading?: boolean; showNavigation?: boolean; onPatientAdded?: () => void }) {
  const [page, setPage] = useState(1);
  const query = useQuery<ResultPage<Profile>>(`/doctor/patients/?page=${page}`);
  const [selected, setSelected] = useState<Profile>();
  const reloadPatients = query.reload;
  useEffect(() => { if (refreshVersion > 0) reloadPatients(); }, [refreshVersion, reloadPatients]);
  if (selected) return <DoctorPatientWorkspace patientId={selected.id} user={user} navigate={navigate} onBack={() => { setSelected(undefined); query.reload(); }} showNavigation={showNavigation} onPatientAdded={onPatientAdded}/>;
  const patients = list(query.data);
  return <Panel className={styles.listPanel} title={showHeading ? "Saved patients" : undefined} action={<div className="inline-actions"><Refresh onClick={query.reload}/>{showNavigation && <button className="button secondary small" onClick={() => navigate("request")}>Find patient<ArrowRight size={14}/></button>}</div>}>
    <p className="progress-note">Your personal patient list. Open a record to review history and continue care.</p>
    <QueryState query={query}>{patients.length ? <div className={styles.patientRows}>{patients.map(patient => <article className={styles.patientRow} key={patient.id}><span className="row-icon"><UserRound size={19}/></span><div><h3>{patient.name}</h3><p>{patient.account_id || patient.health_id} · Born {date(patient.date_of_birth)}</p></div><button className="button secondary small" onClick={() => setSelected(patient)}>Open record<ArrowRight size={14}/></button></article>)}</div> : <Empty title="Your patient list is ready.">Find a patient by ID or scan their health card, then choose Add patient on their record.</Empty>}</QueryState>
    <PageControls page={page} next={query.data?.next} onPage={setPage}/>
  </Panel>;
}
export function Provider({ tab, user, navigate, onUserChange, initialIdentifier = "" }: { tab: string; user: User; navigate: (tab: string) => void; onUserChange: (user: User) => void; initialIdentifier?: string }) {
  const application = useQuery<{ current: Application | null }>("/provider/application/");
  if (tab === "verification") return <Verification user={user}/>;
  if (tab === "profile" && user.role === "doctor") return <DoctorProfile navigate={navigate} onUserChange={onUserChange}/>;
  const current = application.data?.current;
  const verified = current?.status === "approved" && !!current.valid_until && new Date(current.valid_until) > new Date() && (user.role !== "pharmacist" || !!current.shop_license_expires && current.shop_license_expires >= new Date().toISOString().slice(0, 10));
  return <QueryState query={application}>{verified ? tab === "dispensing" ? <DispensingHistory path="/pharmacy/dispensing/"/> : tab === "request" || user.role === "pharmacist" ? <PatientLookup key={tab} user={user} navigate={navigate} initialIdentifier={initialIdentifier}/> : <DoctorPatients user={user} navigate={navigate}/> : <Panel title="Complete your professional verification"><div className="security-hint"><ShieldCheck size={22}/><p>{current ? `Your current application is ${current.status}. Patient access is available only while your verification is approved and valid.` : "Submit your professional credentials and supporting evidence for review before accessing patient records."}</p></div><button className="button primary section-gap" onClick={() => navigate("verification")}>View my verification<ArrowRight size={15}/></button><Refresh onClick={application.reload}/></Panel>}</QueryState>;
}


function ProviderSection({ role, id, title, description, first = false, children }: { role: string; id: string; title: string; description: string; first?: boolean; children: ReactNode }) {
  const Heading = first ? "h1" : "h2";
  return <section id={`${role}-${id}`} data-workspace-section={id} aria-labelledby={`${role}-${id}-title`} className="workspace-section">
    <header className="workspace-section-heading"><Heading id={`${role}-${id}-title`} tabIndex={-1}>{title}</Heading><p>{description}</p></header>
    {children}
  </section>;
}

function ApprovalGate({ query, verified, children }: { query: ApplicationQuery; verified: boolean; children: ReactNode }) {
  return <QueryState query={query}>{verified ? children : <Panel title="Complete your professional verification"><div className="security-hint"><ShieldCheck size={22}/><p>{query.data?.current ? `Your current application is ${query.data.current.status}. Patient access is available only while your verification is approved and valid.` : "Submit your professional credentials and supporting evidence for review before accessing patient records."}</p></div><p className="progress-note section-gap">Use the verification section to review your application and submit credentials.</p><Refresh onClick={query.reload}/></Panel>}</QueryState>;
}

export function ProviderPage({ user, navigate, onUserChange, initialIdentifier = "", onLogout, activeSection }: { user: User; navigate: (tab: string) => void; onUserChange: (user: User) => void; initialIdentifier?: string; onLogout: () => void; activeSection: string }) {
  const application = useQuery<ApplicationData>("/provider/application/");
  const [patientListVersion, setPatientListVersion] = useState(0);
  const patientAdded = useCallback(() => setPatientListVersion(version => version + 1), []);
  const current = application.data?.current;
  const verified = !!(current?.status === "approved" && current.valid_until && new Date(current.valid_until) > new Date() && (user.role !== "pharmacist" || current.shop_license_expires && current.shop_license_expires >= new Date().toISOString().slice(0, 10)));
  const doctor = user.role === "doctor";
  const lookupSection = doctor ? "request" : "prescriptions";
  return <div className="workspace-page">
    {doctor && <ProviderSection role={user.role} id="patients" title="My patients" description="Your saved patients, ready for the next visit." first><ApprovalGate query={application} verified={verified}><DoctorPatients user={user} navigate={navigate} refreshVersion={patientListVersion} showHeading={false} showNavigation={false} onPatientAdded={patientAdded}/></ApprovalGate></ProviderSection>}
    <ProviderSection role={user.role} id={lookupSection} title={doctor ? "Connect with a patient" : "Find prescriptions"} description="Scan a health card or enter a patient’s short account ID." first={!doctor}><ApprovalGate query={application} verified={verified}><PatientLookup user={user} navigate={navigate} initialIdentifier={initialIdentifier} active={activeSection === lookupSection} showHeading={false} showNavigation={false} onPatientAdded={patientAdded}/></ApprovalGate></ProviderSection>
    {!doctor && <ProviderSection role={user.role} id="dispensing" title="Dispensing history" description="A record of medicines handed over by your pharmacy."><ApprovalGate query={application} verified={verified}><DispensingHistory path="/pharmacy/dispensing/" showHeading={false}/></ApprovalGate></ProviderSection>}
    {doctor && <ProviderSection role={user.role} id="profile" title="My profile" description="Keep your personal details and contact information up to date."><DoctorProfile navigate={navigate} onUserChange={onUserChange} showNavigation={false} currentApplication={application.data?.current}/></ProviderSection>}
    <ProviderSection role={user.role} id="verification" title={doctor ? "Professional verification" : "Shop & verification"} description="Keep your credentials and application up to date."><Verification user={user} sharedQuery={application}/></ProviderSection>
    <ProviderSection role={user.role} id="security" title="Account security" description="Manage your password and active sessions."><Security user={user} onLogout={onLogout}/></ProviderSection>
  </div>;
}
