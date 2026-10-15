"""Демо-эксперимент: синтетические видео и правдоподобные ручные замеры.

Позволяет пройти весь путь обработки до реальной съёмки и проверить, что программа
находит заранее известный период. Ручные замеры моделируются так: каждое нажатие
кнопки секундомера ошибается на случайную величину с СКО ≈ 45 мс (типичная оценка
для человека, который видит приближение груза и предугадывает момент).
"""

from __future__ import annotations

import math

import numpy as np
from sqlalchemy.orm import Session

from app.models import Experiment, Series, StopwatchTrial, Video, VideoStatus
from app.schemas import Point, TrackingParamsIn
from app.science import physics
from app.science.synthetic import SyntheticPendulum, pivot_point

DEMO_LENGTHS_CM = (20, 25, 40, 60, 80, 100)
DEMO_AMPLITUDE_DEG = 6.0
DEMO_G = 9.81
HUMAN_EVENT_SIGMA = 0.045
LENGTH_OFFSET_CM = 0.8
"""Длина «измерена» до верха груза, а не до центра масс — демо покажет это на графике T²(L)."""


def demo_spec(length_cm: float, seed: int) -> SyntheticPendulum:
    return SyntheticPendulum(
        length_m=length_cm / 100,
        amplitude_deg=DEMO_AMPLITUDE_DEG,
        g=DEMO_G,
        duration_s=15.0,
        seed=seed,
    )


def create_demo_experiment(
    session: Session,
) -> tuple[Experiment, list[tuple[int, SyntheticPendulum]]]:
    """Создаёт эксперимент и записи видео; сами видео рендерятся в фоне (см. TrackingQueue)."""
    rng = np.random.default_rng(2026)
    experiment = Experiment(
        name="Демо: синтетический маятник",
        g_reference=DEMO_G,
        main_periods=10,
        notes=(
            "Видео сгенерированы программой по уравнению маятника, ручные замеры смоделированы "
            "с ошибкой нажатия ≈ 45 мс. Истинная длина на 0,8 см больше записанной."
        ),
        is_demo=True,
    )
    session.add(experiment)
    pending: list[tuple[Video, SyntheticPendulum]] = []
    for index, length_cm in enumerate(DEMO_LENGTHS_CM):
        series = Series(length_cm=length_cm, length_sigma_cm=0.3, amplitude_deg=DEMO_AMPLITUDE_DEG)
        experiment.series.append(series)

        true_length = (length_cm + LENGTH_OFFSET_CM) / 100
        theta_mean = math.radians(DEMO_AMPLITUDE_DEG) * 0.93
        true_period = physics.period_small_angle(true_length, DEMO_G) * physics.amplitude_factor(
            theta_mean
        )
        n_values = [10] * 10
        if length_cm == 60:  # отдельная серия для графика «ошибка против N»
            n_values += [1] * 8 + [5] * 8 + [20] * 8
        for j, n in enumerate(n_values):
            measured = n * true_period + rng.normal(0, HUMAN_EVENT_SIGMA, 2) @ [1, -1]
            if length_cm == 40 and j == 6:
                measured += true_period  # сбился со счёта: насчитал 10, а было 11
            series.trials.append(
                StopwatchTrial(periods=n, total_time_s=round(float(measured), 2), operator="Демо")
            )

        spec = demo_spec(length_cm + LENGTH_OFFSET_CM, seed=index)
        video = Video(
            original_name=f"demo_L{length_cm:03d}.mp4",
            stored_name="original.mp4",
            size_bytes=0,
            width=spec.width,
            height=spec.height,
            fps_nominal=spec.fps,
            frame_count=round(spec.duration_s * spec.fps),
            duration_s=spec.duration_s,
            status=VideoStatus.QUEUED,
            params=TrackingParamsIn(
                method="motion",
                t_start=0.5,
                pivot=Point(x=pivot_point(spec)[0], y=pivot_point(spec)[1]),
            ).model_dump(),
        )
        session.flush()  # нужен id серии для привязки видео
        video.preferred_series_id = series.id
        experiment.videos.append(video)
        pending.append((video, spec))
    session.commit()
    return experiment, [(video.id, spec) for video, spec in pending]
