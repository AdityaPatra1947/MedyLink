"use client";

import { useRef, useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Check, CheckCircle2, FileText, HeartPulse, LoaderCircle, LockKeyhole, Mail, Pill, ShieldCheck, Stethoscope, Upload, UserRound } from "lucide-react";
import { api, message } from "@/lib/api";
import { Feedback, Field } from "./ui";
import { EmailVerification } from "./email-verification";
import styles from "./registration.module.css";

export type RegistrationRole = "patient" | "doctor" | "pharmacist";

const roles = {
  patient: {
    name: "Patient",
    title: "Your health starts here.",
    description: "Create one personal health identity and keep your care connected.",
    chooser: "Keep your health card, consultations, and prescriptions together. Keep your health history connected with verified professionals.",
    icon: UserRound,
    detailStep: "Health details",
    finalStep: "Review & consent",
    submit: "Create patient account",
  },
  doctor: {
    name: "Doctor",
    title: "A clearer view of care.",
    description: "Join as a doctor and apply to care for patients across their care journey.",
    chooser: "See patient history, record consultations, and issue prescriptions after credential review.",
    icon: Stethoscope,
    detailStep: "Professional details",
    finalStep: "Evidence & review",
    submit: "Submit doctor application",
  },
  pharmacist: {
    name: "Pharmacist",
    title: "Connect your pharmacy.",
    description: "Register your professional details and pharmacy shop for manual verification.",
    chooser: "Access approved prescriptions and record medicine handovers for your verified pharmacy shop.",
    icon: Pill,
    detailStep: "Pharmacy details",
    finalStep: "Evidence & review",
    submit: "Submit pharmacy application",
  },
};

function localDate(value = new Date()) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

function adultDate() {
  const value = new Date();
  value.setFullYear(value.getFullYear() - 18);
  return localDate(value);
}

function SectionHeading({ number, title, children }: { number: string; title: string; children: ReactNode }) {
  return <div className={styles.sectionHeading}><span>{number}</span><div><h2>{title}</h2><p>{children}</p></div></div>;
}

export function Registration({ role }: { role: RegistrationRole | null }) {
  if (role) return <RegistrationForm key={role} role={role}/>;
  return <main className={styles.chooser}>
    <div className={styles.chooserHeading}>
      <span className="pill"><span className="dot"/>YOUR PLACE IN CONNECTED CARE</span>
      <h1>A healthier connection.<br/><em>Choose how you join.</em></h1>
      <p>One account, one role. Find the right space for you.</p>
    </div>
    <div className={styles.roleCards}>
      {(Object.keys(roles) as RegistrationRole[]).map(key => {
        const item = roles[key];
        const Icon = item.icon;
        return <section className={styles.roleCard} key={key}>
          <span className={styles.roleIcon}><Icon size={27} strokeWidth={1.5}/></span>
          <p className="eyebrow">{key === "patient" ? "MY HEALTH" : "PROFESSIONAL CARE"}</p>
          <h2>{item.name}</h2>
          <p>{item.chooser}</p>
          <div className={styles.roleRequirement}><Check size={14}/>{key === "patient" ? "For adults managing their own care" : "Credentials reviewed by an administrator"}</div>
          <Link className="button primary" href={`/register/${key}`}>Continue as {key}<ArrowRight size={15}/></Link>
        </section>;
      })}
    </div>
    <div className={styles.chooserFoot}><LockKeyhole size={15}/><span>Your records are available to approved care professionals. Provider activity is recorded.</span></div>
    <p className={styles.signIn}>Already registered? <Link href="/login">Sign in to your account</Link></p>
  </main>;
}

