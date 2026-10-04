"use client";

import { useState } from "react";
import { ArrowRight, LockKeyhole, ShieldCheck } from "lucide-react";
import { api, date, values } from "@/lib/api";
import type { Application, User } from "@/lib/types";
import { AsyncForm, Badge, Feedback, Field, Panel, QueryState, useQuery } from "./ui";

type DoctorProfileData = { user: User; application: Application | null };
export function DoctorProfile({ navigate, onUserChange, showNavigation = true, currentApplication }: { navigate: (tab: string) => void; onUserChange: (user: User) => void; showNavigation?: boolean; currentApplication?: Application | null }) {
  const query = useQuery<DoctorProfileData>("/doctor/profile/");
  const [saved, setSaved] = useState(false);
  const application = currentApplication === undefined ? query.data?.application : currentApplication;
  return <div className="stack"><Feedback success={saved ? "Profile updated." : ""}/><QueryState query={query}>{query.data && <div className="grid-main">
    <Panel title="Personal details" eyebrow="YOUR DOCTOR PROFILE">
      <p className="progress-note">Keep your name and contact number current. Your account ID stays with you.</p>
      <AsyncForm submit="Save profile" successText="" onSubmit={async form => {
        setSaved(false);
        const data = values(form);
        const result = await api<DoctorProfileData>("/doctor/profile/", { method: "PATCH", body: JSON.stringify({ name: data.name, phone: data.phone }) });
        onUserChange(result.user);
        setSaved(true);
        query.reload();
      }}>
        <Field label="Full name" name="name" required maxLength={150} autoComplete="name" defaultValue={query.data.user.name}/>
        <Field label="Contact phone" name="phone" type="tel" maxLength={30} autoComplete="tel" defaultValue={query.data.user.phone || ""}/>
        <Field label="Email address" value={query.data.user.email} readOnly hint="Your verified sign-in email."/>
        <Field label="Account ID" value={query.data.user.account_id} readOnly hint="Your permanent doctor ID."/>
      </AsyncForm>
    </Panel>
    <div className="stack"><Panel title="Professional details" action={<Badge>{application?.status || "not submitted"}</Badge>}>
      {application ? <dl className="detail-list">
        <div className="detail-item"><dt>Registration number</dt><dd>{application.registration_number}</dd></div>
        <div className="detail-item"><dt>Registering body</dt><dd>{application.registering_body}</dd></div>
        <div className="detail-item"><dt>Qualification</dt><dd>{application.qualification || "—"}</dd></div>
        <div className="detail-item"><dt>Specialty</dt><dd>{application.specialty || "—"}</dd></div>
        <div className="detail-item"><dt>Clinic / hospital</dt><dd>{application.clinic_name || "—"}</dd></div>
        <div className="detail-item"><dt>Verification valid until</dt><dd>{date(application.valid_until)}</dd></div>
      </dl> : <p className="muted">Submit your professional details to start verification.</p>}
      <div className="security-hint section-gap"><ShieldCheck size={18}/><span>Changes to professional credentials go through administrator review. Manage evidence and previous submissions in My verification.</span></div>
      {showNavigation && <button className="button secondary section-gap" type="button" onClick={() => navigate("verification")}>Manage verification<ArrowRight size={15}/></button>}
    </Panel>{showNavigation && <Panel title="Keep your account secure"><p className="progress-note">Manage your password, review signed-in devices, or end active sessions.</p><button className="button secondary" type="button" onClick={() => navigate("security")}><LockKeyhole size={15}/>Manage account security</button></Panel>}</div>
  </div>}</QueryState></div>;
}
