export interface VitalReading { record_id: string; recorded_at: string; author: string; source: string; unit: string; systolic?: number; diastolic?: number; value?: number; context?: string | null; report_id?: string; report_title?: string; view_url?: string }
export interface HealthScoreComponent { key: string; label: string; value: number; score: number; weight: number; formula?: string; explanation?: string; unit?: string; source_report_id?: string | null; source_report_title?: string | null; measured_at?: string | null }
export interface HealthScore { value: number; label: string; method: string; calculated_at: string; components: HealthScoreComponent[]; formula?: string; explanation?: string; disclaimer?: string }
export interface AdherenceSummary { percentage: number; scheduled_doses: number; taken_doses: number; days_logged: number; period_days: number; formula?: string; explanation?: string; source?: string; period_start?: string; period_end?: string; missing_days?: number; report_ids?: string[] }
export interface PatientDashboardData {
  counts: { records: number; active_prescriptions: number; conditions: number; reports: number; report_downloads: number };
  latest: { blood_pressure: VitalReading | null; blood_sugar: VitalReading | null };
  trends: { blood_pressure: VitalReading[]; blood_sugar: VitalReading[] };
  health_score: HealthScore | null;
  health_score_reason?: string;
  adherence: AdherenceSummary | null;
  lab_summary: { abnormal: number | null; total: number | null };
  regional_alerts: { available: boolean; items: { id: string; title: string; description: string; region: string; source_url: string; published_at: string }[] };
  recent_notifications: { id: string; kind: string; title: string; created_at: string; target_tab: string }[];
}
