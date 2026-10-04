"use client";
import { useCallback, useEffect, useId, useState, type ReactNode, type FormEvent, type InputHTMLAttributes } from "react";
import { AlertCircle, ArrowRight, Check, Eye, EyeOff, Inbox, LoaderCircle, RefreshCw } from "lucide-react";
import { api, message } from "@/lib/api";
import styles from "./ui.module.css";

export function useQuery<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(!!path);
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion(value => value + 1), []);
  useEffect(() => {
    let alive = true;
    if (!path) { setData(null); setLoading(false); return; }
    setLoading(true); setError(""); setData(null);
    api<T>(path).then(value => { if (alive) setData(value); }).catch(error => { if (alive) setError(message(error)); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [path, version]);
  return { data, error, loading, reload };
}
export function Feedback({ error, success }: { error?: string; success?: string }) {
  return <>{error && <div className="notice error" role="alert"><AlertCircle size={18}/><span>{error}</span></div>}{success && <div className="notice success" role="status"><Check size={18}/><span>{success}</span></div>}</>;
}
export function Loading() { return <div className="loading" role="status"><LoaderCircle className="spin" size={20}/> Loading your information…</div>; }
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty"><span className="empty-icon"><Inbox size={25}/></span><h3>{title}</h3><p>{children}</p></div>;
}
export function Panel({ title, eyebrow, children, className = "", action }: { title?: string; eyebrow?: string; children: ReactNode; className?: string; action?: ReactNode }) {
  return <section className={`panel ${className}`}>{(title || eyebrow || action) && <div className="panel-head"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}{title && <h2>{title}</h2>}</div>{action}</div>}{children}</section>;
}
export function Badge({ children }: { children: ReactNode }) {
  const value = String(children || "unknown");
  return <span className={`badge badge-${value.toLowerCase().replaceAll(" ", "-")}`}>{value.replaceAll("_", " ")}</span>;
}
export function Field({ label, hint, className = "", ...props }: InputHTMLAttributes<HTMLInputElement> & {label: string; hint?: string}) {
  const generatedId = useId();
  const [passwordVisible, setPasswordVisible] = useState(false);
  if (props.type === "password") {
    const inputId = props.id || generatedId;
    const hintId = `${inputId}-hint`;
    const describedBy = [props["aria-describedby"], hint ? hintId : null].filter(Boolean).join(" ") || undefined;
    return <div className={`field ${styles.passwordField} ${className}`}>
      <label htmlFor={inputId}>{label}{props.required && <span className="required"> *</span>}</label>
      <div className={styles.passwordControl}>
        <input {...props} id={inputId} type={passwordVisible ? "text" : "password"} aria-describedby={describedBy}/>
        <button
          type="button"
          className={styles.passwordToggle}
          aria-label={`${passwordVisible ? "Hide" : "Show"} ${label.toLowerCase()}`}
          aria-controls={inputId}
          disabled={props.disabled}
          onClick={() => setPasswordVisible(visible => !visible)}
        >{passwordVisible ? <EyeOff size={18} aria-hidden="true"/> : <Eye size={18} aria-hidden="true"/>}</button>
      </div>
      {hint && <small id={hintId}>{hint}</small>}
    </div>;
  }
  return <label className={`field ${className}`}><span>{label}{props.required && <span className="required"> *</span>}</span><input {...props}/>{hint && <small>{hint}</small>}</label>;
}
export function Textarea({ label, name, required, defaultValue, placeholder }: {label: string; name: string; required?: boolean; defaultValue?: string; placeholder?: string}) {
  return <label className="field"><span>{label}{required && <span className="required"> *</span>}</span><textarea name={name} required={required} defaultValue={defaultValue} placeholder={placeholder} rows={3}/></label>;
}
export function Select({ label, name, children, defaultValue, required = false, onChange }: {label: string; name: string; children: ReactNode; defaultValue?: string; required?: boolean; onChange?: (value: string) => void}) {
  return <label className="field"><span>{label}{required && <span className="required"> *</span>}</span><select name={name} required={required} defaultValue={defaultValue} onChange={event => onChange?.(event.target.value)}>{children}</select></label>;
}
export function AsyncForm({ children, onSubmit, submit = "Save changes", successText = "Changes saved.", className = "", reset = false }: { children: ReactNode; onSubmit: (form: HTMLFormElement) => Promise<unknown>; submit?: string; successText?: string; className?: string; reset?: boolean }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  async function handle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (pending) return;
    const form = event.currentTarget; setPending(true); setError(""); setSuccess("");
    try { await onSubmit(form); setSuccess(successText); if (reset) form.reset(); }
    catch (error) { setError(message(error)); }
    finally { setPending(false); }
  }
  return <form className={`form ${className}`} onSubmit={handle}><fieldset disabled={pending}>{children}</fieldset><Feedback error={error} success={success}/><button className="button primary" disabled={pending} type="submit">{pending ? <LoaderCircle className="spin" size={17}/> : null}{pending ? "Please wait…" : submit}{!pending && <ArrowRight size={16}/>}</button></form>;
}
export function Action({ children, onClick, danger = false, className = "", after }: {children: ReactNode; onClick: () => Promise<unknown>; danger?: boolean; className?: string; after?: () => void}) {
  const [pending, setPending] = useState(false); const [error, setError] = useState("");
  return <div className="action-wrap"><button className={`button ${danger ? "danger" : "secondary"} ${className}`} type="button" disabled={pending} onClick={async () => { if (pending) return; setPending(true); setError(""); try { await onClick(); after?.(); } catch (error) { setError(message(error)); } finally { setPending(false); } }}>{pending && <LoaderCircle size={16} className="spin"/>}{children}</button><Feedback error={error}/></div>;
}
export function QueryState({ query, children }: { query: {loading: boolean; error: string; reload: () => void}; children: ReactNode }) {
  if (query.loading) return <Loading/>;
  if (query.error) return <><Feedback error={query.error}/><button className="button secondary" onClick={query.reload}><RefreshCw size={15}/>Try again</button></>;
  return <>{children}</>;
}
export function Refresh({ onClick }: { onClick: () => void }) { return <button className="button quiet small" onClick={onClick}><RefreshCw size={15}/>Refresh</button>; }
