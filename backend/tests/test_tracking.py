import math

import numpy as np
import pytest

from app.science import physics
from app.science.periods import analyze_oscillation
from app.science.synthetic import SyntheticPendulum, render_video
from app.science.tracking import (
    ColorRange,
    TrackingParams,
    probe,
    read_frame_at,
    suggest_color_range,
    track_video,
)


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    path = tmp_path_factory.mktemp("video") / "pendulum.mp4"
    spec = SyntheticPendulum(length_m=0.5, amplitude_deg=6, duration_s=12)
    truth = render_video(spec, path)
    return path, spec, truth


def test_probe(video):
    path, spec, _ = video
    info = probe(path)
    assert (info.width, info.height) == (spec.width, spec.height)
    assert info.fps_nominal == pytest.approx(60)


def test_color_suggestion_and_tracking_match_ground_truth(video):
    path, spec, truth = video
    frame, _ = read_frame_at(path, 0.0)
    x0, y0 = truth[0]
    color = suggest_color_range(frame, int(x0), int(y0))
    assert isinstance(color, ColorRange)

    result = track_video(path, TrackingParams(color=color))
    assert result.detection_rate == 1.0
    assert not result.timing.variable_frame_rate
    assert np.nanmax(np.abs(result.x - truth[: result.x.size, 0])) < 0.5  # пикселя

    analysis = analyze_oscillation(result.t, result.x)
    theta_mean = math.radians(spec.amplitude_deg) * 0.9  # амплитуда убывает за запись
    expected = physics.period_small_angle(spec.length_m, spec.g) * physics.amplitude_factor(
        theta_mean
    )
    assert analysis.period == pytest.approx(expected, rel=3e-4)
