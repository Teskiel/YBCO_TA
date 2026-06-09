# -*- coding: utf-8 -*-
"""
实验稳定性控制器 — 2 阶段 + 并行双轨判定。

核心理念：
  - PID 参数按温区硬编码，**永不调整**
  - 三概念分离：趋于平稳 / 进入目标区间 / 进入稳态
  - 只有「进入目标区间」且「进入稳态」同时满足才可测量

2 阶段轮询：
  Phase 1 (sparse) — 低频（30s），等待 trending_stable
  Phase 2 (fine)   — 高频（5s）， 并行判 in_target_zone + steady_state

过冲调整：
  触发条件: trending_stable=True AND in_target_zone=False
  冷却时间: 120s 内不重复调整
  调整量:   overshoot = base + (target − avg)，钳位 [base, MAX_OVERSHOOT_K]

用法：
    ctrl = ExperimentStabilityController()
    ctrl.setup(target_k=30.0, current_temperature=25.0)

    # Phase 1: 每 30s
    ctrl.add_reading(actual_k)
    result = ctrl.check(elapsed_s)
    if ctrl.phase == "fine":
        ...  # 切换到 5s 轮询

    # Phase 2: 每 5s
    if result.stable:  测量()
    sp = ctrl.needs_setpoint_adjustment()
    if sp:  lakeshore.set_temperature(sp, loop=1)
"""

import time as _time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

from stability_monitor import AdvancedStabilityMonitor


# =========================================================================
# 数据定义
# =========================================================================

class StabilityPhase(str, Enum):
    """轮询阶段。"""
    SPARSE = "sparse"   # 低频 — 等待趋于平稳
    FINE = "fine"       # 高频 — 并行判目标区间 + 稳态


@dataclass
class StabilityResult:
    """稳定性检查的结果。"""
    stable: bool                     # in_target_zone AND steady_state 同时满足
    reason: str                      # "stable", "waiting", "good_enough", "timeout"
    phase: StabilityPhase            # 当前轮询阶段
    avg_temp: float                  # 平均温度
    final_temp: float = 0.0
    stable_duration_s: float = 0.0
    total_elapsed_s: float = 0.0
    setpoint_adjustments: int = 0    # 已应用的设定点调整次数


# =========================================================================
# ExperimentStabilityController
# =========================================================================

