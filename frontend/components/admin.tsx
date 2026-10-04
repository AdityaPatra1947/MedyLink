"use client";
import { useState } from "react";
import { ArrowLeft, ArrowRight, FileText, Image as ImageIcon, Search, ShieldCheck, Stethoscope, Store } from "lucide-react";
import { date, dateTime, list, post, values } from "@/lib/api";
import type { Application, ProviderDocument } from "@/lib/types";
import { AsyncForm, Badge, Empty, Field, Panel, QueryState, Refresh, Select, Textarea, useQuery } from "./ui";
import { ApplicationDetails, EmailVerification, ReviewHistory } from "./application-details";
import styles from "./admin.module.css";

type ProviderRole = "doctor" | "pharmacist";
type ApplicationPage = {results:Application[];next:number|null};
function status(application:Application) {
  if (application.status === "approved" && ((!application.valid_until || new Date(application.valid_until) <= new Date()) ||
    (application.role === "pharmacist" && application.shop_license_expires && new Date(application.shop_license_expires+"T23:59:59") < new Date()))) return "expired";
  return application.status;
}
function DocumentReview({ document, canReview, reload }: {document:ProviderDocument;canReview:boolean;reload:()=>void}) {
  return <div className={styles.document}>
    <a href={`/api/v1/provider-documents/${document.id}/download/`} target="_blank" rel="noreferrer" className="text-button">
      {document.kind === "photo" ? <ImageIcon size={16}/> : <FileText size={16}/>} {document.name}
    </a>
    <p><Badge>{document.status}</Badge></p>
    {canReview && <details className="section-gap"><summary className="text-button">Record file review</summary><div className="section-gap stack">
      <AsyncForm submit="Mark file reviewed and safe" successText="" onSubmit={async form => {
        await post(`/admin/provider-documents/${document.id}/validate/`,{...values(form),safe:true}); reload();
      }}>
        <Textarea label="Review / malware scan reference" name="reason" required/>
        <label className="checkbox"><input type="checkbox" required/><span>I completed the required file safety review and confirmed this file is safe.</span></label>
      </AsyncForm>
      <details><summary className="text-button">Reject this file</summary><div className="section-gap"><AsyncForm submit="Reject file" successText="" onSubmit={async form=>{
        await post(`/admin/provider-documents/${document.id}/validate/`,{...values(form),safe:false});reload();
      }}><Textarea label="File rejection reason" name="reason" required/></AsyncForm></div></details>
    </div></details>}
  </div>;
}

