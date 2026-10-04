"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Registration, type RegistrationRole } from "./registration";
import { EmailVerification } from "./email-verification";
import { ArrowLeft, HeartPulse, LockKeyhole, ShieldCheck, Sprout, UserRound } from "lucide-react";
import { post, values } from "@/lib/api";
import type { User } from "@/lib/types";
import { AsyncForm, Field } from "./ui";
import { LocalDemoLink } from "./local-demo-link";

export function Logo() { return <div className="logo"><span className="logo-symbol"><HeartPulse size={23} strokeWidth={1.8}/></span><span>MedyLink<span className="logo-lite">HEALTH, CONNECTED</span></span></div>; }
type Mode = "login" | "register" | "forgot" | "reset" | "verify" | "privacy";
interface AuthResult { user: User }
export function Public({ onLogin }: { onLogin: (user: User) => void }) {
  const pathname = usePathname(); const router = useRouter();
  const registrationRole = (pathname.match(/^\/register\/(patient|doctor|pharmacist)\/?$/)?.[1] || null) as RegistrationRole | null;
  const [mode, setMode] = useState<Mode>("login"); const [token, setToken] = useState(""); const [legacyVerificationLink, setLegacyVerificationLink] = useState(false);
  const [ready, setReady] = useState<string>(""); const [cardLink,setCardLink] = useState(false);
  useEffect(() => {
    setCardLink(pathname.startsWith("/health-card/"));
    const params = new URLSearchParams(window.location.search);
    setToken(pathname.includes("reset-password") ? params.get("token") || "" : "");
    const legacy = pathname.includes("verify-email") && params.has("token");
    setLegacyVerificationLink(previous => pathname.includes("verify-email") && (legacy || previous));
    if (legacy) window.history.replaceState(null, "", pathname);
    if (pathname.includes("reset-password")) setMode("reset");
    else if (pathname.includes("verify-email")) setMode("verify");
    else if (pathname === "/register" || pathname.startsWith("/register/")) setMode("register");
    else if (pathname.includes("privacy")) setMode("privacy");
    else if (pathname.includes("forgot-password")) setMode("forgot");
    else setMode("login");
  }, [pathname]);
  useEffect(() => {
    const unavailable = "MedyLink is temporarily unavailable. Please try again shortly.";
    fetch("/api/v1/ready/", { cache: "no-store" })
      .then(response => { if (!response.ok) setReady(unavailable); })
      .catch(() => setReady(unavailable));
  }, []);
  function choose(next: Mode) {
    const paths: Partial<Record<Mode, string>> = { login: "/login", register: "/register", forgot: "/forgot-password", reset: "/reset-password", verify: "/verify-email", privacy: "/privacy" };
    setMode(next);
    if (paths[next]) router.push(paths[next]!);
  }
  function authenticated(result: AuthResult) {
    if (result.user) onLogin(result.user);
  }
  const headings: Record<Mode, [string, string]> = {
    login: ["Welcome back.", "Sign in to your personal health space."], register: ["A healthier connection.", "Create your account to get started."],
    forgot: ["Forgot your password?", "We’ll email a link if an account exists for this address."], reset: ["A fresh start.", "Choose a strong, unique password for your account."],
    verify: ["Verify your email.", "Enter the six-digit code sent to your email address."],
    privacy: ["Your records. Connected care.", "Privacy notice · version 1.0"],
  };
  return <div className="public"><header className="public-nav"><Link href="/" aria-label="MedyLink home"><Logo/></Link><nav className="public-links"><button className="text-button" onClick={() => choose("privacy")}>Privacy & care</button><button className="button secondary small" onClick={() => choose(mode === "register" ? "login" : "register")}>{mode === "register" ? "Sign in" : "Create account"}</button></nav></header>
    {mode === "register" ? <Registration role={registrationRole}/> : <main className="public-main"><section className="hero"><span className="pill"><span className="dot"/> CARE THAT STAYS WITH YOU</span><h1>Your health story.<br/><em>All together.</em></h1><p>One health identity. A connected medical history. Keep visits, prescriptions, and reports connected with verified care professionals.</p><div className="hero-features"><div className="hero-feature"><span className="hero-feature-icon"><UserRound size={19}/></span><div><strong>One card. Your care, connected.</strong><p>A personal health ID that goes where you go.</p></div></div><div className="hero-feature"><span className="hero-feature-icon"><ShieldCheck size={19}/></span><div><strong>Care from verified professionals.</strong><p>Doctors and pharmacies are reviewed before providing care.</p></div></div><div className="hero-feature"><span className="hero-feature-icon"><Sprout size={19}/></span><div><strong>A clearer picture of your health.</strong><p>Keep consultations and prescriptions together.</p></div></div></div><div className="hero-note"><LockKeyhole size={13}/> Your card identifies you. Provider sign-in and approval are required.</div></section>
    <section className="auth-panel"><p className="eyebrow">YOUR PERSONAL HEALTH SPACE</p><h2>{headings[mode][0]}</h2><p className="muted">{headings[mode][1]}</p>{cardLink && <div className="notice info" style={{marginBottom:18}}><ShieldCheck size={17}/><span>Health card scanned. Sign in as an approved provider to find the patient record. No medical details are shown by this link.</span></div>}{ready && <div className="notice info" style={{marginBottom:18}} role="status"><LockKeyhole size={16}/><span>{ready}</span></div>}
    {mode === "login" && <><LocalDemoLink/><AsyncForm submit="Sign in" successText="" onSubmit={async form => authenticated(await post<AuthResult>("/auth/login/", values(form)))}><Field label="Email address" name="email" type="email" autoComplete="email" required placeholder="you@example.com"/><Field label="Password" name="password" type="password" autoComplete="current-password" required placeholder="Enter your password"/></AsyncForm><div className="auth-links"><button className="text-button" onClick={() => choose("forgot")}>Forgot password?</button><button className="text-button" onClick={() => choose("verify")}>Verify email</button></div><div className="auth-footer">New to MedyLink? <button className="text-button" onClick={() => choose("register")}>Create an account</button></div></>}
    {mode === "forgot" && <AsyncForm submit="Send reset link" successText="If an account exists, a password reset link has been sent." onSubmit={form => post("/auth/forgot-password/", values(form))}><Field label="Email address" name="email" type="email" required autoComplete="email"/></AsyncForm>}
    {mode === "reset" && <AsyncForm submit="Reset password" successText="Password reset. You can now sign in with your new password." onSubmit={form => post("/auth/reset-password/", { ...values(form), token })}>{!token && <Field label="Reset token from email" value={token} onChange={event => setToken(event.target.value)} required/>}<Field label="New password" name="password" type="password" required minLength={10} autoComplete="new-password"/></AsyncForm>}
    {mode === "verify" && <EmailVerification legacyLink={legacyVerificationLink}/>}
    {mode === "privacy" && <div className="legal-copy"><p>MedyLink stores your account, health profile, clinical records, reports, and activity history to support connected care.</p><p>Administrators approve professional accounts. Approved doctors can find your record using your health ID or card and view or add clinical information without a separate patient approval step. Approved pharmacies can view prescriptions and relevant allergy information, not your full clinical history or reports.</p><p>Your health card is a local MedyLink identifier, not a government health ID. Its QR code identifies your record; professional sign-in and current approval are required to retrieve information.</p><p>Downloaded cards, prescriptions, and reports leave this application. Previously downloaded copies cannot be recalled. Keep downloads private and follow the retention policy of your operator.</p><p>Provider credentials are reviewed by administrators. Access and changes are logged. Finalized medical records preserve their author and history.</p><p>Use your deployment operator’s contact and retention policy for privacy requests. Do not enter real health information until your operator has completed production setup.</p></div>}
    {!["login", "register"].includes(mode) && <div className="auth-footer"><button className="text-button" onClick={() => choose("login")}><ArrowLeft size={12} style={{display:"inline",marginRight:5}}/>Back to sign in</button></div>}</section></main>}<footer className="public-footer"><span>© {new Date().getFullYear()} MedyLink</span><span>Connected care. With verified professionals.</span></footer></div>;
}
