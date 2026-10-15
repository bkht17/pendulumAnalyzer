"""Pydantic-схемы API. Единицы: длина — см, время — с, углы — градусы, координаты — пиксели."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import VideoStatus

# --- Эксперимент -------------------------------------------------------------------------


class ExperimentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    g_reference: float = Field(default=9.81, gt=9.7, lt=9.9)
    main_periods: int = Field(default=10, ge=1, le=200)
    notes: str = ""


class ExperimentPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    g_reference: float | None = Field(default=None, gt=9.7, lt=9.9)
    main_periods: int | None = Field(default=None, ge=1, le=200)
    notes: str | None = None


class ExperimentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    g_reference: float
    main_periods: int
    notes: str
    is_demo: bool
    created_at: datetime
    series_count: int = 0
    trials_count: int = 0
    videos_count: int = 0


# --- Длина (серия) -----------------------------------------------------------------------


class SeriesIn(BaseModel):
    length_cm: float = Field(gt=0, le=500)
    length_sigma_cm: float = Field(default=0.3, ge=0, le=10)
    amplitude_deg: float | None = Field(default=None, gt=0, le=60)
    notes: str = ""


class SeriesPatch(BaseModel):
    length_cm: float | None = Field(default=None, gt=0, le=500)
    length_sigma_cm: float | None = Field(default=None, ge=0, le=10)
    amplitude_deg: float | None = Field(default=None, gt=0, le=60)
    notes: str | None = None


class TrialIn(BaseModel):
    periods: int = Field(ge=1, le=500)
    total_time_s: float = Field(gt=0, le=3600)
    operator: str = Field(default="", max_length=100)
    source: Literal["manual", "app"] = "manual"


class TrialPatch(BaseModel):
    excluded: bool | None = None
    operator: str | None = Field(default=None, max_length=100)


class TrialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    periods: int
    total_time_s: float
    period_s: float
    operator: str
    source: str
    excluded: bool
    suspected_outlier: bool = False
    created_at: datetime


# --- Видео и трекинг ---------------------------------------------------------------------


class Point(BaseModel):
    x: float
    y: float


class RoiIn(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)


class ColorIn(BaseModel):
    h_min: int = Field(ge=0, le=179)
    h_max: int = Field(ge=0, le=179)
    s_min: int = Field(default=80, ge=0, le=255)
    s_max: int = Field(default=255, ge=0, le=255)
    v_min: int = Field(default=60, ge=0, le=255)
    v_max: int = Field(default=255, ge=0, le=255)


class ScaleIn(BaseModel):
    """Калибровка: две точки на кадре и реальное расстояние между ними."""

    p1: Point
    p2: Point
    distance_cm: float = Field(gt=0)

    @property
    def px_per_cm(self) -> float:
        return math.dist((self.p1.x, self.p1.y), (self.p2.x, self.p2.y)) / self.distance_cm


class TrackingParamsIn(BaseModel):
    color: ColorIn
    roi: RoiIn | None = None
    min_area: int = Field(default=12, ge=1)
    t_start: float | None = Field(default=None, ge=0)
    t_end: float | None = Field(default=None, gt=0)
    axis: Literal["auto", "x", "y"] = "auto"
    pivot: Point | None = None
    """Точка подвеса — позволяет перевести амплитуду в градусы без калибровки масштаба."""
    scale: ScaleIn | None = None

    @model_validator(mode="after")
    def _check_interval(self) -> TrackingParamsIn:
        if self.t_start is not None and self.t_end is not None and self.t_end <= self.t_start:
            raise ValueError("Конец интервала должен быть позже начала")
        return self


class FrameTimingOut(BaseModel):
    fps_measured: float
    frame_interval_jitter: float
    variable_frame_rate: bool
    dropped_frames: int


class FitOut(BaseModel):
    center: float
    amplitude: float
    damping: float
    period: float
    period_se: float
    phase: float
    t_ref: float
    rms: float


class VideoResultOut(BaseModel):
    axis: Literal["x", "y"]
    period: float
    period_se: float | None
    event_sigma: float | None
    period_std: float | None
    periods_observed: float
    crossings_count: int
    crossing_times: list[float]
    period_values: list[float]
    period_value_times: list[float]
    center_px: float
    amplitude_start_px: float
    amplitude_mean_px: float
    amplitude_start_deg: float | None
    amplitude_mean_deg: float | None
    damping: float | None
    fit: FitOut | None
    detection_rate: float
    frames_analyzed: int
    px_per_cm: float | None
    length_from_video_cm: float | None


class VideoPatch(BaseModel):
    excluded: bool | None = None


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    original_name: str
    size_bytes: int
    width: int
    height: int
    fps_nominal: float
    frame_count: int
    duration_s: float
    status: VideoStatus
    progress: float
    error: str | None
    params: TrackingParamsIn | None
    timing: FrameTimingOut | None
    result: VideoResultOut | None
    excluded: bool
    created_at: datetime
    processed_at: datetime | None


class SampleColorIn(BaseModel):
    time_s: float = Field(ge=0)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    radius: int = Field(default=6, ge=1, le=50)


class PreviewIn(BaseModel):
    time_s: float = Field(ge=0)
    params: TrackingParamsIn


class PreviewOut(BaseModel):
    found: bool
    x: float | None
    y: float | None
    area: int
    mask_png: str
    """Маска области поиска в base64 (PNG, белое — пиксели цвета маркера)."""
    roi: RoiIn


class TrackSeriesOut(BaseModel):
    t: list[float]
    x: list[float | None]
    y: list[float | None]


class SeriesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: int
    length_cm: float
    length_sigma_cm: float
    amplitude_deg: float | None
    notes: str
    created_at: datetime
    trials: list[TrialOut]
    videos: list[VideoOut]


class ExperimentDetail(ExperimentOut):
    series: list[SeriesOut]


# --- Анализ ------------------------------------------------------------------------------


class Estimate(BaseModel):
    value: float
    sigma: float | None


class SummaryOut(BaseModel):
    n: int
    mean: float
    std: float | None
    sem: float | None
    ci95: float | None


class StopwatchByN(BaseModel):
    periods: int
    summary: SummaryOut


class StopwatchStats(BaseModel):
    periods: int
    """Число колебаний в основной серии (по нему считается сравнение)."""
    summary: SummaryOut
    """Статистика периода T = t/N по повторным замерам."""
    event_sigma: float | None
    """Погрешность одного нажатия: σ(t) / √2."""
    excluded: int
    outliers: int
    by_periods: list[StopwatchByN]


class CameraStats(BaseModel):
    videos: int
    period: Estimate
    between_videos: SummaryOut
    event_sigma: float | None
    """Погрешность фиксации момента прохождения равновесия (объединённая по видео)."""
    equivalent_std: float | None
    """Разброс, который дала бы камера при измерении того же числа колебаний, что и секундомер."""
    period_std: float | None
    amplitude_deg: float | None


class MethodComparison(BaseModel):
    difference: float
    """T(секундомер) − T(камера), с."""
    difference_sigma: float | None
    spread_ratio: float | None
    """Во сколько раз разброс секундомера больше разброса камеры."""
    f_statistic: float | None
    p_value: float | None
    stopwatch_rms_error: float | None
    """Среднеквадратичная ошибка отдельного ручного замера относительно камеры."""


class TheoryRow(BaseModel):
    t0: float
    t0_sigma: float
    amplitude_deg: float | None
    t_corrected: float | None


class MethodTheory(BaseModel):
    deviation_pct: float
    """(Tэксп − Tтеор) / Tтеор · 100 % — со знаком, относительно T с учётом амплитуды."""
    z_score: float | None
    """|ΔT| / σ — меньше 2 означает согласие в пределах погрешности."""
    g: Estimate


class SeriesAnalysis(BaseModel):
    series_id: int
    length_cm: float
    length_sigma_cm: float
    stopwatch: StopwatchStats | None
    camera: CameraStats | None
    comparison: MethodComparison | None
    theory: TheoryRow
    stopwatch_vs_theory: MethodTheory | None
    camera_vs_theory: MethodTheory | None


class LengthFit(BaseModel):
    """Аппроксимация T² = k·L + b. g = 4π²/k, b/k — неучтённая добавка к длине."""

    points: int
    slope: float
    slope_se: float | None
    intercept: float
    intercept_se: float | None
    r2: float | None
    g: Estimate
    length_offset_cm: Estimate


class RatioCheck(BaseModel):
    short_cm: float
    long_cm: float
    expected: float
    stopwatch: Estimate | None
    camera: Estimate | None


class NDependencePoint(BaseModel):
    periods: int
    std: float
    trials: int


class NDependence(BaseModel):
    points: list[NDependencePoint]
    event_sigma: float | None
    """Оценка σ нажатия по всем N; модель: σ(T) = √2·σ/N."""


class OverallComparison(BaseModel):
    stopwatch_event_sigma: float | None
    camera_event_sigma: float | None
    ratio: float | None
    p_value: float | None
    stopwatch_df: int
    camera_df: int


class AnalysisOut(BaseModel):
    experiment_id: int
    g_reference: float
    main_periods: int
    series: list[SeriesAnalysis]
    overall: OverallComparison
    fit_stopwatch: LengthFit | None
    fit_camera: LengthFit | None
    ratios: list[RatioCheck]
    n_dependence: NDependence
    conclusions: list[str]
