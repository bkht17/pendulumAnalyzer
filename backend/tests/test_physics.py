import math

import pytest
from scipy.special import ellipk

from app.science import physics


def test_period_one_metre():
    assert physics.period_small_angle(1.0, 9.81) == pytest.approx(2.006, abs=1e-3)


def test_quadrupled_length_doubles_period():
    t1 = physics.period_small_angle(0.2, 9.81)
    t4 = physics.period_small_angle(0.8, 9.81)
    assert t4 / t1 == pytest.approx(2.0)


@pytest.mark.parametrize("deg", [2, 5, 10, 15, 20])
def test_amplitude_factor_matches_exact_elliptic_solution(deg):
    theta = math.radians(deg)
    exact = 2 / math.pi * ellipk(math.sin(theta / 2) ** 2)
    assert physics.amplitude_factor(theta) == pytest.approx(exact, abs=1e-6)


def test_g_roundtrip_and_sigma():
    period = physics.period_small_angle(0.6, 9.81)
    assert physics.g_from_period(0.6, period) == pytest.approx(9.81)
    # δT/T = 0.1 % → вклад 0.2 % в g; δL/L = 0.5 % → итого √(0.5² + 0.2²) ≈ 0.539 %
    sigma = physics.g_from_period_sigma(0.6, 0.003, period, period * 1e-3)
    assert sigma / 9.81 == pytest.approx(math.hypot(0.005, 0.002), rel=1e-6)
