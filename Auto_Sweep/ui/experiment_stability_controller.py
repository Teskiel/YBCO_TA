# -*- coding: utf-8 -*-
"""
实验稳定性控制器 — 简化版：固定 PID + 仅调整设定点过冲。

核心理念：
  - PID 参数按温区硬编码，**永不调整**
  - 温度未达稳态时，不修改 P/I/D，而是增大设定点过冲
  - 过冲调节幅度 Δ = 目标温度 - 实际温度

温区固定参数（来自 config.FIXED_PID_ZONES）：
  ≤20K:    P=100, I=5, D=0,  base_overshoot=0
  20-40K:  P=100, I=0, D=0,  base_overshoot=1.5K
  >40K:    P=150, I=0, D=0,  base_overshoot=2.0K

状态机：
  State 0: INITIAL_SETPOINT — 固定PID + 基础过冲设定点
  State 1: SETPOINT_ADJUST_1 — 过冲 = base + (target - actual_avg)
  State 2: SETPOINT_ADJUST_2 — 过冲 = base + (target - actual_avg)
  → 最终判定: |avg - target| ≤ 0.5K → good_enough，否则超时

稳定性条件（来自 config.custom_stability_settings）：
  final_stable_band_k = 0.5K（已从 0.2K 放宽）

用法：
    ctrl = ExperimentStabilityController()
    ctrl.setup(target_k=30.0, current_temperature=25.0)

    # 循环中每 10 秒：
    ctrl.add_reading(actual_k)
    result = ctrl.check(elapsed_s=elapsed)

    if result.stable or result.reason == "good_enough":
        测量()

    # 获取设定点调整（如果有）
    sp_adj = ctrl.needs_setpoint_adjustment()
    if sp_adj:
        lakeshore.set_temperature(sp_adj, loop=1)
"""

import time as _time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, Optional

from stability_monitor import AdvancedStabilityMonitor


# =========================================================================
# 数据定义
# =========================================================================

class StabilityState(IntEnum):
    """稳定性状态机的状态枚举。"""
    INITIAL_SETPOINT = 0   # 初始设定点（固定PID + 基础过冲）
    SETPOINT_ADJUST_1 = 1  # 设定点调整 #1
    SETPOINT_ADJUST_2 = 2  # 设定点调整 #2


@dataclass
class StabilityResult:
    """稳定性检查的结果。"""
    stable: bool                     # 是否达到稳定（±0.5K 持续 60s）
    reason: str                      # "stable", "waiting", "good_enough", "timeout"
    final_state: StabilityState      # 最终状态
    final_temp: float                # 最终温度
    avg_temp: float                  # 平均温度
    stable_duration_s: float = 0.0
    total_elapsed_s: float = 0.0
    setpoint_adjustments: int = 0    # 已应用的设定点调整次数


# =========================================================================
# ExperimentStabilityController
# =========================================================================

