from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import AppSettings, DbSession, get_or_404
from app.api.serializers import series_out, trial_out
from app.models import Series, StopwatchTrial
from app.schemas import SeriesOut, SeriesPatch, TrialIn, TrialOut, TrialPatch
from app.services.segments import analyze_into, load_track, series_lengths

router = APIRouter(tags=["series"])


@router.get("/series/{series_id}", response_model=SeriesOut)
def get_series(series_id: int, db: DbSession) -> SeriesOut:
    return series_out(get_or_404(db, Series, series_id, "Серия"))


@router.patch("/series/{series_id}", response_model=SeriesOut)
def update_series(
    series_id: int, payload: SeriesPatch, db: DbSession, settings: AppSettings
) -> SeriesOut:
    series = get_or_404(db, Series, series_id, "Серия")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(series, key, value)
    if "length_cm" in changes:
        # Длина участвует в пересчёте угла амплитуды (если подвес известен только по
        # масштабу) — пересчитываем привязанные участки по сохранённым траекториям.
        db.flush()
        for segment in series.segments:
            track = load_track(settings.videos_dir, segment.video)
            if track is not None:
                analyze_into(segment, segment.video, track, series_lengths(segment.video))
    db.commit()
    return series_out(series)


@router.delete("/series/{series_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_series(series_id: int, db: DbSession) -> Response:
    """Видео остаются в эксперименте: их участки просто отвязываются от этой длины."""
    db.delete(get_or_404(db, Series, series_id, "Серия"))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/series/{series_id}/trials", response_model=TrialOut, status_code=status.HTTP_201_CREATED
)
def create_trial(series_id: int, payload: TrialIn, db: DbSession) -> TrialOut:
    series = get_or_404(db, Series, series_id, "Серия")
    trial = StopwatchTrial(**payload.model_dump())
    series.trials.append(trial)
    db.commit()
    return trial_out(trial)


@router.patch("/trials/{trial_id}", response_model=TrialOut)
def update_trial(trial_id: int, payload: TrialPatch, db: DbSession) -> TrialOut:
    trial = get_or_404(db, StopwatchTrial, trial_id, "Замер")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(trial, key, value)
    db.commit()
    return trial_out(trial)


@router.delete("/trials/{trial_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trial(trial_id: int, db: DbSession) -> Response:
    db.delete(get_or_404(db, StopwatchTrial, trial_id, "Замер"))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
