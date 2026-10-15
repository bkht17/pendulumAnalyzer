"""Определение периода по зависимости координаты груза от времени.

Почему не по максимумам (как в исходном плане): в крайней точке скорость равна нулю,
вершина кривой плоская и момент экстремума определяется плохо. В положении равновесия
скорость максимальна, поэтому момент прохождения центра фиксируется с точностью до долей
кадра. Алгоритм:

1. Пики каждого полуколебания (с параболическим уточнением) дают центр колебаний c
   (усреднение соседних пиков компенсирует затухание) и огибающую амплитуды A(t).
2. Моменты прохождения c ищутся с гистерезисом (дрожание около центра не даёт ложных
   переходов) и уточняются «фазовой» подгонкой: arcsin((x − c)/A) линейно растёт со
   временем, поэтому прямая проводится по всем кадрам центральной части полуколебания,
   а не по двум соседним.
3. Регрессия моментов t_k = a + b·d_k + (T/2)·k + q·k² (d_k — направление, учитывает
   несимметричность, q — медленный дрейф периода из-за затухания амплитуды). Выбросы
   (сбой трекинга) отбрасываются по медианному отклонению. Остаток — погрешность
   фиксации одного момента.
4. Независимая проверка — подгонка затухающей синусоиды.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import maximum_filter1d
from scipy.optimize import curve_fit

HYSTERESIS_FRACTION = 0.3
MAX_HALF_PERIOD_SPREAD = 0.2
"""Относительный разброс полупериодов, выше которого это уже не колебания, а шум."""
MAX_SKIPPED_FRACTION = 0.3
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
    period_amplitudes: list[float] = field(default_factory=list)
    """Амплитуда (в единицах координаты) в середине каждого отдельного периода."""
    period_std: float | None = None
    outliers: int = 0
    """Сколько моментов отброшено как сбои трекинга."""
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


def _half_cycle_peaks(
    t: np.ndarray, s: np.ndarray, times: np.ndarray, dirs: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Экстремум между соседними переходами, уточнённый параболой по трём точкам."""
    peak_t: list[float] = []
    peak_v: list[float] = []
    for j in range(len(times) - 1):
        sel = np.flatnonzero((t > times[j]) & (t < times[j + 1]) & np.isfinite(s))
        if sel.size < 3:
            continue
        sign = dirs[j]
        m = sel[int(np.argmax(sign * s[sel]))]
        tm, vm = t[m], s[m]
        if 0 < m < len(s) - 1 and np.isfinite(s[m - 1]) and np.isfinite(s[m + 1]):
            a, b, c = s[m - 1], s[m], s[m + 1]
            denom = a - 2 * b + c
            if denom != 0:
                off = 0.5 * (a - c) / denom
                if abs(off) <= 1:
                    tm = t[m] + off * (t[m + 1] - t[m - 1]) / 2
                    vm = b - 0.25 * (a - c) * off
        peak_t.append(float(tm))
        peak_v.append(float(vm))
    return np.asarray(peak_t), np.asarray(peak_v)


def _center_offset(peak_v: np.ndarray) -> float:
    """Центр по тройкам соседних пиков (p₋ + 2p₀ + p₊)/4 — линейное затухание сокращается."""
    if peak_v.size < 3:
        return float((peak_v.max() + peak_v.min()) / 2) if peak_v.size else 0.0
    triples = (peak_v[:-2] + 2 * peak_v[1:-1] + peak_v[2:]) / 4
    return float(np.median(triples))


def _envelope(t: np.ndarray, peak_t: np.ndarray, peak_v: np.ndarray) -> np.ndarray:
    amp = np.abs(peak_v)
    good = amp > 0
    if good.sum() == 0:
        return np.full_like(t, np.nan)
    if good.sum() == 1:
        return np.full_like(t, amp[good][0])
    return np.exp(np.interp(t, peak_t[good], np.log(amp[good])))


def _phase_refine(
    t: np.ndarray,
    s: np.ndarray,
    env: np.ndarray,
    times: np.ndarray,
    dirs: np.ndarray,
    period: float,
) -> np.ndarray:
    """Уточнение каждого момента по центральной части полуколебания (|s| < A·sin 55°).

    Фаза u = arcsin(s/A) линейна во времени; веса cos²u учитывают, что ближе к краям
    arcsin сильнее усиливает шум.
    """
    limit = math.sin(math.radians(55))
    refined = times.copy()
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = s / env
    for j, (tc, d) in enumerate(zip(times, dirs, strict=True)):
        win = (np.abs(t - tc) < period / 4) & np.isfinite(ratio) & (np.abs(ratio) < limit)
        if win.sum() < 3:
            continue
        u = np.arcsin(ratio[win]) * d
        w = np.sqrt(np.cos(u) ** 2)
        dt = t[win] - tc
        design = np.column_stack([np.ones_like(dt), dt]) * w[:, None]
        (a, b), *_ = np.linalg.lstsq(design, u * w, rcond=None)
        if b > 0 and abs(a / b) < period / 8:
            refined[j] = tc - a / b
    return refined