class ExperimentStabilityController:
    """简化版稳定性控制器：固定 PID + 仅调整设定点过冲。

    PID 参数永不改变，仅通过增大设定点过冲来推动温度达到目标。
    """

    # 默认参数（可从 config 覆盖）
    MAX_SETPOINT_ADJUSTMENTS = 2
    GOOD_ENOUGH_BAND_K = 0.5
    DIAGNOSTIC_INTERVAL_S = 60
    STABLE_HOLD_SECONDS = 60
    MAX_WAIT_SECONDS = 30 * 60
    MAX_OVERSHOOT_K = 10.0  # 设定点过冲安全上限

    def __init__(self):
        self._target_k: float = 0.0
        self._state: StabilityState = StabilityState.INITIAL_SETPOINT
        self._monitor = AdvancedStabilityMonitor()
        self._fixed_pid: Dict[str, float] = {"p": 100.0, "i": 0.0, "d": 0.0}
        self._base_overshoot: float = 0.0
        self._current_overshoot: float = 0.0
        self._setpoint_adjust_count: int = 0
        self._last_stable_time: Optional[float] = None
        self._state_elapsed_at_entry: float = 0.0
        self._start_time: float = 0.0
        self._adj_returned_for_state: Optional[StabilityState] = None

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def setup(self, target_k: float, current_temperature: float):
        """为新温度目标初始化。

        根据温区查找固定 PID 和基础过冲，写入 self._fixed_pid。

        Args:
            target_k: 目标温度 (K)
            current_temperature: 当前实际温度 (K)
        """
        import config

        self._target_k = target_k
        self._state = StabilityState.INITIAL_SETPOINT
        self._monitor.clear()
        self._last_stable_time = None
        self._state_elapsed_at_entry = 0.0
        self._start_time = 0.0
        self._setpoint_adjust_count = 0
        self._adj_returned_for_state = None

        # 查找温区对应的固定 PID 和基础过冲
        zone = self._find_zone(target_k)
        self._fixed_pid = {"p": zone["p"], "i": zone["i"], "d": zone["d"]}
        self._base_overshoot = zone["base_overshoot_k"]
        self._current_overshoot = zone["base_overshoot_k"]

    def add_reading(self, temperature: float):
        """添加温度读数到稳定性监视器。

        每 10 秒由 ExperimentWorker 调用一次。

        Args:
            temperature: 当前实际温度 (K)
        """
        now = _time.monotonic()
        if self._start_time == 0.0:
            self._start_time = now
            self._state_elapsed_at_entry = 0.0

        self._monitor.add_reading(temperature, self._target_k)

    def check(self, elapsed_s: float) -> StabilityResult:
        """检查稳定性并推进状态机。

        每 10 秒由 ExperimentWorker 调用一次。

        Args:
            elapsed_s: 自稳定性等待开始以来的总秒数

        Returns:
            StabilityResult — 包含稳定状态、原因
        """
        now = _time.monotonic()

        # 1. 检查稳定性
        stability = self._monitor.check_stability(self._target_k, method="custom")
        is_stable = stability.get("stable", False)
        avg_temp = stability.get("avg_temp", self._target_k)
        if avg_temp is None:
            avg_temp = self._target_k

        # 2. 跟踪稳定持续时间
        if is_stable:
            if self._last_stable_time is None:
                self._last_stable_time = now
            hold_duration = now - self._last_stable_time
            if hold_duration >= self.STABLE_HOLD_SECONDS:
                return StabilityResult(
                    stable=True,
                    reason="stable",
                    final_state=self._state,
                    final_temp=avg_temp,
                    avg_temp=avg_temp,
                    stable_duration_s=hold_duration,
                    total_elapsed_s=elapsed_s,
                    setpoint_adjustments=self._setpoint_adjust_count,
                )
        else:
            self._last_stable_time = None

        # 3. 如果不稳定，检查是否需要推进状态
        time_in_state = elapsed_s - self._state_elapsed_at_entry
        if not is_stable and time_in_state >= self.DIAGNOSTIC_INTERVAL_S:
            self._advance_state(elapsed_s, avg_temp)

        # 4. 最终判定：State 2 等待期过后检查 ±0.5K
        if self._state == StabilityState.SETPOINT_ADJUST_2:
            time_in_final = elapsed_s - self._state_elapsed_at_entry
            if time_in_final >= self.DIAGNOSTIC_INTERVAL_S:
                if abs(avg_temp - self._target_k) <= self.GOOD_ENOUGH_BAND_K:
                    return StabilityResult(
                        stable=False,
                        reason="good_enough",
                        final_state=self._state,
                        final_temp=avg_temp,
                        avg_temp=avg_temp,
                        total_elapsed_s=elapsed_s,
                        setpoint_adjustments=self._setpoint_adjust_count,
                    )

        # 5. 总超时检查
        if elapsed_s >= self.MAX_WAIT_SECONDS:
            return StabilityResult(
                stable=False,
                reason="timeout",
                final_state=self._state,
                final_temp=avg_temp,
                avg_temp=avg_temp,
                total_elapsed_s=elapsed_s,
                setpoint_adjustments=self._setpoint_adjust_count,
            )

        # 6. 仍在等待
        return StabilityResult(
            stable=False,
            reason="waiting",
            final_state=self._state,
            final_temp=avg_temp,
            avg_temp=avg_temp,
            total_elapsed_s=elapsed_s,
            setpoint_adjustments=self._setpoint_adjust_count,
        )

    def needs_setpoint_adjustment(self) -> Optional[float]:
        """返回新的设定点温度（如果需要调整），否则 None。

        每个状态只返回一次调整。
        设定点 = target + 当前过冲量。
        过冲量在状态推进时更新。

        Returns:
            新的设定点温度 (K)，或 None
        """
        if self._adj_returned_for_state == self._state:
            return None

        self._adj_returned_for_state = self._state

        if self._state == StabilityState.INITIAL_SETPOINT:
            # 返回初始设定点
            return self._calculate_setpoint_from_overshoot()
        elif self._state in (StabilityState.SETPOINT_ADJUST_1,
                             StabilityState.SETPOINT_ADJUST_2):
            return self._calculate_setpoint_from_overshoot()

        return None

    def get_fixed_pid(self) -> Dict[str, float]:
        """返回当前温区的固定 PID 参数（永不改变）。"""
        return dict(self._fixed_pid)

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def current_state(self) -> StabilityState:
        return self._state

    @property
    def current_overshoot(self) -> float:
        """当前过冲量 (K)。"""
        return self._current_overshoot

    @property
    def base_overshoot(self) -> float:
        """基础过冲量 (K)。"""
        return self._base_overshoot

    @property
    def setpoint_adjust_count(self) -> int:
        return self._setpoint_adjust_count

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _find_zone(target_k: float) -> dict:
        """根据目标温度查找温区配置。"""
        import config
        for zone_name in ("low", "medium", "high"):
            zone = config.FIXED_PID_ZONES[zone_name]
            if target_k <= zone["max_temp"]:
                return zone
        return config.FIXED_PID_ZONES["high"]

    def _calculate_setpoint_from_overshoot(self) -> float:
        """根据当前过冲量计算设定点温度。

        冷却时（无过冲）：设定点 = 目标温度。
        升温时：设定点 = 目标温度 + 过冲量（钳位）。
        """
        if self._current_overshoot <= 0:
            return self._target_k
        sp = self._target_k + self._current_overshoot
        # 安全上限
        return min(sp, self._target_k + self.MAX_OVERSHOOT_K)

    def _advance_state(self, elapsed_s: float, avg_temp: float):
        """推进状态机并更新过冲量。

        过冲调节幅度：Δ = 目标温度 - 平均温度（正值表示需要升温）。
        新的过冲 = 基础过冲 + Δ（钳位在 [base, MAX_OVERSHOOT_K]）。

        Args:
            elapsed_s: 当前总耗时
            avg_temp: 当前平均温度（来自稳定性监视器）
        """
        delta = self._target_k - avg_temp  # 需要升温的量

        if self._state == StabilityState.INITIAL_SETPOINT:
            self._state = StabilityState.SETPOINT_ADJUST_1
            self._setpoint_adjust_count = 1
            # 第一次调整：过冲 = base + Δ
            if delta > 0:
                self._current_overshoot = min(
                    self._base_overshoot + delta,
                    self.MAX_OVERSHOOT_K,
                )
        elif self._state == StabilityState.SETPOINT_ADJUST_1:
            self._state = StabilityState.SETPOINT_ADJUST_2
            self._setpoint_adjust_count = 2
            # 第二次调整：在现有基础上继续加大
            if delta > 0:
                self._current_overshoot = min(
                    max(self._current_overshoot, self._base_overshoot + delta),
                    self.MAX_OVERSHOOT_K,
                )
        # SETPOINT_ADJUST_2 不进一步推进

        self._state_elapsed_at_entry = elapsed_s
        self._adj_returned_for_state = None  # 新状态可以返回调整

    # ------------------------------------------------------------------
    # 测试辅助方法
    # ------------------------------------------------------------------

    def _advance_to_state_for_test(self, target_state: StabilityState):
        """测试辅助：直接设置状态机到指定状态。"""
        self._state = target_state
        self._state_elapsed_at_entry = 0.0
        self._setpoint_adjust_count = int(target_state)
        self._adj_returned_for_state = None
        if self._start_time == 0.0:
            self._start_time = _time.monotonic()
