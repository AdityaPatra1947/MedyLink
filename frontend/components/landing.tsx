"use client";

import { useEffect, useRef, useState, type MouseEvent } from "react";
import Link from "next/link";
import {
  Activity, ArrowDown, ArrowRight, ArrowUpRight, BadgeCheck, Check,
  ChevronDown, ClipboardList, FileHeart, FileText, Heart, HeartPulse,
  History, IdCard, LockKeyhole, Menu, Pill, Plus, QrCode, ScanLine,
  ShieldCheck, Stethoscope, UserRound, UsersRound, X,
} from "lucide-react";
import { Logo } from "./auth";
import styles from "./landing.module.css";

const navigation = [
  ["features", "Why MedyLink"],
  ["how-it-works", "How it works"],
  ["for-everyone", "Who it’s for"],
  ["questions", "FAQs"],
];

const roles = {
  patient: {
    label: "Patients", icon: Heart,
    eyebrow: "A little clarity. A lot less paperwork.",
    title: "Feel more at home with your health.",
    description: "From your first consultation to your next follow-up, keep the details that matter within reach.",
    points: ["Your own health card and unique patient ID", "Doctor visits, reports, and prescriptions together", "Health trends based on your recorded information"],
    action: "Create a patient account", note: "Verify your email to get started.",
    previewTitle: "Your care, in one place", previewNote: "A connected view of your health journey",
    items: [[IdCard, "Health card", "One identity for your care"], [FileHeart, "Medical reports", "View and download your documents"], [Activity, "Health overview", "Follow your recorded trends"]],
  },
  doctor: {
    label: "Doctors", icon: Stethoscope,
    eyebrow: "More context for every consultation.",
    title: "See the story before the next chapter.",
    description: "Find a patient with their health card or ID, review their history, and add the next step in their care.",
    points: ["Find patients by QR code or unique ID", "Review earlier consultations and uploaded reports", "Create new records and prescriptions, with your authorship preserved"],
    action: "Create a doctor account", note: "Email verification and administrator approval are required.",
    previewTitle: "Ready for the next visit", previewNote: "A workspace built around continuity of care",
    items: [[ScanLine, "Find a patient", "Scan their card or enter their ID"], [History, "Review their history", "Consultations from their care team"], [ClipboardList, "Record the next visit", "Add findings, reports, and prescriptions"]],
  },
  pharmacist: {
    label: "Pharmacists", icon: Pill,
    eyebrow: "Keep the next step in care connected.",
    title: "Clear prescriptions. Connected dispensing.",
    description: "Bring prescribed medicines and dispensing records into the same care journey, in a dedicated pharmacy workspace.",
    points: ["Find a patient’s prescriptions with their card or ID", "Check prescription details and relevant allergies", "Record medicines dispensed and review dispensing history"],
    action: "Create a pharmacist account", note: "Email verification and administrator approval are required.",
    previewTitle: "From prescription to pharmacy", previewNote: "The details you need for the next step",
    items: [[FileText, "Find prescriptions", "See medicines prescribed by the doctor"], [Pill, "Record dispensing", "Keep medicine handovers on record"], [ShieldCheck, "Focused access", "Prescription access for approved pharmacies"]],
  },
} as const;

const questions = [
  ["What is MedyLink?", "MedyLink brings your health card, medical records, reports, prescriptions, and dispensing history into one connected account. Patients, approved doctors, and approved pharmacies each have their own workspace."],
  ["Who can access my medical records?", "Approved doctors can find your record using your patient ID or health-card QR code and review your history. Approved pharmacies can access prescriptions and relevant allergies, but not your full clinical history or medical reports. Access and changes are recorded. Read Privacy & care for more details."],
  ["How does my health card work?", "Your digital card carries your unique patient ID and a QR code. A signed-in, approved care provider can use either to find your information. The card is a MedyLink identity, not a government-issued health ID, and the public card link does not display your medical details."],
  ["Can I view and download my reports?", "Yes. Your patient workspace keeps uploaded reports with your history and provides options to view or download them. Any copies you download or share outside MedyLink remain outside the app’s access controls."],
  ["Can a doctor or pharmacist start using an account immediately?", "Professional accounts first verify their email and submit their registration details and supporting documents. An administrator reviews the application before patient access is enabled."],
  ["Does MedyLink replace medical advice?", "No. Health summaries and any available predictions support understanding and clinical decisions; they are not a diagnosis. Discuss symptoms, test results, and treatment decisions with a qualified healthcare professional."],
];

