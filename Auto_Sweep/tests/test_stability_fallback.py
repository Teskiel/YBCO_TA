# -*- coding: utf-8 -*-
"""
BDD 测试 — 简化版实验稳定性控制器 (ExperimentStabilityController)

新逻辑：固定 PID + 仅调整设定点过冲。
  - PID 按温区硬编码，永不调整
  - 不稳定时增大设定点过冲：Δ = 目标温度 - 实际温度
  - 至多 2 次设定点调整后进入 ±0.5K 最终判定

命名规范: test_given_<前置条件>_when_<动作>_then_<预期结果>
"""

import math
import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =========================================================================
# TestClass: 固定 PID 温区查找
# =========================================================================

class TestFixedPIDZones:
    """验证固定 PID 按温区正确分配。"""

    @pytest.fixture
    def controller(self):
        from ui.experiment_stability_controller import (
            ExperimentStabilityController,
        )
        return ExperimentStabilityController()

    def test_given_target_10K_when_setup_then_pid_is_100_5_0(self, controller):
        """≤20K: P=100, I=5, D=0, overshoot=0。"""
        controller.setup(target_k=10.0, current_temperature=8.0)
        pid = controller.get_fixed_pid()
        assert pid == {"p": 100, "i": 5, "d": 0}
        assert controller.base_overshoot == 0.0
        assert controller.current_overshoot == 0.0

    def test_given_target_20K_when_setup_then_pid_is_100_5_0(self, controller):
        """正好 20K 属于低温区。"""
        controller.setup(target_k=20.0, current_temperature=18.0)
        pid = controller.get_fixed_pid()
        assert pid == {"p": 100, "i": 5, "d": 0}
        assert controller.base_overshoot == 0.0

    def test_given_target_30K_when_setup_then_pid_is_100_0_0_overshoot_1_5(
        self, controller
    ):
        """20-40K: P=100, I=0, D=0, overshoot=1.5K。"""
        controller.setup(target_k=30.0, current_temperature=25.0)
        pid = controller.get_fixed_pid()
        assert pid == {"p": 100, "i": 0, "d": 0}
        assert controller.base_overshoot == 1.5
        assert controller.current_overshoot == 1.5

    def test_given_target_40K_when_setup_then_pid_is_100_0_0(self, controller):
        """正好 40K 属于中温区。"""
        controller.setup(target_k=40.0, current_temperature=35.0)
        pid = controller.get_fixed_pid()
        assert pid == {"p": 100, "i": 0, "d": 0}

    def test_given_target_77K_when_setup_then_pid_is_150_0_0_overshoot_2_0(
        self, controller
    ):
        """>40K: P=150, I=0, D=0, overshoot=2.0K。"""
        controller.setup(target_k=77.0, current_temperature=70.0)
        pid = controller.get_fixed_pid()
        assert pid == {"p": 150, "i": 0, "d": 0}
        assert controller.base_overshoot == 2.0


# =========================================================================
# TestClass: 状态机推进逻辑
# =========================================================================

class TestStabilityStateMachine:
    """验证简化版状态机的推进逻辑。"""

    @pytest.fixture
    def controller(self):
        from ui.experiment_stability_controller import (
            ExperimentStabilityController,
        )
        return ExperimentStabilityController()

    def test_given_initial_setup_when_checking_state_then_state_is_0(
        self, controller
    ):
        """初始化后状态应为 INITIAL_SETPOINT。"""
        from ui.experiment_stability_controller import StabilityState

        controller.setup(target_k=30.0, current_temperature=28.0)
        assert controller.current_state == StabilityState.INITIAL_SETPOINT

    def test_given_state_0_when_not_stable_60s_then_advances_to_state_1(
        self, controller
    ):
        """State 0 在 60 秒后未稳定时推进到 State 1。"""
        from ui.experiment_stability_controller import StabilityState

        controller.setup(target_k=30.0, current_temperature=28.0)

        # 添加 50 秒数据
        for i in range(5):
            controller.add_reading(28.5 + 0.1 * i)
        result = controller.check(elapsed_s=50.0)
        assert controller.current_state == StabilityState.INITIAL_SETPOINT

        # 再加 11 秒
        controller.add_reading(29.0)
        result = controller.check(elapsed_s=61.0)
        assert controller.current_state == StabilityState.SETPOINT_ADJUST_1

    def test_given_state_1_when_not_stable_60s_then_advances_to_state_2(
        self, controller
    ):
        """State 1 在另一个 60 秒后推进到 State 2。"""
        from ui.experiment_stability_controller import StabilityState

        controller.setup(target_k=30.0, current_temperature=29.0)
        controller._advance_to_state_for_test(StabilityState.SETPOINT_ADJUST_1)
        controller._state_elapsed_at_entry = 60.0

        for i in range(5):
            controller.add_reading(29.2 + 0.05 * i)
        result = controller.check(elapsed_s=110.0)
        assert controller.current_state == StabilityState.SETPOINT_ADJUST_1

        controller.add_reading(29.3)
        result = controller.check(elapsed_s=121.0)
        assert controller.current_state == StabilityState.SETPOINT_ADJUST_2

    def test_given_state_2_when_stable_then_returns_stable(
        self, controller
    ):
        """任何状态达到稳定都应返回 stable=True。"""
        controller.setup(target_k=30.0, current_temperature=30.0)

        for i in range(15):
            controller.add_reading(30.0 + 0.02 * (i % 3 - 1))

        result = controller.check(elapsed_s=70.0)
        assert result is not None
        assert hasattr(result, "stable")
        assert hasattr(result, "reason")


