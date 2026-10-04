"use client";

import type { ReactNode } from "react";
import type { User } from "@/lib/types";
import { AdminApprovals } from "./admin";
import { AdminAnalytics } from "./admin-analytics";
import { AdminML } from "./admin-ml";
import { AuditHistory } from "./clinical";
import { Security } from "./security";

function AdminSection({ id, title, description, first = false, children }: { id: string; title: string; description: string; first?: boolean; children: ReactNode }) {
  const Heading = first ? "h1" : "h2";
  return <section id={`admin-${id}`} data-workspace-section={id} aria-labelledby={`admin-${id}-title`} className="workspace-section">
    <header className="workspace-section-heading"><Heading id={`admin-${id}-title`} tabIndex={-1}>{title}</Heading><p>{description}</p></header>
    {children}
  </section>;
}

export function AdminPage({ user, onLogout, mlPage = false }: { user: User; onLogout: () => void; mlPage?: boolean }) {
  if (mlPage) return <div className="workspace-page"><AdminSection id="ml" title="ML insights" description="Understand patterns in synthetic patient data, with results explained in plain language." first><AdminML/></AdminSection></div>;
  return <div className="workspace-page">
    <AdminSection id="analytics" title="Population analytics" description="Explore synthetic patient cohorts and understand how spatial groups are formed." first><AdminAnalytics/></AdminSection>
    <AdminSection id="doctors" title="Doctor approvals" description="Review qualifications and credentials before enabling patient access."><AdminApprovals role="doctor" showHeading={false}/></AdminSection>
    <AdminSection id="pharmacists" title="Pharmacist approvals" description="Review professional registration and pharmacy shop credentials."><AdminApprovals role="pharmacist" showHeading={false}/></AdminSection>
    <AdminSection id="audit" title="Security audit" description="Review access to information and changes across the workspace."><AuditHistory path="/admin/audit/" showHeading={false}/></AdminSection>
    <AdminSection id="security" title="Account security" description="Manage your password and active sessions."><Security user={user} onLogout={onLogout}/></AdminSection>
  </div>;
}
