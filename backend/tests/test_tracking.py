import math

import numpy as np
import pytest

from app.science import physics
from app.science.periods import analyze_oscillation
from app.science.pipeline import track_with_segments
from app.science.synthetic import SyntheticPendulum, pivot_point, render_video
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


def expected_period(spec: SyntheticPendulum) -> float:
    theta_mean = math.radians(spec.amplitude_deg) * 0.9  # амплитуда убывает за запись
    return physics.period_small_angle(spec.length_m, spec.g) * physics.amplitude_factor(theta_mean)


def test_probe(video):
    path, spec, _ = video
    info = probe(path)
    assert (info.width, info.height) == (spec.width, spec.height)
    assert info.fps_nominal == pytest.approx(60)


def test_color_method_matches_ground_truth(video):
    path, spec, truth = video
    frame, _ = read_frame_at(path, 0.0)
    x0, y0 = truth[0]
    color = suggest_color_range(frame, int(x0), int(y0))
    assert isinstance(color, ColorRange)

    result = track_video(path, TrackingParams(method="color", color=color))
    assert result.detection_rate == 1.0
    assert not result.timing.variable_frame_rate
    assert np.nanmax(np.abs(result.x - truth[: result.x.size, 0])) < 0.5  # пикселя
    assert analyze_oscillation(result.t, result.x).period == pytest.approx(
        expected_period(spec), rel=3e-4
    )


def test_motion_method_needs_no_marker(video):
    path, spec, truth = video
    result = track_video(path, TrackingParams(method="motion", min_area=30))
    assert result.detection_rate == 1.0
    assert np.nanmax(np.abs(result.x - truth[: result.x.size, 0])) < 1.0
    assert analyze_oscillation(result.t, result.x).period == pytest.approx(
        expected_period(spec), rel=3e-4
    )


def test_ball_held_before_release_is_not_burned_into_background(tmp_path):
    """Регрессия: если груз держат неподвижно перед запуском, он попадает в медианный фон
    и в крайней точке теряется. Второй проход строит фон только по серии колебаний."""
    spec = SyntheticPendulum(length_m=0.4, amplitude_deg=15, duration_s=24, hold_s=9)
    truth = render_video(spec, tmp_path / "held.mp4")
    track, segments, axis = track_with_segments(
        tmp_path / "held.mp4", TrackingParams(method="motion", min_area=30)
    )
    assert axis == "x" and len(segments) == 1
    seg = segments[0]
    assert seg.t_start == pytest.approx(spec.hold_s, abs=0.6)

    swinging = (track.t > seg.t_start) & (track.t < seg.t_end)
    error = np.abs(track.x[swinging] - truth[: track.t.size, 0][swinging])
    assert np.nanmax(error) < 1.0  # в т.ч. в крайних точках, где груз держали

    res = analyze_oscillation(track.t[swinging], track.x[swinging])
    assert res.event_sigma < 1e-3
    pivot = pivot_point(spec)
    assert pivot[0] == pytest.approx(320)
