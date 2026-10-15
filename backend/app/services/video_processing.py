"""Полный цикл обработки одного видео: трекинг → период → амплитуда → сохранение."""

from __future__ import annotations

import csv
import math
from dataclasses import asdict
from pathlib import Path

import numpy as np

from app.schemas import FitOut, FrameTimingOut, TrackingParamsIn, VideoResultOut
from app.science.periods import analyze_oscillation
from app.science.tracking import ColorRange, Roi, TrackingParams, TrackResult, oscillation_axis

TRACK_FILE = "track.csv"


def video_dir(videos_root: Path, video_id: int) -> Path:
    return videos_root / str(video_id)


def to_tracking_params(params: TrackingParamsIn) -> TrackingParams:
    roi = params.roi
    return TrackingParams(
        color=ColorRange(**params.color.model_dump()),
        roi=Roi(roi.x, roi.y, roi.w, roi.h) if roi else None,
        min_area=params.min_area,
        t_start=params.t_start,
        t_end=params.t_end,
    )


def _amplitude_deg(
    amplitude_px: float, length_px: float | None, px_per_cm: float | None, length_cm: float
) -> float | None:
    """Угол по амплитуде: через точку подвеса (L в пикселях) или через масштаб и L в см."""
    if length_px and length_px > amplitude_px:
        return math.degrees(math.asin(amplitude_px / length_px))
    if px_per_cm:
        ratio = amplitude_px / px_per_cm / length_cm
        if ratio < 1:
            return math.degrees(math.asin(ratio))
    return None


def analyze_track(track: TrackResult, params: TrackingParamsIn, length_cm: float) -> VideoResultOut:
    axis = oscillation_axis(track.x, track.y) if params.axis == "auto" else params.axis
    signal = track.x if axis == "x" else track.y
    res = analyze_oscillation(track.t, signal)

    length_px = None
    if params.pivot:
        # Равновесное положение груза: центр колебаний по одной оси, медиана — по другой.
        other = track.y if axis == "x" else track.x
        other_center = float(np.nanmedian(other))
        bob = (res.center, other_center) if axis == "x" else (other_center, res.center)
        length_px = math.dist(bob, (params.pivot.x, params.pivot.y))
    px_per_cm = params.scale.px_per_cm if params.scale else None

    fit = res.fit
    return VideoResultOut(
        axis=axis,
        period=res.period,
        period_se=res.period_se,
        event_sigma=res.event_sigma,
        period_std=res.period_std,
        periods_observed=res.periods_observed,
        crossings_count=len(res.crossing_times),
        crossing_times=res.crossing_times,
        period_values=res.period_values,
        period_value_times=res.period_value_times,
        center_px=res.center,
        amplitude_start_px=res.amplitude_start,
        amplitude_mean_px=res.amplitude_mean,
        amplitude_start_deg=_amplitude_deg(res.amplitude_start, length_px, px_per_cm, length_cm),
        amplitude_mean_deg=_amplitude_deg(res.amplitude_mean, length_px, px_per_cm, length_cm),
        damping=res.damping,
        fit=FitOut(**asdict(fit)) if fit else None,
        detection_rate=track.detection_rate,
        frames_analyzed=int(track.t.size),
        px_per_cm=px_per_cm,
        length_from_video_cm=length_px / px_per_cm if length_px and px_per_cm else None,
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
                    a,
                ]
            )


def read_track_csv(path: Path) -> tuple[list[float], list[float | None], list[float | None]]:
    ts: list[float] = []
    xs: list[float | None] = []
    ys: list[float | None] = []
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ts.append(float(row["t_s"]))
            xs.append(float(row["x_px"]) if row["x_px"] else None)
            ys.append(float(row["y_px"]) if row["y_px"] else None)
    return ts, xs, ys