def analyze_oscillation(t: np.ndarray, x: np.ndarray) -> PeriodAnalysis:
    t = np.asarray(t, dtype=float)
    x = np.asarray(x, dtype=float)
    valid = np.isfinite(x)
    if valid.sum() < MIN_POINTS:
        raise AnalysisError(
            f"Груз найден только на {int(valid.sum())} кадрах — нужно хотя бы {MIN_POINTS}."
        )
    frame_dt = float(np.median(np.diff(t)))
    max_gap = 3.5 * frame_dt

    center = float(np.median(x[valid]))
    rough = _rough_crossings(t, x - center, max_gap)
    if len(rough) < 3:
        raise AnalysisError(
            "На записи меньше одного полного колебания — проверьте настройки трекинга и обрезку."
        )
    period_est = 2 * float(np.median(np.diff(rough)))

    # Порог гистерезиса — от локальной амплитуды (скользящий максимум за период): так он
    # годится и в начале длинной серии, и в конце, когда амплитуда сильно затухла.
    window = max(3, round(period_est / frame_dt))
    local_amp = maximum_filter1d(np.where(valid, np.abs(x - center), 0.0), size=window)

    times = dirs = peak_t = peak_v = np.array([])
    for _ in range(3):  # центр уточняется по пикам, затем переходы ищутся заново
        s = x - center
        times, dirs = find_crossings(t, s, HYSTERESIS_FRACTION * local_amp, max_gap)
        if len(times) < 3:
            raise AnalysisError(
                "Не удалось надёжно найти моменты прохождения положения равновесия."
            )
        peak_t, peak_v = _half_cycle_peaks(t, s, times, dirs)
        offset = _center_offset(peak_v)
        center += offset
        if abs(offset) < 0.05:
            break
    s = x - center
    peak_t, peak_v = _half_cycle_peaks(t, s, times, dirs)
    env = _envelope(t, peak_t, peak_v)
    period_est = 2 * float(np.median(np.diff(times)))
    times = _phase_refine(t, s, env, times, dirs, period_est)

    # Номер полупериода — по разностям соседних переходов: устойчиво к пропущенным
    # переходам (потеря груза), к дрейфу периода и к неравным полупериодам (центр чуть
    # смещён), чего не даёт округление от первого перехода.
    steps = np.maximum(np.rint(np.diff(times) / (period_est / 2)), 1).astype(int)
    k = np.concatenate([[0], np.cumsum(steps)])
    halves = np.diff(times) / steps
    irregular = np.std(halves) / np.mean(halves) > MAX_HALF_PERIOD_SPREAD
    if irregular or np.mean(steps > 1) > MAX_SKIPPED_FRACTION:
        raise AnalysisError("Переходы через равновесие идут нерегулярно — проверьте трекинг.")

    keep = _reject_outliers(times, dirs, k)
    times, dirs, k = times[keep], dirs[keep], k[keep]
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
    value_times = np.array([tm for tm, _ in same_dir_values])

    amps = np.abs(peak_v)
    damping = None
    if amps.size >= 3 and np.all(amps > 0):
        damping = float(-np.polyfit(peak_t, np.log(amps), 1)[0])
    crossing_env = np.interp(times, t[np.isfinite(env)], env[np.isfinite(env)])

    return PeriodAnalysis(
        period=period,
        period_se=period_se,
        event_sigma=event_sigma,
        center=center,
        amplitude_start=float(crossing_env[0]),
        amplitude_mean=float(np.mean(crossing_env)),
        damping=damping,
        crossing_times=times.tolist(),
        crossing_directions=dirs.tolist(),
        period_values=values,
        period_value_times=value_times.tolist(),
        period_amplitudes=(
            np.interp(value_times, times, crossing_env).tolist() if value_times.size else []
        ),
        period_std=float(np.std(values, ddof=1)) if len(values) >= 2 else None,
        outliers=int((~keep).sum()),
        fit=fit_damped_cosine(t, x, period_est, center),
    )


def _design(dirs: np.ndarray, k: np.ndarray, quadratic: bool) -> np.ndarray:
    cols = [np.ones(len(k)), dirs / 2, k.astype(float)]
    if quadratic:
        kc = k - k.mean()
        cols.append(kc.astype(float) ** 2)
    return np.column_stack(cols)


def _reject_outliers(times: np.ndarray, dirs: np.ndarray, k: np.ndarray) -> np.ndarray:
    """Сбой трекинга даёт момент, далеко выпадающий из регрессии. Отбрасываем такие
    точки по медианному отклонению (не больше 10 % переходов)."""
    keep = np.ones(len(times), dtype=bool)
    if len(times) < 10:
        return keep
    budget = max(1, len(times) // 10)
    for _ in range(budget):
        design = _design(dirs[keep], k[keep], quadratic=True)
        coef, *_ = np.linalg.lstsq(design, times[keep], rcond=None)
        resid = np.full(len(times), 0.0)
        resid[keep] = times[keep] - design @ coef
        mad = 1.4826 * float(np.median(np.abs(resid[keep])))
        worst = int(np.argmax(np.abs(resid) * keep))
        if mad <= 0 or abs(resid[worst]) <= 5 * mad:
            break
        keep[worst] = False
    return keep


def _crossing_regression(
    times: np.ndarray, dirs: np.ndarray, k: np.ndarray
) -> tuple[float, float | None, float | None]:
    """Средний период по регрессии моментов и погрешность одного момента.

    Модель с квадратичным членом поглощает медленный дрейф периода (он реален: период
    уменьшается вместе с амплитудой), поэтому остаток — это именно погрешность измерения.
    Средний период на участке — производная dt/dk в середине, умноженная на 2.
    """
    n = len(times)
    quadratic = n >= 8
    design = _design(dirs, k, quadratic)
    p = design.shape[1]
    if n <= p:
        same = [(times[j + 2] - times[j]) for j in range(n - 2) if k[j + 2] - k[j] == 2]
        if not same:
            raise AnalysisError("Недостаточно переходов для вычисления периода.")
        return float(np.mean(same)), None, None
    coef, *_ = np.linalg.lstsq(design, times, rcond=None)
    resid = times - design @ coef
    sigma = float(math.sqrt(resid @ resid / (n - p)))
    cov = sigma**2 * np.linalg.inv(design.T @ design)
    # Квадратичный член центрирован, поэтому в середине участка наклон равен coef[2].
    return float(2 * coef[2]), float(2 * math.sqrt(cov[2, 2])), sigma
