"""Трекинг груза на видео средствами OpenCV. Нейросеть не используется.

Два метода:

* «Движение» (по умолчанию, маркер не нужен): фон — медиана кадров в скользящем окне
  (груз в каждой точке бывает недолго, поэтому в медиану не попадает). На кадре груз —
  самое заметное пятно, отличающееся от фона; его центр взвешивается по величине отличия.
  Работает и со стальным шариком, и с любым грузом, контрастным к фону.
* «Цвет маркера»: пиксели заданного диапазона HSV, центр масс крупнейшего пятна.

Время кадра берётся из метки времени контейнера (CAP_PROP_POS_MSEC), а не как
«номер кадра / fps»: смартфоны часто пишут видео с переменной частотой кадров,
и деление на номинальные 30 кадр/с даёт систематическую ошибку.
"""

from __future__ import annotations

import math
import warnings
from collections import deque
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
    method: str = "motion"
    """"motion" — вычитание фона, "color" — цветной маркер."""
    color: ColorRange | None = None
    roi: Roi | None = None
    min_area: int = 12
    t_start: float | None = None
    t_end: float | None = None
    motion_threshold: int = 25
    """Минимальное отличие пикселя от фона (0–255), чтобы считать его частью груза."""
    polarity: int = 0
    """−1 — груз темнее фона, +1 — светлее, 0 — определить автоматически."""


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
    if params.color is None:
        raise VideoError("Не выбран цвет маркера.")
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


# --- Метод «движение»: вычитание медианного фона --------------------------------------------

BACKGROUND_WINDOW_S = 20.0
"""Окно медианы фона: груз за 20 с пробегает каждую точку много раз, но нигде не задерживается."""
BACKGROUND_SAMPLES = 24
MAX_JUMP_FRACTION = 0.25
FRAGMENT_FRACTION = 0.2
"""Пятна меньше этой доли типичной площади груза считаются мусором (нить, блики)."""
AREA_MEMORY = 30
"""Груз не может за кадр сместиться больше чем на эту долю диагонали области поиска."""


@dataclass
class BackgroundModel:
    """Фоны (в оттенках серого) для блоков времени. Камеру между сериями часто сдвигают,
    поэтому один фон на всё видео не годится — берётся ближайший по времени блок.

    Три способа (поле mode):

    * "median" — медиана образцов, отличие берётся по модулю. Устойчива к микродрожанию
      камеры, но при малой амплитуде (груз смещается меньше своего диаметра и почти всё
      время закрывает центр) груз сам попадает в фон;
    * "masked" — медиана, из которой вырезан груз (его положения известны из первого
      прохода). Лучший вариант: устойчив к дрожанию и к малой амплитуде;
    * "percentile" — для груза темнее фона 90-й перцентиль (почти самое светлое значение
      пикселя), для светлого — 10-й. Нужен, когда первого прохода ещё нет, а медиана не
      сработала; чувствителен к дрожанию тёмных краёв."""

    times: np.ndarray
    images: list[np.ndarray]
    polarities: list[int]
    """−1 — груз темнее фона, +1 — светлее, 0 — отличие по модулю."""
    roi: Roi

    def index(self, t: float) -> int:
        return int(np.argmin(np.abs(self.times - t)))

    def at(self, t: float) -> np.ndarray:
        return self.images[self.index(t)]

    def difference(self, gray: np.ndarray, t: float) -> np.ndarray:
        """Насколько пиксель «похож на груз»: отличие от фона в сторону цвета груза."""
        k = self.index(t)
        background = self.images[k].astype(np.int16)
        delta = gray.astype(np.int16) - background
        if self.polarities[k] == 0:
            return np.abs(delta).astype(np.uint8)
        if self.polarities[k] < 0:
            delta = -delta
        return np.clip(delta, 0, 255).astype(np.uint8)


def _crop(frame: np.ndarray, roi: Roi) -> np.ndarray:
    return frame[roi.y : roi.y + roi.h, roi.x : roi.x + roi.w]


def _gray(frame: np.ndarray, roi: Roi) -> np.ndarray:
    return cv2.cvtColor(_crop(frame, roi), cv2.COLOR_BGR2GRAY)


def _object_polarity(stack: np.ndarray, threshold: int) -> int:
    """Груз темнее или светлее фона: каких сильных отклонений от медианы больше."""
    median = np.median(stack, axis=0).astype(np.int16)
    delta = stack.astype(np.int16) - median
    darker = int((delta < -threshold).sum())
    brighter = int((delta > threshold).sum())
    return -1 if darker >= brighter else 1


