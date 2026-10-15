from __future__ import annotations

from app.models import Experiment, Series, StopwatchTrial, Video
from app.schemas import ExperimentDetail, ExperimentOut, SeriesOut, TrialOut, VideoOut
from app.services.analysis import trial_outlier_flags


def trial_out(trial: StopwatchTrial, outlier: bool = False) -> TrialOut:
    out = TrialOut.model_validate(trial)
    out.suspected_outlier = outlier
    return out


def video_out(video: Video) -> VideoOut:
    return VideoOut.model_validate(video)


def series_out(series: Series) -> SeriesOut:
    flags = trial_outlier_flags(series.trials)
    return SeriesOut(
        id=series.id,
        experiment_id=series.experiment_id,
        length_cm=series.length_cm,
        length_sigma_cm=series.length_sigma_cm,
        amplitude_deg=series.amplitude_deg,
        notes=series.notes,
        created_at=series.created_at,
        trials=[trial_out(t, flags.get(t.id, False)) for t in series.trials],
        videos=[video_out(v) for v in series.videos],
    )


def experiment_out(experiment: Experiment) -> ExperimentOut:
    out = ExperimentOut.model_validate(experiment)
    out.series_count = len(experiment.series)
    out.trials_count = sum(len(s.trials) for s in experiment.series)
    out.videos_count = sum(len(s.videos) for s in experiment.series)
    return out


def experiment_detail(experiment: Experiment) -> ExperimentDetail:
    base = experiment_out(experiment)
    return ExperimentDetail(**base.model_dump(), series=[series_out(s) for s in experiment.series])
