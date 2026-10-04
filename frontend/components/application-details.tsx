"use client";
import { MailCheck, MailWarning } from "lucide-react";
import { date, dateTime } from "@/lib/api";
import type { Application, ProviderReview } from "@/lib/types";
import { Badge } from "./ui";

export function EmailVerification({ verified }: { verified: boolean }) {
  return <span className={`notice ${verified ? "success" : "info"}`} style={{padding:"8px 10px",margin:0,fontSize:12}}>
    {verified ? <MailCheck size={15}/> : <MailWarning size={15}/>}
    {verified ? "Email verified" : "Email verification pending"}
  </span>;
}

export function ApplicationDetails({ application }: { application: Application }) {
  const fields: [string, string | number | null | undefined][] = [
    ["Full name", application.name], ["Email address", application.provider_email || application.email],
    ["Account role", application.role], ["Contact phone", application.contact_phone],
    ["Professional registration", application.registration_number], ["Registering body / jurisdiction", application.registering_body],
    ["Qualification", application.qualification], ["Specialty", application.specialty],
    ["Clinic name", application.clinic_name], ["Years of experience", application.years_experience],
    [application.role === "pharmacist" ? "Shop address" : "Practice address", application.practice_address],
    ["Shop name", application.shop_name], ["Shop licence number", application.shop_license],
    ["Shop licence expiry", application.shop_license_expires ? date(application.shop_license_expires) : null],
    ["Opening hours", application.opening_hours], ["Application version", application.version],
    ["Submitted", dateTime(application.created_at)], ["Verification valid until", application.valid_until ? dateTime(application.valid_until) : null],
    ["Latest decision reason", application.reason],
  ];
  return <div className="stack"><EmailVerification verified={application.email_verified}/><dl className="detail-list">
    {fields.filter(([, value]) => value !== "" && value !== null && value !== undefined).map(([label, value]) =>
      <div className="detail-item" key={label}><dt>{label}</dt><dd className="wrap-text">{value}</dd></div>)}
  </dl></div>;
}

export function ReviewHistory({ reviews }: { reviews: ProviderReview[] }) {
  if (!reviews?.length) return <p className="muted">No review decisions have been recorded for this submission.</p>;
  return <div>{reviews.map((review, index) => <article className="timeline-item" key={`${review.created_at}-${index}`}>
    <time>{dateTime(review.created_at)} · {review.reviewer_name}</time>
    <h3><Badge>{review.decision}</Badge></h3><p className="wrap-text">{review.reason}</p>
    {review.evidence_reviewed && <p className="muted wrap-text">Evidence reviewed: {review.evidence_reviewed}</p>}
    {review.valid_until && <p className="muted">Valid until {dateTime(review.valid_until)}</p>}
  </article>)}</div>;
}
