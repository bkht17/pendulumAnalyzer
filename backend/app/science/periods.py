"""Определение периода по зависимости координаты маркера от времени.

Почему не по максимумам (как в исходном плане): в крайней точке скорость равна нулю,
вершина кривой плоская и момент экстремума определяется плохо. В положении равновесия
скорость максимальна, поэтому момент прохождения через центр фиксируется с точностью
до долей кадра. Алгоритм:

1. Грубая оценка центра (медиана) и периода (по переходам через медиану).
2. Подгонка затухающей синусоиды x(t) = c + A·e^(−γt)·cos(2πt/T + φ) — даёт центр c,
   огибающую амплитуды и независимую оценку периода.
3. Поиск моментов прохождения через c с гистерезисом (защита от дрожания маркера)
   и субкадровой точностью (линейная аппроксимация по кадрам в окрестности нуля).
4. Линейная регрессия моментов: t_k = a + b·d_k + k·T/2 (d_k — направление, учитывает
   несимметричность). Наклон даёт период, остаток — погрешность фиксации одного момента.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import curve_fit

HYSTERESIS_FRACTION = 0.3
MIN_POINTS = 30


class AnalysisError(ValueError):
    """Данных недостаточно или они не похожи на колебания."""


@dataclass(frozen=True)
class DampedFit:
    center: float
    amplitude: float
    damping: float
    period: float
    period_se: float
    phase: float
    t_ref: float
    rms: float


@dataclass
class PeriodAnalysis:
    period: float
    """Период по регрессии моментов прохождения равновесия, с."""
    period_se: float | None
    """Стандартная ошибка периода из регрессии, с."""
    event_sigma: float | None
    """Погрешность фиксации одного момента времени (СКО остатков регрессии), с."""
    center: float
    amplitude_start: float
    """Амплитуда в начале анализируемого участка (в единицах координаты)."""
    amplitude_mean: float
    damping: float | None
    crossing_times: list[float] = field(default_factory=list)
    crossing_directions: list[int] = field(default_factory=list)
    period_values: list[float] = field(default_factory=list)
    """Отдельные периоды — интервалы между соседними одноимёнными переходами."""
    period_value_times: list[float] = field(default_factory=list)
    period_std: float | None = None
    fit: DampedFit | None = None

    @property
    def periods_observed(self) -> float:
        if len(self.crossing_times) < 2:
            return 0.0
        return (self.crossing_times[-1] - self.crossing_times[0]) / self.period


def _damped_cosine(
    t: np.ndarray, c: float, a: float, gamma: float, period: float, phi: float
) -> np.ndarray:
    return c + a * np.exp(-gamma * t) * np.cos(2 * np.pi * t / period + phi)


def _rough_crossings(t: np.ndarray, s: np.ndarray, max_gap: float) -> np.ndarray:
    """Моменты смены знака без гистерезиса — только для начальной оценки периода."""
    ok = np.isfinite(s[:-1]) & np.isfinite(s[1:]) & (np.diff(t) <= max_gap)
    idx = np.nonzero(ok & (np.sign(s[:-1]) * np.sign(s[1:]) < 0))[0]
    frac = s[idx] / (s[idx] - s[idx + 1])
    return t[idx] + frac * (t[idx + 1] - t[idx])


def fit_damped_cosine(
    t: np.ndarray, x: np.ndarray, period_guess: float, center_guess: float
) -> DampedFit | None:
    valid = np.isfinite(x)
    tv, xv = t[valid], x[valid]
    t_ref = float(tv[0])
    tr = tv - t_ref
    amp_guess = float(np.percentile(xv, 98) - np.percentile(xv, 2)) / 2
    up = _rough_crossings(tr, xv - center_guess, max_gap=np.inf)
    phi_guess = 0.0
    if len(up):
        # cos(2πt/T + φ) = 0 в первом переходе; выбираем знак так, чтобы скорость совпала
        rising = np.interp(up[0] + 1e-3, tr, xv) > center_guess
        phi_guess = (-np.pi / 2 if rising else np.pi / 2) - 2 * np.pi * up[0] / period_guess
    p0 = [center_guess, amp_guess, 0.0, period_guess, phi_guess]
    bounds = (
        [-np.inf, 0.0, -0.5, period_guess * 0.7, -np.inf],
        [np.inf, np.inf, 5.0, period_guess * 1.3, np.inf],
    )
    try:
        popt, pcov = curve_fit(_damped_cosine, tr, xv, p0=p0, bounds=bounds, maxfev=20000)
    except (RuntimeError, ValueError):
        return None
    if not np.all(np.isfinite(pcov)):
        return None
    resid = xv - _damped_cosine(tr, *popt)
    c, a, gamma, period, phi = (float(v) for v in popt)
    return DampedFit(
        center=c,
        amplitude=a,
        damping=gamma,
        period=period,
        period_se=float(math.sqrt(pcov[3, 3])),
        phase=float(math.remainder(phi, 2 * math.pi)),
        t_ref=t_ref,
        rms=float(np.sqrt(np.mean(resid**2))),
    )


def find_crossings(
    t: np.ndarray, s: np.ndarray, threshold: np.ndarray, max_gap: float
) -> tuple[np.ndarray, np.ndarray]:
    """Переходы сигнала s через ноль с гистерезисом ±threshold.

    Переход засчитывается, только когда сигнал уходит из зоны −h в зону +h (или наоборот),
    поэтому дрожание маркера около центра не даёт ложных переходов. Момент вычисляется
    линейной аппроксимацией по всем кадрам внутри зоны (|s| < h) и двум крайним кадрам.
    """
    times: list[float] = []
    dirs: list[int] = []
    state = 0
    last_outside = -1
    finite = np.flatnonzero(np.isfinite(s))
    for i in finite:
        level = 1 if s[i] >= threshold[i] else -1 if s[i] <= -threshold[i] else 0
        if level == 0:
            continue
        if state != 0 and level != state and last_outside >= 0:
            window = finite[(finite >= last_outside) & (finite <= i)]
            tw, sw = t[window], s[window]
            if np.all(np.diff(tw) <= max_gap):
                slope, intercept = np.polyfit(tw - tw[0], sw, 1)
                if slope != 0:
                    root = tw[0] - intercept / slope
                    if tw[0] <= root <= tw[-1]:
                        times.append(float(root))
                        dirs.append(level)
        state = level
        last_outside = i
    return np.asarray(times), np.asarray(dirs, dtype=int)


def analyze_oscillation(t: np.ndarray, x: np.ndarray) -> PeriodAnalysis:
    t = np.asarray(t, dtype=float)
    x = np.asarray(x, dtype=float)
    valid = np.isfinite(x)
    if valid.sum() < MIN_POINTS:
        raise AnalysisError(
            f"Маркер найден только на {int(valid.sum())} кадрах — нужно хотя бы {MIN_POINTS}."
        )
    frame_dt = float(np.median(np.diff(t)))
    max_gap = 3.5 * frame_dt

    center0 = float(np.median(x[valid]))
    rough = _rough_crossings(t, x - center0, max_gap)
    if len(rough) < 3:
        raise AnalysisError(
            "На записи меньше одного полного колебания — проверьте настройки цвета и обрезку."
        )
    period0 = 2 * float(np.median(np.diff(rough)))

    fit = fit_damped_cosine(t, x, period0, center0)
    center = fit.center if fit else center0
    period_est = fit.period if fit else period0

    if fit:
        envelope = fit.amplitude * np.exp(-fit.damping * (t - fit.t_ref))
    else:
        amp = float(np.percentile(x[valid], 98) - np.percentile(x[valid], 2)) / 2
        envelope = np.full_like(t, amp)
    times, dirs = find_crossings(t, x - center, HYSTERESIS_FRACTION * envelope, max_gap)
    if len(times) < 3:
        raise AnalysisError("Не удалось надёжно найти моменты прохождения положения равновесия.")

    # Номер полупериода: устойчив к пропущенным переходам (например, из-за потери маркера).
    k = np.rint((times - times[0]) / (period_est / 2)).astype(int)
    if np.any(np.diff(k) <= 0):
        raise AnalysisError("Переходы через равновесие идут нерегулярно — проверьте трекинг.")

    period, period_se, event_sigma = _crossing_regression(times, dirs, k)

    same_dir_values: list[tuple[float, float]] = []
    for d in (1, -1):
        sel = dirs == d
        td, kd = times[sel], k[sel]
        for j in range(len(td) - 1):
            if kd[j + 1] - kd[j] == 2:
                same_dir_values.append(((td[j] + td[j + 1]) / 2, td[j + 1] - td[j]))
    same_dir_values.sort()
    values = [v for _, v in same_dir_values]

    span = times[-1] - times[0]
    if fit and fit.damping > 1e-6 and span > 0:
        amp_start = fit.amplitude * math.exp(-fit.damping * (times[0] - fit.t_ref))
        amp_mean = amp_start * (1 - math.exp(-fit.damping * span)) / (fit.damping * span)
    else:
        amp_start = amp_mean = float(envelope[0])

    return PeriodAnalysis(
        period=period,
        period_se=period_se,
        event_sigma=event_sigma,
        center=center,
        amplitude_start=amp_start,
        amplitude_mean=amp_mean,
        damping=fit.damping if fit else None,
        crossing_times=times.tolist(),
        crossing_directions=dirs.tolist(),
        period_values=values,
        period_value_times=[tm for tm, _ in same_dir_values],
        period_std=float(np.std(values, ddof=1)) if len(values) >= 2 else None,
        fit=fit,
    )


def _crossing_regression(
    times: np.ndarray, dirs: np.ndarray, k: np.ndarray
) -> tuple[float, float | None, float | None]:
    """МНК для t = a + b·d + (T/2)·k. Возвращает (T, SE(T), СКО остатков)."""
    design = np.column_stack([np.ones_like(times), dirs / 2, k.astype(float)])
    n, p = design.shape
    if n <= p:
        same = [(times[j + 2] - times[j]) for j in range(n - 2) if k[j + 2] - k[j] == 2]
        if not same:
            raise AnalysisError("Недостаточно переходов для вычисления периода.")
        return float(np.mean(same)), None, None
    coef, *_ = np.linalg.lstsq(design, times, rcond=None)
    resid = times - design @ coef
    sigma = float(math.sqrt(resid @ resid / (n - p)))
    cov = sigma**2 * np.linalg.inv(design.T @ design)
    return float(2 * coef[2]), float(2 * math.sqrt(cov[2, 2])), sigma
