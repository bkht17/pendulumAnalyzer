"""Участки видео: анализ, пересоздание после трекинга, ручная правка границ."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from app.models import Video, VideoSegment
from app.schemas import TrackingParamsIn
from app.science import physics
from app.science.periods import AnalysisError
from app.science.segments import Segment
from app.services.video_processing import (
    TRACK_FILE,
    analyze_segment,
    read_track_csv,
    slice_track,
    video_dir,
)

Track = tuple[np.ndarray, np.ndarray, np.ndarray]

MAX_EVENT_SIGMA_FRACTION = 0.01
"""Автоматический участок, где погрешность момента больше 1 % периода, — не свободные
колебания, а возня рук перед запуском: такие участки не создаются (у нормальных ≈ 0,1 %)."""


def acceptable(segment: VideoSegment) -> bool:
    result = segment.result
    if result is None:
        return False
    sigma = result.get("event_sigma")
    return sigma is None or sigma <= MAX_EVENT_SIGMA_FRACTION * result["period"]


def load_track(videos_root: Path, video: Video) -> Track | None:
    path = video_dir(videos_root, video.id) / TRACK_FILE
    return read_track_csv(path) if path.exists() else None


def series_lengths(video: Video) -> dict[int, float]:
    return {s.id: s.length_cm for s in video.experiment.series}


def analyze_into(
    segment: VideoSegment, video: Video, track: Track, lengths: dict[int, float]
) -> None:
    """Пересчитать результат участка по сохранённой траектории (без повторного трекинга).

    Длина серии нужна только как запасной способ найти угол амплитуды (масштаб × длина)."""
    if video.params is None or video.track_info is None:
        segment.result, segment.error = None, "Видео ещё не обработано."
        return
    params = TrackingParamsIn.model_validate(video.params)
    t, x, y = slice_track(*track, segment.t_start, segment.t_end)
    length_cm = lengths.get(segment.series_id) if segment.series_id else None
    try:
        result = analyze_segment(t, x, y, params, video.track_info["axis"], length_cm)
    except AnalysisError as exc:
        segment.result, segment.error = None, str(exc)
        return
    segment.result, segment.error = result.model_dump(), None


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def replace_auto_segments(video: Video, found: list[Segment], track: Track) -> None:
    """Автоматические участки заменяются новыми; привязка к длине переходит к новому
    участку, который больше всего перекрывается со старым. Ручные участки сохраняются."""
    previous = [(s.t_start, s.t_end, s.series_id, s.excluded) for s in video.segments if s.auto]
    for seg in [s for s in video.segments if s.auto]:
        video.segments.remove(seg)

    manual = [(s.t_start, s.t_end) for s in video.segments if not s.auto]
    for item in found:
        span = (item.t_start, item.t_end)
        # Участок, который человек уже задал вручную, не дублируем автоматическим.
        if any(_overlap(span, m) > 0.5 * (item.t_end - item.t_start) for m in manual):
            continue
        best = max(previous, key=lambda p: _overlap(span, (p[0], p[1])), default=None)
        inherited = best if best and _overlap(span, (best[0], best[1])) > 0 else None
        segment = VideoSegment(
            t_start=item.t_start,
            t_end=item.t_end,
            auto=True,
            series_id=inherited[2] if inherited else None,
            excluded=inherited[3] if inherited else False,
        )
        video.segments.append(segment)

    lengths = series_lengths(video)
    for segment in video.segments:
        analyze_into(segment, video, track, lengths)
    for segment in [s for s in video.segments if s.auto and not acceptable(s)]:
        video.segments.remove(segment)

    auto = [s for s in video.segments if s.auto]
    if len(auto) == 1 and auto[0].series_id is None and video.preferred_series_id:
        auto[0].series_id = video.preferred_series_id
        analyze_into(auto[0], video, track, lengths)


MATCH_TOLERANCE = 0.12
"""Насколько (относительно) период участка может отличаться от теоретического для длины."""
MATCH_MARGIN = 0.03
"""Вторая по близости длина должна отличаться по периоду хотя бы на 3 % (≈ 6 % по длине) —
иначе длины ближе, чем обычная разница «измеренная/эффективная», и решать должен человек."""


def match_series(segment: VideoSegment, lengths: dict[int, float], g: float) -> int | None:
    """Длина, к которой участок подходит по периоду, или None, если выбор неочевиден.

    Сравнивается T₀ участка (без влияния амплитуды) с 2π√(L/g). Длины, измеренные
    линейкой, обычно немного меньше эффективной длины маятника (центр качания ниже
    точки, до которой мерили), поэтому допуск взят с запасом, а неоднозначные случаи
    оставляются человеку."""
    result = segment.result
    if not result or not lengths:
        return None
    period = result.get("t0") or result["period"]
    errors = sorted(
        (abs(period / physics.period_small_angle(length / 100, g) - 1), series_id)
        for series_id, length in lengths.items()
        if length > 0
    )
    best_error, best_id = errors[0]
    if best_error > MATCH_TOLERANCE:
        return None
    if len(errors) > 1 and errors[1][0] - best_error < MATCH_MARGIN:
        return None
    return best_id


def auto_assign(video: Video, track: Track) -> list[int]:
    """Привязать непривязанные участки к длинам по периоду. Возвращает id привязанных."""
    lengths = series_lengths(video)
    g = video.experiment.g_reference
    assigned = []
    for segment in video.segments:
        if segment.series_id is not None or segment.excluded:
            continue
        series_id = match_series(segment, lengths, g)
        if series_id is not None:
            segment.series_id = series_id
            analyze_into(segment, video, track, lengths)
            assigned.append(segment.id)
    return assigned
