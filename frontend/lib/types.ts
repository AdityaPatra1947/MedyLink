export type Role = "patient" | "doctor" | "pharmacist" | "admin";
export interface User { id: string; account_id: string; name: string; email: string; role: Role; email_verified: boolean; phone?: string }
export interface Profile { id: string; account_id: string; name: string; health_id: string; date_of_birth: string; gender: "" | "female" | "male" | "other" | "prefer_not_to_say"; phone: string; address: string; blood_group: string; emergency_contact: string; allergy_status: string; photo_url?: string | null }
export interface Entry { id: string; name: string; notes: string; source: string; author_id: string; author_name: string; created_at: string; resolved_at?: string }
export interface ClinicalRecord { id: string; patient_id: string; doctor_id: string; doctor_account_id?: string; doctor_name: string; complaint: string; diagnosis: string; notes: string; vitals: Record<string, string>; created_at: string; correction_of?: string; correction_reason?: string }
export interface Medicine { id: string; medicine: string; dosage: string; instructions: string; quantity: string; unit: string; dispensed: string; remaining: string }
export interface Prescription { id: string; doctor_id: string; record_id?: string | null; patient: Profile; doctor_name: string; doctor_registration: string; created_at: string; valid_until: string; status: string; notes: string; items: Medicine[]; allergies: Entry[]; allergy_status: string; cancellation_reason?: string }
export interface ProviderDocument { id: string; name: string; status: string; kind: "credential" | "photo" }
export interface ProviderReview { decision: string; reason: string; evidence_reviewed: string; valid_until: string | null; reviewer_name: string; created_at: string }
export interface Application {
  id: string; provider_id: string; name: string; role: Role; provider_email: string; email?: string; email_verified: boolean;
  version: number; status: string; reason: string; valid_until: string | null; is_current: boolean;
  registration_number: string; registering_body: string; specialty: string; qualification: string; clinic_name: string;
  years_experience: number | null; opening_hours: string; practice_address: string; shop_name: string; shop_license: string;
  shop_license_expires: string | null; contact_phone: string; documents: ProviderDocument[]; created_at: string;
  reviewed_at?: string | null; evidence_reviewed?: string; reviews: ProviderReview[]; history?: Application[];
}
export interface Dispensing { id: string; prescription_id: string; pharmacist_name: string; shop_name: string; patient_name: string; patient_health_id: string; created_at: string; items: {medicine: string; quantity: string; unit: string}[] }
export interface Audit { id: string; event: string; outcome: string; actor_name: string; created_at: string; request_id: string }
export interface Session { id: string; created_at: string; last_used_at: string; expires_at: string; user_agent: string; current: boolean }
export interface HealthCardData { patient_id: string; account_id: string; health_id: string; name: string; locator: string; qr_data_url: string; date_of_birth: string; blood_group: string; photo_url: string | null }
export interface MedicalReport { id: string; patient_id: string; record_id: string | null; name: string; title: string; content_type: string; size_bytes: number; uploaded_by: { id: string; name: string; role: Role }; created_at: string; download_url: string; view_url?: string; extraction?: { status: "extracted" | "unsupported"; format?: string; measured_at?: string; blood_pressure?: { systolic: number; diastolic: number; unit: string }; blood_sugar?: { value: number; unit: string; context?: string } } }
export interface PatientVisit { id: string; created_at: string; doctor: { id: string; name: string; qualification: string; specialty: string; clinic_name: string }; record: ClinicalRecord; prescriptions: Prescription[]; reports: MedicalReport[] }
export interface ResultPage<T> { results: T[]; next?: number | null }
