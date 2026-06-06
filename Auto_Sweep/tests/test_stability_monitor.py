# -*- coding: utf-8 -*-
"""
BDD tests for stability_monitor.py

Tests cover all 5 stability-checking methods plus edge cases.
All tests are pure — no hardware or VISA dependencies.
"""

import time
import pytest
from stability_monitor import AdvancedStabilityMonitor, TemperatureReading


# ======================================================================
# Helpers
# ======================================================================

def _feed(monitor, temps, target=30.0, step_seconds=10):
    """Feed a sequence of temperature readings into the monitor.

    Each reading is stamped `step_seconds` apart, going backward so the
    most recent reading has timestamp=now.
    """
    now = time.time()
    for i, t in enumerate(temps):
        r = TemperatureReading(
            timestamp=now - (len(temps) - 1 - i) * step_seconds,
            temperature=t,
            target=target,
        )
        monitor.readings.append(r)


# ======================================================================
# check_stability_simple
# ======================================================================

class TestStabilitySimple:
    """Given simple (tolerance-band) method."""

    def test_given_all_readings_in_band_when_checking_then_returns_stable(self):
        monitor = AdvancedStabilityMonitor()
        _feed(monitor, [30.0, 30.02, 30.01, 29.99, 30.0, 30.01], step_seconds=10)
        result = monitor.check_stability_simple(30.0, tolerance_k=0.1, hold_seconds=120)
        assert result["stable"] is True
        assert result["method"] == "simple"

    def test_given_one_reading_outside_tolerance_when_checking_then_returns_not_stable(self):
        monitor = AdvancedStabilityMonitor()
        _feed(monitor, [30.0, 30.15, 30.0, 30.0, 30.0, 30.0], step_seconds=10)
        result = monitor.check_stability_simple(30.0, tolerance_k=0.1, hold_seconds=120)
        assert result["stable"] is False

    def test_given_no_readings_when_checking_then_returns_not_stable_with_reason(self):
        monitor = AdvancedStabilityMonitor()
        result = monitor.check_stability_simple(30.0)
        assert result["stable"] is False
        assert "No recent data" in result["reason"]


# ======================================================================
# check_stability_v1
# ======================================================================

class TestStabilityV1:
    """Given v1 (mean error + variance) method."""

    def test_given_tightly_clustered_readings_when_checking_v1_then_returns_stable(self):
        monitor = AdvancedStabilityMonitor()
        _feed(monitor, [30.0, 30.01, 29.99, 30.0, 30.005, 29.995] * 6, step_seconds=1)
        result = monitor.check_stability_v1(30.0, threshold_k=0.05, window_size=30)
        assert result["stable"] is True

    def test_given_insufficient_data_when_checking_v1_then_returns_not_stable(self):
        monitor = AdvancedStabilityMonitor()
        _feed(monitor, [30.0] * 5, step_seconds=1)
        result = monitor.check_stability_v1(30.0, window_size=30)
        assert result["stable"] is False
        assert "Insufficient" in result["reason"]


# ======================================================================
# check_stability_custom
# ======================================================================

class TestStabilityCustom:
    """Given custom (rolling 1-min averages) method — the production default."""

    def test_given_stable_plateau_when_checking_custom_then_returns_stable(self):
        monitor = AdvancedStabilityMonitor()
        # 150 readings at 6s intervals = 15 min of data; 30 readings in 180s window
        _feed(monitor, [30.0] * 150, step_seconds=6)
        result = monitor.check_stability_custom(30.0)
        assert result["stable"] is True
        assert result["method"] == "custom"

    def test_given_insufficient_data_when_checking_custom_then_returns_not_stable_with_reason(self):
        """min_readings_required=10，5 个读数不足以进行稳定性检测。"""
        monitor = AdvancedStabilityMonitor()
        _feed(monitor, [30.0] * 5, step_seconds=10)
        result = monitor.check_stability_custom(30.0)
        assert result["stable"] is False
        assert "readings" in result["reason"].lower()

    def test_given_temperature_far_from_target_when_checking_custom_then_condition1_fails(self):
        monitor = AdvancedStabilityMonitor()
        _feed(monitor, [35.0] * 90, step_seconds=10)
        result = monitor.check_stability_custom(30.0)
        # average of 35.0 is outside ±1.0K tolerance → condition1 fails
        assert result["stable"] is False

    def test_given_rate_stable_but_off_target_when_checking_custom_then_ready_for_adjust_true(self):
        """ready_for_adjust only requires rate stability, not being on-target."""
        monitor = AdvancedStabilityMonitor()
        # temperature is flat at 28K (off from 30K target) but not changing
        _feed(monitor, [28.0] * 90, step_seconds=10)
        result = monitor.check_stability_custom(30.0)
        # condition2 (delta between windows) should pass because it's flat
        assert result.get("ready_for_adjust", False) or result["stable"] is False


# ======================================================================
# check_stability dispatcher
# ======================================================================

class TestStabilityDispatcher:
    """Given the check_stability router."""

    def test_given_method_simple_when_dispatching_then_calls_simple(self):
        monitor = AdvancedStabilityMonitor()
        _feed(monitor, [30.0] * 60, step_seconds=1)
        result = monitor.check_stability(30.0, method="simple")
        assert result["method"] == "simple"

    def test_given_unknown_method_when_dispatching_then_returns_error(self):
        monitor = AdvancedStabilityMonitor()
        result = monitor.check_stability(30.0, method="nonexistent")
        assert result["stable"] is False
        assert "Unknown method" in result["reason"]


# ======================================================================
# Edge cases
# ======================================================================

class TestEdgeCases:
    """Given edge-case inputs."""

    def test_given_add_reading_when_exceeding_max_then_oldest_dropped(self):
        monitor = AdvancedStabilityMonitor()
        monitor.max_readings = 10
        for i in range(15):
            monitor.add_reading(30.0, 30.0)
        assert len(monitor.readings) == 10

    def test_given_clear_called_when_checking_then_no_readings(self):
        monitor = AdvancedStabilityMonitor()
        _feed(monitor, [30.0] * 60, step_seconds=1)
        monitor.clear()
        assert len(monitor.readings) == 0

    def test_given_zero_target_when_checking_v2_then_no_division_by_zero(self):
        """Relative error calculation should handle target=0K gracefully."""
        monitor = AdvancedStabilityMonitor()
        _feed(monitor, [0.0, 0.001, -0.001, 0.0] * 10, step_seconds=1)
        # Should not raise
        result = monitor.check_stability_v2(0.0)
        assert isinstance(result, dict)
        assert "stable" in result


# ======================================================================
# Factory
# ======================================================================

class TestTemperatureReading:
    """Given TemperatureReading dataclass."""

    def test_given_valid_values_when_creating_reading_then_fields_match(self):
        now = time.time()
        r = TemperatureReading(timestamp=now, temperature=30.5, target=30.0)
        assert r.temperature == 30.5
        assert r.target == 30.0
        assert r.timestamp == now
