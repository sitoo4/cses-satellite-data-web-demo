export type QualityFlagSummary = Record<string, { distribution: Record<string, number>; sample_count?: number }>;

export type UploadedFileRecord = {
  upload_id: string;
  filename: string;
  size_bytes: number;
  duplicate_of?: string | null;
  status: string;
  hpm_product: string;
  sample_count: number;
  time_parseable: boolean;
  start_time?: string | null;
  end_time?: string | null;
  display_start_time?: string | null;
  display_end_time?: string | null;
  has_vector_magnetic: boolean;
  has_scalar_magnetic: boolean;
  quality_flag_summary: QualityFlagSummary;
  warnings: string[];
  errors: string[];
};

export type SegmentRange = {
  segment_id: string;
  start: string;
  end: string;
  sample_count: number;
};

export type CropSelectDefault = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
};

export type CropSelectOptions = {
  years: number[];
  months: number[];
  days: number[];
  hours: number[];
  minutes_by_hour: Record<string, number[]>;
  default: CropSelectDefault | null;
};

export type UploadSessionPayload = {
  upload_session_id: string;
  mode: "single" | "batch";
  created_at: string;
  per_file_records: UploadedFileRecord[];
  sorted_files: Array<{ upload_id: string; filename: string; hpm_product: string; start: string | null; end: string | null; display_start?: string | null; display_end?: string | null }>;
  merged_time_range: { start: string | null; end: string | null };
  display_time_zone?: string;
  display_time_range?: { start: string | null; end: string | null };
  crop_options?: { start: CropSelectOptions; end: CropSelectOptions };
  segments: SegmentRange[];
  plot_groups?: Array<{ group_id: string; start: string; end: string; display_start?: string; display_end?: string; segment_ids: string[]; reason: string; sample_count?: number }>;
  sample_count: number;
  raw_sample_count: number;
  dedupe: { duplicate_file_count: number; duplicate_sample_count: number };
  data_products: string[];
  time_parseable: boolean;
  crop_enabled: boolean;
  quality_flag_summary: QualityFlagSummary;
  run_log: string[];
};

export type PlotPayload = {
  upload_session_id: string;
  plot_type: "magnetic" | "orbit" | string;
  status: "ok" | "unavailable" | "disabled" | "unsupported";
  reason?: string;
  segments?: SegmentRange[];
  artifact?: {
    artifact_id: string;
    label?: string;
    media_type?: string;
    path?: string;
    exists?: boolean;
  };
};

export type ExportPayload = {
  upload_session_id: string;
  format: string;
  status: "ok" | "unsupported";
  reason?: string;
  row_count?: number;
  artifact?: {
    artifact_id: string;
    label?: string;
    media_type?: string;
    path?: string;
    exists?: boolean;
  };
  manifest_artifact?: {
    artifact_id: string;
    label?: string;
    media_type?: string;
    path?: string;
    exists?: boolean;
  };
  manifest?: Record<string, unknown>;
};

export type NumericStats = {
  status?: string;
  finite_count?: number;
  nan_count?: number;
  min?: number | null;
  max?: number | null;
  mean?: number | null;
  median?: number | null;
  std?: number | null;
  q25?: number | null;
  q75?: number | null;
  iqr?: number | null;
  rms?: number | null;
  peak_to_peak?: number | null;
  unit?: string | null;
};

export type FeatureStatisticsPayload = {
  session_id: string;
  product_type_status: { status: string; products?: string[]; product_type?: string; reason?: string };
  time_range: { start_time: string | null; end_time: string | null; display_start_time?: string | null; display_end_time?: string | null };
  processing_summary: {
    uploaded_file_count: number;
    unique_file_count: number;
    duplicate_file_count: number;
    raw_sample_count: number;
    merged_sample_count: number;
    duplicate_time_removed_count: number;
    sorted_by_time: boolean;
    dedup_by_time: boolean;
    segment_count: number;
    crop_applied: boolean;
    crop_start?: string | null;
    crop_end?: string | null;
    final_sample_count: number;
  };
  overall_statistics: {
    time_coverage?: Record<string, unknown>;
    sampling?: { cadence_median_seconds?: number | null; gap_count?: number; large_gap_threshold_seconds?: number | null };
    magnetic?: { status: string; reason?: string; product_type?: string; variables?: Record<string, NumericStats> };
    position?: { status: string; variables?: Record<string, NumericStats> };
    quality_flags?: Record<string, { status: string; value_counts: Record<string, number>; value_percent?: Record<string, number>; total_count: number }>;
  };
  per_file_statistics?: Array<Record<string, unknown>>;
  per_segment_statistics?: Array<Record<string, unknown>>;
  quality_flag_statistics?: Record<string, { status: string; value_counts: Record<string, number>; value_percent?: Record<string, number>; total_count: number }>;
  warnings: string[];
  errors: string[];
  generated_at: string;
  run_log_entry?: string;
  artifacts?: {
    statistics_json?: { artifact_id: string; label?: string; media_type?: string; path?: string; exists?: boolean };
    statistics_summary_csv?: { artifact_id: string; label?: string; media_type?: string; path?: string; exists?: boolean };
    manifest_json?: { artifact_id: string; label?: string; media_type?: string; path?: string; exists?: boolean };
  };
};

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `API request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
}

export function artifactUrl(artifactId: string): string {
  return `/api/artifacts/${encodeURIComponent(artifactId)}`;
}

export function artifactDownloadUrl(artifactId: string): string {
  return `${artifactUrl(artifactId)}?download=1`;
}

export const api = {
  uploadCsesHpm: (files: File[]) => {
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    return apiFetch<UploadSessionPayload>("/api/cses-hpm/uploads", {
      method: "POST",
      body
    });
  },
  getUploadSession: (sessionId: string) => apiFetch<UploadSessionPayload>(`/api/cses-hpm/uploads/${encodeURIComponent(sessionId)}`),
  plotUploadSession: (sessionId: string, payload: Record<string, unknown>) =>
    apiPost<PlotPayload>(`/api/cses-hpm/uploads/${encodeURIComponent(sessionId)}/plot`, payload),
  exportUploadSession: (sessionId: string, payload: Record<string, unknown>) =>
    apiPost<ExportPayload>(`/api/cses-hpm/uploads/${encodeURIComponent(sessionId)}/export`, payload),
  statisticsUploadSession: (sessionId: string, payload: Record<string, unknown>) =>
    apiPost<FeatureStatisticsPayload>(`/api/sessions/${encodeURIComponent(sessionId)}/statistics`, payload)
};
