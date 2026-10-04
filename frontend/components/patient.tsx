"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { UserRound } from "lucide-react";
import { api, message, values } from "@/lib/api";
import type { Profile, User } from "@/lib/types";
import { AsyncForm, Feedback, Field, Panel, QueryState, Select, Textarea } from "./ui";
import { DispensingHistory, Entries, Prescriptions, Records } from "./clinical";
import { HealthCard, PhotoUpload } from "./patient-card";
import { PatientVisits } from "./patient-visits";
import { PatientReports } from "./patient-reports";
import { PatientDashboard } from "./patient-dashboard";
import { Security } from "./security";
import styles from "./patient.module.css";

export { HealthCard } from "./patient-card";

function ProfileForm({ profile, user, reload }: { profile: Profile; user: User; reload: () => void }) {
  return <div className="grid-main">
    <Panel title="Personal information" eyebrow="YOUR PROFILE">
      <AsyncForm submit="Save profile" successText="Profile updated." onSubmit={async form => {
        await api("/patients/me/", { method: "PATCH", body: JSON.stringify(values(form)) });
        reload();
      }}>
        <div className="form-grid">
          <Field label="Full name" value={profile.name} readOnly hint="Name registered with your account."/>
          <Field label="Account ID" value={profile.account_id} readOnly hint="Your unique MedyLink ID."/>
          <Field label="Existing health ID" value={profile.health_id} readOnly hint="Older cards with this ID continue to work."/>
          <Field label="Date of birth" name="date_of_birth" type="date" min="1900-01-01" required defaultValue={profile.date_of_birth || ""} hint="MedyLink supports adults managing their own profiles."/>
          <Select label="Gender (optional)" name="gender" defaultValue={profile.gender || ""}><option value="">Not specified</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option><option value="prefer_not_to_say">Prefer not to say</option></Select>
          <Field label="Phone number" name="phone" type="tel" maxLength={30} defaultValue={profile.phone} autoComplete="tel"/>
          <Select label="Blood group" name="blood_group" defaultValue={profile.blood_group || "unknown"}><option value="unknown">Unknown</option>{["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"].map(value => <option key={value}>{value}</option>)}</Select>
          <Select label="Allergy status" name="allergy_status" defaultValue={profile.allergy_status || "unknown"}><option value="unknown">Unknown / not assessed</option><option value="none_known">No known allergies</option><option value="reported">Known allergies (listed separately)</option></Select>
        </div>
        <Textarea label="Contact address" name="address" defaultValue={profile.address}/>
        <Field label="Emergency contact" name="emergency_contact" maxLength={250} defaultValue={profile.emergency_contact} placeholder="Name, relationship, phone number"/>
      </AsyncForm>
    </Panel>
    <div className="stack">
      <Panel title="Your profile photo"><div className={styles.profilePhoto}><span>{profile.photo_url ? <img src={profile.photo_url} alt={profile.name + "'s profile photo"}/> : <UserRound size={35} strokeWidth={1.3}/>}</span><div><h3>{profile.name}</h3><p>Make your health card yours.</p></div></div><PhotoUpload onUploaded={reload}/></Panel>
      <Entries patientId={profile.id} kind="allergies" user={user}/>
      <Entries patientId={profile.id} kind="conditions" user={user}/>
    </div>
  </div>;
}

// Retain the loaded profile while refreshing so open forms and card state survive.
function usePatientProfile() {
  const [data, setData] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => {
    setLoading(true);
    setError("");
    setVersion(value => value + 1);
  }, []);
  useEffect(() => {
    let alive = true;
    api<Profile>("/patients/me/")
      .then(profile => { if (alive) setData(profile); })
      .catch(error => { if (alive) setError(message(error)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [version]);
  return { data, error, loading, reload };
}

function PatientSection({ id, title, description, children }: { id: string; title: string; description: string; children: ReactNode }) {
  return <section id={`patient-${id}`} data-patient-section={id} aria-labelledby={`patient-${id}-title`} className="patient-section">
    <header className={styles.sectionHeading}><h2 id={`patient-${id}-title`} tabIndex={-1}>{title}</h2><p>{description}</p></header>
    {children}
  </section>;
}

export function Patient({ user, navigate, onLogout }: { user: User; navigate: (tab: string) => void; onLogout: () => void }) {
  const query = usePatientProfile();
  const profile = query.data;
  const initialProfileQuery = { ...query, loading: !profile && query.loading, error: profile ? "" : query.error };
  return <div className={styles.continuousPage}>
    <section id="patient-overview" data-patient-section="overview" aria-labelledby="patient-overview-title" className="patient-section">
      <header className="page-heading"><div><p className="eyebrow">HELLO, {user.name.split(" ")[0]}</p><h1 id="patient-overview-title" tabIndex={-1}>Your health, all together.</h1><p>A little clarity for your everyday care.</p></div></header>
      {profile && query.loading && <p className="progress-note" role="status">Updating your profile...</p>}
      {profile && query.error && <div className="stack"><Feedback error={query.error}/><button type="button" className="button secondary small" onClick={query.reload}>Retry profile refresh</button></div>}
      <QueryState query={initialProfileQuery}>{profile && <PatientDashboard profile={profile} user={user} navigate={navigate} showVisits={false}/>}</QueryState>
    </section>
    <PatientSection id="card" title="Your health card" description="One identity to connect your care, wherever you go.">
      <QueryState query={initialProfileQuery}>{profile && <div className={styles.fullCard}><Panel><HealthCard profile={profile} full showPhotoUpload={false} onProfileUpdated={query.reload}/></Panel></div>}</QueryState>
    </PatientSection>
    <PatientSection id="records" title="Your medical timeline" description="A connected history, with every visit in its place."><Records path="/patients/me/records/" showHeading={false}/></PatientSection>
    <PatientSection id="visits" title="Recent doctor visits" description="Consultations, prescriptions, and reports together in one timeline."><PatientVisits user={user} navigate={navigate} showReportLibrary={false} showHeading={false} showNavigation={false}/></PatientSection>
    <PatientSection id="reports" title="Medical reports" description="Upload and keep your reports with your health history."><PatientReports user={user} showHeading={false}/></PatientSection>
    <PatientSection id="prescriptions" title="Prescriptions" description="Instructions and medicines prescribed by your doctor."><Prescriptions path="/patients/me/prescriptions/" user={user} showHeading={false}/></PatientSection>
    <PatientSection id="dispensing" title="Dispensing history" description="A record of medicines handed over by verified pharmacies."><DispensingHistory path="/patients/me/dispensing/" showHeading={false}/></PatientSection>
    <PatientSection id="profile" title="My health profile" description="Your details help your care team know you better.">
      <QueryState query={initialProfileQuery}>{profile && <ProfileForm profile={profile} user={user} reload={query.reload}/>}</QueryState>
    </PatientSection>
    <PatientSection id="security" title="Account security" description="Manage your password and active sessions."><Security user={user} onLogout={onLogout}/></PatientSection>
  </div>;
}
