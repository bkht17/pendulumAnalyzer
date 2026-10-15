from __future__ import annotations

from app.models import Experiment, Series, StopwatchTrial, Video, VideoSegment
from app.schemas import (
    ExperimentDetail,
    ExperimentOut,
    SegmentOut,
    SeriesOut,
    TrialOut,
    VideoOut,
)
from app.services.analysis import trial_outlier_flags


def trial_out(trial: StopwatchTrial, outlier: bool = False) -> TrialOut:
    out = TrialOut.model_validate(trial)
    out.suspected_outlier = outlier
    return out


def segment_out(segment: VideoSegment) -> SegmentOut:
    out = SegmentOut.model_validate(segment)
    out.video_name = segment.video.original_name
    return out


def video_out(video: Video) -> VideoOut:
    out = VideoOut.model_validate(video)
    out.segments = [segment_out(s) for s in video.segments]
    return out


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
        segments=[segment_out(s) for s in series.segments],
    )


def experiment_out(experiment: Experiment) -> ExperimentOut:
    out = ExperimentOut.model_validate(experiment)
    out.series_count = len(experiment.series)
    out.trials_count = sum(len(s.trials) for s in experiment.series)
    out.videos_count = len(experiment.videos)
    return out


def experiment_detail(experiment: Experiment) -> ExperimentDetail:
    base = experiment_out(experiment)
    return ExperimentDetail(
        **base.model_dump(),
        series=[series_out(s) for s in experiment.series],
        videos=[video_out(v) for v in experiment.videos],
    )
