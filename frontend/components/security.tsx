"use client";
import { LockKeyhole, Monitor, ShieldCheck } from "lucide-react";
import { api, dateTime, list, post } from "@/lib/api";
import type { Session, User } from "@/lib/types";
import { Action, Badge, Empty, Panel, QueryState, Refresh, useQuery } from "./ui";

export function Security({ user, onLogout }: { user: User; onLogout: () => void }) {
  const sessions = useQuery<{ results: Session[] }>("/auth/sessions/");
  return <div className="stack">
    <Panel title="Your account">
      <dl className="detail-list">
        <div className="detail-item"><dt>Account ID</dt><dd><code>{user.account_id}</code></dd></div>
        <div className="detail-item"><dt>Name</dt><dd>{user.name}</dd></div>
        <div className="detail-item"><dt>Email</dt><dd>{user.email}</dd></div>
        <div className="detail-item"><dt>Role</dt><dd style={{ textTransform: "capitalize" }}>{user.role}</dd></div>
        <div className="detail-item"><dt>Email verified</dt><dd>{user.email_verified ? "Yes" : "No"}</dd></div>
      </dl>
      <div className="security-hint section-gap"><ShieldCheck size={19}/><span>Sign in with your email and password. Keep your password and email verification codes private.</span></div>
      <div className="section-gap"><Action onClick={() => post("/auth/forgot-password/", { email: user.email })}>Send password reset email</Action><p className="progress-note">Check your inbox after requesting. Resetting your password ends all active sessions.</p></div>
    </Panel>
    <Panel title="Active sessions" action={<Refresh onClick={sessions.reload}/>}>
      <QueryState query={sessions}>{list(sessions.data).length ? list(sessions.data).map(session => <div className="list-row" key={session.id}>
        <span className="row-icon"><Monitor size={18}/></span>
        <div className="row-content"><h3>{session.current ? "This device" : "Signed-in device"} {session.current && <Badge>current</Badge>}</h3><p style={{ overflowWrap: "anywhere" }}>{session.user_agent || "Browser details unavailable"}</p><p>Last used {dateTime(session.last_used_at)} · Expires {dateTime(session.expires_at)}</p></div>
        <Action danger onClick={async () => { await api(`/auth/sessions/${session.id}/`, { method: "DELETE" }); if (session.current) onLogout(); else sessions.reload(); }}>End session</Action>
      </div>) : <Empty title="No active sessions listed.">Refresh to get the latest session activity.</Empty>}</QueryState>
      <div className="section-gap"><Action danger onClick={async () => { await post("/auth/logout-all/"); onLogout(); }}><LockKeyhole size={15}/>Sign out of every device</Action></div>
    </Panel>
  </div>;
}
