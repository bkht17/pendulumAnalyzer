"""Синтетическое видео маятника с заранее известным периодом.

Нужно для двух вещей: автотестов алгоритма (точность проверяется на эталоне)
и демо-режима, где можно посмотреть весь путь обработки без реальной съёмки.
Движение считается численным решением нелинейного уравнения маятника
θ'' = −(g/L)·sin θ − 2β·θ', поэтому в видео честно присутствует поправка на амплитуду.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy.integrate import solve_ivp


@dataclass(frozen=True)
class SyntheticPendulum:
    length_m: float
    amplitude_deg: float = 6.0
    g: float = 9.81
    damping: float = 0.02
    """β, 1/с — амплитуда убывает как e^(−βt)."""
    fps: float = 60.0
    duration_s: float = 15.0
    width: int = 640
    height: int = 480
    noise: float = 3.0
    """СКО гауссова шума яркости, имитирует шум матрицы."""
    seed: int = 0
    hold_s: float = 0.0
    """Сколько секунд груз держат неподвижно перед запуском (как рукой в реальной записи)."""


def pivot_point(p: SyntheticPendulum) -> tuple[float, float]:
    return p.width / 2, 20.0


def simulate_angle(p: SyntheticPendulum, t: np.ndarray) -> np.ndarray:
    theta = np.full_like(t, math.radians(p.amplitude_deg))
    free = t >= p.hold_s
    if free.any():
        theta[free] = _free_swing(p, t[free] - p.hold_s)
    return theta


def _free_swing(p: SyntheticPendulum, t: np.ndarray) -> np.ndarray:
    omega2 = p.g / p.length_m

    def rhs(_t: float, state: np.ndarray) -> list[float]:
        theta, w = state
        return [w, -omega2 * math.sin(theta) - 2 * p.damping * w]

    sol = solve_ivp(
        rhs,
        (0.0, max(float(t[-1]), 1e-6)),
        [math.radians(p.amplitude_deg), 0.0],
        t_eval=t,
        rtol=1e-10,
        atol=1e-12,
        method="DOP853",
    )
    return sol.y[0]


def render_video(p: SyntheticPendulum, path: Path) -> np.ndarray:
    """Пишет видео в path (mp4) и возвращает истинные координаты центра груза (N×2)."""
    n_frames = round(p.duration_s * p.fps)
    t = np.arange(n_frames) / p.fps
    theta = simulate_angle(p, t)

    pivot = pivot_point(p)
    length_px = (p.height - 70) * min(1.0, 0.25 + p.length_m * 0.75)
    bob_radius = 12
    shift = 4  # субпиксельная отрисовка: координаты умножаются на 2^shift
    scale = 1 << shift

    background = np.empty((p.height, p.width, 3), np.uint8)
    gradient = np.linspace(205, 235, p.height, dtype=np.float32)[:, None]
    background[:] = gradient[..., None].astype(np.uint8)

    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*"mp4v"), p.fps, (p.width, p.height))
    if not writer.isOpened():
        raise RuntimeError("OpenCV не смог создать видеофайл.")
    rng = np.random.default_rng(p.seed)
    # Генерировать шум на каждый кадр дорого; набора из 16 кадров шума достаточно.
    noise_bank = (
        [rng.normal(0, p.noise, background.shape).astype(np.int16) for _ in range(16)]
        if p.noise > 0
        else []
    )
    positions = np.empty((n_frames, 2))
    try:
        for i, th in enumerate(theta):
            x = pivot[0] + length_px * math.sin(th)
            y = pivot[1] + length_px * math.cos(th)
            positions[i] = (x, y)
            frame = background.copy()
            cv2.line(
                frame,
                (int(pivot[0] * scale), int(pivot[1] * scale)),
                (int(x * scale), int(y * scale)),
                (60, 60, 60),
                1,
                cv2.LINE_AA,
                shift,
            )
            cv2.circle(
                frame,
                (int(x * scale), int(y * scale)),
                bob_radius * scale,
                (40, 200, 40),
                -1,
                cv2.LINE_AA,
                shift,
            )
            cv2.rectangle(
                frame, (int(pivot[0]) - 30, 8), (int(pivot[0]) + 30, 20), (90, 90, 90), -1
            )
            if noise_bank:
                noisy = frame.astype(np.int16) + noise_bank[rng.integers(len(noise_bank))]
                frame = np.clip(noisy, 0, 255).astype(np.uint8)
            writer.write(frame)
    finally:
        writer.release()
    return positions
