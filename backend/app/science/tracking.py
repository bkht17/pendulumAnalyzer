"""Трекинг цветного маркера на видео средствами OpenCV.

Нейросеть не используется: на каждом кадре выделяются пиксели заданного цветового
диапазона HSV, из них выбирается самое крупное связное пятно, его центр масс
(с субпиксельной точностью) и есть положение груза.

Время кадра берётся из метки времени контейнера (CAP_PROP_POS_MSEC), а не как
«номер кадра / fps»: смартфоны часто пишут видео с переменной частотой кадров,
и деление на номинальные 30 кадр/с даёт систематическую ошибку.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

# OpenCV хранит оттенок в диапазоне 0..179 (градусы / 2).
HUE_MAX = 179


class VideoError(RuntimeError):
    pass


@dataclass(frozen=True)
class ColorRange:
    h_min: int
    h_max: int
    s_min: int = 80
    s_max: int = 255
    v_min: int = 60
    v_max: int = 255

    @property
    def wraps(self) -> bool:
        """Красный цвет лежит по обе стороны от 0: h_min > h_max означает «через ноль»."""
        return self.h_min > self.h_max


@dataclass(frozen=True)
class Roi:
    x: int
    y: int
    w: int
    h: int

    def clip(self, width: int, height: int) -> Roi:
        x0 = min(max(self.x, 0), width - 1)
        y0 = min(max(self.y, 0), height - 1)
        x1 = min(max(self.x + self.w, x0 + 1), width)
        y1 = min(max(self.y + self.h, y0 + 1), height)
        return Roi(x0, y0, x1 - x0, y1 - y0)


@dataclass(frozen=True)
class TrackingParams:
    color: ColorRange
    roi: Roi | None = None
    min_area: int = 12
    t_start: float | None = None
    t_end: float | None = None


@dataclass(frozen=True)
class Detection:
    found: bool
    x: float = math.nan
    y: float = math.nan
    area: int = 0


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps_nominal: float
    frame_count: int
    duration: float


@dataclass(frozen=True)
class FrameTiming:
    fps_measured: float
    """1 / медианный интервал между кадрами."""
    frame_interval_jitter: float
    """Относительный разброс интервалов между кадрами (СКО / медиана)."""
    variable_frame_rate: bool
    dropped_frames: int
    """Число интервалов длиннее 1,5 медианных — вероятные пропуски кадров."""


@dataclass
class TrackResult:
    t: np.ndarray
    x: np.ndarray
    y: np.ndarray
    area: np.ndarray
    timing: FrameTiming

    @property
    def detection_rate(self) -> float:
        return float(np.isfinite(self.x).mean()) if self.x.size else 0.0


def _open(path: Path) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise VideoError("Не удалось открыть видео — формат не поддерживается или файл повреждён.")
    return cap


def probe(path: Path) -> VideoInfo:
    cap = _open(path)
    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        ok, frame = cap.read()
        if not ok or frame is None:
            raise VideoError("В видео не найдено ни одного кадра.")
        # С учётом поворота из метаданных размеры берём у фактически декодированного кадра.
        height, width = frame.shape[:2]
    finally:
        cap.release()
    duration = frames / fps if fps > 0 else 0.0
    return VideoInfo(width, height, fps, frames, duration)


def read_frame_at(path: Path, time_s: float) -> tuple[np.ndarray, float]:
    cap = _open(path)
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(time_s, 0.0) * 1000)
        ok, frame = cap.read()
        if not ok or frame is None:
            raise VideoError(f"Не удалось прочитать кадр на {time_s:.2f} с.")
        return frame, cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
    finally:
        cap.release()


def iter_frames(
    path: Path, t_start: float | None = None, t_end: float | None = None
) -> Iterator[tuple[float, np.ndarray]]:
    cap = _open(path)
    try:
        if t_start:
            cap.set(cv2.CAP_PROP_POS_MSEC, t_start * 1000)
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                return
            t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            if t_end is not None and t > t_end:
                return
            yield t, frame
    finally:
        cap.release()


def color_mask(bgr: np.ndarray, color: ColorRange) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    if color.wraps:
        low = cv2.inRange(
            hsv,
            np.array([color.h_min, color.s_min, color.v_min]),
            np.array([HUE_MAX, color.s_max, color.v_max]),
        )
        high = cv2.inRange(
            hsv,
            np.array([0, color.s_min, color.v_min]),
            np.array([color.h_max, color.s_max, color.v_max]),
        )
        mask = cv2.bitwise_or(low, high)
    else:
        mask = cv2.inRange(
            hsv,
            np.array([color.h_min, color.s_min, color.v_min]),
            np.array([color.h_max, color.s_max, color.v_max]),
        )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)


def locate_marker(bgr: np.ndarray, params: TrackingParams) -> tuple[Detection, np.ndarray]:
    """Возвращает положение маркера в координатах полного кадра и маску области поиска."""
    height, width = bgr.shape[:2]
    roi = params.roi.clip(width, height) if params.roi else Roi(0, 0, width, height)
    crop = bgr[roi.y : roi.y + roi.h, roi.x : roi.x + roi.w]
    mask = color_mask(crop, params.color)
    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 1:
        return Detection(False), mask
    areas = stats[1:, cv2.CC_STAT_AREA]
    best = int(np.argmax(areas))
    if areas[best] < params.min_area:
        return Detection(False), mask
    cx, cy = centroids[best + 1]
    return Detection(True, float(cx) + roi.x, float(cy) + roi.y, int(areas[best])), mask


def _circular_hue_stats(hues: np.ndarray) -> tuple[float, float]:
    """Средний оттенок и 90-й перцентиль отклонения с учётом цикличности 0..179."""
    angles = hues.astype(float) * (2 * np.pi / (HUE_MAX + 1))
    mean_angle = math.atan2(np.sin(angles).mean(), np.cos(angles).mean())
    mean_hue = (mean_angle * (HUE_MAX + 1) / (2 * np.pi)) % (HUE_MAX + 1)
    diff = np.abs((hues - mean_hue + 90) % (HUE_MAX + 1) - 90)
    return mean_hue, float(np.percentile(diff, 90))


def suggest_color_range(bgr: np.ndarray, x: int, y: int, radius: int = 6) -> ColorRange:
    """Подбирает диапазон HSV по пятну вокруг точки, на которую кликнул пользователь."""
    height, width = bgr.shape[:2]
    x0, x1 = max(x - radius, 0), min(x + radius + 1, width)
    y0, y1 = max(y - radius, 0), min(y + radius + 1, height)
    if x0 >= x1 or y0 >= y1:
        raise VideoError("Точка вне кадра.")
    hsv = cv2.cvtColor(bgr[y0:y1, x0:x1], cv2.COLOR_BGR2HSV).reshape(-1, 3)
    mean_hue, spread = _circular_hue_stats(hsv[:, 0])
    tolerance = int(min(max(8, 2 * spread + 4), 25))
    h_min = round(mean_hue - tolerance) % (HUE_MAX + 1)
    h_max = round(mean_hue + tolerance) % (HUE_MAX + 1)
    s_low = float(np.percentile(hsv[:, 1], 10))
    v_low = float(np.percentile(hsv[:, 2], 10))
    return ColorRange(
        h_min=h_min,
        h_max=h_max,
        s_min=int(max(40, s_low * 0.55)),
        v_min=int(max(40, v_low * 0.45)),
    )


def measure_timing(t: np.ndarray) -> FrameTiming:
    dt = np.diff(t)
    dt = dt[dt > 0]
    if dt.size == 0:
        return FrameTiming(0.0, 0.0, False, 0)
    median = float(np.median(dt))
    jitter = float(np.std(dt) / median)
    dropped = int(np.sum(dt > 1.5 * median))
    return FrameTiming(
        fps_measured=1 / median,
        frame_interval_jitter=jitter,
        variable_frame_rate=jitter > 0.05,
        dropped_frames=dropped,
    )


def track_video(
    path: Path,
    params: TrackingParams,
    progress: Callable[[float], None] | None = None,
    total_frames: int | None = None,
) -> TrackResult:
    ts: list[float] = []
    xs: list[float] = []
    ys: list[float] = []
    areas: list[int] = []
    for i, (t, frame) in enumerate(iter_frames(path, params.t_start, params.t_end)):
        det, _ = locate_marker(frame, params)
        ts.append(t)
        xs.append(det.x)
        ys.append(det.y)
        areas.append(det.area)
        if progress and total_frames and i % 30 == 0:
            progress(min(i / total_frames, 0.99))
    if len(ts) < 2:
        raise VideoError("В выбранном интервале слишком мало кадров.")
    t_arr = np.asarray(ts)
    return TrackResult(
        t=t_arr,
        x=np.asarray(xs),
        y=np.asarray(ys),
        area=np.asarray(areas),
        timing=measure_timing(t_arr),
    )


def oscillation_axis(x: np.ndarray, y: np.ndarray) -> str:
    """Ось с наибольшим размахом движения: для маятника сбоку — обычно горизонталь."""

    def spread(v: np.ndarray) -> float:
        v = v[np.isfinite(v)]
        return float(np.percentile(v, 95) - np.percentile(v, 5)) if v.size else 0.0

    return "x" if spread(x) >= spread(y) else "y"
