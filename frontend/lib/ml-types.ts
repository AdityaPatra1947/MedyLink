import type { ClusterResult, StationAnchor } from "./analytics-types";

export interface MLFilters {
  dataset_id: string;
  disease_code: string;
  disease_codes?: string;
  disease_search?: string;
  line: string;
  station_id: string;
  date_from: string | null;
  date_to: string | null;
}

export interface MLCatalog {
  synthetic: boolean;
  suppression_threshold?: number;
  datasets: { dataset_id: string; as_of: string; observation_start: string }[];
  diseases: { disease_code: string; label: string }[];
  stations: StationAnchor[];
  lines: string[];
  defaults: MLFilters;
}

export interface MLMetrics {
  accuracy: number;
  macro_f1: number;
}

export interface MLPatientGroups {
  algorithm?: string;
  status: "completed" | "insufficient_data";
  eligible_patients?: number | null;
  reason?: string;
  disclaimer?: string;
  silhouette?: number | null;
  features?: { key: string; label: string }[];
  pca?: { explained_variance: number[]; meaning: string };
  groups: {
    group: number;
    label: string;
    patient_count: number | null;
    suppressed: boolean;
    profile: Record<string, { mean: number | null; observations: number | null }>;
    position: { x: number; y: number } | null;
    conditions: { code: string; patient_count: number | null }[];
    explanation: string;
  }[];
}

export interface MLRun<TReport = MLDiseaseReport> {
  id: string;
  task?: "disease";
  status: "queued" | "running" | "completed" | "failed" | "insufficient_data";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  filters: MLFilters;
  error: string | null;
  message: string;
  report: TReport | null;
}

export interface MLDiseaseReport {
  status: "completed" | "insufficient_data";
  reason?: string;
  models: {
    id: string;
    name: string;
    cv: { mean: Pick<MLMetrics, "accuracy" | "macro_f1"> };
    holdout: Pick<MLMetrics, "accuracy" | "macro_f1"> & {
      examples?: number | null;
      patients?: number | null;
      per_disease_recall?: Record<string, number | null>;
    };
  }[];
  selection: {
    model_id: string;
    model_name: string;
    prediction_enabled: boolean;
    message: string;
    criterion?: string;
    gate_checks?: Record<string, boolean>;
  } | null;
  split?: {
    training_patients: number | null;
    holdout_patients: number | null;
    training_examples?: number | null;
    holdout_examples?: number | null;
  };
  feature_importance?: { feature: string; label: string; importance: number }[];
  class_labels?: { code: string; label: string }[];
  training_dates?: { from: string | null; through: string | null };
}

export interface MLDiseaseInsights {
  model: MLRun<MLDiseaseReport> | null;
  training: MLRun<MLDiseaseReport> | null;
  prediction: {
    prediction_enabled: boolean;
    counts: { code: string; label: string; count: number | null }[] | null;
    reason?: string;
  };
  source: { patients: number | null; visits: number | null };
}

export interface MLInsights {
  synthetic: boolean;
  filters: MLFilters;
  source: {
    patients: number | null;
    visits: number | null;
    reports: number | null;
    labs: number | null;
    adherence_logs: number | null;
    extracted_reports?: number | null;
    unsupported_reports?: number | null;
    historically_unavailable_reports?: number | null;
    corrections_deduplicated?: number | null;
    history_start: string | null;
    history_end: string | null;
    excluded?: Record<string, number | null>;
  };
  summary: {
    patients: number | null;
    disease_counts: { code: string; label: string; count: number | null }[];
    monthly_counts: { month: string; count: number | null }[];
    stations: { station_id: string; station_name: string; patient_count: number | null; suppressed?: boolean }[];
    station_disease_counts?: {
      station_id: string; station_name: string; patient_count: number | null;
      diseases: { code: string; label: string; count: number | null }[];
    }[];
  };
  patient_groups: MLPatientGroups;
  hotspots: (Partial<ClusterResult> & { status?: string; reason?: string }) | null;
  disease?: MLDiseaseInsights;
  notes: string[];
}
