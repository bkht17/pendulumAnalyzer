"""Формулы математического маятника и распространение погрешностей.

Все функции принимают длину в метрах, время в секундах, углы в радианах.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

G_STANDARD = 9.80665


def period_small_angle(length_m: float, g: float) -> float:
    """T₀ = 2π·√(L/g) — период при бесконечно малой амплитуде."""
    return 2 * math.pi * math.sqrt(length_m / g)


def period_small_angle_sigma(length_m: float, length_sigma_m: float, g: float) -> float:
    """Погрешность теоретического периода, вызванная погрешностью длины: δT = T·δL/(2L)."""
    return period_small_angle(length_m, g) * length_sigma_m / (2 * length_m)


def amplitude_factor(theta0: float) -> float:
    """Поправка на конечную амплитуду: T/T₀ ≈ 1 + θ²/16 + 11θ⁴/3072.

    При 5° поправка 0,05 %, при 15° — уже 0,43 %, что больше точности видеометода.
    """
    return 1 + theta0**2 / 16 + 11 * theta0**4 / 3072


def g_from_period(length_m: float, period_s: float) -> float:
    """g = 4π²L/T²."""
    return 4 * math.pi**2 * length_m / period_s**2


def g_from_period_sigma(
    length_m: float, length_sigma_m: float, period_s: float, period_sigma_s: float
) -> float:
    """δg/g = √((δL/L)² + (2δT/T)²)."""
    g = g_from_period(length_m, period_s)
    return g * math.hypot(length_sigma_m / length_m, 2 * period_sigma_s / period_s)


@dataclass(frozen=True)
class AmplitudeModel:
    """Период, приведённый к малой амплитуде, и проверка поправки θ²/16."""

    t0: float
    """T₀ = среднее T/f(θ) по отдельным периодам — период при бесконечно малой амплитуде."""
    t0_se: float | None
    k: float | None
    """Коэффициент в свободной подгонке T = T₀·(1 + k·θ²); теория даёт 1/16 = 0,0625."""
    k_se: float | None
    theta_min_deg: float
    theta_max_deg: float
    periods: int


def amplitude_model(
    periods: list[float], thetas: list[float], length_rel_error: float = 0.0
) -> AmplitudeModel | None:
    """periods — отдельные периоды, thetas — амплитуда (рад) в середине каждого периода.

    length_rel_error — относительная погрешность длины нити в пикселях, по которой считался
    угол. Она даёт систематическую ошибку поправки: δT₀ ≈ T₀·(θ²/8)·δL/L — добавляется к
    статистической погрешности T₀."""
    t = np.asarray(periods, dtype=float)
    th = np.asarray(thetas, dtype=float)
    ok = np.isfinite(t) & np.isfinite(th)
    t, th = t[ok], th[ok]
    if t.size < 2:
        return None
    corrected = t / np.array([amplitude_factor(v) for v in th])
    t0 = float(corrected.mean())
    t0_se = float(corrected.std(ddof=1) / math.sqrt(t.size)) if t.size > 2 else None
    if t0_se is not None and length_rel_error > 0:
        systematic = t0 * float(np.mean(th**2)) / 8 * length_rel_error
        t0_se = math.hypot(t0_se, systematic)
    k = k_se = None
    if t.size >= 6 and np.ptp(th**2) > 0:
        design = np.column_stack([np.ones_like(th), th**2])
        coef, *_ = np.linalg.lstsq(design, t, rcond=None)
        resid = t - design @ coef
        cov = (resid @ resid / (t.size - 2)) * np.linalg.inv(design.T @ design)
        a, b = coef
        if a > 0:
            k = float(b / a)
            k_se = (
                float(abs(k) * math.hypot(math.sqrt(cov[1, 1]) / b, math.sqrt(cov[0, 0]) / a))
                if b
                else None
            )
    return AmplitudeModel(
        t0=t0,
        t0_se=t0_se,
        k=k,
        k_se=k_se,
        theta_min_deg=float(np.degrees(th.min())),
        theta_max_deg=float(np.degrees(th.max())),
        periods=int(t.size),
    )
