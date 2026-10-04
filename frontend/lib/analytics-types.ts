export interface AnalyticsFilters {
  dataset_id: string;
  disease_code: string;
  line: string;
  station_id: string;
  date_from: string;
  date_to: string;
}

export interface AnalyticsParameters { radius_km: number; min_samples: number }
export interface AnalyticsMetric { value: number | null; reason: string | null; sample_size?: number | null; coverage?: number | null }
export interface StationAnchor { station_id: string; station_name: string; lines: string[]; latitude: number; longitude: number }
export interface AnalyticsCatalog {
  synthetic: boolean;
  suppression_threshold: number;
  datasets: { dataset_id: string; as_of: string; observation_start: string; generator_version: string; patient_count: number }[];
  diseases: { disease_code: string; label: string }[];
  stations: StationAnchor[];
  lines: string[];
  defaults: AnalyticsFilters & AnalyticsParameters;
}
export interface StationCount { station_id: string; station_name: string; patient_count: number | null; suppressed: boolean; lines?: string[] }
export interface AnalyticsSummary {
  synthetic: boolean;
  dataset_id: string;
  filters: AnalyticsFilters;
  suppression_threshold: number;
  counts: { distinct_patients: number | null; observations: number | null; patient_disease_pairs: number | null; missing_coordinates: number | null; first_recorded_episodes_in_window: number | null };
  diseases: { disease_code: string; label: string; patient_count: number | null; suppressed: boolean }[];
  stations: StationCount[];
  lines: { line: string; patient_count: number | null; suppressed: boolean }[];
  age_bands: { age_band: string; patient_count: number | null; suppressed: boolean }[];
  weekly?: { week_start: string; patient_count: number | null; suppressed: boolean; first_recorded_episode_count?: number | null }[];
  notes: string[];
}
export interface AnalyticsCluster {
  cluster: number;
  patient_count: number | null;
  suppressed: boolean;
  centroid: { latitude: number; longitude: number } | null;
  bounds: { south: number; north: number; west: number; east: number } | null;
  stations: StationCount[];
}
export interface ClusterResult {
  counts: { eligible_patients: number | null; with_coordinates: number | null; missing_coordinates: number | null; clustered_patients: number | null; noise_patients: number | null; cluster_count: number | null };
  metrics: { noise_fraction: number | null; noise_fraction_reason?: string | null; silhouette: AnalyticsMetric };
  clusters: AnalyticsCluster[];
  notes: string[];
}
export interface EvaluationCell extends AnalyticsParameters { cluster_count: number | null; noise_fraction: number | null; silhouette: AnalyticsMetric }
export interface EvaluationResult {
  grid: EvaluationCell[];
  selected: AnalyticsParameters;
  stability: {
    seed: number; subsample_fraction: number; perturbation_km: number;
    repeats: { repeat: number; shared_patients: number | null; retained_fraction: number | null; noise_fraction: number | null; adjusted_rand_index: AnalyticsMetric }[];
    mean_adjusted_rand_index: AnalyticsMetric;
  };
  synthetic_pattern_recovery: {
    adjusted_rand_index: AnalyticsMetric; evaluated_patients: number | null; coverage: number | null; background_convention: string; reason: string | null;
  };
  counts: Record<string, number | null>;
  notes: string[];
}
export interface AnalyticsRun<T> {
  id: string; kind: "cluster" | "evaluation"; status: string; reused: boolean; created_at: string;
  synthetic: boolean; dataset_id: string; filters: AnalyticsFilters; parameters: AnalyticsParameters;
  runtime_ms: number; versions: Record<string, string>; result: T;
}