function Decision({ application, reload }: {application:Application;reload:()=>void}) {
  const evidenceId=`admin-${application.role}-${application.id}-credential-evidence`;
  const blockersId=`admin-${application.role}-${application.id}-approval-blockers`;
  const credentials=application.documents.filter(document=>document.kind!=="photo");
  const pendingDocuments=credentials.filter(document=>!["validated","rejected"].includes(document.status));
  const rejectedDocuments=credentials.filter(document=>document.status==="rejected");
  const evidenceReady=credentials.length>0 && credentials.every(document=>document.status==="validated");
  const current=application.is_current !== false;
  const reviewable=current && ["pending","suspended","approved"].includes(application.status);
  const canApprove=reviewable && application.email_verified && evidenceReady;
  const [minimum]=useState(()=>{const now=new Date();return new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,16);});
  return <Panel title="Record a decision">
    <p className="progress-note">Check the professional registration and, for pharmacies, the shop licence independently. Every decision records your identity, time, and reason.</p>
    {!current && <p className="notice info">This is a previous submission. Decisions can only be made on the current application.</p>}
    {current && application.status === "rejected" && <p className="notice info">This submission was rejected. The provider can review the reason and submit corrected details and evidence. The previous decision remains in the history.</p>}
    {reviewable && <div className="stack">
      {!canApprove && <div id={blockersId} className={styles.blockers}>
        <h3>Before you can approve</h3>
        <ul>
          {!application.email_verified && <li>The applicant must verify their email address.</li>}
          {!credentials.length && <li>No credential documents have been uploaded for this submission. The provider must open <strong>{application.role==="pharmacist" ? "Shop & verification" : "My verification"} → Credential evidence → Upload evidence</strong> and upload their credentials. A profile photo does not count as evidence.</li>}
          {!!pendingDocuments.length && <li>{pendingDocuments.length} credential {pendingDocuments.length===1 ? "document needs" : "documents need"} a file review: <strong>{pendingDocuments.map(document=>document.name).join(", ")}</strong>. Open each file, then choose <strong>Record file review</strong> and complete the review.</li>}
          {!!rejectedDocuments.length && <li>{rejectedDocuments.length} credential {rejectedDocuments.length===1 ? "document was" : "documents were"} rejected: <strong>{rejectedDocuments.map(document=>document.name).join(", ")}</strong>. Resolve the rejection before approval. The provider can submit corrected credentials and evidence in {application.role==="pharmacist" ? "Shop & verification" : "My verification"}.</li>}
        </ul>
        {!evidenceReady && <a className="button secondary small" href={`#${evidenceId}`}>Review credential documents<ArrowRight size={15}/></a>}
        <button type="button" className="text-button" onClick={reload}>Refresh application</button>
      </div>}
      {canApprove ? <AsyncForm submit={application.status === "pending" ? "Approve provider" : "Renew / restore approval"} successText="" onSubmit={async form=>{
        const data=values(form);await post(`/admin/provider-applications/${application.id}/approve/`,{...data,valid_until:new Date(data.valid_until).toISOString()});reload();
      }}>
        <Textarea label="Evidence reviewed" name="evidence_reviewed" required/>
        <Textarea label="Approval reason" name="reason" required/>
        <Field label="Verification valid until" name="valid_until" type="datetime-local" min={minimum} max={application.role==="pharmacist" && application.shop_license_expires ? application.shop_license_expires+"T23:59" : undefined} required/>
        <label className="checkbox"><input type="checkbox" required/><span>I verified the credentials and reviewed the supporting evidence.</span></label>
      </AsyncForm> : <button className={`button primary ${styles.disabled}`} disabled aria-describedby={blockersId}>Approve provider</button>}
      <details><summary className="text-button">Reject application</summary><div className="section-gap"><AsyncForm submit="Confirm rejection" successText="" onSubmit={async form=>{
        await post(`/admin/provider-applications/${application.id}/reject/`,values(form));reload();
      }}><Textarea label="Rejection reason shown to the applicant" name="reason" required/></AsyncForm></div></details>
    </div>}
    {current && application.status==="approved" && <details className="section-gap"><summary className="text-button">Suspend this provider</summary><div className="section-gap"><AsyncForm submit="Suspend provider" successText="" onSubmit={async form=>{
      await post(`/admin/providers/${application.provider_id}/suspend/`,values(form));reload();
    }}><Textarea label="Suspension reason" name="reason" required/><label className="checkbox"><input type="checkbox" required/><span>I understand this immediately revokes this provider’s patient access.</span></label></AsyncForm></div></details>}
  </Panel>;
}

function ReviewApplication({ id, role, onBack }: {id:string;role:ProviderRole;onBack:()=>void}) {
  const query=useQuery<Application>(`/admin/provider-applications/${id}/`);const application=query.data;
  return <div><button className="page-back" onClick={onBack}><ArrowLeft size={15}/>Back to {role==="doctor" ? "doctor" : "pharmacist"} approvals</button>
    <QueryState query={query}>{application && (application.role!==role ? <Panel title="Application is in another approval queue"><p className="muted">Use the matching provider approval page to review this application.</p></Panel> :
      <><div className={styles.reviewIdentity}><div><h2>{application.name}</h2><p>{application.provider_email || application.email}</p></div><Badge>{status(application)}</Badge></div>
      <div className={styles.reviewGrid}>
        <div id={`admin-${role}-${id}-credential-evidence`} tabIndex={-1} className={styles.evidence}>
        <Panel title="Credential evidence" action={<Refresh onClick={query.reload}/>}><p className="progress-note">Open each credential document, then choose Record file review to record your checks. Once every credential is marked safe, complete the approval form.</p>
          {application.documents.filter(document=>document.kind!=="photo").length ? application.documents.filter(document=>document.kind!=="photo").map(document=>
            <DocumentReview key={document.id} document={document} canReview={application.is_current!==false && application.status==="pending"} reload={query.reload}/>) :
            <Empty title="Credential evidence is missing.">The provider must upload documents in {role==="pharmacist" ? "Shop & verification" : "My verification"} → Credential evidence → Upload evidence. Refresh this application after the upload.</Empty>}
        </Panel></div>
        <div className={styles.decision}><Decision application={application} reload={query.reload}/></div>
        <div className="stack">
        <Panel title="Application details"><ApplicationDetails application={application}/></Panel>
        <Panel title={role==="pharmacist" ? "Shop photo" : "Profile photo"}><p className="progress-note">An optional private {role==="pharmacist" ? "shop" : "profile"} photo. It does not replace professional credential evidence.</p>
          {application.documents.filter(document=>document.kind==="photo").length ? application.documents.filter(document=>document.kind==="photo").map(document=>
            <DocumentReview key={document.id} document={document} canReview={application.is_current!==false && application.status==="pending"} reload={query.reload}/>) : <p className="muted">No photo submitted.</p>}
        </Panel>
      </div><div className="stack">
        <Panel title="Review history" action={<Refresh onClick={query.reload}/>}><ReviewHistory reviews={application.reviews}/></Panel>
        <Panel title="Previous submissions">{application.history?.length ? application.history.filter(previous=>previous.id!==application.id).map(previous=><details className={styles.history} key={previous.id}>
          <summary className="text-button">Version {previous.version} · {previous.status} · {date(previous.created_at)}</summary>
          <div className="stack section-gap"><ApplicationDetails application={previous}/><ReviewHistory reviews={previous.reviews}/>
            {previous.documents.map(document=><a key={document.id} className="text-button" href={`/api/v1/provider-documents/${document.id}/download/`} target="_blank" rel="noreferrer">{document.kind==="photo" ? "Photo" : "Credential"}: {document.name}</a>)}
          </div>
        </details>) : <p className="muted">This is the provider’s first submission.</p>}</Panel>
      </div></div></>)}
    </QueryState>
  </div>;
}