/** Illustrative product artwork only; no patient data or clinical estimates. */
function CarePreview() {
  return <figure className={styles.preview} aria-label="Illustration of a MedyLink health card and connected care records">
    <div className={styles.previewOrbit} aria-hidden="true" />
    <div className={styles.previewOrbitInner} aria-hidden="true" />
    <span className={styles.artPlus} aria-hidden="true"><Plus size={24} strokeWidth={1.1} /></span>
    <span className={styles.artDot} aria-hidden="true" />
    <div className={styles.recordStack} aria-hidden="true">
      <div className={styles.previewTop}><span className={styles.smallIcon}><HeartPulse size={17} /></span><strong>Your care journey</strong><span className={styles.previewLabel}>ALL TOGETHER</span></div>
      <div className={styles.miniVisit}><span className={styles.visitIcon}><Stethoscope size={20}/></span><div><strong>Doctor consultation</strong><span>Every visit, part of your story</span></div><Check size={16}/></div>
      <div className={styles.miniVisit}><span className={styles.visitIcon}><FileText size={20}/></span><div><strong>Reports & prescriptions</strong><span>Right where you need them</span></div><Check size={16}/></div>
      <div className={styles.previewChart}><span>Your health, over time</span><svg viewBox="0 0 340 70" fill="none"><path d="M0 58H340M0 29H340" stroke="#dce6df" strokeDasharray="4 5"/><path className={styles.chartLine} d="M2 48C28 48 29 24 58 31S94 57 125 35S161 32 185 26S210 38 240 22S288 30 338 8" stroke="#36846b" strokeWidth="2.5" strokeLinecap="round"/></svg></div>
    </div>
    <div className={styles.demoCard} aria-hidden="true">
      <div className={styles.demoCardTop}><span><HeartPulse size={19}/> MedyLink</span><span>HEALTH CARD</span></div>
      <div className={styles.demoCardMain}><span className={styles.cardAvatar}><UserRound size={25} strokeWidth={1.4}/></span><div><span>YOUR HEALTH. YOUR IDENTITY.</span><strong>Your name here</strong></div></div>
      <div className={styles.demoCardBottom}><div><span>PATIENT ID</span><strong>ML-DEMO</strong></div><span className={styles.demoQr}><QrCode size={39} strokeWidth={1.3}/></span></div>
      <span className={styles.cardCurve}/>
    </div>
    <div className={styles.verifiedFloat} aria-hidden="true"><span><BadgeCheck size={21}/></span><div><strong>Connected to your care</strong><small>Patients · Doctors · Pharmacies</small></div></div>
    <figcaption>PRODUCT PREVIEW <span>·</span> Illustrative information only</figcaption>
  </figure>;
}

