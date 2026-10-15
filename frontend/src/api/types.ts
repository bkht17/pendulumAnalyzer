// Зеркало pydantic-схем backend/app/schemas.py. Единицы: см, с, градусы, пиксели.

export interface Experiment {
  id: number;
  name: string;
  g_reference: number;
  main_periods: number;
  notes: string;
  is_demo: boolean;
  created_at: string;
  series_count: number;
  trials_count: number;
  videos_count: number;
}

export interface ExperimentInput {
  name: string;
  g_reference?: number;
  main_periods?: number;
  notes?: string;
}

export interface Trial {
  id: number;
  periods: number;
  total_time_s: number;
  period_s: number;
  operator: string;
  source: "manual" | "app";
  excluded: boolean;
  suspected_outlier: boolean;
  created_at: string;
}

export interface TrialInput {
  periods: number;
  total_time_s: number;
  operator?: string;
  source?: "manual" | "app";
}

export interface Point {
  x: number;
  y: number;
}

export interface Roi {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ColorRange {
  h_min: number;
  h_max: number;
  s_min: number;
  s_max: number;
  v_min: number;
  v_max: number;
}

export interface ScaleCalibration {
  p1: Point;
  p2: Point;
  distance_cm: number;
}

export type TrackingMethod = "motion" | "color";

export interface TrackingParams {
  method: TrackingMethod;
  color: ColorRange | null;
  roi: Roi | null;
  min_area: number;
  motion_threshold: number;
  polarity: "auto" | "dark" | "bright";
  t_start: number | null;
  t_end: number | null;
  axis: "auto" | "x" | "y";
  pivot: Point | null;
  scale: ScaleCalibration | null;
}

export interface TrackInfo {
  axis: "x" | "y";
  detection_rate: number;
  frames: number;
}

export interface FrameTiming {
  fps_measured: number;
  frame_interval_jitter: number;
  variable_frame_rate: boolean;
  dropped_frames: number;
}

export interface DampedFit {
  center: number;
  amplitude: number;
  damping: number;
  period: number;
  period_se: number;
  phase: number;
  t_ref: number;
  rms: number;
}

export interface SegmentResult {
  axis: "x" | "y";
  period: number;
  period_se: number | null;
  event_sigma: number | null;
  period_std: number | null;
  periods_observed: number;
  crossings_count: number;
  outliers: number;
  crossing_times: number[];
  period_values: number[];
  period_value_times: number[];
  period_amplitudes_deg: number[];
  center_px: number;
  amplitude_start_px: number;
  amplitude_mean_px: number;
  amplitude_start_deg: number | null;
  amplitude_mean_deg: number | null;
  damping: number | null;
  fit: DampedFit | null;
  detection_rate: number;
  frames_analyzed: number;
  length_px: number | null;
  length_px_source: "pivot" | "arc" | "scale" | null;
  pivot_px: Point | null;
  px_per_cm: number | null;
  length_from_video_cm: number | null;
  t0: number | null;
  t0_se: number | null;
  amplitude_k: number | null;
  amplitude_k_se: number | null;
  theta_min_deg: number | null;
  theta_max_deg: number | null;
}

export interface Segment {
  id: number;
  video_id: number;
  video_name: string;
  series_id: number | null;
  t_start: number;
  t_end: number;
  auto: boolean;
  excluded: boolean;
  result: SegmentResult | null;
  error: string | null;
}

export interface SegmentPatch {
  series_id?: number | null;
  excluded?: boolean;
  t_start?: number;
  t_end?: number;
}

export type VideoStatus = "uploaded" | "queued" | "processing" | "done" | "failed";

export interface Video {
  id: number;
  experiment_id: number;
  preferred_series_id: number | null;
  original_name: string;
  size_bytes: number;
  width: number;
  height: number;
  fps_nominal: number;
  frame_count: number;
  duration_s: number;
  status: VideoStatus;
  progress: number;
  error: string | null;
  params: TrackingParams | null;
  timing: FrameTiming | null;
  track_info: TrackInfo | null;
  segments: Segment[];
  excluded: boolean;
  created_at: string;
  processed_at: string | null;
}

export interface Series {
  id: number;
  experiment_id: number;
  length_cm: number;
  length_sigma_cm: number;
  amplitude_deg: number | null;
  notes: string;
  created_at: string;
  trials: Trial[];
  segments: Segment[];
}

export interface SeriesInput {
  length_cm: number;
  length_sigma_cm?: number;
  amplitude_deg?: number | null;
  notes?: string;
}

export interface ExperimentDetail extends Experiment {
  series: Series[];
  videos: Video[];
}

export interface Preview {
  found: boolean;
  x: number | null;
  y: number | null;
  area: number;
  mask_png: string;
  roi: Roi;
}

export interface TrackData {
  t: number[];
  x: (number | null)[];
  y: (number | null)[];
}

// --- Анализ ---------------------------------------------------------------------------

export interface Estimate {
  value: number;
  sigma: number | null;
}

export interface Summary {
  n: number;
  mean: number;
  std: number | null;
  sem: number | null;
  ci95: number | null;
}

export interface StopwatchStats {
  periods: number;
  summary: Summary;
  event_sigma: number | null;
  excluded: number;
  outliers: number;
  by_periods: { periods: number; summary: Summary }[];
}

export interface CameraStats {
  segments: number;
  period: Estimate;
  t0: Estimate | null;
  between_segments: Summary;
  event_sigma: number | null;
  equivalent_std: number | null;
  period_std: number | null;
  amplitude_deg: number | null;
  amplitude_min_deg: number | null;
  amplitude_max_deg: number | null;
  amplitude_k: Estimate | null;
}

export interface MethodComparison {
  difference: number;
  difference_sigma: number | null;
  spread_ratio: number | null;
  f_statistic: number | null;
  p_value: number | null;
  stopwatch_rms_error: number | null;
}

export interface TheoryRow {
  t0: number;
  t0_sigma: number;
  amplitude_deg: number | null;
  t_corrected: number | null;
}

export interface MethodTheory {
  compared: "t0" | "mean";
  deviation_pct: number;
  z_score: number | null;
  g: Estimate;
}

export interface SeriesAnalysis {
  series_id: number;
  length_cm: number;
  length_sigma_cm: number;
  stopwatch: StopwatchStats | null;
  camera: CameraStats | null;
  comparison: MethodComparison | null;
  theory: TheoryRow;
  stopwatch_vs_theory: MethodTheory | null;
  camera_vs_theory: MethodTheory | null;
}

export interface LengthFit {
  points: number;
  slope: number;
  slope_se: number | null;
  intercept: number;
  intercept_se: number | null;
  r2: number | null;
  g: Estimate;
  length_offset_cm: Estimate;
}

export interface RatioCheck {
  short_cm: number;
  long_cm: number;
  expected: number;
  stopwatch: Estimate | null;
  camera: Estimate | null;
}

export interface Analysis {
  experiment_id: number;
  g_reference: number;
  main_periods: number;
  series: SeriesAnalysis[];
  overall: {
    stopwatch_event_sigma: number | null;
    camera_event_sigma: number | null;
    ratio: number | null;
    p_value: number | null;
    stopwatch_df: number;
    camera_df: number;
  };
  fit_stopwatch: LengthFit | null;
  fit_camera: LengthFit | null;
  ratios: RatioCheck[];
  n_dependence: {
    points: { periods: number; std: number; trials: number }[];
    event_sigma: number | null;
  };
  conclusions: string[];
}
