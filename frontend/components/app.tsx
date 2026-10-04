"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { BadgeCheck, BarChart3, ChevronRight, ClipboardList, FileHeart, History, House, IdCard, LockKeyhole, LogOut, Pill, ScanLine, Settings2, ShieldCheck, Stethoscope, UserRound, UsersRound, type LucideIcon } from "lucide-react";
import { api, post } from "@/lib/api";
import type { User } from "@/lib/types";
import { Logo, Public } from "./auth";
import { Landing } from "./landing";
import { Feedback, Loading } from "./ui";
import { Patient } from "./patient";
import { ProviderPage } from "./provider";
import { AdminPage } from "./admin-page";
import { useWorkspaceNavigation } from "@/lib/use-workspace-navigation";

type Nav = [string, string, LucideIcon];
const menus: Record<string, Nav[]> = {
  patient: [["overview", "Overview", House], ["card", "Health card", IdCard], ["records", "Medical records", ClipboardList], ["visits", "Recent visits", Stethoscope], ["reports", "Medical reports", FileHeart], ["prescriptions", "Prescriptions", Pill], ["dispensing", "Dispensing history", ClipboardList], ["profile", "My profile", UserRound]],
  doctor: [["patients", "My patients", UsersRound], ["request", "Find patient", ScanLine], ["profile", "My profile", UserRound], ["verification", "My verification", BadgeCheck]],
  pharmacist: [["prescriptions", "Find prescriptions", Pill], ["dispensing", "Dispensing history", ClipboardList], ["verification", "Shop & verification", BadgeCheck]],
  admin: [["ml", "ML insights", BarChart3], ["doctors", "Doctor approvals", Stethoscope], ["pharmacists", "Pharmacist approvals", Pill], ["audit", "Security audit", History]],
};
const sectionOrder = Object.fromEntries(Object.entries(menus).map(([role, items]) => [role, [...items.map(([id]) => id), "security"]]));
const titles: Record<string, [string, string]> = {
  ml: ["ML insights", "Understand patterns in synthetic patient data."],
  visits: ["Recent doctor visits", "Consultations, prescriptions, and reports together in one timeline."], reports: ["Medical reports", "Upload and keep your reports with your health history."],
  overview: ["Your health, all together.", "A little clarity for your everyday care."], profile: ["My health profile", "Your details help your care team know you better."], card: ["Your health card", "One identity to connect your care, wherever you go."], records: ["Your medical timeline", "A connected history, with every visit in its place."], prescriptions: ["Prescriptions", "Instructions and medicines prescribed by your doctor."], dispensing: ["Dispensing history", "A record of medicines handed over by verified pharmacies."], audit: ["Access history", "See when information was accessed or changed."], patients: ["My patients", "Your saved patients, ready for the next visit."], request: ["Connect with a patient", "Scan a health card or enter a patient’s short account ID."], verification: ["Professional verification", "Keep your credentials and application up to date."], doctors: ["Doctor approvals", "Review qualifications and credentials before enabling patient access."], pharmacists: ["Pharmacist approvals", "Review professional registration and pharmacy shop credentials."], security: ["Account security", "Manage your password and active sessions."],
};
function adminTab(pathname: string) { const section=pathname.split("/")[2]; return sectionOrder.admin.includes(section) ? section : "ml"; }
export function App() {
  const pathname=usePathname();
  const [user, setUser] = useState<User | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [cardIdentifier,setCardIdentifier]=useState("");
  useEffect(() => { const locator = window.location.pathname.match(/^\/health-card\/([^/]+)/)?.[1]; if(locator)setCardIdentifier(locator); const expired = () => {setUser(null);setError("");window.scrollTo({top:0,behavior:"instant"});}; window.addEventListener("medylink:session-expired",expired); return () => window.removeEventListener("medylink:session-expired",expired); },[]);
  useEffect(() => { let alive = true; api<{user: User}>("/auth/me/").then(result => { if (alive) { setUser(result.user); } }).catch(() => {}).finally(() => { if (alive) setLoading(false); }); return () => { alive = false; }; }, []);
  const role = user?.role || "patient";
  const workspacePage = !!user?.email_verified && (role === "admin" || !pathname.startsWith("/admin/"));
  const initialSection = cardIdentifier && role === "doctor" ? "request" : cardIdentifier && role === "pharmacist" ? "prescriptions" : sectionOrder[role][0];
  const workspaceNavigation = useWorkspaceNavigation(workspacePage, role, sectionOrder[role], initialSection);
  const tab = workspaceNavigation.active;
  function navigate(next: string) {
    if (pathname.startsWith("/admin/") && role !== "admin") window.history.replaceState(null, "", `/#${role}-${next}`);
    else workspaceNavigation.navigate(next === "request" && role === "pharmacist" ? "prescriptions" : next);
  }
  function login(next: User) {
    setUser(next);
    const hash = window.location.hash.startsWith(`#${next.role}-`) ? window.location.hash : "";
    const base = next.role === "admin" ? `/admin/${adminTab(pathname)}` : "/";
    window.history.replaceState(null, "", base + hash);
  }
  function signedOut() { setUser(null); setError(""); window.history.replaceState(null, "", "/"); window.scrollTo({ top: 0, behavior: "instant" }); }
  async function logout() { try { await post("/auth/logout/"); signedOut(); } catch { setError("Could not sign out. Check your connection and try again."); } }
  if (loading) return <div style={{maxWidth:400,margin:"15vh auto",padding:30}}><Logo/><Loading/></div>;
  if (!user) return pathname === "/" ? <Landing/> : <Public onLogin={login}/>;
  const nav: Nav[] = [...menus[user.role], ["security", "Security settings", Settings2]];
  const current = nav.find(item => item[0] === tab); const title = tab === "profile" && user.role === "doctor" ? ["My profile", "Your personal details, professional credentials, and account security."] : titles[tab] || titles.overview;
  return <div className={`app-shell${workspacePage ? " workspace-shell" : ""}`}><aside className="sidebar"><Logo/><span className="workspace-label">{user.role === "patient" ? "MY HEALTH SPACE" : user.role === "admin" ? "ADMINISTRATION" : "CARE WORKSPACE"}</span><nav className="nav-items" aria-label="Main navigation">{nav.map(([id, label, Icon]) => workspacePage ? <a key={id} href={role === "admin" ? `/admin/${id}` : `#${role}-${id}`} className={`nav-item ${tab === id ? "active" : ""}`} aria-current={tab === id ? "location" : undefined} onClick={event => { if (event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { event.preventDefault(); navigate(id); } }}><Icon size={18} strokeWidth={1.6}/>{label}</a> : <button key={id} className={`nav-item ${tab === id ? "active" : ""}`} aria-current={tab === id ? "page" : undefined} onClick={() => navigate(id)}><Icon size={18} strokeWidth={1.6}/>{label}</button>)}</nav><div className="sidebar-bottom"><div className="privacy-note"><ShieldCheck size={19}/><strong>Verified care. Connected records.</strong><span>Professional accounts are reviewed. Access and changes are recorded.</span></div><div className="account-block"><span className="avatar">{user.name.slice(0,1).toUpperCase()}</span><div><div className="account-name">{user.name}</div><div className="account-role">{user.role} · {user.account_id}</div></div><button className="signout" aria-label="Sign out" title="Sign out" onClick={logout}><LogOut size={17}/></button></div></div></aside>
    <div><header className="topbar"><div className="breadcrumb"><span>{user.role === "patient" ? "My health" : "Workspace"}</span><ChevronRight size={12}/><strong>{current?.[1]}</strong></div><div className="topbar-right"><span className="secure-label"><LockKeyhole size={12}/>Private workspace</span><span>{new Intl.DateTimeFormat("en-IN",{day:"numeric",month:"long",year:"numeric"}).format(new Date())}</span><button className="signout topbar-mobile-account" style={{display:"none"}} onClick={logout} aria-label="Sign out"><LogOut size={17}/></button></div></header><main className="main-content">{!workspacePage && <div className="page-heading"><div><p className="eyebrow">MEDYLINK</p><h1>{title[0]}</h1><p>{title[1]}</p></div></div>}<Feedback error={error}/>{!user.email_verified ? <div className="panel"><h2>Verify your email to continue</h2><p className="muted">Use the email verification page to request and enter a six-digit code for {user.email}.</p><button className="button secondary section-gap" onClick={logout}>Back to sign in</button></div> : pathname.startsWith("/admin/") && user.role !== "admin" ? <div className="panel"><h2>Administrator access required</h2><p className="muted">This page is only available to an administrator.</p><button className="button secondary section-gap" onClick={() => navigate(menus[user.role][0][0])}>Return to my workspace</button></div> : user.role === "patient" ? <Patient key={user.id} user={user} navigate={navigate} onLogout={signedOut}/> : user.role === "admin" ? <AdminPage key={user.id} user={user} onLogout={signedOut}/> : <ProviderPage key={user.id} user={user} navigate={navigate} onUserChange={setUser} initialIdentifier={cardIdentifier} activeSection={tab} onLogout={signedOut}/>}<footer className="app-footer"><span>MedyLink · Your health, connected</span><span style={{display:"flex",gap:6,alignItems:"center"}}><Stethoscope size={12}/>Care, connected</span></footer></main></div></div>;
}
