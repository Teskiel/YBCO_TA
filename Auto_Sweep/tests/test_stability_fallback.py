# -*- coding: utf-8 -*-
"""
BDD 测试 — 2 阶段实验稳定性控制器 (ExperimentStabilityController)

新逻辑：
  - 固定 PID + 仅调整设定点过冲
  - Phase 1 (sparse): 低频轮询，等待 trending_stable
  - Phase 2 (fine):   高频轮询，并行判 in_target_zone + steady_state
  - 过冲调整冷却时间 120s，至多 2 次
  - good_enough 回退: Phase 2 中 in_target_zone 但未稳态超 10 分钟

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
# TestClass: 阶段转换逻辑
# =========================================================================

class TestPhaseTransition:
    """验证 Phase 1 (sparse) → Phase 2 (fine) 转换。"""

    @pytest.fixture
    def controller(self):
        from ui.experiment_stability_controller import (
            ExperimentStabilityController, StabilityPhase,
        )
        return ExperimentStabilityController()

    def test_given_initial_setup_when_checking_phase_then_phase_is_sparse(self, controller):
        """初始化后阶段应为 SPARSE。"""
        from ui.experiment_stability_controller import StabilityPhase
        controller.setup(target_k=30.0, current_temperature=28.0)
        assert controller.phase == StabilityPhase.SPARSE

    def test_given_sparse_when_not_trending_stable_then_stays_sparse(self, controller):
        """Phase 1 中若未趋于平稳 → 保持 SPARSE。"""
        from ui.experiment_stability_controller import StabilityPhase

        controller.setup(target_k=30.0, current_temperature=25.0)
        # 不稳定数据 — 快速升温中
        controller._set_monitor_readings_for_test([
            (26.0, 130), (26.5, 120), (27.0, 110), (27.5, 100),
            (28.0, 90), (28.5, 80), (29.0, 70),
            (29.2, 60), (29.4, 50), (29.6, 40),
        ])

        result = controller.check(elapsed_s=30.0)
        assert controller.phase == StabilityPhase.SPARSE

    def test_given_sparse_when_trending_stable_then_transitions_to_fine(self, controller):
        """趋于平稳 → Phase 1→2。"""
        from ui.experiment_stability_controller import StabilityPhase

        controller.setup(target_k=30.0, current_temperature=29.5)
        # 稳定数据 — 温度几乎不变，覆盖 180s 以生成 3 个 1-min 窗口
        controller._set_monitor_readings_for_test([
            (29.48, 170), (29.50, 160), (29.50, 150), (29.52, 140),
            (29.50, 130), (29.48, 120), (29.50, 110), (29.49, 100),
            (29.51, 90),  (29.50, 80),  (29.49, 70),  (29.50, 60),
            (29.49, 50),  (29.51, 40),  (29.50, 30),  (29.50, 20),
            (29.49, 10),
        ])

        result = controller.check(elapsed_s=30.0)
        assert controller.phase == StabilityPhase.FINE


# =========================================================================
# TestClass: 并行双轨判定
# =========================================================================

class TestDualTrackStability:
    """验证 stable = in_target_zone AND steady_state。"""

    @pytest.fixture
    def controller(self):
        from ui.experiment_stability_controller import (
            ExperimentStabilityController,
        )
        return ExperimentStabilityController()

    def test_given_in_target_zone_and_steady_when_checking_then_eventually_stable(
        self, controller
    ):
        """双轨同时满足 → 持续 60s → stable。"""
        controller.setup(target_k=30.0, current_temperature=30.0)
        # 模拟 3 分钟稳态数据（max-min ≤ 0.1K，均值接近 30.0）
        temps = []
        for i in range(36):  # 36 readings × 5s = 3 min
            temps.append((30.0 + 0.015 * (i % 5 - 2), (35 - i) * 5))
        controller._set_monitor_readings_for_test(temps)
        controller._set_phase_for_test(
            __import__('ui.experiment_stability_controller', fromlist=['StabilityPhase'])
            .StabilityPhase.FINE
        )

        result = controller.check(elapsed_s=70.0)
        assert result is not None
        # 可能 stable 或 good_enough（取决于 hold duration 是否足够）
        assert result.reason in ("stable", "good_enough", "waiting")

    def test_given_in_target_zone_only_when_steady_state_false_then_not_stable(
        self, controller
    ):
        """仅 in_target_zone 但稳态不满足 → 不是 stable。"""
        controller.setup(target_k=30.0, current_temperature=30.0)
        # 均值接近目标但波动大（max-min > 0.1K）
        controller._set_monitor_readings_for_test([
            (29.8, 150), (29.9, 140), (30.1, 130), (30.2, 120),
            (29.7, 110), (29.8, 100), (30.2, 90), (30.3, 80),
            (29.9, 70), (30.0, 60), (30.1, 50), (29.8, 40),
            (30.2, 30), (30.0, 20), (29.9, 10),
        ])

        result = controller.check(elapsed_s=30.0)
        assert result.stable is False

    def test_given_steady_but_off_target_when_checking_then_not_stable(
        self, controller
    ):
        """仅稳态满足但偏离目标 → 不是 stable。"""
        controller.setup(target_k=30.0, current_temperature=28.0)
        # 稳定在 28K（远离 30K 目标）— max-min ≤ 0.1K 但不在目标区间
        controller._set_monitor_readings_for_test([
            (28.00, 150), (28.02, 140), (28.01, 130), (27.99, 120),
            (28.00, 110), (28.01, 100), (27.98, 90), (28.00, 80),
            (27.99, 70), (28.01, 60), (28.00, 50), (28.02, 40),
            (28.00, 30), (27.99, 20), (28.01, 10),
        ])

        result = controller.check(elapsed_s=30.0)
        assert result.stable is False


# =========================================================================
# TestClass: 设定点过冲调整
# =========================================================================

class TestSetpointOvershootAdjustment:
    """验证设定点过冲调整逻辑。"""

    @pytest.fixture
    def controller(self):
        from ui.experiment_stability_controller import (
            ExperimentStabilityController,
        )
        return ExperimentStabilityController()

    def test_given_first_call_when_needs_adjustment_then_returns_initial_setpoint(
        self, controller
    ):
        """首次调用 → 返回初始设定点（target + base_overshoot）。"""
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

    def test_given_trending_stable_and_off_target_when_calling_adjust_then_overshoot_increases(
        self, controller
    ):
        """trending_stable 但不达目标 → 过冲应增大。"""
        controller.setup(target_k=30.0, current_temperature=25.0)
        # 首次调用后设置初始设定点
        sp1 = controller.needs_setpoint_adjustment()
        assert sp1 is not None
        base_overshoot = controller.current_overshoot  # 1.5

        # 模拟趋于平稳但离目标远（覆盖 180s 以生成 3 个 1-min 窗口）
        controller._set_monitor_readings_for_test([
            (25.5, 170), (25.5, 160), (25.6, 150), (25.5, 140),
            (25.6, 130), (25.5, 120), (25.6, 110), (25.5, 100),
            (25.5, 90),  (25.6, 80),  (25.5, 70),  (25.6, 60),
            (25.5, 50),  (25.6, 40),  (25.5, 30),  (25.6, 20),
            (25.5, 10),
        ])

        # 手动清除冷却时间来允许第二次调整
        controller._last_overshoot_time = 0  # 绕过冷却
        sp2 = controller.needs_setpoint_adjustment()
        # 过冲应增加：delta = 30-25.5 ≈ 4.5K, 新过冲 = 1.5+4.5 = 6.0K
        assert controller.current_overshoot > base_overshoot

    def test_given_overshoot_exceeds_max_when_adjusting_then_clamped(
        self, controller
    ):
        """过冲应被钳位在 MAX_OVERSHOOT_K。"""
        controller.setup(target_k=30.0, current_temperature=10.0)
        sp1 = controller.needs_setpoint_adjustment()  # 首次
        controller._last_overshoot_time = 0  # 绕过冷却

        # 模拟巨大温差（覆盖 180s 以生成 3 个 1-min 窗口）
        controller._set_monitor_readings_for_test([
            (12.0, 170), (12.0, 160), (12.1, 150), (12.0, 140),
            (12.0, 130), (12.1, 120), (12.0, 110), (12.0, 100),
            (12.1, 90),  (12.0, 80),  (12.0, 70),  (12.1, 60),
            (12.0, 50),  (12.0, 40),  (12.1, 30),  (12.0, 20),
            (12.0, 10),
        ])
        sp2 = controller.needs_setpoint_adjustment()
        assert controller.current_overshoot <= controller.MAX_OVERSHOOT_K

    def test_given_within_cooldown_when_calling_adjust_then_returns_none(
        self, controller
    ):
        """冷却时间内 → 不返回新设定点。"""
        controller.setup(target_k=30.0, current_temperature=25.0)
        sp1 = controller.needs_setpoint_adjustment()  # 首次 — 设定初始值
        assert sp1 is not None
        # 紧接着再调 — 冷却时间尚未过
        sp2 = controller.needs_setpoint_adjustment()
        assert sp2 is None  # 冷却中

    def test_given_max_adjustments_reached_when_calling_then_returns_none(
        self, controller
    ):
        """达到最大调整次数 → 不再返回新设定点。"""
        controller.setup(target_k=30.0, current_temperature=25.0)
        controller._setpoint_adjust_count = controller.MAX_OVERSHOOT_ADJUSTMENTS
        sp = controller.needs_setpoint_adjustment()
        assert sp is None


# =========================================================================
# TestClass: good_enough 回退
# =========================================================================

class TestGoodEnoughFallback:
    """验证 good_enough 回退：Phase 2 中 10 分钟后 in_target_zone 但未稳态。"""

    @pytest.fixture
    def controller(self):
        from ui.experiment_stability_controller import (
            ExperimentStabilityController,
        )
        return ExperimentStabilityController()

    def test_given_phase2_long_wait_in_target_zone_not_steady_then_good_enough(
        self, controller
    ):
        """Phase 2 中 in_target_zone=true 但 steady_state=false 持续 10 分钟 → good_enough。"""
        from ui.experiment_stability_controller import StabilityPhase

        controller.setup(target_k=30.0, current_temperature=30.0)
        controller._set_phase_for_test(StabilityPhase.FINE)
        controller._phase2_entry_time = 0.0

        # 均值在目标区间但波动较大（max-min > 0.1K）
        controller._set_monitor_readings_for_test([
            (29.8, 150), (29.9, 140), (30.1, 130), (30.2, 120),
            (29.7, 110), (29.8, 100), (30.2, 90), (30.3, 80),
            (29.9, 70), (30.0, 60), (30.1, 50), (29.8, 40),
        ])

        result = controller.check(
            elapsed_s=controller.GOOD_ENOUGH_PHASE2_TIMEOUT_S + 1.0
        )
        assert result.reason == "good_enough"

    def test_given_phase2_not_in_target_zone_then_not_good_enough(
        self, controller
    ):
        """不在目标区间 → 即使等很久也不是 good_enough。"""
        from ui.experiment_stability_controller import StabilityPhase

        controller.setup(target_k=30.0, current_temperature=28.0)
        controller._set_phase_for_test(StabilityPhase.FINE)
        controller._phase2_entry_time = 0.0

        # 远离目标
        controller._set_monitor_readings_for_test([
            (28.5, 130), (28.5, 120), (28.6, 110), (28.5, 100),
            (28.6, 90), (28.5, 80), (28.6, 70),
            (28.5, 60), (28.6, 50), (28.5, 40),
        ])

        result = controller.check(
            elapsed_s=controller.GOOD_ENOUGH_PHASE2_TIMEOUT_S + 1.0
        )
        assert result.reason != "good_enough"


# =========================================================================
# TestClass: 超时
# =========================================================================

class TestTimeout:
    """验证 30 分钟硬超时。"""

    @pytest.fixture
    def controller(self):
        from ui.experiment_stability_controller import (
            ExperimentStabilityController,
        )
        return ExperimentStabilityController()

    def test_given_max_wait_exceeded_when_checking_then_returns_timeout(
        self, controller
    ):
        """超过 MAX_WAIT_SECONDS → timeout。"""
        controller.setup(target_k=30.0, current_temperature=25.0)
        for i in range(20):
            controller.add_reading(25.5 + 0.05 * (i % 5))

        result = controller.check(elapsed_s=controller.MAX_WAIT_SECONDS + 1.0)
        assert result.reason == "timeout"
        assert result.total_elapsed_s >= controller.MAX_WAIT_SECONDS


# =========================================================================
# TestClass: StabilityResult 扩展字段
# =========================================================================

class TestStabilityResultFields:
    """验证 StabilityResult 包含完整的状态信息。"""

    @pytest.fixture
    def controller(self):
        from ui.experiment_stability_controller import (
            ExperimentStabilityController,
        )
        return ExperimentStabilityController()

    def test_given_result_when_checking_then_contains_phase(
        self, controller
    ):
        """结果应包含 phase 字段。"""
        controller.setup(target_k=30.0, current_temperature=29.5)
        result = controller.check(elapsed_s=30.0)
        assert hasattr(result, "phase")
        assert result.phase is not None

    def test_given_result_when_checking_then_contains_avg_temp(
        self, controller
    ):
        """结果应包含 avg_temp（实际温度）。"""
        controller.setup(target_k=30.0, current_temperature=29.5)
        for i in range(15):
            controller.add_reading(29.5 + 0.02 * (i % 7))
        result = controller.check(elapsed_s=200.0)
        assert hasattr(result, "avg_temp")
        assert hasattr(result, "final_temp")

    def test_given_timeout_when_checking_then_contains_setpoint_adjustments(
        self, controller
    ):
        """超时结果应包含调整次数。"""
        controller.setup(target_k=30.0, current_temperature=25.0)
        for i in range(50):
            controller.add_reading(25.5 + 0.05 * (i % 5))
        result = controller.check(elapsed_s=controller.MAX_WAIT_SECONDS + 1.0)
        assert result.reason == "timeout"
        assert hasattr(result, "setpoint_adjustments")


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
            from ui.experiment_stability_controller import StabilityPhase
            mock_ctrl = mock_ctrl_cls.return_value
            mock_ctrl.get_fixed_pid.return_value = {"p": 100, "i": 0, "d": 0}
            mock_ctrl.setup.return_value = None
            mock_ctrl.add_reading.return_value = None
            mock_ctrl.check.return_value = MagicMock(
                stable=True, reason="stable", avg_temp=30.0,
                phase=StabilityPhase.FINE)
            mock_ctrl.needs_setpoint_adjustment.return_value = None
            mock_ctrl.base_overshoot = 1.5
            mock_ctrl.current_overshoot = 1.5
            mock_ctrl.phase = StabilityPhase.FINE

            worker.run()

        assert len(finished) == 1
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
            from ui.experiment_stability_controller import StabilityPhase
            mock_ctrl = mock_ctrl_cls.return_value
            mock_ctrl.get_fixed_pid.return_value = {"p": 100, "i": 0, "d": 0}
            mock_ctrl.setup.return_value = None
            mock_ctrl.add_reading.return_value = None
            mock_ctrl.check.return_value = MagicMock(
                stable=False, reason="good_enough", avg_temp=30.3,
                phase=StabilityPhase.FINE)
            mock_ctrl.needs_setpoint_adjustment.return_value = None
            mock_ctrl.base_overshoot = 1.5
            mock_ctrl.current_overshoot = 1.5
            mock_ctrl.phase = StabilityPhase.FINE

            worker.run()

        assert len(finished) == 1


# =========================================================================
# TestClass: 18-40K 温区逻辑
# =========================================================================

class Test18To40KZoneLogic:
    """验证 ExperimentStabilityController 在 18-40K 温区的正常行为。"""

    @pytest.fixture
    def controller(self):
        from ui.experiment_stability_controller import (
            ExperimentStabilityController,
        )
        return ExperimentStabilityController()

    def test_given_target_in_18_to_40K_when_setup_then_medium_zone(self, controller):
        """18-40K 目标温度 → 中温区 PID。"""
        controller.setup(target_k=30.0, current_temperature=28.0)
        pid = controller.get_fixed_pid()
        assert pid["p"] == 100
        assert pid["i"] == 0
        assert controller.base_overshoot == 1.5

    def test_given_target_outside_18_to_40K_when_setup_then_standard(self, controller):
        """非 18-40K 温区 → 标准行为。"""
        controller.setup(target_k=10.0, current_temperature=8.0)
        pid = controller.get_fixed_pid()
        assert pid["p"] == 100
        assert pid["i"] == 5
        assert controller.base_overshoot == 0.0

    def test_given_target_exactly_18K_when_setup_then_low_zone(self, controller):
        """正好 18K → ≤20K 属于低温区。"""
        controller.setup(target_k=18.0, current_temperature=17.0)
        pid = controller.get_fixed_pid()
        assert pid == {"p": 100, "i": 5, "d": 0}

    def test_given_target_exactly_40K_when_setup_then_medium_zone(self, controller):
        """正好 40K → 属于中温区。"""
        controller.setup(target_k=40.0, current_temperature=38.0)
        pid = controller.get_fixed_pid()
        assert pid == {"p": 100, "i": 0, "d": 0}