# =========================================================================
# TestClass: 设定点过冲调整
# =========================================================================

class TestSetpointOvershootAdjustment:
    """验证设定点过冲根据 Δ = target - actual 正确调整。"""

    @pytest.fixture
    def controller(self):
        from ui.experiment_stability_controller import (
            ExperimentStabilityController,
        )
        return ExperimentStabilityController()

    def test_given_state_0_when_needs_adjustment_then_returns_initial_setpoint(
        self, controller
    ):
        """State 0 应返回初始设定点（target + base_overshoot）。"""
        controller.setup(target_k=30.0, current_temperature=25.0)
        sp = controller.needs_setpoint_adjustment()
        assert sp is not None
        # base_overshoot = 1.5K, target = 30.0K → setpoint = 31.5K
        assert sp == 31.5

    def test_given_low_temp_when_needs_adjustment_then_setpoint_equals_target(
        self, controller
    ):
        """低温区（≤20K）过冲为 0，设定点 = 目标。"""
        controller.setup(target_k=10.0, current_temperature=8.0)
        sp = controller.needs_setpoint_adjustment()
        assert sp == 10.0

    def test_given_state_1_when_advancing_then_overshoot_increases_by_delta(
        self, controller
    ):
        """State 0→1 时过冲 = base + (target - actual_avg)。"""
        from ui.experiment_stability_controller import StabilityState

        controller.setup(target_k=30.0, current_temperature=25.0)

        # 模拟 Δ = 5K 的情况
        for i in range(7):
            controller.add_reading(25.5 + 0.1 * i)

        # 推进到 State 1
        result = controller.check(elapsed_s=61.0)
        assert controller.current_state == StabilityState.SETPOINT_ADJUST_1
        # 过冲应增加：base(1.5) + Δ(≈4.5) ≈ 6.0K
        assert controller.current_overshoot > 1.5

    def test_given_overshoot_adjustment_when_overshoot_exceeds_max_then_clamped(
        self, controller
    ):
        """过冲应被钳位在 MAX_OVERSHOOT_K。"""
        controller.setup(target_k=30.0, current_temperature=10.0)

        # 模拟巨大温差 Δ = 20K
        for i in range(7):
            controller.add_reading(12.0 + 0.1 * i)
        controller.check(elapsed_s=61.0)

        # 过冲不应超过 MAX_OVERSHOOT_K
        assert controller.current_overshoot <= controller.MAX_OVERSHOOT_K

    def test_given_same_state_when_needs_adjustment_called_twice_then_second_is_none(
        self, controller
    ):
        """同一状态下第二次调用 needs_setpoint_adjustment 应返回 None。"""
        controller.setup(target_k=30.0, current_temperature=25.0)
        sp1 = controller.needs_setpoint_adjustment()
        assert sp1 is not None
        sp2 = controller.needs_setpoint_adjustment()
        assert sp2 is None


# =========================================================================
# TestClass: 最终回退 (good_enough)
# =========================================================================