def build_background(
    path: Path,
    roi: Roi | None,
    t_start: float | None,
    t_end: float | None,
    progress: Callable[[float], None] | None = None,
    polarity: int = 0,
    threshold: int = 25,
    mode: str = "median",
    exclude: Callable[[float], tuple[float, float] | None] | None = None,
    exclude_radius: float = 0.0,
) -> BackgroundModel:
    """Проход по видео за образцами фона. Кадры между образцами только «пропускаются»
    (grab без декодирования в изображение), а фоны считаются потоково — в памяти держатся
    лишь образцы текущего окна. exclude(t) — положение груза в момент t (для mode="masked")."""
    info = probe(path)
    start = t_start or 0.0
    end = min(t_end, info.duration) if t_end else info.duration
    span = max(end - start, 1e-3)
    region = (roi or Roi(0, 0, info.width, info.height)).clip(info.width, info.height)
    window = min(BACKGROUND_WINDOW_S, span)
    step = max(window / BACKGROUND_SAMPLES, 1 / max(info.fps_nominal, 1))
    if span <= BACKGROUND_WINDOW_S * 1.5:
        centers = [start + span / 2]
        window = span
    else:
        centers = list(np.arange(start + window / 2, end - window / 2 + 1e-6, window / 2))
        if end - window / 2 - centers[-1] > 1e-3:
            centers.append(end - window / 2)

    times: list[float] = []
    images: list[np.ndarray] = []
    polarities: list[int] = []
    buffer: list[tuple[float, np.ndarray]] = []

    def flush(center: float) -> None:
        chosen = [(t, img) for t, img in buffer if abs(t - center) <= window / 2 + 1e-6]
        if len(chosen) < 3:
            chosen = list(buffer)
        stack = np.stack([img for _, img in chosen])
        times.append(center)
        if mode == "percentile":
            sign = polarity or _object_polarity(stack, threshold)
            polarities.append(sign)
            images.append(np.percentile(stack, 90 if sign < 0 else 10, axis=0).astype(np.uint8))
            return
        polarities.append(0)
        median = np.median(stack, axis=0)
        if mode == "masked" and exclude is not None:
            masked = stack.astype(np.float32)
            rows, cols = np.ogrid[: region.h, : region.w]
            for k, (t, _) in enumerate(chosen):
                pos = exclude(t)
                if pos is not None:
                    hole = (cols - (pos[0] - region.x)) ** 2 + (rows - (pos[1] - region.y)) ** 2
                    masked[k][hole <= exclude_radius**2] = np.nan
            with np.errstate(all="ignore"), warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)  # пиксель закрыт всегда
                clean = np.nanmedian(masked, axis=0)
            if np.isnan(clean).any():
                # При амплитуде меньше радиуса груза центр закрыт на всех образцах — там
                # фон берём перцентилем по яркости груза (дрожание краёв здесь не мешает:
                # это пиксели под самим грузом).
                sign = polarity or _object_polarity(stack, threshold)
                fallback = np.percentile(stack, 90 if sign < 0 else 10, axis=0)
                clean = np.where(np.isnan(clean), fallback, clean)
            median = clean
        images.append(median.astype(np.uint8))

    cap = _open(path)
    try:
        if start:
            cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
        next_sample = start
        pending = 0
        while cap.grab():
            t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            if t > end:
                break
            if t + 1e-9 < next_sample:
                continue
            ok, frame = cap.retrieve()
            if not ok or frame is None:
                continue
            buffer.append((t, _gray(frame, region)))
            next_sample = t + step
            while pending < len(centers) and t > centers[pending] + window / 2:
                flush(centers[pending])
                pending += 1
                low = centers[pending] - window / 2 if pending < len(centers) else math.inf
                buffer = [(bt, img) for bt, img in buffer if bt >= low - step]
            if progress:
                progress(min((t - start) / span, 1.0))
        if len(buffer) + len(images) == 0:
            raise VideoError("Слишком короткий интервал для построения фона.")
        while pending < len(centers):
            if buffer:
                flush(centers[pending])
            pending += 1
    finally:
        cap.release()
    if not images:
        raise VideoError("Слишком короткий интервал для построения фона.")
    return BackgroundModel(times=np.array(times), images=images, polarities=polarities, roi=region)


