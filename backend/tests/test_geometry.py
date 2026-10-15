import math

import numpy as np
import pytest

from app.science.geometry import fit_circle


def arc(radius, amp_deg, pivot=(540.0, 300.0), n=600, noise=0.8, seed=0):
    rng = np.random.default_rng(seed)
    theta = np.radians(amp_deg) * np.cos(np.linspace(0, 12 * np.pi, n))
    x = pivot[0] + radius * np.sin(theta) + rng.normal(0, noise, n)
    y = pivot[1] + radius * np.cos(theta) + rng.normal(0, noise, n)
    return x, y


def test_recovers_pivot_and_length_from_swing_arc():
    x, y = arc(800, 20)
    fit = fit_circle(x, y)
    assert fit is not None and fit.reliable
    assert fit.radius == pytest.approx(800, rel=0.01)
    assert (fit.cx, fit.cy) == pytest.approx((540, 300), abs=10)
    assert fit.arc_deg == pytest.approx(40, abs=2)


def test_small_arc_is_flagged_unreliable():
    x, y = arc(800, 1.5, noise=1.5)
    fit = fit_circle(x, y)
    assert fit is None or not fit.reliable


def test_robust_to_tracking_glitches():
    x, y = arc(400, 25)
    x[::50] += 60  # редкие сбои трекинга
    fit = fit_circle(x, y)
    assert fit is not None
    assert fit.radius == pytest.approx(400, rel=0.02)
    assert math.isfinite(fit.radius_se)
