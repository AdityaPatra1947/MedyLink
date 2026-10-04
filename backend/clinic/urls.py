from django.urls import path

from . import views as v
from .health_tracking_views import AdherenceView, LabsView
from .dashboard_views import PatientDashboardView

urlpatterns = [
    path("patients/me/adherence/", AdherenceView.as_view()),
    path("patients/me/labs/", LabsView.as_view()),
    path("patients/<uuid:patient_id>/labs/", LabsView.as_view()),
    path("patients/me/", v.ProfileView.as_view()),
    path("patients/me/dashboard/", PatientDashboardView.as_view()),
    path("patients/me/card/", v.CardView.as_view()),
    path("patients/me/card.pdf/", v.CardView.as_view(), {"pdf": True}),
    path("patients/me/card/replace/", v.ReplaceCardView.as_view()),
    path("provider/patients/lookup/", v.PatientLookupView.as_view()),
    path("patients/me/photo/", v.PatientPhotoView.as_view()),
    path("patients/<uuid:patient_id>/photo/", v.PatientPhotoView.as_view()),
    path("patients/me/reports/", v.ReportsView.as_view()),
    path("patients/<uuid:patient_id>/reports/", v.ReportsView.as_view()),
    path("patients/me/visits/", v.VisitsView.as_view()),
    path("reports/<uuid:pk>/download/", v.ReportDownloadView.as_view()),
    path("reports/<uuid:pk>/view/", v.ReportDownloadView.as_view(), {"inline": True}),
    path("patients/me/records/", v.RecordsView.as_view()),
    path("patients/me/prescriptions/", v.PrescriptionsView.as_view()),
    path("patients/me/dispensing/", v.DispensingHistoryView.as_view()),
    path("patients/me/access-history/", v.AuditView.as_view()),
    path("provider/application/", v.ApplicationView.as_view()),
    path("provider/application/documents/", v.UploadDocumentView.as_view()),
    path("provider-documents/<uuid:pk>/download/", v.DocumentDownloadView.as_view()),
    path(
        "admin/provider-documents/<uuid:pk>/validate/", v.ValidateDocumentView.as_view()
    ),
    path("admin/provider-applications/", v.AdminApplicationsView.as_view()),
    path("admin/provider-applications/<uuid:pk>/", v.AdminApplicationsView.as_view()),
    path(
        "admin/provider-applications/<uuid:pk>/approve/",
        v.ReviewApplicationView.as_view(),
        {"decision": "approve"},
    ),
    path(
        "admin/provider-applications/<uuid:pk>/reject/",
        v.ReviewApplicationView.as_view(),
        {"decision": "reject"},
    ),
    path("admin/providers/<uuid:pk>/suspend/", v.SuspendProviderView.as_view()),
    path("admin/audit/", v.AuditView.as_view(), {"admin": True}),
    path("doctor/patients/", v.DoctorPatientsView.as_view()),
    path("doctor/patients/<uuid:patient_id>/", v.AddDoctorPatientView.as_view()),
    path("doctor/profile/", v.DoctorProfileView.as_view()),
    path(
        "patients/<uuid:patient_id>/clinical-summary/", v.ClinicalSummaryView.as_view()
    ),
    path("patients/<uuid:patient_id>/records/", v.RecordsView.as_view()),
    path("records/<uuid:pk>/corrections/", v.CorrectionView.as_view()),
    path(
        "patients/<uuid:patient_id>/allergies/",
        v.EntriesView.as_view(),
        {"kind": "allergy"},
    ),
    path(
        "patients/<uuid:patient_id>/conditions/",
        v.EntriesView.as_view(),
        {"kind": "condition"},
    ),
    path(
        "patients/<uuid:patient_id>/allergies/<uuid:pk>/resolve/",
        v.ResolveEntryView.as_view(),
        {"kind": "allergy"},
    ),
    path(
        "patients/<uuid:patient_id>/conditions/<uuid:pk>/resolve/",
        v.ResolveEntryView.as_view(),
        {"kind": "condition"},
    ),
    path("patients/<uuid:patient_id>/prescriptions/", v.PrescriptionsView.as_view()),
    path("prescriptions/<uuid:pk>/", v.PrescriptionView.as_view()),
    path("prescriptions/<uuid:pk>/pdf/", v.PrescriptionView.as_view(), {"pdf": True}),
    path("prescriptions/<uuid:pk>/cancel/", v.CancelPrescriptionView.as_view()),
    path("prescriptions/<uuid:pk>/dispense/", v.DispenseView.as_view()),
    path("pharmacy/me/", v.ApplicationView.as_view()),
    path("pharmacy/shared-prescriptions/", v.SharedPrescriptionsView.as_view()),
    path("pharmacy/dispensing/", v.DispensingHistoryView.as_view()),
]
