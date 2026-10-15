import pytest

from app.models import VideoSegment
from app.services.segments import acceptable, match_series


def segment(result):
    return VideoSegment(t_start=0, t_end=10, result=result)


def test_quality_gate_rejects_hand_fidgeting():
    assert acceptable(segment({"period": 0.76, "event_sigma": 0.0015}))  # нормальная серия
    assert not acceptable(segment({"period": 0.76, "event_sigma": 0.017}))  # возня рук
    assert not acceptable(segment(None))  # анализ не удался
    assert acceptable(segment({"period": 1.0, "event_sigma": None}))  # мало переходов для σ


# T₀ участков из реальной записи IMG_9685 и длины, измеренные линейкой.
REAL_T0 = {"A1": 1.58402, "A2": 1.58465, "B": 1.31493, "C1": 0.96687, "C2": 0.96556, "D": 0.74408}
LENGTHS = {1: 60.0, 2: 40.0, 3: 20.0}


@pytest.mark.parametrize(
    ("run", "expected"),
    [("A1", 1), ("A2", 1), ("B", 2), ("C1", 3), ("C2", 3), ("D", None)],
)
def test_runs_match_measured_lengths_by_period(run, expected):
    # Эффективная длина на 2–3 см больше измеренной (центр шарика ниже точки замера),
    # но длины всё равно узнаются; серия D (≈ 14 см) ни к одной не подходит.
    seg = segment({"period": REAL_T0[run] * 1.01, "t0": REAL_T0[run]})
    assert match_series(seg, LENGTHS, 9.81) == expected


def test_ambiguous_lengths_are_left_to_the_user():
    seg = segment({"period": 0.97, "t0": 0.967})  # ≈ 23 см: между 22 и 24 см
    assert match_series(seg, {1: 22.0, 2: 24.0}, 9.81) is None
    assert match_series(seg, {}, 9.81) is None


def test_retracking_does_not_duplicate_manual_segments(monkeypatch):
    from app.models import Experiment, Video
    from app.science.segments import Segment
    from app.services import segments as service

    def fake_analyze(segment, video, track, lengths):
        segment.result = {"period": 1.0, "event_sigma": 0.001}

    monkeypatch.setattr(service, "analyze_into", fake_analyze)

    video = Video(params=None, track_info=None)
    video.experiment = Experiment(name="x")
    video.segments = [VideoSegment(t_start=10.0, t_end=30.0, auto=False, series_id=None)]
    found = [Segment(10.5, 29.0, 30, 1.0), Segment(40.0, 60.0, 30, 1.0)]
    service.replace_auto_segments(video, found, track=(None, None, None))
    spans = sorted((s.t_start, s.auto) for s in video.segments)
    assert spans == [(10.0, False), (40.0, True)]
