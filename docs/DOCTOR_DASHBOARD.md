# Doctor dashboard

## Find and review a patient

Open **Find patient** and enter the compact patient ID printed on the health card. Existing health IDs remain accepted. Alternatively use **Scan QR with camera**. A successfully decoded health-card QR opens the patient record automatically. Camera access needs browser and operating-system permission, using HTTPS or localhost. ID entry remains available if a camera is unavailable.

The patient workspace contains the clinical timeline, prescriptions, medical reports, allergies and conditions. Approved doctors can read entries from other doctors and download uploaded reports. Each entry retains its author and date.

Finalized consultations and report files cannot be overwritten or deleted. A doctor can add a new consultation, prescription or report. Corrections to the doctor's own consultations create a separate linked entry with a reason; the original remains unchanged. Another doctor's consultation cannot be corrected by the viewing doctor.

## My patients

Choose **Add patient** in the patient record to save that patient to **My patients**. Opening or scanning a record does not automatically add it. Saving again does not create a duplicate. The list belongs to the signed-in doctor and persists across sessions. Existing patients from that doctor's earlier consultations and prescriptions are carried forward when the database is updated.

Saved patients still require current professional approval to access. The saved list does not change clinical permissions.

## My profile and Security settings

**My profile** allows the doctor to update their name and personal contact phone. Email and account ID are fixed. Professional qualifications, registration details and clinic information are displayed from the current application; changes are submitted through **My verification** for review.

**Security settings** provides the same account information, password reset email, active sessions and sign-out controls as the patient account. Authenticator enrollment remains removed. Profile and security settings remain available while a doctor's professional application is pending.

## Verification

The isolated doctor workflow is `scripts/doctor-workflow.mjs`. Run it after `scripts/browser-workflow.mjs` on the same newly seeded test fixture. It uses two synthetic doctors to verify prior-record visibility, author restrictions and saved-list isolation. QR decoding is exercised with a synthetic camera stream that varies the card distance, as it would during camera alignment. Test artifacts are kept in `.local/doctor-workflow/`.

## Camera troubleshooting

The doctor and pharmacist share the same scanner. It starts only after clicking **Scan QR with camera**, stops on close, after a successful scan, or when leaving the lookup section, and adapts its scan frame to the available preview size.

If starting fails, the scanner distinguishes browser permission denial, system permission denial, a missing camera, and a camera that is busy/unavailable. **Camera details** shows the browser's error; **Retry camera** starts a fresh attempt after correcting the issue.

For Windows **Permission denied by system**, open Settings > Privacy & security > Camera (Privacy > Camera on Windows 10). Enable camera access for apps and desktop apps, and allow the browser/desktop app if listed. A site's Allow setting alone does not override Windows privacy settings. See [Microsoft's camera permission guide](https://support.microsoft.com/en-us/windows/privacy/manage-app-permissions-for-a-camera-in-windows). If an embedded browser still fails, open the app in Chrome or Edge. Close another camera app if the device is busy.

Scanner regressions: `cd frontend` then `npm run test:e2e -- tests/health-card-scanner.spec.ts --workers=2`. These tests use synthetic camera streams and intercepted API requests, so they neither access physical cameras nor alter patient records.
