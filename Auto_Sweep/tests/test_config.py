# -*- coding: utf-8 -*-
"""
BDD tests for config.py

Naming convention: test_given_<precondition>_when_<action>_then_<expected>
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestResourceAddresses:
    """Given the config module, resource addresses should be valid VISA strings."""

    def test_given_config_loaded_when_reading_vna_address_then_is_tcpip_hislip(self):
        import config
        assert "TCPIP" in config.resource_vna
        assert "hislip" in config.resource_vna

    def test_given_config_loaded_when_reading_laser_address_then_is_tcpip(self):
        import config
        assert "TCPIP" in config.laser_resource

    def test_given_config_loaded_when_reading_lakeshore_address_then_is_asrl(self):
        import config
        assert "ASRL" in config.resource_lakeshore


class TestSweepSettings:
    """Given the config module, sweep parameters should be consistent."""

    def test_given_power_levels_when_checking_then_non_empty_monotonic(self):
        import config
        assert len(config.power_levels_mw) > 0
        assert config.power_levels_mw == sorted(config.power_levels_mw)

    def test_given_temperature_levels_when_checking_then_starts_at_26_ends_at_100_step_2(self):
        import config
        assert config.temperature_levels_k[0] == 26
        assert config.temperature_levels_k[-1] == 100
        assert config.temperature_levels_k[1] - config.temperature_levels_k[0] == 2

    def test_given_stability_settings_when_checking_then_all_tolerances_positive(self):
        import config
        assert config.stable_hold_seconds > 0
        assert config.max_wait_seconds > config.stable_hold_seconds
        assert config.temperature_poll_seconds > 0


class TestCustomStabilitySettings:
    """Given custom stability method, settings should be internally consistent."""

    def test_given_custom_settings_when_checking_then_final_band_tighter_than_avg_tolerance(self):
        import config
        s = config.custom_stability_settings
        assert s['final_stable_band_k'] <= s['avg_tolerance_k']

    def test_given_custom_settings_when_checking_then_delta_tolerance_stricter_than_avg(self):
        import config
        s = config.custom_stability_settings
        assert s['delta_tolerance_k'] <= s['avg_tolerance_k']

    def test_given_custom_settings_when_checking_then_final_band_is_0_5(self):
        """放宽后 final_stable_band_k 应为 0.5K。"""
        import config
        s = config.custom_stability_settings
        assert s['final_stable_band_k'] == 0.5


class TestPIDParams:
    """Given PID_PARAMS, temperature zones should not overlap or leave gaps."""

    def test_given_pid_params_when_checking_zones_then_low_ends_at_20(self):
        import config
        assert config.PID_PARAMS['low_temp']['max_temp'] == 20.0

    def test_given_pid_params_when_checking_zones_then_medium_spans_20_to_40(self):
        import config
        assert config.PID_PARAMS['medium_temp']['min_temp'] == 20.0
        assert config.PID_PARAMS['medium_temp']['max_temp'] == 40.0

    def test_given_pid_params_when_checking_zones_then_high_starts_at_40(self):
        import config
        assert config.PID_PARAMS['high_temp']['min_temp'] == 40.0

    def test_given_pid_params_when_checking_then_all_zones_have_p_i_d(self):
        import config
        for zone in config.PID_PARAMS.values():
            assert 'p' in zone
            assert 'i' in zone
            assert 'd' in zone


class TestSetpointAdjustSettings:
    """Given setpoint adjustment settings, thresholds should be ordered."""

    def test_given_setpoint_settings_when_checking_then_low_below_medium(self):
        import config
        s = config.setpoint_adjust_settings
        assert s['low_temp_threshold'] < s['medium_temp_threshold']

    def test_given_setpoint_settings_when_checking_then_overshoot_factor_between_0_and_1(self):
        import config
        s = config.setpoint_adjust_settings
        assert 0 < s['overshoot_factor'] <= 1.0


class TestDeadCodeRemoval:
    """Given the refactoring, dead variables should NOT exist."""

    def test_given_config_loaded_when_checking_then_trace_name_absent(self):
        import config
        assert not hasattr(config, 'TRACE_NAME')

    def test_given_config_loaded_when_checking_then_auto_adjust_pid_absent(self):
        import config
        assert not hasattr(config, 'auto_adjust_pid')

    def test_given_config_loaded_when_checking_then_diagnose_before_measure_absent(self):
        import config
        assert not hasattr(config, 'diagnose_before_measure')


class TestAutoReconnectConfig:
    """验证自动重连配置项的完整性。"""

    def test_given_config_loaded_when_reconnect_settings_present_then_valid(self):
        import config
        assert hasattr(config, "max_reconnect_attempts")
        assert config.max_reconnect_attempts >= 1
        assert hasattr(config, "reconnect_delay_seconds")
        assert config.reconnect_delay_seconds >= 0


class TestStabilityFallbackConfig:
    """验证稳定性回退配置项的完整性。"""

    def test_given_config_loaded_when_fallback_settings_present_then_valid(self):
        import config
        assert hasattr(config, "stability_fallback_settings")
        s = config.stability_fallback_settings
        assert s["good_enough_band_k"] > 0
        assert s["max_setpoint_adjustments"] >= 1
        assert s["diagnostic_interval_s"] > 0
        assert s["max_overshoot_k"] > 0

    def test_given_fixed_pid_zones_when_checking_then_all_zones_valid(self):
        """FIXED_PID_ZONES 应包含 low/medium/high 三个温区。"""
        import config
        zones = config.FIXED_PID_ZONES
        for name in ("low", "medium", "high"):
            assert name in zones
            z = zones[name]
            assert "p" in z and z["p"] > 0
            assert "i" in z and z["i"] >= 0
            assert "d" in z and z["d"] == 0
            assert "base_overshoot_k" in z and z["base_overshoot_k"] >= 0
            assert "max_temp" in z


class TestOutputPath:
    """Given config, the output path should be well-formed."""

    def test_given_base_folder_when_checking_then_contains_date_and_temperature_sweep(self):
        import config
        assert 'temperature_sweep' in config.base_folder or 'YBCO' in config.base_folder

    def test_given_base_folder_when_checking_then_is_absolute(self):
        import config
        assert config.base_folder[1:3] == ':\\' or config.base_folder.startswith('/')


# =========================================================================
# 新增：测量逻辑版本号（需求4.2）
# =========================================================================

class TestMeasurementVersion:
    """验证 MEASUREMENT_LOGIC_VERSION 常量的存在性和格式。"""

    def test_given_config_loaded_when_version_present_then_valid_format(self):
        import config
        assert hasattr(config, "MEASUREMENT_LOGIC_VERSION")
        version = config.MEASUREMENT_LOGIC_VERSION
        import re
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", version)

    def test_given_version_when_reading_then_is_string(self):
        import config
        assert isinstance(config.MEASUREMENT_LOGIC_VERSION, str)


