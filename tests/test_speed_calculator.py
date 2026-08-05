"""Тесты для SpeedCalculator (EMA скорости)."""

import pytest
from speed_calculator import SpeedCalculator


def test_initial_state():
    calc = SpeedCalculator()
    assert calc.get_speed() == 0.0
    assert calc.ema_speed == 0.0
    assert calc.is_initialized is False


def test_first_update_sets_ema():
    calc = SpeedCalculator(alpha=0.2)
    result = calc.update(100.0)
    assert result == 100.0
    assert calc.get_speed() == 100.0
    assert calc.is_initialized is True


def test_ema_smoothing():
    calc = SpeedCalculator(alpha=0.2)
    calc.update(100.0)
    result = calc.update(200.0)
    # EMA_new = 0.2 * 200 + 0.8 * 100 = 40 + 80 = 120
    assert result == 120.0
    assert calc.get_speed() == 120.0


def test_zero_speed_does_not_update_ema():
    calc = SpeedCalculator(alpha=0.2)
    calc.update(50.0)
    result = calc.update(0.0)
    assert result == 50.0
    assert calc.get_speed() == 50.0


def test_negative_speed_does_not_update_ema():
    calc = SpeedCalculator(alpha=0.2)
    calc.update(30.0)
    result = calc.update(-10.0)
    assert result == 30.0


def test_reset():
    calc = SpeedCalculator()
    calc.update(100.0)
    calc.reset()
    assert calc.get_speed() == 0.0
    assert calc.is_initialized is False


def test_alpha_clamped():
    calc = SpeedCalculator(alpha=1.5)
    assert calc.alpha == 1.0
    calc2 = SpeedCalculator(alpha=-0.1)
    assert calc2.alpha == 0.0