function RegistrationForm({ role }: { role: RegistrationRole }) {
  const info = roles[role];
  const Icon = info.icon;
  const isPatient = role === "patient";
  const [step, setStep] = useState(0);
  const [data, setData] = useState<Record<string, string>>({ blood_group: "unknown", gender: "" });
  const [documents, setDocuments] = useState<File[]>([]);
  const [photo, setPhoto] = useState<File>();
  const [consent, setConsent] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [complete, setComplete] = useState(false);
  const formHeading = useRef<HTMLHeadingElement>(null);
  const steps = ["Your account", info.detailStep, info.finalStep];
  const patch = (name: string, value: string) => setData(previous => ({ ...previous, [name]: value }));
  const input = (name: string) => ({ name, value: data[name] || "", onChange: (event: React.ChangeEvent<HTMLInputElement>) => patch(name, event.target.value) });

  function textArea(label: string, name: string, required = false, placeholder?: string) {
    return <label className="field"><span>{label}{required && <span className="required"> *</span>}</span><textarea name={name} value={data[name] || ""} onChange={event => patch(name, event.target.value)} required={required} rows={3} maxLength={500} placeholder={placeholder}/></label>;
  }

  function changeStep(next: number) {
    setError("");
    setStep(next);
    requestAnimationFrame(() => formHeading.current?.focus());
  }

  function fileProblem(files: File[], profilePhoto = false): string {
    if (profilePhoto) {
      if (files.some(file => !/\.(jpe?g|png)$/i.test(file.name))) return "Choose a JPEG or PNG for your photo.";
      if (files.some(file => file.size > 2 * 1024 * 1024)) return "Your photo must be 2 MB or smaller.";
      return "";
    }
    if (files.length > 5) return "Choose up to five credential documents.";
    if (files.some(file => !/\.(pdf|jpe?g|png)$/i.test(file.name))) return "Credential documents must be PDF, JPEG, or PNG files.";
    if (files.some(file => file.size > 5 * 1024 * 1024)) return "Each credential document must be 5 MB or smaller.";
    if (files.reduce((total, file) => total + file.size, 0) > 20 * 1024 * 1024) return "Your credential documents must total 20 MB or less.";
    return "";
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setError("");
    if (step === 0 && data.password !== data.password_confirm) {
      setError("Your passwords do not match. Enter the same password in both fields.");
      event.currentTarget.querySelector<HTMLInputElement>("[name=password_confirm]")?.focus();
      return;
    }
    if (step < 2) { changeStep(step + 1); return; }
    if (!isPatient) {
      const problem = !documents.length ? "Add at least one credential document for review." : fileProblem(documents) || fileProblem(photo ? [photo] : [], true);
      if (problem) { setError(problem); return; }
    }
    const body = new FormData();
    for (const [name, value] of Object.entries(data)) {
      if (!isPatient && ["blood_group", "gender"].includes(name)) continue;
      if (value !== "") body.append(name, value);
    }
    body.set("role", role);
    body.set("consent", String(consent));
    body.set("privacy_version", "1.0");
    documents.forEach(file => body.append("credential_documents", file));
    if (photo) body.append("photo", photo);
    setPending(true);
    try {
      await api("/auth/register/", { method: "POST", body });
      setComplete(true);
      setData(previous => ({ ...previous, password: "", password_confirm: "" }));
      setDocuments([]);
      setPhoto(undefined);
      requestAnimationFrame(() => formHeading.current?.focus());
    } catch (failure) { setError(message(failure)); }
    finally { setPending(false); }
  }

  return <main className={styles.registration}>
    <aside className={styles.introduction}>
      <Link href="/register" className={styles.backLink}><ArrowLeft size={14}/>Choose a different role</Link>
      <span className={styles.roleIcon}><Icon size={27} strokeWidth={1.5}/></span>
      <p className="eyebrow">{info.name.toUpperCase()} REGISTRATION</p>
      <h1>{info.title}</h1>
      <p>{info.description}</p>
      <div className={styles.expectation}>
        <ShieldCheck size={22}/>
        <h3>{isPatient ? "Your records. Connected care." : "A review before patient access."}</h3>
        <p>{isPatient ? "Verify your email to get started. Approved doctors can access your clinical records and approved pharmacies can access prescriptions without an additional permission request." : "Your application starts as pending. An administrator reviews your credentials before you can access patient records."}</p>
      </div>
      <div className={styles.emailNote}><Mail size={16}/><span>Verify by email. Your phone number is an optional contact detail.</span></div>
    </aside>
    <section className={styles.formPanel}>
      {complete ? <div className={styles.complete}>
        <span className={styles.completeIcon}><Mail size={31} strokeWidth={1.4}/></span>
        <p className="eyebrow">YOUR NEXT STEP</p>
        <h2 ref={formHeading} tabIndex={-1}>Check your email</h2>
        <p>If <strong>{data.email}</strong> is eligible, a six-digit verification code is on its way. Enter it below to confirm your email before signing in.</p>
        {!isPatient && <div className={styles.nextStep}><FileText size={20}/><p>New professional applications are pending review. After verifying your email, sign in to follow your application’s status.</p></div>}
        <EmailVerification initialEmail={data.email} initialCooldown={60}/>
      </div> : <>
        <ol className={styles.steps} aria-label="Registration progress">{steps.map((title, index) => <li key={title} className={index === step ? styles.currentStep : index < step ? styles.finishedStep : ""} aria-current={index === step ? "step" : undefined}><span>{index < step ? <Check size={13}/> : index + 1}</span><p>{title}</p></li>)}</ol>
        <div className={styles.formIntro}><p className="eyebrow">STEP {step + 1} OF 3</p><h2 ref={formHeading} tabIndex={-1}>{steps[step]}</h2><p>{step === 0 ? "Start with the details you’ll use to sign in." : step === 1 ? isPatient ? "A few details to make your health profile yours." : "Enter the details shown on your professional credentials." : isPatient ? "Review your details and choose to create your account." : "Upload evidence for your administrator to review."} Fields marked * are required.</p></div>
        <form className={styles.form} onSubmit={submit}>
          <fieldset disabled={pending}>
            {step === 0 && <>
              <div className="form-grid"><Field label="Full name" {...input("name")} required maxLength={150} autoComplete="name" placeholder="Your full name"/><Field label="Email address" {...input("email")} required type="email" maxLength={254} autoComplete="email" placeholder="you@example.com"/></div>
              <Field label="Phone number (optional)" {...input("phone")} type="tel" maxLength={30} autoComplete="tel" hint="For contact only. Verification is by email."/>
              <div className="form-grid"><Field label="Password" {...input("password")} type="password" required minLength={10} maxLength={1024} autoComplete="new-password" hint="At least 10 characters. Avoid common passwords."/><Field label="Confirm password" {...input("password_confirm")} type="password" required minLength={10} maxLength={1024} autoComplete="new-password"/></div>
            </>}
            {step === 1 && isPatient && <>
              <div className="form-grid"><Field label="Date of birth" {...input("date_of_birth")} type="date" required min="1900-01-01" max={adultDate()} hint="For adults aged 18 or older managing their own records."/><label className="field"><span>Gender (optional)</span><select name="gender" value={data.gender} onChange={event => patch("gender", event.target.value)}><option value="">Not specified</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option><option value="prefer_not_to_say">Prefer not to say</option></select></label></div>
              {textArea("Address (optional)", "address", false, "Your contact address")}
              <div className="form-grid"><label className="field"><span>Blood group (optional)</span><select name="blood_group" value={data.blood_group} onChange={event => patch("blood_group", event.target.value)}><option value="unknown">Unknown</option>{["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"].map(group => <option key={group} value={group}>{group}</option>)}</select><small>Leave as unknown if you are unsure.</small></label><Field label="Emergency contact (optional)" {...input("emergency_contact")} maxLength={250} placeholder="Name, relationship, phone number"/></div>
            </>}
            {step === 1 && !isPatient && <>
              <SectionHeading number="01" title="Professional identity">Details for your individual professional registration.</SectionHeading>
              <div className="form-grid"><Field label="Professional registration number" {...input("registration_number")} required maxLength={100}/><Field label="Registering body / jurisdiction" {...input("registering_body")} required maxLength={150} placeholder={role === "doctor" ? "Medical council and state / jurisdiction" : "Pharmacy council and state / jurisdiction"}/></div>
              {role === "doctor" ? <>
                <div className="form-grid"><Field label="Qualification" {...input("qualification")} required maxLength={150} placeholder="e.g. MBBS, MD"/><Field label="Specialty" {...input("specialty")} required maxLength={150}/></div>
                <SectionHeading number="02" title="Your practice">Where you provide care and your experience.</SectionHeading>
                <div className="form-grid"><Field label="Clinic / hospital name (optional)" {...input("clinic_name")} maxLength={180}/><Field label="Years of experience (optional)" {...input("years_experience")} type="number" min="0" max="80" step="1"/></div>
                {textArea("Practice address", "practice_address", true, "Clinic / hospital address, city, state, and postal code")}
              </> : <>
                <SectionHeading number="02" title="Your pharmacy shop">One named pharmacist account represents one shop.</SectionHeading>
                <Field label="Pharmacy shop name" {...input("shop_name")} required maxLength={180}/>
                {textArea("Pharmacy address", "practice_address", true, "Shop address, city, state, and postal code")}
                <div className="form-grid"><Field label="Shop licence number" {...input("shop_license")} required maxLength={100}/><Field label="Shop licence valid until" {...input("shop_license_expires")} type="date" required min={localDate()}/></div>
                <Field label="Opening hours (optional)" {...input("opening_hours")} maxLength={300} placeholder="e.g. Monday–Saturday, 9 am–8 pm"/>
              </>}
            </>}
            {step === 2 && <>
              {!isPatient && <>
                <div className={styles.uploadPanel}><div><Upload size={22}/><h3>Credential evidence</h3><p>{role === "doctor" ? "Upload your professional registration and relevant qualification evidence." : "Upload your pharmacist registration and pharmacy shop licence evidence."}</p></div><Field label="Credential documents" name="credential_documents" type="file" multiple accept=".pdf,.jpg,.jpeg,.png" required={documents.length === 0} hint="1–5 PDF, JPEG, or PNG files. Up to 5 MB each and 20 MB in total." onChange={event => { const files = Array.from(event.target.files || []); setDocuments(files); setError(fileProblem(files)); }}/>{documents.length > 0 && <ul className={styles.fileList}>{documents.map((file, index) => <li key={`${file.name}-${index}`}><FileText size={14}/><span>{file.name}</span><small>{(file.size / 1024 / 1024).toFixed(2)} MB</small></li>)}</ul>}</div>
                <Field label={role === "pharmacist" ? "Shop photo (optional)" : "Profile photo (optional)"} name="photo" type="file" accept=".jpg,.jpeg,.png" hint="JPEG or PNG, up to 2 MB. Submitted privately with your application." onChange={event => { const file = event.target.files?.[0]; setPhoto(file); setError(fileProblem(file ? [file] : [], true)); }}/>{photo && <p className={styles.selectedPhoto}><CheckCircle2 size={14}/>Selected: {photo.name}</p>}
              </>}
              <div className={styles.review}><div><h3>Review your details</h3><button type="button" className="text-button" onClick={() => changeStep(0)}>Edit</button></div><dl><div><dt>Registering as</dt><dd>{info.name}</dd></div><div><dt>Full name</dt><dd>{data.name}</dd></div><div><dt>Email</dt><dd>{data.email}</dd></div>{data.phone && <div><dt>Phone</dt><dd>{data.phone}</dd></div>}{isPatient ? <><div><dt>Date of birth</dt><dd>{data.date_of_birth}</dd></div><div><dt>Blood group</dt><dd>{data.blood_group === "unknown" ? "Unknown" : data.blood_group}</dd></div></> : <><div><dt>Professional registration</dt><dd>{data.registration_number}</dd></div><div><dt>Registering body</dt><dd>{data.registering_body}</dd></div>{role === "doctor" ? <><div><dt>Qualification</dt><dd>{data.qualification}</dd></div><div><dt>Specialty</dt><dd>{data.specialty}</dd></div></> : <><div><dt>Pharmacy shop</dt><dd>{data.shop_name}</dd></div><div><dt>Shop licence</dt><dd>{data.shop_license}</dd></div></>}</>}</dl><button type="button" className="text-button" onClick={() => changeStep(1)}>Edit {isPatient ? "health" : "professional"} details</button></div>
              <label className="checkbox"><input type="checkbox" name="consent" required checked={consent} onChange={event => setConsent(event.target.checked)}/><span>I accept the <Link href="/privacy" target="_blank" rel="noreferrer">privacy notice (version 1.0)</Link> and consent to storing my account{isPatient ? " and health records" : ", professional details, and credential evidence"}. {isPatient ? "I confirm that I am 18 or older and manage my own profile." : "I confirm my professional details are accurate and understand that patient access requires administrator approval."}</span></label>
            </>}
          </fieldset>
          <Feedback error={error}/>
          <div className={styles.formActions}>{step > 0 ? <button type="button" className="button secondary" disabled={pending} onClick={() => changeStep(step - 1)}><ArrowLeft size={15}/>Back</button> : <Link href="/login" className={styles.backLink}>Back to sign in</Link>}<button type="submit" className="button primary" disabled={pending}>{pending && <LoaderCircle size={17} className="spin"/>}{pending ? "Submitting…" : step === 2 ? info.submit : "Continue"}{!pending && <ArrowRight size={16}/>}</button></div>
        </form>
        <div className={styles.privateFoot}><HeartPulse size={15}/><span>{isPatient ? "A local health identity for connected care." : "Registration never grants access to patient records by itself."}</span></div>
      </>}
    </section>
  </main>;
}