export function Landing() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [role, setRole] = useState<keyof typeof roles>("patient");
  const root = useRef<HTMLDivElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const selected = roles[role];

  useEffect(() => {
    // The session check mounts this page after the browser's initial fragment scroll.
    const id = window.location.hash.slice(1);
    if (!["top", "main-content", ...navigation.map(([section]) => section)].includes(id)) return;
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: "instant", block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (motion.matches || !("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) {
        entry.target.setAttribute("data-entered", "true");
        observer.unobserve(entry.target);
      }
    }, { threshold: 0.12 });
    root.current?.querySelectorAll("[data-reveal]").forEach(element => observer.observe(element));
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setMenuOpen(false); menuButton.current?.focus(); }
    };
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Element && !event.target.closest("[data-landing-header]")) setMenuOpen(false);
    };
    document.addEventListener("keydown", dismiss);
    document.addEventListener("pointerdown", outside);
    return () => { document.removeEventListener("keydown", dismiss); document.removeEventListener("pointerdown", outside); };
  }, [menuOpen]);

  function scrollToSection(event: MouseEvent<HTMLAnchorElement>) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const hash = event.currentTarget.hash;
    const target = document.getElementById(hash.slice(1));
    if (!target) return;
    event.preventDefault();
    setMenuOpen(false);
    window.history.pushState(null, "", hash);
    target.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
    target.focus({ preventScroll: true });
  }

  return <div className={styles.landing} ref={root}>
    <a className={styles.skipLink} href="#main-content">Skip to content</a>
    <header className={styles.header} data-landing-header>
      <div className={styles.headerInner}>
        <Link href="/" className={styles.brand} aria-label="MedyLink home"><Logo/></Link>
        <button className={styles.menuToggle} ref={menuButton} aria-label="Toggle navigation" aria-expanded={menuOpen} aria-controls="landing-navigation" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={22}/> : <Menu size={22}/>}</button>
        <nav id="landing-navigation" aria-label="Main navigation" className={`${styles.navigation} ${menuOpen ? styles.navigationOpen : ""}`} onBlur={event => { if (!event.currentTarget.parentElement?.contains(event.relatedTarget)) setMenuOpen(false); }}>
          <div className={styles.navLinks}>{navigation.map(([id, label]) => <a href={`#${id}`} key={id} onClick={scrollToSection}>{label}</a>)}</div>
          <div className={styles.navActions}><Link href="/login" className={styles.signIn}>Sign in <ArrowUpRight size={14}/></Link><Link href="/register" className={`${styles.button} ${styles.primary} ${styles.headerCta}`}>Get started <ArrowRight size={15}/></Link></div>
        </nav>
      </div>
    </header>

    <main id="main-content" tabIndex={-1}>
      <section id="top" className={`${styles.container} ${styles.hero}`} tabIndex={-1} aria-labelledby="hero-title">
        <div className={styles.heroCopy}>
          <div className={styles.eyebrow}><span className={styles.statusDot}/> A HEALTHIER WAY TO STAY CONNECTED</div>
          <h1 id="hero-title">Your health story.<br/><em>All together.</em></h1>
          <p>Your records, your doctors, your next step.<br className={styles.desktopBreak}/> One connected space for the care that matters to you.</p>
          <div className={styles.heroActions}><Link href="/register" className={`${styles.button} ${styles.primary}`}>Start your health journey <ArrowUpRight size={18}/></Link><a href="#how-it-works" className={styles.textLink} onClick={scrollToSection}>See how it works <span><ArrowDown size={16}/></span></a></div>
          <div className={styles.heroFootnote}><ShieldCheck size={17}/><span>Your own health ID. Reviewed care providers. Connected records.</span></div>
        </div>
        <CarePreview/>
      </section>

      <div className={styles.connectionStrip}>
        <div className={styles.container}><span>ONE CONNECTED CARE JOURNEY</span><div><IdCard size={19}/>Your health identity</div><Plus size={15} className={styles.stripPlus}/><div><Stethoscope size={19}/>Your care team</div><Plus size={15} className={styles.stripPlus}/><div><FileHeart size={19}/>Your medical history</div></div>
      </div>

      <section id="features" tabIndex={-1} className={`${styles.container} ${styles.section}`} aria-labelledby="features-title">
        <div className={styles.sectionHeading} data-reveal><div><span className={styles.eyebrow}>LESS SEARCHING. MORE CLARITY.</span><h2 id="features-title">A place for every part<br/>of <em>your health.</em></h2></div><p>Care happens across visits, doctors, and pharmacies. MedyLink helps keep the pieces together.</p></div>
        <div className={styles.featureGrid}>
          <article className={`${styles.featureCard} ${styles.historyFeature}`} data-reveal>
            <span className={styles.featureIcon}><History size={22}/></span><h3>Your story, without the gaps.</h3><p>Consultations, diagnoses, prescriptions, and reports in one timeline, with the doctor behind each visit.</p>
            <div className={styles.featureTimeline} aria-hidden="true"><div><span/><div><small>THE FIRST STEP</small><strong>A consultation with your doctor</strong></div><Stethoscope size={18}/></div><div><span/><div><small>THE FULLER PICTURE</small><strong>Reports, added to your history</strong></div><FileText size={18}/></div><div><span/><div><small>WHAT COMES NEXT</small><strong>A prescription to guide your care</strong></div><Pill size={18}/></div></div>
            <span className={styles.cardTag}>EVERY VISIT HAS ITS PLACE</span>
          </article>
          <article className={`${styles.featureCard} ${styles.identityFeature}`} data-reveal><span className={styles.featureIcon}><ScanLine size={22}/></span><h3>One card. Your connection.</h3><p>A unique patient ID and QR code help approved providers find your history.</p><div className={styles.identityArt} aria-hidden="true"><span><QrCode size={42} strokeWidth={1.3}/></span><div><small>YOUR MEDYLINK ID</small><strong>Made for your journey.</strong></div><ArrowUpRight size={22}/></div></article>
          <article className={styles.featureCard} data-reveal><span className={styles.featureIcon}><FileHeart size={22}/></span><h3>Your reports, within reach.</h3><p>Keep uploaded medical reports together. Open or download them when you need a closer look.</p><span className={styles.miniTag}><FileText size={14}/> Organised. Accessible. In one place.</span></article>
          <article className={styles.featureCard} data-reveal><span className={styles.featureIcon}><Pill size={22}/></span><h3>A clearer path for medicines.</h3><p>See prescribed medicines and instructions, alongside a history of pharmacy dispensing.</p></article>
          <article className={`${styles.featureCard} ${styles.trendsFeature}`} data-reveal><span className={styles.featureIcon}><Activity size={22}/></span><h3>See how your health changes.</h3><p>Follow recorded blood pressure and blood sugar over time. Your overview reflects the information available in your account.</p><div className={styles.trendDecoration} aria-hidden="true"><span/><span/><span/><span/><span/><span/><span/><span/><span/></div><span className={styles.trendLabel}>YOUR RECORDS → A CLEARER PICTURE</span></article>
        </div>
      </section>

      <section id="how-it-works" tabIndex={-1} className={styles.stepsSection} aria-labelledby="steps-title">
        <div className={styles.container}>
          <div className={styles.centerHeading} data-reveal><span className={styles.eyebrow}>A SIMPLE START</span><h2 id="steps-title">Connected care starts<br/>with <em>you.</em></h2><p>A few steps to bring your health story together.</p></div>
          <div className={styles.steps}>
            {[{ number: "01", icon: UserRound, title: "Make it yours", text: "Choose your account type, add your details, and verify your email." }, { number: "02", icon: IdCard, title: "Connect your care", text: "Use your patient health card or ID with approved doctors and pharmacies." }, { number: "03", icon: HeartPulse, title: "Keep the story going", text: "Return to your workspace for records, reports, prescriptions, and the next visit." }].map(({number, icon: Icon, title, text}) => <article className={styles.step} key={number} data-reveal><div className={styles.stepTop}><span className={styles.stepNumber}>{number}</span><Icon size={26} strokeWidth={1.3}/></div><h3>{title}</h3><p>{text}</p></article>)}
          </div>
          <p className={styles.stepsNote}><BadgeCheck size={16}/> Doctors and pharmacists complete an administrator review before accessing patient information.</p>
        </div>
      </section>

      <section id="for-everyone" tabIndex={-1} className={`${styles.container} ${styles.section}`} aria-labelledby="roles-title">
        <div className={styles.centerHeading} data-reveal><span className={styles.eyebrow}>DIFFERENT ROLES. SHARED CARE.</span><h2 id="roles-title">Built for everyone<br/>in <em>your care circle.</em></h2></div>
        <div className={styles.roleSelector} role="group" aria-label="Choose your role">{(Object.keys(roles) as (keyof typeof roles)[]).map(key => { const Icon = roles[key].icon; return <button key={key} type="button" aria-pressed={role === key} aria-controls="role-details" onClick={() => setRole(key)}><Icon size={18}/>{roles[key].label}</button>; })}</div>
        <div id="role-details" className={styles.rolePanel}>
          <div className={styles.roleCopy} key={role}><span className={styles.eyebrow}>{selected.eyebrow}</span><h3>{selected.title}</h3><p>{selected.description}</p><ul>{selected.points.map(point => <li key={point}><Check size={17}/>{point}</li>)}</ul><Link href={`/register/${role}`} className={`${styles.button} ${styles.primary}`}>{selected.action}<ArrowRight size={17}/></Link><small>{selected.note}</small></div>
          <div className={styles.roleVisual}><div className={styles.rolePreview}><div className={styles.rolePreviewHeader}><span><HeartPulse size={19}/></span><span>YOUR MEDYLINK WORKSPACE</span><span className={styles.statusDot}/></div><h4>{selected.previewTitle}</h4><p>{selected.previewNote}</p><div className={styles.rolePreviewItems}>{selected.items.map(([Icon,title,description]) => <div key={title}><span><Icon size={21}/></span><div><strong>{title}</strong><small>{description}</small></div><Check size={15}/></div>)}</div><div className={styles.rolePreviewFoot}><LockKeyhole size={13}/> Your own dedicated workspace</div></div><span className={styles.roleVisualCaption}>A LITTLE MORE CONNECTED, AT EVERY STEP.</span></div>
        </div>
      </section>

      <section className={`${styles.container} ${styles.trustSection}`} aria-labelledby="trust-title" data-reveal>
        <div className={styles.trustIntro}><span className={styles.trustSymbol}><ShieldCheck size={38} strokeWidth={1.3}/></span><span className={styles.eyebrow}>THOUGHTFUL BY DESIGN</span><h2 id="trust-title">Care is personal.<br/><em>So are your records.</em></h2><p>Clear roles and recorded access help keep your care connected and accountable.</p><Link href="/privacy" className={styles.textLink}>Read our privacy & care notice <ArrowUpRight size={17}/></Link></div>
        <div className={styles.trustItems}>{[{icon: BadgeCheck,title:"Reviewed care providers",text:"Doctor and pharmacy applications are reviewed before patient access is enabled."},{icon: UsersRound,title:"Access that fits the role",text:"Doctors can review medical history. Pharmacies see prescriptions and relevant allergies."},{icon: History,title:"A history that stays a history",text:"Access and changes are logged. Earlier medical records retain their authorship."}].map(({icon:Icon,title,text})=><div key={title}><span><Icon size={22}/></span><div><h3>{title}</h3><p>{text}</p></div></div>)}</div>
      </section>

      <section id="questions" tabIndex={-1} className={`${styles.container} ${styles.section} ${styles.faqSection}`} aria-labelledby="faq-title">
        <div data-reveal><span className={styles.eyebrow}>A LITTLE MORE CLARITY</span><h2 id="faq-title">Good questions.<br/><em>Clear answers.</em></h2><p>A few things to know before<br className={styles.desktopBreak}/> you begin your journey.</p><span className={styles.faqMark} aria-hidden="true">?</span></div>
        <div className={styles.faqList}>{questions.map(([question,answer])=><details key={question}><summary>{question}<ChevronDown size={18}/></summary><p>{answer}{question === "Who can access my medical records?" && <> <Link href="/privacy">Read the privacy notice <ArrowUpRight size={13}/></Link></>}</p></details>)}</div>
      </section>

      <section className={styles.ctaSection} aria-labelledby="cta-title">
        <div className={`${styles.container} ${styles.ctaInner}`} data-reveal><span className={styles.ctaIcon}><HeartPulse size={30} strokeWidth={1.4}/></span><span className={styles.eyebrow}>YOUR NEXT CHAPTER STARTS HERE</span><h2 id="cta-title">A little more connected.<br/>A little more <em>at ease.</em></h2><p>Make space for your health story with MedyLink.</p><Link href="/register" className={`${styles.button} ${styles.lightButton}`}>Create your account <ArrowUpRight size={18}/></Link><span className={styles.ctaSignIn}>Already part of MedyLink? <Link href="/login">Sign in <ArrowRight size={13}/></Link></span></div>
      </section>
    </main>

    <footer className={styles.footer}>
      <div className={`${styles.container} ${styles.footerMain}`}><div><Link href="/" className={styles.brand} aria-label="MedyLink home"><Logo/></Link><p>One health identity.<br/>A more connected care journey.</p></div><nav aria-label="Explore MedyLink"><strong>EXPLORE</strong><a href="#features" onClick={scrollToSection}>Why MedyLink</a><a href="#how-it-works" onClick={scrollToSection}>How it works</a><a href="#questions" onClick={scrollToSection}>FAQs</a></nav><nav aria-label="Join MedyLink"><strong>YOUR WORKSPACE</strong><Link href="/register/patient">For patients</Link><Link href="/register/doctor">For doctors</Link><Link href="/register/pharmacist">For pharmacists</Link></nav><nav aria-label="Account and privacy"><strong>GOOD TO KNOW</strong><Link href="/privacy">Privacy & care</Link><Link href="/login">Sign in</Link><a href="#top" onClick={scrollToSection}>Back to top <ArrowUpRight size={13}/></a></nav></div>
      <div className={`${styles.container} ${styles.footerBottom}`}><span>© {new Date().getFullYear()} MedyLink. Health, connected.</span><span>Supports your care. Does not replace medical advice.</span></div>
    </footer>
  </div>;
}
