import numpy as np
import pytest

from app.science.periods import AnalysisError, analyze_oscillation, find_crossings


def damped_signal(period=1.7, fps=60.0, duration=18.0, noise=0.4, gamma=0.03, seed=1, jitter=0.0):
    rng = np.random.default_rng(seed)
    t = np.arange(0, duration, 1 / fps)
    if jitter:
        t = np.sort(t + rng.uniform(-jitter, jitter, t.size) / fps)
    x = 320 + 80 * np.exp(-gamma * t) * np.cos(2 * np.pi * t / period + 0.7)
    return t, x + rng.normal(0, noise, t.size)


def test_period_recovered_with_subframe_precision():
    t, x = damped_signal()
    res = analyze_oscillation(t, x)
    assert res.period == pytest.approx(1.7, abs=5e-4)
    assert res.fit is not None and res.fit.period == pytest.approx(1.7, abs=5e-4)
    # Кадр = 16.7 мс, а момент прохождения находится с точностью до долей миллисекунды.
    assert res.event_sigma < 2e-3
    assert res.period_se < 3e-4
    assert res.center == pytest.approx(320, abs=0.5)
    assert len(res.period_values) >= 15


def test_variable_frame_rate_timestamps():
    t, x = damped_signal(fps=30.0, jitter=0.3)
    assert analyze_oscillation(t, x).period == pytest.approx(1.7, abs=1e-3)


def test_lost_frames_are_tolerated():
    t, x = damped_signal()
    x[200:212] = np.nan  # маркер пропал на 12 кадров
    res = analyze_oscillation(t, x)
    assert res.period == pytest.approx(1.7, abs=1e-3)


def test_hysteresis_rejects_jitter_near_center():
    t = np.linspace(0, 1, 101)
    s = np.array([-1.0] * 40 + [0.05, -0.05, 0.05, -0.05] + [1.0] * 57)
    times, dirs = find_crossings(t, s, np.full_like(t, 0.3), max_gap=1.0)
    assert len(times) == 1 and dirs[0] == 1


def test_no_oscillation_raises():
    t = np.linspace(0, 10, 600)
    with pytest.raises(AnalysisError):
        analyze_oscillation(
            t, np.full_like(t, 100.0) + np.random.default_rng(0).normal(0, 0.1, 600)
        )
