"""Статистика повторных измерений, линейная регрессия, сравнение дисперсий."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats as sps


@dataclass(frozen=True)
class Summary:
    n: int
    mean: float
    std: float | None
    """Выборочное СКО (ddof=1) — «разброс» отдельного измерения."""
    sem: float | None
    """Стандартная ошибка среднего."""
    ci95: float | None
    """Полуширина 95 % доверительного интервала по Стьюденту."""


def summarize(values: Sequence[float]) -> Summary | None:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return None
    if arr.size == 1:
        return Summary(n=1, mean=float(arr[0]), std=None, sem=None, ci95=None)
    std = float(np.std(arr, ddof=1))
    sem = std / math.sqrt(arr.size)
    return Summary(
        n=int(arr.size),
        mean=float(arr.mean()),
        std=std,
        sem=sem,
        ci95=float(sps.t.ppf(0.975, arr.size - 1) * sem),
    )


def robust_outliers(values: Sequence[float], z_limit: float = 4.0) -> list[bool]:
    """Выбросы по медиане и MAD — типичная причина: сбился со счёта колебаний."""
    arr = np.asarray(values, dtype=float)
    if arr.size < 4:
        return [False] * arr.size
    med = np.median(arr)
    mad = np.median(np.abs(arr - med)) * 1.4826
    if mad == 0:
        return [False] * arr.size
    return (np.abs(arr - med) / mad > z_limit).tolist()


@dataclass(frozen=True)
class LinearFit:
    slope: float
    slope_se: float | None
    intercept: float
    intercept_se: float | None
    r2: float | None
    n: int


def linear_fit(
    x: Sequence[float], y: Sequence[float], sigma_y: Sequence[float] | None = None
) -> LinearFit | None:
    """Взвешенный МНК y = k·x + b.

    Ошибки параметров берутся из ковариационной матрицы, масштабированной на χ²/ν
    (как curve_fit с absolute_sigma=False): так оценка честная, даже если заявленные
    погрешности занижены.
    """
    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)
    n = xa.size
    if n < 2 or np.ptp(xa) == 0:
        return None
    if sigma_y is not None:
        s = np.asarray(sigma_y, dtype=float)
        w = np.where(np.isfinite(s) & (s > 0), 1 / np.maximum(s, 1e-12) ** 2, np.nan)
        # Точкам без оценки погрешности (одиночный замер) даём «типичный» вес.
        w = np.where(np.isnan(w), np.nanmedian(w) if np.any(np.isfinite(w)) else 1.0, w)
    else:
        w = np.ones(n)
    design = np.column_stack([xa, np.ones(n)])
    wd = design * np.sqrt(w)[:, None]
    wy = ya * np.sqrt(w)
    coef, *_ = np.linalg.lstsq(wd, wy, rcond=None)
    slope, intercept = float(coef[0]), float(coef[1])
    resid = ya - design @ coef
    ss_res = float(np.sum(w * resid**2))
    ss_tot = float(np.sum(w * (ya - np.average(ya, weights=w)) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    if n == 2:
        return LinearFit(slope, None, intercept, None, r2, n)
    cov = np.linalg.inv(wd.T @ wd) * ss_res / (n - 2)
    return LinearFit(
        slope=slope,
        slope_se=float(math.sqrt(cov[0, 0])),
        intercept=intercept,
        intercept_se=float(math.sqrt(cov[1, 1])),
        r2=r2,
        n=n,
    )


@dataclass(frozen=True)
class VarianceComparison:
    ratio: float
    """σ₁ / σ₂ — во сколько раз разброс первого метода больше."""
    f_statistic: float
    p_value: float
    df1: int
    df2: int


def compare_variances(std1: float, df1: int, std2: float, df2: int) -> VarianceComparison | None:
    """Односторонний F-тест: H₁ — дисперсия первого метода больше второго."""
    if df1 < 1 or df2 < 1 or std2 <= 0:
        return None
    f = (std1 / std2) ** 2
    return VarianceComparison(
        ratio=std1 / std2,
        f_statistic=f,
        p_value=float(sps.f.sf(f, df1, df2)),
        df1=df1,
        df2=df2,
    )