export function AdminApprovals({ role, showHeading = true }: {role:ProviderRole;showHeading?:boolean}) {
  const [page,setPage]=useState(1);const [statusFilter,setStatusFilter]=useState("pending");const [search,setSearch]=useState("");const [selected,setSelected]=useState<string>();
  const params=new URLSearchParams({role,page:String(page),search});if(statusFilter)params.set("status",statusFilter);
  const query=useQuery<ApplicationPage>(`/admin/provider-applications/?${params.toString()}`);
  if(selected)return <ReviewApplication id={selected} role={role} onBack={()=>{setSelected(undefined);query.reload();}}/>;
  const applications=list(query.data);const label=role==="doctor" ? "Doctor" : "Pharmacist";
  return <Panel title={showHeading ? `${label} applications` : undefined} action={<Refresh onClick={query.reload}/>}>
    <div className={styles.queueIntro}>{role==="doctor" ? <Stethoscope size={23}/> : <Store size={23}/>}<p>{role==="doctor" ? "Review doctor qualifications, registration, and practice details before enabling patient access." : "Review the named pharmacist’s registration, pharmacy shop licence, and supporting evidence."} Email verification and professional approval are separate checks.</p></div>
    <form className={styles.filters} onSubmit={event=>{event.preventDefault();const data=values(event.currentTarget);setSearch(data.search.trim());setPage(1);}}>
      <Field label="Search applicants" name="search" type="search" maxLength={100} placeholder="Name, email, registration, or shop" defaultValue={search}/>
      <Select label="Application status" name="status" defaultValue={statusFilter} onChange={value=>{setStatusFilter(value);setPage(1);}}>
        <option value="pending">Pending review</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="suspended">Suspended</option><option value="expired">Expired</option><option value="">All statuses</option>
      </Select><button className="button secondary" type="submit"><Search size={16}/>Search</button>
    </form>
    <QueryState query={query}>{applications.length ? <div className={styles.list}>{applications.map(application=><article className={styles.applicant} key={application.id}>
      <div className={styles.identity}><div><h3>{application.name}</h3><p>{application.provider_email || application.email}</p><p>{role==="doctor" ? [application.qualification,application.specialty,application.clinic_name].filter(Boolean).join(" · ") : application.shop_name}</p></div><Badge>{status(application)}</Badge></div>
      <div className={styles.meta}><EmailVerification verified={application.email_verified}/><span>{application.registration_number} · {application.registering_body}</span></div>
      <div className={styles.bottom}><p>Version {application.version} · Submitted {dateTime(application.created_at)}</p><button className="button secondary small" onClick={()=>setSelected(application.id)}>Review application<ArrowRight size={14}/></button></div>
    </article>)}</div> : <Empty title={`No ${role} applications match these filters.`}>Try another status or search term. New submissions appear under Pending review.</Empty>}</QueryState>
    {(page>1 || query.data?.next) && <div className="inline-actions section-gap"><button className="button secondary small" disabled={page===1 || query.loading} onClick={()=>setPage(page-1)}>Previous</button><span className="muted">Page {page}</span><button className="button secondary small" disabled={!query.data?.next || query.loading} onClick={()=>setPage(page+1)}>Next</button></div>}
    <div className="security-hint section-gap"><ShieldCheck size={17}/><span>Approval lets this professional find patients and view records permitted for their role.</span></div>
  </Panel>;
}
