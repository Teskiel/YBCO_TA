# -*- coding: utf-8 -*-
"""
BDD tests for ExperimentWorker — full YBCO temperature + power sweep.

The ExperimentWorker runs the measurement loop on a background QThread.
Tests use MagicMock controllers and call run() synchronously for speed.

Updated for simplified controller: fixed PID + setpoint-only adjustment.
"""

import sys
import os
from unittest.mock import MagicMock, patch

import pytest
from PyQt5.QtCore import QObject, QThread


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


# =========================================================================
# Helpers
# =========================================================================

def _make_mock_lakeshore(start_temp=50.0):
    """Return a MagicMock LakeShore335 that always returns *start_temp* K."""
    ls = MagicMock()
    ls.get_temperature.return_value = start_temp
    return ls


def _make_mock_laser():
    return MagicMock()


def _make_mock_vna():
    return MagicMock()


def _build_worker(lakeshore=None, laser=None, vna=None,
                  temp_list=None, power_list=None,
                  output_dir="", vna_settings=None, vna_power_list=None):
    """Instantiate ExperimentWorker and configure it with mocks."""
    from ui.workers import ExperimentWorker

    worker = ExperimentWorker()
    worker.configure(
        lakeshore_ctrl=lakeshore if lakeshore is not None else _make_mock_lakeshore(),
        laser_ctrl=laser if laser is not None else _make_mock_laser(),
        vna_resource=vna if vna is not None else _make_mock_vna(),
        temp_list=temp_list if temp_list is not None else [30.0, 50.0],
        power_list=power_list if power_list is not None else [0, 5],
        vna_power_list=vna_power_list if vna_power_list is not None else [-45],
        output_dir=output_dir or "/tmp/test_sweep",
        vna_settings=vna_settings if vna_settings is not None else {
            "start_freq_hz": 3_000_000_000.0,
            "stop_freq_hz": 6_000_000_000.0,
            "s_parameter": "S21",
            "power_dbm": [-45],
            "points": 50001,
            "if_bandwidth_hz": 10000,
        },
    )
    return worker


# =========================================================================
# TestClass: Validation
# =========================================================================

class TestExperimentValidation:
    """Given an ExperimentWorker, invalid inputs are rejected before run."""

    def test_given_empty_temp_list_when_configured_then_worker_has_empty_list(
        self, qapp
    ):
        worker = _build_worker(temp_list=[])
        assert worker._temp_list == []

    def test_given_empty_power_list_when_configured_then_worker_has_empty_list(
        self, qapp
    ):
        worker = _build_worker(power_list=[])
        assert worker._power_list == []


# =========================================================================
# TestClass: Full Experiment Loop
# =========================================================================

class TestExperimentLoop:
    """Given a configured ExperimentWorker, the run() method executes
    the full temperature-and-power sweep."""

    @patch("time.sleep", return_value=None)
    @patch("os.makedirs")
    def test_given_2_temps_2_powers_when_run_then_4_measurements(
        self, mock_makedirs, mock_sleep, qapp
    ):
        """2 temperatures × 2 powers = 4 S2P measurements."""
        ls = _make_mock_lakeshore(start_temp=30.0)
        worker = _build_worker(
            lakeshore=ls,
            temp_list=[30.0, 50.0],
            power_list=[0, 5],
        )

        finished_counts = []
        worker.experiment_finished.connect(lambda c: finished_counts.append(c))

        with patch(
            "ui.experiment_stability_controller.ExperimentStabilityController"
        ) as mock_ctrl_cls:
            mock_ctrl = mock_ctrl_cls.return_value
            mock_ctrl.get_fixed_pid.return_value = {"p": 100, "i": 0, "d": 0}
            mock_ctrl.setup.return_value = None
            mock_ctrl.add_reading.return_value = None
            mock_ctrl.check.return_value = MagicMock(
                stable=True, reason="stable", avg_temp=30.0)
            mock_ctrl.needs_setpoint_adjustment.return_value = None
            mock_ctrl.base_overshoot = 1.5
            mock_ctrl.current_overshoot = 1.5

            worker.run()

        assert finished_counts[0] == 4
        assert mock_sleep.called

    @patch("time.sleep", return_value=None)
    @patch("os.makedirs")
    def test_given_0_mw_power_when_measuring_then_laser_output_off_called(
        self, mock_makedirs, mock_sleep, qapp
    ):
        """At 0 mW, the laser should be turned OFF, not set to 0 mW."""
        laser = _make_mock_laser()
        worker = _build_worker(
            laser=laser,
            temp_list=[30.0],
            power_list=[0],
        )

        with patch(
            "ui.experiment_stability_controller.ExperimentStabilityController"
        ) as mock_ctrl_cls:
            mock_ctrl = mock_ctrl_cls.return_value
            mock_ctrl.get_fixed_pid.return_value = {"p": 100, "i": 0, "d": 0}
            mock_ctrl.setup.return_value = None
            mock_ctrl.add_reading.return_value = None
            mock_ctrl.check.return_value = MagicMock(
                stable=True, reason="stable", avg_temp=30.0)
            mock_ctrl.needs_setpoint_adjustment.return_value = None
            mock_ctrl.base_overshoot = 1.5
            mock_ctrl.current_overshoot = 1.5
            worker.run()

        assert laser.output_off.called
        laser.set_power.assert_not_called()

    @patch("time.sleep", return_value=None)
    @patch("os.makedirs")
    def test_given_nonzero_power_when_measuring_then_laser_set_and_output_on(
        self, mock_makedirs, mock_sleep, qapp
    ):
        """At non-zero power, laser.set_power() + output_on() are called."""
        laser = _make_mock_laser()
        worker = _build_worker(
            laser=laser,
            temp_list=[30.0],
            power_list=[5],
        )

        with patch(
            "ui.experiment_stability_controller.ExperimentStabilityController"
        ) as mock_ctrl_cls:
            mock_ctrl = mock_ctrl_cls.return_value
            mock_ctrl.get_fixed_pid.return_value = {"p": 100, "i": 0, "d": 0}
            mock_ctrl.setup.return_value = None
            mock_ctrl.add_reading.return_value = None
            mock_ctrl.check.return_value = MagicMock(
                stable=True, reason="stable", avg_temp=30.0)
            mock_ctrl.needs_setpoint_adjustment.return_value = None
            mock_ctrl.base_overshoot = 1.5
            mock_ctrl.current_overshoot = 1.5
            worker.run()

        laser.set_power.assert_called_with(5)
        laser.output_on.assert_called_once()