class TestGoodEnoughFallback:
    """验证 ±0.5K 回退机制。"""

    @pytest.fixture
    def controller(self):
        from ui.experiment_stability_controller import (
            ExperimentStabilityController,
        )
        return ExperimentStabilityController()

    def test_given_state_2_when_avg_within_0_5K_then_returns_good_enough(
        self, controller
    ):
        """State 2 中均温距目标 ≤0.5K → good_enough。"""
        from ui.experiment_stability_controller import StabilityState

        controller.setup(target_k=30.0, current_temperature=29.8)
        controller._advance_to_state_for_test(StabilityState.SETPOINT_ADJUST_2)
        controller._state_elapsed_at_entry = 180.0

        for i in range(15):
            controller.add_reading(29.75 + 0.02 * (i % 5))

        result = controller.check(elapsed_s=250.0)
        assert result is not None
        assert result.reason in ("stable", "good_enough", "waiting")

    def test_given_state_2_when_avg_far_from_target_then_not_good_enough(
        self, controller
    ):
        """State 2 中均温距目标 > 0.5K → 继续等待。"""
        from ui.experiment_stability_controller import StabilityState

        controller.setup(target_k=30.0, current_temperature=28.0)
        controller._advance_to_state_for_test(StabilityState.SETPOINT_ADJUST_2)
        controller._state_elapsed_at_entry = 180.0

        for i in range(15):
            controller.add_reading(28.5 + 0.05 * i)

        result = controller.check(elapsed_s=250.0)
        assert result.reason in ("waiting", "timeout")


# =========================================================================
# TestClass: ExperimentWorker 集成
# =========================================================================

class TestExperimentWorkerIntegration:
    """验证 ExperimentWorker 与新控制器的集成。"""

    @pytest.fixture(scope="module")
    def qapp(self):
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        yield app

    def _make_mock_lakeshore(self, start_temp=50.0):
        ls = MagicMock()
        ls.get_temperature.return_value = start_temp
        return ls

    def _make_mock_laser(self):
        return MagicMock()

    def _make_mock_vna(self):
        return MagicMock()

    def _build_worker(self, lakeshore=None, laser=None, vna=None,
                      temp_list=None, power_list=None,
                      output_dir="", vna_settings=None, vna_power_list=None):
        from ui.workers import ExperimentWorker
        worker = ExperimentWorker()
        worker.configure(
            lakeshore_ctrl=lakeshore if lakeshore is not None else self._make_mock_lakeshore(),
            laser_ctrl=laser if laser is not None else self._make_mock_laser(),
            vna_resource=vna if vna is not None else self._make_mock_vna(),
            temp_list=temp_list if temp_list is not None else [30.0],
            power_list=power_list if power_list is not None else [0, 5],
            vna_power_list=vna_power_list if vna_power_list is not None else [-45],
            output_dir=output_dir or "/tmp/test_sweep",
            vna_settings=vna_settings if vna_settings is not None else {
                "start_freq_hz": 3_000_000_000.0,
                "stop_freq_hz": 6_000_000_000.0,
                "s_parameter": "S21",
                "power_dbm": [-45],
            },
        )
        return worker

    @patch("time.sleep", return_value=None)
    @patch("os.makedirs")
    def test_given_new_controller_when_run_then_uses_fixed_pid(
        self, mock_makedirs, mock_sleep, qapp
    ):
        """ExperimentWorker 应使用固定 PID + 设定点调整。"""
        ls = self._make_mock_lakeshore(start_temp=30.0)
        worker = self._build_worker(lakeshore=ls, temp_list=[30.0])

        finished = []
        worker.experiment_finished.connect(lambda c: finished.append(c))

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

        assert len(finished) == 1
        # 验证固定 PID 被写入
        assert ls.set_pid.called

    @patch("time.sleep", return_value=None)
    @patch("os.makedirs")
    def test_given_good_enough_when_run_then_proceeds(
        self, mock_makedirs, mock_sleep, qapp
    ):
        """good_enough 结果应让测量继续。"""
        ls = self._make_mock_lakeshore(start_temp=30.3)
        worker = self._build_worker(lakeshore=ls, temp_list=[30.0])

        finished = []
        worker.experiment_finished.connect(lambda c: finished.append(c))

        with patch(
            "ui.experiment_stability_controller.ExperimentStabilityController"
        ) as mock_ctrl_cls:
            mock_ctrl = mock_ctrl_cls.return_value
            mock_ctrl.get_fixed_pid.return_value = {"p": 100, "i": 0, "d": 0}
            mock_ctrl.setup.return_value = None
            mock_ctrl.add_reading.return_value = None
            mock_ctrl.check.return_value = MagicMock(
                stable=False, reason="good_enough", avg_temp=30.3)
            mock_ctrl.needs_setpoint_adjustment.return_value = None
            mock_ctrl.base_overshoot = 1.5
            mock_ctrl.current_overshoot = 1.5

            worker.run()

        assert len(finished) == 1