class ExperimentStabilityController:
    """2 阶段稳定性控制器：固定 PID + 并行双轨判定。

    PID 参数永不改变，仅通过设定点过冲推动温度。
    三概念分离：趋于平稳 → 进入目标区间 + 进入稳态 → 可测量。
    """

    # 默认参数
    MAX_OVERSHOOT_K = 10.0
    GOOD_ENOUGH_BAND_K = 0.5
    STABLE_HOLD_SECONDS = 120
    MAX_WAIT_SECONDS = 30 * 60
    OVERSHOOT_COOLDOWN_S = 120       # 过冲调整冷却时间
    MAX_OVERSHOOT_ADJUSTMENTS = 2    # 至多调整 2 次
    GOOD_ENOUGH_PHASE2_TIMEOUT_S = 600  # Phase 2 中 10 分钟后 good_enough

    def __init__(self):
        self._target_k: float = 0.0
        self._phase: StabilityPhase = StabilityPhase.SPARSE
        self._monitor = AdvancedStabilityMonitor()
        self._fixed_pid: Dict[str, float] = {"p": 100.0, "i": 0.0, "d": 0.0}
        self._base_overshoot: float = 0.0
        self._current_overshoot: float = 0.0
        self._setpoint_adjust_count: int = 0
        self._last_overshoot_time: float = 0.0
        self._last_stable_time: Optional[float] = None
        self._start_time: float = 0.0
        self._phase2_entry_time: float = 0.0
        self._adj_returned_this_cycle: bool = False
        self._initial_setpoint_written: bool = False

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def setup(self, target_k: float, current_temperature: float):
        """为新温度目标初始化。

        根据温区查找固定 PID 和基础过冲。

        Args:
            target_k: 目标温度 (K)
            current_temperature: 当前实际温度 (K)
        """
        import config

        self._target_k = target_k
        self._phase = StabilityPhase.SPARSE
        self._monitor.clear()
        self._last_stable_time = None
        self._last_overshoot_time = 0.0
        self._start_time = 0.0
        self._phase2_entry_time = 0.0
        self._setpoint_adjust_count = 0
        self._adj_returned_this_cycle = False
        self._initial_setpoint_written = False

        zone = self._find_zone(target_k)
        self._fixed_pid = {"p": zone["p"], "i": zone["i"], "d": zone["d"]}
        self._base_overshoot = zone["base_overshoot_k"]
        self._current_overshoot = zone["base_overshoot_k"]

    def add_reading(self, temperature: float):
        """添加温度读数到稳定性监视器。

        Args:
            temperature: 当前实际温度 (K)
        """
        now = _time.monotonic()
        if self._start_time == 0.0:
            self._start_time = now

        self._monitor.add_reading(temperature, self._target_k)

    def check(self, elapsed_s: float) -> StabilityResult:
        """检查稳定性并管理阶段转换。

        Args:
            elapsed_s: 自稳定性等待开始以来的总秒数

        Returns:
            StabilityResult — 包含稳定状态、原因、当前阶段
        """
        now = _time.monotonic()

        # 底层稳定性判定
        stability = self._monitor.check_stability(self._target_k)
        trending_stable = stability.get("trending_stable", False)
        in_target_zone = stability.get("in_target_zone", False)
        steady_state = stability.get("steady_state", False)
        avg_temp = stability.get("avg_temp", self._target_k)
        if avg_temp is None:
            avg_temp = self._target_k

        # ---- 阶段转换: SPARSE → FINE ----
        if self._phase == StabilityPhase.SPARSE and trending_stable:
            self._phase = StabilityPhase.FINE
            self._phase2_entry_time = elapsed_s

        # ---- 稳定判定: 双轨同时满足 ----
        if in_target_zone and steady_state:
            if self._last_stable_time is None:
                self._last_stable_time = now
            hold_duration = now - self._last_stable_time
            if hold_duration >= self.STABLE_HOLD_SECONDS:
                return StabilityResult(
                    stable=True,
                    reason="stable",
                    phase=self._phase,
                    avg_temp=avg_temp,
                    final_temp=avg_temp,
                    stable_duration_s=hold_duration,
                    total_elapsed_s=elapsed_s,
                    setpoint_adjustments=self._setpoint_adjust_count,
                )
        else:
            self._last_stable_time = None

        # ---- good_enough 回退: Phase 2 中 10 分钟后 in_target_zone 但未稳态 ----
        if (self._phase == StabilityPhase.FINE
                and in_target_zone
                and not steady_state):
            time_in_phase2 = elapsed_s - self._phase2_entry_time
            if time_in_phase2 >= self.GOOD_ENOUGH_PHASE2_TIMEOUT_S:
                return StabilityResult(
                    stable=False,
                    reason="good_enough",
                    phase=self._phase,
                    avg_temp=avg_temp,
                    final_temp=avg_temp,
                    total_elapsed_s=elapsed_s,
                    setpoint_adjustments=self._setpoint_adjust_count,
                )

        # ---- 超时 ----
        if elapsed_s >= self.MAX_WAIT_SECONDS:
            return StabilityResult(
                stable=False,
                reason="timeout",
                phase=self._phase,
                avg_temp=avg_temp,
                final_temp=avg_temp,
                total_elapsed_s=elapsed_s,
                setpoint_adjustments=self._setpoint_adjust_count,
            )

        # ---- 仍在等待 ----
        return StabilityResult(
            stable=False,
            reason="waiting",
            phase=self._phase,
            avg_temp=avg_temp,
            final_temp=avg_temp,
            total_elapsed_s=elapsed_s,
            setpoint_adjustments=self._setpoint_adjust_count,
        )

    def needs_setpoint_adjustment(self) -> Optional[float]:
        """返回新的设定点温度（如果需要调整），否则 None。

        触发条件（同时满足）：
          1. trending_stable（趋于平稳）
          2. NOT in_target_zone（尚未进入目标区间）
          3. 距上次调整 ≥ OVERSHOOT_COOLDOWN_S
          4. 调整次数 < MAX_OVERSHOOT_ADJUSTMENTS

        调整量: overshoot = base + (target − avg)，钳位 [base, MAX_OVERSHOOT_K]

        Returns:
            新的设定点温度 (K)，或 None
        """
        if self._setpoint_adjust_count >= self.MAX_OVERSHOOT_ADJUSTMENTS:
            return None

        # 首次调用 — 无条件返回初始设定点
        if not self._initial_setpoint_written:
            self._initial_setpoint_written = True
            now = _time.monotonic()
            self._last_overshoot_time = now
            return self._calculate_setpoint_from_overshoot()

        # 后续调整需满足: trending_stable AND NOT in_target_zone
        stability = self._monitor.check_stability(self._target_k)
        trending_stable = stability.get("trending_stable", False)
        in_target_zone = stability.get("in_target_zone", False)
        avg_temp = stability.get("avg_temp", self._target_k)
        if avg_temp is None:
            avg_temp = self._target_k

        if not trending_stable:
            return None
        if in_target_zone:
            return None

        # 冷却时间保护
        now = _time.monotonic()
        if now - self._last_overshoot_time < self.OVERSHOOT_COOLDOWN_S:
            return None

        # 过冲调整
        delta = self._target_k - avg_temp
        if delta > 0:
            self._current_overshoot = min(
                self._base_overshoot + delta,
                self.MAX_OVERSHOOT_K,
            )
        self._setpoint_adjust_count += 1
        self._last_overshoot_time = now

        return self._calculate_setpoint_from_overshoot()

    def get_fixed_pid(self) -> Dict[str, float]:
        """返回当前温区的固定 PID 参数（永不改变）。"""
        return dict(self._fixed_pid)

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def phase(self) -> StabilityPhase:
        """当前轮询阶段（sparse / fine）。"""
        return self._phase

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
        return min(sp, self._target_k + self.MAX_OVERSHOOT_K)

    # ------------------------------------------------------------------
    # 测试辅助方法
    # ------------------------------------------------------------------

    def _set_phase_for_test(self, phase: StabilityPhase):
        """测试辅助：直接设置阶段。"""
        self._phase = phase
        if phase == StabilityPhase.FINE and self._phase2_entry_time == 0.0:
            self._phase2_entry_time = 60.0
        if self._start_time == 0.0:
            self._start_time = _time.monotonic()

    def _set_monitor_readings_for_test(self, readings: list):
        """测试辅助：直接写入监视器读数。

        Args:
            readings: list of (temperature, seconds_ago) tuples
        """
        now = _time.time()
        from stability_monitor import TemperatureReading
        self._monitor.readings = [
            TemperatureReading(
                timestamp=now - ago,
                temperature=temp,
                target=self._target_k,
            )
            for temp, ago in readings
        ]
