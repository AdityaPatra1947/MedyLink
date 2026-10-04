"use client";

import { useEffect, useId, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";
import type { Html5Qrcode } from "html5-qrcode";
import { Feedback } from "./ui";
import styles from "./doctor-workspace.module.css";

// A newly opened scanner must wait for the previous camera to finish releasing,
// including a permission request that resolves after its component was closed.
let pendingCameraCleanup: Promise<void> = Promise.resolve();

function cameraError(cause: unknown) {
  const detail = cause instanceof Error ? `${cause.name}: ${cause.message}` : String(cause);
  if (/permission denied by system/i.test(detail)) return {
    message: "Camera access was denied by your operating system. In Windows camera privacy settings, enable camera access for apps and desktop apps, including your browser. If using an in-app browser, try opening this site in Chrome or Edge. Then retry.", detail,
  };
  if (/NotAllowedError|PermissionDeniedError|permission denied/i.test(detail)) return {
    message: "Camera permission was denied. Allow this site to use your camera in the browser’s site settings, then retry. If permission is already allowed, check your system camera privacy settings.", detail,
  };
  if (/NotFoundError|DevicesNotFoundError/i.test(detail)) return {
    message: "No camera was found. Connect or enable a camera, then retry. You can also enter the patient ID.", detail,
  };
  if (/NotReadableError|TrackStartError|AbortError/i.test(detail)) return {
    message: "The camera is unavailable or in use by another app. Close other camera apps or tabs, check the camera’s privacy switch, then retry.", detail,
  };
  if (/OverconstrainedError|ConstraintNotSatisfiedError/i.test(detail)) return {
    message: "This camera could not use the requested settings. Check that your camera is enabled, then retry or enter the patient ID.", detail,
  };
  return { message: "Camera could not be started. Try again, open this site in Chrome or Edge, or enter the patient ID.", detail };
}

export function HealthCardScanner({ onScan, onClose }: { onScan: (text: string) => void; onClose: () => void }) {
  const id = `health-card-scanner-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const callback = useRef(onScan);
  const [error, setError] = useState<{ message: string; detail: string } | null>(null);
  const [busy, setBusy] = useState(true);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => { callback.current = onScan; }, [onScan]);
  useEffect(() => {
    let cancelled = false;
    let completed = false;
    let instance: Html5Qrcode | null = null;
    let releasePromise: Promise<void> | undefined;
    let restoreVideoHandling = () => {};
    // Retain the element even after unmount so any acquired stream can be stopped.
    const reader = document.getElementById(id);
    function release() {
      if (releasePromise) return releasePromise;
      releasePromise = (async () => {
        if (!instance) { restoreVideoHandling(); return; }
        try {
          // start() can resolve before isScanning becomes true (video playing).
          const state = instance.getState();
          if (state === 2 || state === 3) await instance.stop(); // SCANNING or PAUSED
        } catch { /* Stop any remaining tracks below if library cleanup failed. */ }
        reader?.querySelectorAll("video").forEach(video => {
          if (video.srcObject instanceof MediaStream) video.srcObject.getTracks().forEach(track => track.stop());
          video.srcObject = null;
        });
        try { instance.clear(); } catch { /* The reader may have unmounted. */ }
        restoreVideoHandling();
      })();
      return releasePromise;
    }
    const ready = pendingCameraCleanup.then(async () => {
      if (cancelled) return;
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
        setBusy(false);
        setError({ message: "Camera scanning requires HTTPS or localhost and a browser with camera support. Open this site in Chrome or Edge, or enter the patient ID.", detail: "Secure camera access is unavailable in this browser." });
        return;
      }
      const { Html5Qrcode, Html5QrcodeSupportedFormats } = await import("html5-qrcode");
      if (cancelled) return;
      if (reader) {
        // html5-qrcode ignores play()'s promise. Handle it on this reader's own
        // video before the library starts playback, including late cancellation.
        // This leaves other videos and global browser APIs untouched.
        const append = reader.append;
        reader.append = (...nodes) => {
          for (const node of nodes) if (node instanceof HTMLVideoElement) {
            const play = node.play.bind(node);
            node.play = () => {
              if (cancelled) return Promise.resolve();
              const playback = play();
              void playback.catch((cause: unknown) => {
                if (!cancelled && !completed && !releasePromise) {
                  setBusy(false);
                  setError(cameraError(cause));
                  void ready.then(release);
                }
              });
              return playback;
            };
          }
          append.apply(reader, nodes);
        };
        restoreVideoHandling = () => { reader.append = append; };
      }
      instance = new Html5Qrcode(id, { formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE], verbose: false });
      await instance.start({ facingMode: "environment" }, { fps: 10, qrbox: (width, height) => {
        const size = Math.min(220, Math.floor(Math.min(width, height) * .8));
        return { width: size, height: size };
      } }, text => {
        if (cancelled || completed) return;
        completed = true;
        void ready.then(release).then(() => { if (!cancelled) callback.current(text); });
      }, () => {});
      if (cancelled) await release();
      else setBusy(false);
    }).catch(async (cause: unknown) => {
      await release();
      if (!cancelled) {
        setBusy(false);
        setError(cameraError(cause));
      }
    });
    return () => { cancelled = true; pendingCameraCleanup = ready.then(release); };
  }, [id, attempt]);
  return <div className={styles.scannerBox}>
    <p className="progress-note">Position the patient’s QR code inside the frame. Their record opens when the code is read.</p>
    <div className={`scanner ${styles.reader}`} id={id}/>
    {busy && <p className={styles.status} role="status"><LoaderCircle size={16} className="spin"/>Starting camera…</p>}
    <Feedback error={error?.message}/>
    {error && <details className={styles.cameraDetails}><summary>Camera details</summary><p>{error.detail}</p></details>}
    <div className="inline-actions">
      {error && <button className="button secondary small" type="button" onClick={() => { setError(null); setBusy(true); setAttempt(value => value + 1); }}>Retry camera</button>}
      <button className="button quiet small" type="button" onClick={onClose}>Close scanner</button>
    </div>
  </div>;
}
