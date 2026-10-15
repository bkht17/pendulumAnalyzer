"""Поиск участков свободных колебаний в длинной записи.

В реальной записи обычно несколько серий подряд: груз запускают, он качается, потом руки
меняют длину нити и запускают снова. Участок свободных колебаний узнаётся по признакам:

* груз виден без перерывов;
* переходы через центр идут регулярно (полупериоды отличаются не больше чем на 12 %);
* амплитуда не растёт (рост означает толчок рукой);
* таких переходов подряд не меньше MIN_CROSSINGS.

Центр колебаний и амплитуда оцениваются локально — как середина и полуразмах между
скользящими верхним и нижним перцентилями. Медиана здесь не годится: пока груз держат
у края перед запуском, она смещается к этому краю, а середина размаха — нет (точка
удержания и есть край размаха).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import numpy as np
from scipy.ndimage import percentile_filter

from app.science.periods import find_crossings

MIN_CROSSINGS = 8
HALF_PERIOD_TOLERANCE = 0.12
AMPLITUDE_GROWTH_LIMIT = 1.15
MIN_AMPLITUDE_PX = 4.0
LOCAL_WINDOW_S = 2.5
MAX_GAP_FRAMES = 3


@dataclass(frozen=True)
class Segment:
    t_start: float
    t_end: float
    crossings: int
    period_estimate: float


def _fill_gaps(values: np.ndarray) -> np.ndarray:
    idx = np.arange(values.size)
    ok = np.isfinite(values)
    if ok.sum() < 2:
        return np.zeros_like(values)
    return np.interp(idx, idx[ok], values[ok])


def find_segments(t: np.ndarray, x: np.ndarray) -> list[Segment]:
    t = np.asarray(t, dtype=float)
    x = np.asarray(x, dtype=float)
    valid = np.isfinite(x)
    if valid.sum() < MIN_CROSSINGS * 3:
        return []
    frame_dt = float(np.median(np.diff(t)))
    window = max(5, round(LOCAL_WINDOW_S / frame_dt) | 1)

    filled = _fill_gaps(x)
    upper = percentile_filter(filled, 97, size=window, mode="nearest")
    lower = percentile_filter(filled, 3, size=window, mode="nearest")
    center = (upper + lower) / 2
    s = np.where(valid, x - center, np.nan)
    local_amp = (upper - lower) / 2
    threshold = np.maximum(0.3 * local_amp, MIN_AMPLITUDE_PX / 2)
    times, _ = find_crossings(t, s, threshold, max_gap=(MAX_GAP_FRAMES + 0.5) * frame_dt)
    if times.size < MIN_CROSSINGS:
        return []

    # Пропуски (груз не найден) и пик |s| для каждого полуколебания.
    invalid_cum = np.concatenate([[0], np.cumsum(~valid)])
    idx = np.searchsorted(t, times)
    peaks = []
    for a, b in pairwise(idx):
        seg = s[a:b]
        peaks.append(float(np.nanmax(np.abs(seg))) if np.isfinite(seg).any() else 0.0)

    segments: list[Segment] = []
    chain = [0]

    def close_chain() -> None:
        if len(chain) >= MIN_CROSSINGS:
            first, last = times[chain[0]], times[chain[-1]]
            half = float(np.median(np.diff(times[chain])))
            segments.append(
                Segment(
                    t_start=float(max(first - half / 2, t[0])),
                    t_end=float(min(last + half / 2, t[-1])),
                    crossings=len(chain),
                    period_estimate=2 * half,
                )
            )

    for j in range(1, times.size):
        prev = chain[-1]
        half = times[j] - times[prev]
        recent = np.diff(times[chain[-5:]]) if len(chain) >= 2 else np.array([half])
        typical = float(np.median(recent))
        gaps = invalid_cum[idx[j]] - invalid_cum[idx[prev]]
        # Сравниваем с пиком на той же стороне (два полуколебания назад): так проверка не
        # зависит от небольшой ошибки локального центра.
        amp_now = peaks[j - 1]
        amp_before = peaks[j - 3] if len(chain) >= 3 else amp_now
        regular = abs(half / typical - 1) <= HALF_PERIOD_TOLERANCE
        not_pushed = amp_now <= AMPLITUDE_GROWTH_LIMIT * amp_before
        visible = gaps <= MAX_GAP_FRAMES and amp_now >= MIN_AMPLITUDE_PX
        if regular and not_pushed and visible:
            chain.append(j)
        else:
            close_chain()
            # Нерегулярный полупериод мог возникнуть из-за ложного перехода (дрожание
            # груза перед запуском) — тогда последний переход старой цепочки настоящий
            # и с него можно начать новую. После толчка или потери груза — только заново.
            chain = [prev, j] if visible and not_pushed else [j]
    close_chain()
    return segments
