"""Полный цикл трекинга длинной записи: трекинг → поиск серий → уточнение каждой серии.

Зачем второй проход. Медианный фон первого прохода «пачкается» самим грузом в двух
случаях: перед запуском груз 10–20 секунд держат рукой неподвижно (на графике потом
срезанные вершины), и при малой амплитуде, когда груз смещается меньше своего диаметра
и почти всё время закрывает центр. Поэтому для каждой найденной серии фон строится
заново — медианой только по её кадрам, где груз всё время движется, — и серия трекается
ещё раз с запасом по краям (границы тоже уточняются). Если амплитуда меньше ~2,5 радиуса
груза, из образцов фона дополнительно вырезается сам груз (его положения известны из
первого прохода). Всегда так не делается: вырезанный круг заодно прячет от медианы
дрожащие края соседних предметов.

Если первый проход не нашёл ни одной серии (чаще всего — та же малая амплитуда),
он повторяется с перцентильным фоном.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import numpy as np

from app.science.segments import Segment, find_segments
from app.science.tracking import (
    TrackingParams,
    TrackResult,
    build_background,
    oscillation_axis,
    track_video,
)

REFINE_MARGIN_S = 4.0
SMALL_AMPLITUDE_RADII = 2.5
FIRST_PASS_SHARE = 0.55


def _signal(track: TrackResult, axis: str) -> np.ndarray:
    return track.x if axis == "x" else track.y


def _position_lookup(track: TrackResult):
    """Положение груза из первого прохода в ближайший к t кадр (или None, если не найден)."""

    def lookup(t: float) -> tuple[float, float] | None:
        i = int(np.clip(np.searchsorted(track.t, t), 0, track.t.size - 1))
        if not (np.isfinite(track.x[i]) and np.isfinite(track.y[i])):
            return None
        return float(track.x[i]), float(track.y[i])

    return lookup


def _ball_radius(track: TrackResult, seg: Segment) -> float:
    """Радиус вырезаемого круга: по типичной площади пятна груза с запасом."""
    m = (track.t >= seg.t_start) & (track.t <= seg.t_end) & (track.area > 0)
    area = float(np.median(track.area[m])) if m.any() else 400.0
    return 1.6 * float(np.sqrt(area / np.pi)) + 4.0


def _amplitude(track: TrackResult, seg: Segment, axis: str) -> float:
    m = (track.t >= seg.t_start) & (track.t <= seg.t_end)
    values = _signal(track, axis)[m]
    values = values[np.isfinite(values)]
    return float(np.percentile(values, 95) - np.percentile(values, 5)) / 2 if values.size else 0.0


def _choose_axis(track: TrackResult, axis: str) -> tuple[str, list[Segment]]:
    """«Авто»: ось, вдоль которой больше регулярных колебаний. Размах по всей записи не
    годится — руки, перевязывающие нить, дают большие вертикальные смещения."""
    if axis != "auto":
        return axis, find_segments(track.t, _signal(track, axis))
    options = {a: find_segments(track.t, _signal(track, a)) for a in ("x", "y")}
    best = max(options, key=lambda a: sum(s.crossings for s in options[a]))
    if not options[best]:
        best = oscillation_axis(track.x, track.y)
    return best, options[best]


def track_with_segments(
    path: Path,
    params: TrackingParams,
    axis: str = "auto",
    progress: Callable[[float], None] | None = None,
    total_frames: int | None = None,
) -> tuple[TrackResult, list[Segment], str]:
    first_share = FIRST_PASS_SHARE if params.method == "motion" else 1.0
    track = track_video(
        path,
        params,
        progress=(lambda p: progress(p * first_share / 2)) if progress else None,
        total_frames=total_frames,
    )
    resolved_axis, segments = _choose_axis(track, axis)
    if params.method == "motion" and not segments:
        track = track_video(
            path,
            params,
            progress=(lambda p: progress(first_share * (0.5 + p / 2))) if progress else None,
            total_frames=total_frames,
            background_mode="percentile",
        )
        resolved_axis, segments = _choose_axis(track, axis)
    if params.method != "motion" or not segments:
        return track, segments, resolved_axis

    t_min, t_max = float(track.t[0]), float(track.t[-1])
    total = sum(s.t_end - s.t_start + 2 * REFINE_MARGIN_S for s in segments)
    done = 0.0
    for seg in segments:
        lo = max(seg.t_start - REFINE_MARGIN_S, t_min)
        hi = min(seg.t_end + REFINE_MARGIN_S, t_max)
        weight = (hi - lo) / total * (1 - first_share)
        base = first_share + done

        radius = _ball_radius(track, seg)
        small = _amplitude(track, seg, resolved_axis) < SMALL_AMPLITUDE_RADII * radius

        def report(p: float, base: float = base, weight: float = weight) -> None:
            if progress:
                progress(base + weight * p)

        background = build_background(
            path,
            params.roi,
            seg.t_start,
            seg.t_end,
            progress=lambda p: report(0.3 * p),
            polarity=params.polarity,
            threshold=params.motion_threshold,
            mode="masked" if small else "median",
            exclude=_position_lookup(track) if small else None,
            exclude_radius=radius,
        )
        frames = round((hi - lo) / max(float(np.median(np.diff(track.t))), 1e-3))
        sub = track_video(
            path,
            replace(params, t_start=lo, t_end=hi),
            progress=lambda p: report(0.3 + 0.7 * p),
            total_frames=frames,
            background=background,
        )
        idx = np.searchsorted(track.t, sub.t)
        ok = (idx < track.t.size) & (
            np.abs(track.t[np.minimum(idx, track.t.size - 1)] - sub.t) < 1e-4
        )
        track.x[idx[ok]] = sub.x[ok]
        track.y[idx[ok]] = sub.y[ok]
        track.area[idx[ok]] = sub.area[ok]
        done += weight

    return track, find_segments(track.t, _signal(track, resolved_axis)), resolved_axis
