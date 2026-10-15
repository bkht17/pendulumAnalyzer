"""Формулы математического маятника и распространение погрешностей.

Все функции принимают длину в метрах, время в секундах, углы в радианах.
"""

from __future__ import annotations

import math

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
