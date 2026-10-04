# Dashboard navigation

All four roles use one continuous page. The sidebar jumps to a section and highlights the section currently being viewed. On small screens, the navigation remains at the top and brings the active item into view. Section links support keyboard navigation, browser Back/Forward, and direct URLs with a section hash.

## Section order

- Patient: Overview, Health card, Medical records, Recent visits, Medical reports, Prescriptions, Dispensing history, My profile, Security settings.
- Doctor: My patients, Find patient, My profile, My verification, Security settings.
- Pharmacist: Find prescriptions, Dispensing history, Shop & verification, Security settings. ID lookup and QR scanning share the Find prescriptions section.
- Administrator: Doctor approvals, Pharmacist approvals, Security audit, Security settings.

The sidebar is the primary section navigation. Repeated header shortcuts and duplicate section headings are removed. Context-specific actions still open their details, submit forms, upload files, or download documents. Sections stay mounted while scrolling so unsaved form entries and selected records remain in place. Clinical sub-tabs remain inside an opened doctor patient record.

Examples: `/#patient-card`, `/#doctor-request`, `/#pharmacist-dispensing`, and `/admin/doctors#admin-pharmacists`. Existing `/admin/doctors`, `/admin/pharmacists`, `/admin/audit`, and `/admin/security` URLs still open their corresponding sections. A health-card QR deep link opens the appropriate provider lookup section after sign-in.

Patient health-card metadata follows saved profile updates. Photo editing is located in My profile; the health-card section retains card flipping, QR, PDF download, and lost-card replacement. Normal role and approval requirements still apply to every API request.
