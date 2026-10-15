import math

import numpy as np
import pytest

from app.science.segments import find_segments


def swing(t, start, period, amp, center=500.0, gamma=0.02):
    tau = t - start
    return center + amp * np.exp(-gamma * tau) * np.cos(2 * np.pi * tau / period)


def test_finds_two_runs_separated_by_hands():
    fps = 30
    t = np.arange(0, 70, 1 / fps)
    x = np.full_like(t, np.nan)
    rng = np.random.default_rng(0)
    first = (t >= 2) & (t < 25)
    x[first] = swing(t[first], 2, 1.6, 200)
    # руки перевязывают нить: груз то пропадает, то дёргается
    hands = (t >= 25) & (t < 38)
    x[hands] = 300 + rng.normal(0, 60, hands.sum())
    x[(t >= 30) & (t < 33)] = np.nan
    held = (t >= 38) & (t < 42)
    x[held] = 650 + rng.normal(0, 1.5, held.sum())  # держат у края перед запуском
    second = t >= 42
    x[second] = swing(t[second], 42, 0.98, 150)
    x += rng.normal(0, 0.8, t.size)

    segments = find_segments(t, x)
    assert len(segments) == 2
    a, b = segments
    assert a.period_estimate == pytest.approx(1.6, rel=0.01)
    assert b.period_estimate == pytest.approx(0.98, rel=0.01)
    assert a.t_start == pytest.approx(2, abs=0.6) and a.t_end == pytest.approx(25, abs=1.0)
    assert b.t_start == pytest.approx(42, abs=0.6)


def test_push_by_hand_splits_run():
    t = np.arange(0, 40, 1 / 30)
    x = swing(t, 0, 1.2, 120)
    after = t >= 20
    x[after] = swing(t[after], 20, 1.2, 220)  # толчок: амплитуда резко выросла
    segments = find_segments(t, x)
    assert len(segments) == 2
    assert segments[0].t_end <= 20.6 and segments[1].t_start >= 19.4


def test_no_oscillation_gives_no_segments():
    t = np.arange(0, 20, 1 / 30)
    x = 400 + np.random.default_rng(1).normal(0, 1, t.size)
    assert find_segments(t, x) == []


def test_short_wiggle_is_ignored():
    t = np.arange(0, 20, 1 / 30)
    x = np.full_like(t, 400.0)
    m = (t > 5) & (t < 7)  # меньше двух колебаний
    x[m] = swing(t[m], 5, 1.0, 50, center=400)
    assert find_segments(t, x) == []


def test_period_estimate_unaffected_by_center_drift():
    t = np.arange(0, 30, 1 / 60)
    x = swing(t, 0, 1.3, 100) + 3 * t  # медленный дрейф камеры
    (seg,) = find_segments(t, x)
    assert seg.period_estimate == pytest.approx(1.3, rel=0.01)
    assert math.isfinite(seg.t_end)