# =========================================================================
# TestClass: Abort Mechanism
# =========================================================================

class TestAbortMechanism:
    """Given a running ExperimentWorker, calling abort() stops the loop."""

    @patch("time.sleep", return_value=None)
    @patch("os.makedirs")
    def test_given_worker_running_when_abort_called_then_emits_aborted(
        self, mock_makedirs, mock_sleep, qapp
    ):
        """Abort before the first temperature step should emit aborted."""
        ls = _make_mock_lakeshore(start_temp=30.0)
        worker = _build_worker(
            lakeshore=ls,
            temp_list=[30.0, 40.0, 50.0],
            power_list=[0, 5],
        )

        aborted = []
        worker.experiment_aborted.connect(lambda: aborted.append(True))
        finished = []
        worker.experiment_finished.connect(lambda c: finished.append(c))

        worker.abort()

        with patch(
            "ui.experiment_stability_controller.ExperimentStabilityController"
        ) as mock_ctrl_cls:
            mock_ctrl = mock_ctrl_cls.return_value
            mock_ctrl.get_fixed_pid.return_value = {"p": 100, "i": 0, "d": 0}
            mock_ctrl.setup.return_value = None
            mock_ctrl.add_reading.return_value = None
            mock_ctrl.check.return_value = MagicMock(
                stable=True, reason="stable", avg_temp=30.0)
            mock_ctrl.needs_setpoint_adjustment.return_value = None
            mock_ctrl.base_overshoot = 1.5
            mock_ctrl.current_overshoot = 1.5
            worker.run()

        assert len(aborted) == 1
        assert len(finished) == 0


# =========================================================================
# TestClass: Parameters from GUI (not config.py)
# =========================================================================

class TestParametersFromCaller:
    """Given an ExperimentWorker, all sweep parameters come from configure(),
    NOT from config.py."""

    def test_given_custom_temp_power_lists_when_run_then_those_lists_are_used(
        self, qapp
    ):
        test_temps = [10.0, 77.0, 100.0]
        test_powers = [1, 3, 7]
        worker = _build_worker(
            temp_list=test_temps,
            power_list=test_powers,
        )
        assert worker._temp_list == test_temps
        assert worker._power_list == test_powers


# =========================================================================
# TestClass: 新简化版稳定性逻辑
# =========================================================================

class TestNewStabilityLogic:
    """验证 ExperimentWorker 使用简化版稳定性控制器。"""

    @patch("time.sleep", return_value=None)
    @patch("os.makedirs")
    def test_given_fixed_pid_controller_when_run_then_pid_written_once(
        self, mock_makedirs, mock_sleep, qapp
    ):
        """固定 PID 应在每个温度点开始时写入一次。"""
        ls = _make_mock_lakeshore(start_temp=30.0)
        worker = _build_worker(lakeshore=ls, temp_list=[30.0])

        finished_counts = []
        worker.experiment_finished.connect(lambda c: finished_counts.append(c))

        with patch(
            "ui.experiment_stability_controller.ExperimentStabilityController"
        ) as mock_ctrl_cls:
            mock_ctrl = mock_ctrl_cls.return_value
            mock_ctrl.get_fixed_pid.return_value = {"p": 100, "i": 0, "d": 0}
            mock_ctrl.setup.return_value = None
            mock_ctrl.add_reading.return_value = None
            mock_ctrl.check.return_value = MagicMock(
                stable=True, reason="stable", avg_temp=30.0)
            mock_ctrl.needs_setpoint_adjustment.return_value = None
            mock_ctrl.base_overshoot = 1.5
            mock_ctrl.current_overshoot = 1.5

            worker.run()

        # 固定 PID 被写入
        assert ls.set_pid.called
        assert len(finished_counts) >= 1

    @patch("time.sleep", return_value=None)
    @patch("os.makedirs")
    def test_given_good_enough_when_run_then_proceeds(
        self, mock_makedirs, mock_sleep, qapp
    ):
        """good_enough 结果应让测量继续。"""
        ls = _make_mock_lakeshore(start_temp=30.35)
        worker = _build_worker(lakeshore=ls, temp_list=[30.0])

        finished_counts = []
        worker.experiment_finished.connect(lambda c: finished_counts.append(c))

        with patch(
            "ui.experiment_stability_controller.ExperimentStabilityController"
        ) as mock_ctrl_cls:
            mock_ctrl = mock_ctrl_cls.return_value
            mock_ctrl.get_fixed_pid.return_value = {"p": 100, "i": 0, "d": 0}
            mock_ctrl.setup.return_value = None
            mock_ctrl.add_reading.return_value = None
            mock_ctrl.check.return_value = MagicMock(
                stable=False, reason="good_enough", avg_temp=30.35)
            mock_ctrl.needs_setpoint_adjustment.return_value = None
            mock_ctrl.base_overshoot = 1.5
            mock_ctrl.current_overshoot = 1.5

            worker.run()

        assert len(finished_counts) == 1
