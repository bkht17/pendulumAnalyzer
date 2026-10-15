from app.models import VideoSegment
from app.services.segments import acceptable


def segment(result):
    return VideoSegment(t_start=0, t_end=10, result=result)


def test_quality_gate_rejects_hand_fidgeting():
    assert acceptable(segment({"period": 0.76, "event_sigma": 0.0015}))  # нормальная серия
    assert not acceptable(segment({"period": 0.76, "event_sigma": 0.017}))  # возня рук
    assert not acceptable(segment(None))  # анализ не удался
    assert acceptable(segment({"period": 1.0, "event_sigma": None}))  # мало переходов для σ
