from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import AppSettings, DbSession, Queue, remove_video_files
from app.api.serializers import experiment_detail, experiment_out, series_out
from app.models import Experiment, Series, Video, VideoSegment
from app.schemas import (
    AnalysisOut,
    ExperimentDetail,
    ExperimentIn,
    ExperimentOut,
    ExperimentPatch,
    SeriesIn,
    SeriesOut,
)
from app.services.analysis import analyze_experiment
from app.services.demo import create_demo_experiment

router = APIRouter(prefix="/experiments", tags=["experiments"])

_FULL = (
    selectinload(Experiment.series).selectinload(Series.trials),
    selectinload(Experiment.series).selectinload(Series.segments).selectinload(VideoSegment.video),
    selectinload(Experiment.videos).selectinload(Video.segments),
)


def _load(db: DbSession, experiment_id: int) -> Experiment:
    experiment = db.scalars(
        select(Experiment).where(Experiment.id == experiment_id).options(*_FULL)
    ).one_or_none()
    if experiment is None:
        raise HTTPException(status_code=404, detail="Эксперимент не найден")
    return experiment


@router.get("", response_model=list[ExperimentOut])
def list_experiments(db: DbSession) -> list[ExperimentOut]:
    experiments = db.scalars(
        select(Experiment).options(*_FULL).order_by(Experiment.created_at.desc())
    ).all()
    return [experiment_out(e) for e in experiments]


@router.post("", response_model=ExperimentOut, status_code=status.HTTP_201_CREATED)
def create_experiment(payload: ExperimentIn, db: DbSession) -> ExperimentOut:
    experiment = Experiment(**payload.model_dump())
    db.add(experiment)
    db.commit()
    return experiment_out(experiment)


@router.post("/demo", response_model=ExperimentOut, status_code=status.HTTP_201_CREATED)
def create_demo(db: DbSession, queue: Queue) -> ExperimentOut:
    experiment, pending = create_demo_experiment(db)
    for video_id, spec in pending:
        queue.submit_synthetic(video_id, spec)
    return experiment_out(experiment)


@router.get("/{experiment_id}", response_model=ExperimentDetail)
def get_experiment(experiment_id: int, db: DbSession) -> ExperimentDetail:
    return experiment_detail(_load(db, experiment_id))


@router.patch("/{experiment_id}", response_model=ExperimentOut)
def update_experiment(experiment_id: int, payload: ExperimentPatch, db: DbSession) -> ExperimentOut:
    experiment = _load(db, experiment_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(experiment, key, value)
    db.commit()
    return experiment_out(experiment)


@router.delete("/{experiment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_experiment(experiment_id: int, db: DbSession, settings: AppSettings) -> Response:
    experiment = _load(db, experiment_id)
    video_ids = [v.id for v in experiment.videos]
    db.delete(experiment)
    db.commit()
    remove_video_files(settings, video_ids)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{experiment_id}/series", response_model=SeriesOut, status_code=status.HTTP_201_CREATED
)
def create_series(experiment_id: int, payload: SeriesIn, db: DbSession) -> SeriesOut:
    experiment = _load(db, experiment_id)
    series = Series(**payload.model_dump())
    experiment.series.append(series)
    db.commit()
    return series_out(series)


@router.get("/{experiment_id}/analysis", response_model=AnalysisOut)
def get_analysis(experiment_id: int, db: DbSession) -> AnalysisOut:
    return analyze_experiment(_load(db, experiment_id))


def _num(value: float | None, digits: int = 4) -> str:
    """Числа с десятичной запятой: так CSV сразу открывается в русскоязычном Excel."""
    return "" if value is None else f"{value:.{digits}f}".replace(".", ",")


@router.get("/{experiment_id}/export.csv")
def export_csv(experiment_id: int, db: DbSession) -> Response:
    experiment = _load(db, experiment_id)
    analysis = analyze_experiment(experiment)
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        [
            "L, см",
            "σL, см",
            "N колебаний",
            "Замеров секундомером",
            "T секундомер, с",
            "Разброс σ, с",
            "Ст. ошибка, с",
            "Участков видео",
            "T камера (средний), с",
            "Погрешность T камеры, с",
            "T₀ камера (малые колебания), с",
            "Погрешность T₀, с",
            "Разброс камеры (тот же N), с",
            "Разница, с",
            "Отношение разбросов",
            "p (F-тест)",
            "T теория, с",
            "Амплитуда, °",
            "T теория с поправкой, с",
            "Откл. секундомера, %",
            "Откл. камеры, %",
            "g секундомер, м/с²",
            "g камера, м/с²",
        ]
    )
    for row in analysis.series:
        sw, cam, cmp_ = row.stopwatch, row.camera, row.comparison
        writer.writerow(
            [
                _num(row.length_cm, 1),
                _num(row.length_sigma_cm, 2),
                sw.periods if sw else "",
                sw.summary.n if sw else "",
                _num(sw.summary.mean if sw else None),
                _num(sw.summary.std if sw else None),
                _num(sw.summary.sem if sw else None),
                cam.segments if cam else "",
                _num(cam.period.value if cam else None, 5),
                _num(cam.period.sigma if cam else None, 5),
                _num(cam.t0.value if cam and cam.t0 else None, 5),
                _num(cam.t0.sigma if cam and cam.t0 else None, 5),
                _num(cam.equivalent_std if cam else None, 5),
                _num(cmp_.difference if cmp_ else None),
                _num(cmp_.spread_ratio if cmp_ else None, 1),
                _num(cmp_.p_value if cmp_ else None, 4),
                _num(row.theory.t0),
                _num(row.theory.amplitude_deg, 1),
                _num(row.theory.t_corrected),
                _num(row.stopwatch_vs_theory.deviation_pct if row.stopwatch_vs_theory else None, 2),
                _num(row.camera_vs_theory.deviation_pct if row.camera_vs_theory else None, 2),
                _num(row.stopwatch_vs_theory.g.value if row.stopwatch_vs_theory else None, 3),
                _num(row.camera_vs_theory.g.value if row.camera_vs_theory else None, 3),
            ]
        )
    filename = f"experiment_{experiment.id}.csv"
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
