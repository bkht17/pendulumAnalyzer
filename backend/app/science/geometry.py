"""Геометрия маятника по траектории груза.

Груз движется по дуге окружности с центром в точке подвеса. Подгонка окружности к
точкам (x, y) даёт точку подвеса и длину нити в пикселях без клика пользователя, а
вместе с масштабом (линейка в кадре) — длину в сантиметрах. Отсюда угол амплитуды:
θ = arcsin(A / L), где A — горизонтальная амплитуда.

При малой амплитуде дуга почти прямая и радиус определяется плохо, поэтому результат
сопровождается оценкой погрешности; при большой погрешности им лучше не пользоваться.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

MIN_ARC_DEG = 6.0
MAX_RELATIVE_RADIUS_ERROR = 0.10


@dataclass(frozen=True)
class CircleFit:
    cx: float
    cy: float
    radius: float
    radius_se: float
    rms: float
    arc_deg: float

    @property
    def reliable(self) -> bool:
        return (
            self.arc_deg >= MIN_ARC_DEG
            and self.radius_se / self.radius <= MAX_RELATIVE_RADIUS_ERROR
        )


def fit_circle(x: np.ndarray, y: np.ndarray) -> CircleFit | None:
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = np.asarray(x, float)[ok], np.asarray(y, float)[ok]
    if x.size < 10 or np.ptp(x) < 5:
        return None
    # Грубые сбои трекинга (груз «прыгнул» на руку или мебель) портят даже начальное
    # приближение — отсекаем их по медианному отклонению каждой координаты.
    rough = np.ones(x.size, dtype=bool)
    for v in (x, y):
        mad = 1.4826 * float(np.median(np.abs(v - np.median(v))))
        rough &= np.abs(v - np.median(v)) <= 6 * mad + 5
    if rough.sum() >= 10:
        x, y = x[rough], y[rough]
    # Алгебраическое начальное приближение (Kåsa), затем геометрическая подгонка.
    design = np.column_stack([x, y, np.ones_like(x)])
    rhs = x**2 + y**2
    (a, b, c), *_ = np.linalg.lstsq(design, rhs, rcond=None)
    cx0, cy0 = a / 2, b / 2
    r0 = math.sqrt(max(c + cx0**2 + cy0**2, 1e-9))

    def solve(xs: np.ndarray, ys: np.ndarray, start: list[float]):
        def residuals(p: np.ndarray) -> np.ndarray:
            return np.hypot(xs - p[0], ys - p[1]) - p[2]

        sol = least_squares(residuals, start, loss="soft_l1", f_scale=2.0)
        return sol, residuals(sol.x)

    sol, resid = solve(x, y, [cx0, cy0, r0])
    # Сбои трекинга (рука, чужое пятно) — далёкие выбросы: убираем и подгоняем заново,
    # иначе они раздувают оценку погрешности радиуса.
    mad = 1.4826 * float(np.median(np.abs(resid)))
    inliers = np.abs(resid) <= max(5 * mad, 1.0)
    if inliers.sum() >= 10 and not inliers.all():
        x, y = x[inliers], y[inliers]
        sol, resid = solve(x, y, list(sol.x))
    cx, cy, r = sol.x
    if r <= 0 or cy >= np.median(y):  # точка подвеса должна быть выше груза
        return None
    dof = max(x.size - 3, 1)
    rms = float(math.sqrt(resid @ resid / dof))
    try:
        cov = np.linalg.inv(sol.jac.T @ sol.jac) * rms**2
        radius_se = float(math.sqrt(cov[2, 2]))
    except np.linalg.LinAlgError:
        radius_se = math.inf
    angles = np.degrees(np.arctan2(x - cx, y - cy))
    return CircleFit(
        cx=float(cx),
        cy=float(cy),
        radius=float(r),
        radius_se=radius_se,
        rms=rms,
        arc_deg=float(np.percentile(angles, 98) - np.percentile(angles, 2)),
    )
