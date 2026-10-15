"""Обработка видео: параметры трекинга, анализ участков, хранение траектории."""

from __future__ import annotations

import csv
import math
from dataclasses import asdict
from pathlib import Path

import numpy as np

from app.schemas import (
    FitOut,
    FrameTimingOut,
    Point,
    SegmentResultOut,
    TrackingParamsIn,
)
from app.science.geometry import fit_circle
from app.science.periods import analyze_oscillation
from app.science.physics import amplitude_model
from app.science.tracking import ColorRange, Roi, TrackingParams, TrackResult

TRACK_FILE = "track.csv"
MAX_SINE = 0.999
PIVOT_CLICK_ERROR_PX = 5.0
"""Насколько точно человек попадает кликом в точку подвеса."""
SCALE_REL_ERROR = 0.03
"""Масштаб по линейке: линейка и маятник обычно на разном расстоянии от камеры."""


def video_dir(videos_root: Path, video_id: int) -> Path:
    return videos_root / str(video_id)


def to_tracking_params(params: TrackingParamsIn) -> TrackingParams:
    roi = params.roi
    return TrackingParams(
        method=params.method,
        color=ColorRange(**params.color.model_dump()) if params.color else None,
        roi=Roi(roi.x, roi.y, roi.w, roi.h) if roi else None,
        min_area=params.min_area,
        t_start=params.t_start,
        t_end=params.t_end,
        motion_threshold=params.motion_threshold,
        polarity={"auto": 0, "dark": -1, "bright": 1}[params.polarity],
    )


def _degrees(amplitude_px: float, length_px: float | None) -> float | None:
    if not length_px:
        return None
    return math.degrees(math.asin(min(amplitude_px / length_px, MAX_SINE)))


def _equilibrium_point(
    t: np.ndarray, x: np.ndarray, y: np.ndarray, axis: str, crossings: list[float]
) -> tuple[float, float]:
    """Положение груза в момент прохождения равновесия (медиана по всем переходам)."""
    ok = np.isfinite(x) & np.isfinite(y)
    px = np.interp(crossings, t[ok], x[ok])
    py = np.interp(crossings, t[ok], y[ok])
    return float(np.median(px)), float(np.median(py))


def analyze_segment(
    t: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    params: TrackingParamsIn,
    axis: str,
    series_length_cm: float | None = None,
) -> SegmentResultOut:
    """Период, амплитуда и геометрия маятника на одном участке свободных колебаний."""
    signal = x if axis == "x" else y
    res = analyze_oscillation(t, signal)
    px_per_cm = params.scale.px_per_cm if params.scale else None

    # Длина нити в пикселях нужна для угла амплитуды. Источники по убыванию надёжности:
    # отмеченная точка подвеса, дуга траектории, масштаб + длина, записанная для серии.
    length_px: float | None = None
    length_rel_error = 0.0
    source: str | None = None
    pivot: Point | None = None
    if params.pivot:
        pivot = params.pivot
        bob = _equilibrium_point(t, x, y, axis, res.crossing_times)
        length_px, source = math.dist(bob, (pivot.x, pivot.y)), "pivot"
        length_rel_error = PIVOT_CLICK_ERROR_PX / length_px
    else:
        circle = fit_circle(x, y)
        if circle and circle.reliable:
            length_px, source = circle.radius, "arc"
            length_rel_error = circle.radius_se / circle.radius
            pivot = Point(x=circle.cx, y=circle.cy)
        elif px_per_cm and series_length_cm:
            length_px, source = series_length_cm * px_per_cm, "scale"
            length_rel_error = SCALE_REL_ERROR

    thetas = (
        [math.asin(min(a / length_px, MAX_SINE)) for a in res.period_amplitudes]
        if length_px
        else []
    )
    model = amplitude_model(res.period_values, thetas, length_rel_error) if thetas else None

    return SegmentResultOut(
        axis=axis,  # type: ignore[arg-type]
        period=res.period,
        period_se=res.period_se,
        event_sigma=res.event_sigma,
        period_std=res.period_std,
        periods_observed=res.periods_observed,
        crossings_count=len(res.crossing_times),
        outliers=res.outliers,
        crossing_times=res.crossing_times,
        period_values=res.period_values,
        period_value_times=res.period_value_times,
        period_amplitudes_deg=[math.degrees(v) for v in thetas],
        center_px=res.center,
        amplitude_start_px=res.amplitude_start,
        amplitude_mean_px=res.amplitude_mean,
        amplitude_start_deg=_degrees(res.amplitude_start, length_px),
        amplitude_mean_deg=_degrees(res.amplitude_mean, length_px),
        damping=res.damping,
        fit=FitOut(**asdict(res.fit)) if res.fit else None,
        detection_rate=float(np.isfinite(signal).mean()),
        frames_analyzed=int(t.size),
        length_px=length_px,
        length_px_source=source,  # type: ignore[arg-type]
        pivot_px=pivot,
        px_per_cm=px_per_cm,
        length_from_video_cm=(
            length_px / px_per_cm if length_px and px_per_cm and source != "scale" else None
        ),
        t0=model.t0 if model else None,
        t0_se=model.t0_se if model else None,
        amplitude_k=model.k if model else None,
        amplitude_k_se=model.k_se if model else None,
        theta_min_deg=model.theta_min_deg if model else None,
        theta_max_deg=model.theta_max_deg if model else None,
    )


def timing_out(track: TrackResult) -> FrameTimingOut:
    return FrameTimingOut(**asdict(track.timing))


def write_track_csv(path: Path, track: TrackResult) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["t_s", "x_px", "y_px", "area_px"])
        for t, x, y, a in zip(track.t, track.x, track.y, track.area, strict=True):
            writer.writerow(
                [
                    f"{t:.6f}",
                    "" if math.isnan(x) else f"{x:.3f}",
                    "" if math.isnan(y) else f"{y:.3f}",
                    int(a),
                ]
            )


def read_track_csv(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ts: list[float] = []
    xs: list[float] = []
    ys: list[float] = []
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ts.append(float(row["t_s"]))
            xs.append(float(row["x_px"]) if row["x_px"] else math.nan)
            ys.append(float(row["y_px"]) if row["y_px"] else math.nan)
    return np.asarray(ts), np.asarray(xs), np.asarray(ys)


def slice_track(
    t: np.ndarray, x: np.ndarray, y: np.ndarray, t_start: float, t_end: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    m = (t >= t_start) & (t <= t_end)
    return t[m], x[m], y[m]
