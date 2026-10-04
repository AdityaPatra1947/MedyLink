"use client";

import { useState } from "react";
import { Camera, Download, HeartPulse, RefreshCw, UserRound } from "lucide-react";
import { api, date, post } from "@/lib/api";
import type { HealthCardData, Profile } from "@/lib/types";
import { AsyncForm, Empty, Field, QueryState, useQuery } from "./ui";
import styles from "./patient-card.module.css";

export function PhotoUpload({ onUploaded }: { onUploaded: () => void }) {
  return <AsyncForm submit="Upload photo" successText="Your photo has been updated." reset onSubmit={async form => {
    const body = new FormData(form);
    const file = body.get("file");
    if (!(file instanceof File) || !file.size) throw new Error("Choose a JPEG or PNG photo.");
    if (!/\.(jpe?g|png)$/i.test(file.name) || file.size > 2 * 1024 * 1024) throw new Error("Choose a JPEG or PNG photo up to 2 MB.");
    await api<Profile>("/patients/me/photo/", { method: "POST", body });
    onUploaded();
  }}>
    <Field label="Patient photo" name="file" type="file" accept=".jpg,.jpeg,.png" required hint="JPEG or PNG, up to 2 MB. This photo will appear on your health card."/>
  </AsyncForm>;
}

export function HealthCard({ profile, full = false, onProfileUpdated, showPhotoUpload = true }: { profile: Profile; full?: boolean; onProfileUpdated?: () => void; showPhotoUpload?: boolean }) {
  const query = useQuery<HealthCardData>(profile.date_of_birth ? "/patients/me/card/" : null);
  const [flipped, setFlipped] = useState(false);
  const [uploading, setUploading] = useState(false);
  const card = query.data;
  function reload() { query.reload(); onProfileUpdated?.(); }
  return <div className={styles.wrapper}>
    <QueryState query={query}>
      {profile.date_of_birth ? <>
        <button type="button" className={`${styles.card} ${flipped ? styles.flipped : ""}`} aria-label="Flip health card" aria-pressed={flipped} onClick={() => setFlipped(!flipped)}>
          <span className={styles.cardInner}>
            <span className={`${styles.face} ${styles.front}`} aria-hidden={flipped}>
              <span className={styles.brand}><span><HeartPulse size={20} strokeWidth={1.5}/>MedyLink</span><span>HEALTH CARD</span></span>
              <span className={styles.identity}>
                <span className={styles.portrait}>{profile.photo_url ? <img src={profile.photo_url} alt={`${profile.name}'s profile photo`}/> : <UserRound size={40} strokeWidth={1.1}/>}</span>
                <span className={styles.person}><span className={styles.smallLabel}>CARD HOLDER</span><span className={styles.name} title={profile.name}>{profile.name}</span><span className={styles.healthId} title="Account ID">{profile.account_id}</span></span>
              </span>
              <span className={styles.details}><span><span className={styles.smallLabel}>DATE OF BIRTH</span><strong>{date(profile.date_of_birth)}</strong></span><span><span className={styles.smallLabel}>BLOOD GROUP</span><strong>{profile.blood_group === "unknown" ? "Unknown" : profile.blood_group || "Unknown"}</strong></span><span className={styles.cardMark}><HeartPulse size={33} strokeWidth={.9}/></span></span>
              <span className={styles.cardFooter}><span>ONE IDENTITY. CONNECTED CARE.</span><span>Tap to flip <RefreshCw size={10}/></span></span>
            </span>
            <span className={`${styles.face} ${styles.back}`} aria-hidden={!flipped}>
              <span className={styles.brand}><span><HeartPulse size={20} strokeWidth={1.5}/>MedyLink</span><span>YOUR HEALTH IDENTITY</span></span>
              <span className={styles.backBody}><span className={styles.qrWrap}>{card?.qr_data_url ? <img src={card.qr_data_url} alt="Health card QR code"/> : <span>QR loading</span>}</span><span className={styles.backDetails}><span className={styles.smallLabel}>ACCOUNT ID</span><strong>{profile.account_id}</strong><span className={styles.smallLabel}>EMERGENCY CONTACT</span><span className={styles.emergencyContact} title={profile.emergency_contact || ""}>{profile.emergency_contact || "Not added yet"}</span></span></span>
              <span className={styles.backNote}>A local MedyLink identity. Not a government health ID.</span>
              <span className={styles.cardFooter}><span>Keep your health details up to date.</span><span>Tap for front <RefreshCw size={10}/></span></span>
            </span>
          </span>
        </button>
        <div className={styles.cardActions}><p>{flipped ? "Back of card" : "Front of card"} · Click or tap to flip</p><a className="text-button" href="/api/v1/patients/me/card.pdf/" target="_blank" rel="noreferrer"><Download size={13}/>Download card</a></div>
        {full && <>
          {showPhotoUpload && <><div className={styles.actionRow}><button className="button secondary small" type="button" onClick={() => setUploading(!uploading)}><Camera size={15}/>{uploading ? "Close photo upload" : profile.photo_url ? "Change photo" : "Add photo"}</button><p>Your photo is included on both your digital card and downloaded card.</p></div>
          {uploading && <div className={styles.upload}><PhotoUpload onUploaded={() => { setUploading(false); reload(); }}/></div>}</>}
          <details className={styles.replace}><summary>Replace a lost card</summary><p>Replacing your card changes its QR identifier. Your health ID and medical history stay the same.</p><AsyncForm submit="Replace my card" successText="Your card has been replaced." onSubmit={async () => { await post("/patients/me/card/replace/"); query.reload(); }}><label className="checkbox"><input required type="checkbox"/><span>I want to replace my current card and use the new QR code.</span></label></AsyncForm></details>
        </>}
      </> : <Empty title="Your card is nearly ready.">Add your date of birth in My profile to create your personal health card.</Empty>}
    </QueryState>
  </div>;
}
