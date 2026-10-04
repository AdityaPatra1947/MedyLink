"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, LoaderCircle } from "lucide-react";
import { message, post } from "@/lib/api";
import { Feedback, Field } from "./ui";

export function EmailVerification({
  initialEmail = "",
  initialCooldown = 0,
  legacyLink = false,
}: {
  initialEmail?: string;
  initialCooldown?: number;
  legacyLink?: boolean;
}) {
  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState("");
  const [cooldown, setCooldown] = useState(initialCooldown);
  const [pending, setPending] = useState<"verify" | "resend" | null>(null);
  const [error, setError] = useState("");
  const [sent, setSent] = useState("");
  const [hasRequested, setHasRequested] = useState(initialCooldown > 0);
  const [verified, setVerified] = useState(false);
  const cooldownDeadline = useRef<number | null>(null);
  const form = useRef<HTMLFormElement>(null);
  const success = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (cooldown <= 0 || verified) return;
    if (cooldownDeadline.current === null) cooldownDeadline.current = Date.now() + cooldown * 1000;
    const update = () => setCooldown(Math.max(0, Math.ceil(((cooldownDeadline.current ?? 0) - Date.now()) / 1000)));
    const interval = window.setInterval(update, 1000);
    window.addEventListener("focus", update);
    document.addEventListener("visibilitychange", update);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", update);
      document.removeEventListener("visibilitychange", update);
    };
  }, [cooldown, verified]);

  useEffect(() => {
    if (verified) success.current?.focus();
  }, [verified]);

  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setError("");
    setSent("");
    if (!/^[0-9]{6}$/.test(code)) {
      setError("Enter the six-digit code from your email.");
      return;
    }
    setPending("verify");
    try {
      await post("/auth/verify-email/", { email: email.trim(), code });
      setCode("");
      setVerified(true);
    } catch (failure) {
      setError(message(failure));
    } finally {
      setPending(null);
    }
  }

  async function resend() {
    if (pending || cooldown > 0) return;
    const emailInput = form.current?.elements.namedItem("email") as HTMLInputElement | null;
    if (!emailInput?.reportValidity()) return;
    setPending("resend");
    setError("");
    setSent("");
    try {
      const result = await post<{ resend_after?: number }>("/auth/resend-verification/", { email: email.trim() });
      setCode("");
      setHasRequested(true);
      const seconds = Number.isFinite(result.resend_after) ? Math.max(60, Math.min(300, Math.ceil(result.resend_after!))) : 60;
      cooldownDeadline.current = Date.now() + seconds * 1000;
      setCooldown(seconds);
      setSent("If this address needs verification, a code has been sent. Check your inbox and spam folder.");
    } catch (failure) {
      setError(message(failure));
    } finally {
      setPending(null);
    }
  }

  if (verified) return <div className="stack" style={{ width: "100%", textAlign: "left" }}>
    <div ref={success} tabIndex={-1} className="notice success" role="status"><CheckCircle2 size={19}/><span>Your email is verified. You can now sign in.</span></div>
    <Link href="/login" className="button primary">Sign in<ArrowRight size={16}/></Link>
  </div>;

  return <form ref={form} onSubmit={verify} className="form" style={{ width: "100%", textAlign: "left" }}>
    {legacyLink && <div className="notice info" role="status">Email verification now uses a six-digit code. Enter your email address and select Send code to request a new code.</div>}
    <fieldset disabled={pending !== null}>
      <Field label="Email address" name="email" type="email" required maxLength={254} autoComplete="email" value={email} onChange={event => { setEmail(event.target.value); setCode(""); setError(""); setSent(""); }}/>
      <Field label="Verification code" name="code" type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} minLength={6} required placeholder="6-digit code" value={code} onChange={event => setCode(event.target.value.replace(/[^0-9]/g, "").slice(0, 6))} hint="Use the latest code from your email. It expires after 10 minutes."/>
    </fieldset>
    <Feedback error={error} success={sent}/>
    <button type="submit" className="button primary" disabled={pending !== null}>{pending === "verify" && <LoaderCircle className="spin" size={16}/>} {pending === "verify" ? "Verifying…" : "Verify email"}<ArrowRight size={16}/></button>
    <button type="button" className="button secondary" disabled={pending !== null || cooldown > 0} onClick={resend}>{pending === "resend" ? "Sending…" : cooldown > 0 ? `Resend code in ${cooldown}s` : hasRequested ? "Resend code" : "Send code"}</button>
    <p className="muted" style={{ fontSize: 11 }} aria-live="polite">{cooldown > 0 ? "Please wait before requesting another code." : "You can request a new code if yours expired or did not arrive."} Too many incorrect attempts require a new code.</p>
  </form>;
}