def locate_moving(
    frame: np.ndarray,
    background: BackgroundModel,
    t: float,
    params: TrackingParams,
    previous: tuple[float, float] | None = None,
    expected_area: float | None = None,
) -> tuple[Detection, np.ndarray]:
    """Груз — пятно, отличающееся от фона. Тонкая нить убирается морфологическим «открытием».

    Выбор пятна: если известна типичная площадь груза, мелочь (кусочки нити, блики, шум
    сжатия) отбрасывается; из оставшихся берётся ближайшее к прошлому положению (руки в
    кадре не мешают). Осколки рядом с выбранным пятном присоединяются к нему — так груз,
    который стойка штатива «разрезала» пополам, считается целиком, а не по одной половине."""
    roi = background.roi
    diff = background.difference(_gray(frame, roi), t)
    mask = (diff > params.motion_threshold).astype(np.uint8) * 255
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    )
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    candidates = [j for j in range(1, count) if stats[j, cv2.CC_STAT_AREA] >= params.min_area]
    if expected_area:
        # Строгий порог — только если после него что-то остаётся: груз терять нельзя.
        strict = [
            j for j in candidates if stats[j, cv2.CC_STAT_AREA] >= FRAGMENT_FRACTION * expected_area
        ]
        candidates = strict or candidates
    if not candidates:
        return Detection(False), mask

    best = max(candidates, key=lambda j: stats[j, cv2.CC_STAT_AREA])
    if previous is not None and len(candidates) > 1:
        px, py = previous[0] - roi.x, previous[1] - roi.y
        nearest = min(candidates, key=lambda j: math.dist(centroids[j], (px, py)))
        if math.dist(centroids[nearest], (px, py)) <= MAX_JUMP_FRACTION * math.hypot(roi.w, roi.h):
            best = nearest

    # Осколки того же груза: пятна меньше основного, чьи центры ближе 1,5 радиуса груза.
    best_area = int(stats[best, cv2.CC_STAT_AREA])
    radius = math.sqrt(max(expected_area or 0, best_area) / math.pi)
    members = [
        j
        for j in range(1, count)
        if j == best
        or (
            params.min_area <= stats[j, cv2.CC_STAT_AREA] < best_area
            and math.dist(centroids[j], centroids[best]) <= 1.5 * radius
        )
    ]
    x0 = min(int(stats[j, cv2.CC_STAT_LEFT]) for j in members)
    y0 = min(int(stats[j, cv2.CC_STAT_TOP]) for j in members)
    x1 = max(int(stats[j, cv2.CC_STAT_LEFT] + stats[j, cv2.CC_STAT_WIDTH]) for j in members)
    y1 = max(int(stats[j, cv2.CC_STAT_TOP] + stats[j, cv2.CC_STAT_HEIGHT]) for j in members)
    region = np.isin(labels[y0:y1, x0:x1], members)
    weights = diff[y0:y1, x0:x1].astype(np.float64) * region
    total = weights.sum()
    rows, cols = np.indices(weights.shape)
    cx = (cols * weights).sum() / total + x0
    cy = (rows * weights).sum() / total + y0
    # Площадь — только основного пятна: по ней дальше оценивается типичный размер груза,
    # и прилипшая рядом рука не должна её раздувать.
    return Detection(True, cx + roi.x, cy + roi.y, best_area), mask


def track_video(
    path: Path,
    params: TrackingParams,
    progress: Callable[[float], None] | None = None,
    total_frames: int | None = None,
    background: BackgroundModel | None = None,
    background_mode: str = "median",
) -> TrackResult:
    share = 0.0  # доля прогресса, отведённая первому проходу
    if params.method == "motion" and background is None:
        share = 0.3
        background = build_background(
            path,
            params.roi,
            params.t_start,
            params.t_end,
            progress=(lambda p: progress(p * share)) if progress else None,
            polarity=params.polarity,
            threshold=params.motion_threshold,
            mode=background_mode,
        )
    elif params.method != "motion" and params.color is None:
        raise VideoError("Для метода «Цвет маркера» выберите цвет.")

    ts: list[float] = []
    xs: list[float] = []
    ys: list[float] = []
    areas: list[int] = []
    previous: tuple[float, float] | None = None
    last_seen = -math.inf
    recent_areas: deque[int] = deque(maxlen=AREA_MEMORY)
    for i, (t, frame) in enumerate(iter_frames(path, params.t_start, params.t_end)):
        if background is not None:
            fresh = t - last_seen < 0.5
            det, _ = locate_moving(
                frame,
                background,
                t,
                params,
                previous if fresh else None,
                float(np.median(recent_areas)) if fresh and len(recent_areas) >= 5 else None,
            )
        else:
            det, _ = locate_marker(frame, params)
        if det.found:
            previous, last_seen = (det.x, det.y), t
            recent_areas.append(det.area)
        ts.append(t)
        xs.append(det.x)
        ys.append(det.y)
        areas.append(det.area)
        if progress and total_frames and i % 30 == 0:
            progress(share + (1 - share) * min(i / total_frames, 0.99))
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


def quick_background(
    path: Path, params: TrackingParams, time_s: float, span_s: float = 8.0
) -> BackgroundModel:
    """Фон для предпросмотра одного кадра: ±span_s/2 вокруг него (последовательное чтение)."""
    start = max(time_s - span_s / 2, 0.0)
    return build_background(
        path,
        params.roi,
        start,
        start + span_s,
        polarity=params.polarity,
        threshold=params.motion_threshold,
    )


def oscillation_axis(x: np.ndarray, y: np.ndarray) -> str:
    """Ось с наибольшим размахом движения: для маятника сбоку — обычно горизонталь."""

    def spread(v: np.ndarray) -> float:
        v = v[np.isfinite(v)]
        return float(np.percentile(v, 95) - np.percentile(v, 5)) if v.size else 0.0

    return "x" if spread(x) >= spread(y) else "y"
