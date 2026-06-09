# -*- coding: utf-8 -*-
"""
Temperature stability monitoring algorithms.

Pure algorithm module — no hardware or VISA dependencies.

Three independent concepts:
  - trending_stable: |window₀−window₂| ≤ 0.2K (over 2 min) → 趋于平稳
  - in_target_zone:  |1min_avg−target| ≤ 0.5K → 进入目标区间
  - steady_state:    3-min window max−min ≤ 0.1K → 进入稳态

stable = in_target_zone AND steady_state (两者并行，无先后关系)

Usage:
    from stability_monitor import AdvancedStabilityMonitor

    monitor = AdvancedStabilityMonitor()
    monitor.add_reading(30.05, target=30.0)
    result = monitor.check_stability(30.0)
    if result["stable"]:
        print("Ready to measure!")
"""

from dataclasses import dataclass
from time import time
from typing import List, Optional


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class TemperatureReading:
    timestamp: float
    temperature: float
    target: float


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

class AdvancedStabilityMonitor:
    """Ring-buffer-based temperature stability analyser.

    Uses rolling 1-minute averages for two coarse checks, plus a 3-minute
    max-min window for steady-state detection:

      Phase A — trending_stable: |window₀−window₂| ≤ 0.2K (over 2 min) → 趋于平稳
      Phase B — in_target_zone:  |1min_avg−target| ≤ 0.5K → 进入目标区间
      Phase C — steady_state:    3-min max−min ≤ 0.1K → 进入稳态

    stable = in_target_zone AND steady_state (parallel, no ordering).
    """

    def __init__(self):
        self.readings: List[TemperatureReading] = []
        self.max_readings = 1000

    # ---- data management ----

    def add_reading(self, temperature: float, target: float):
        """Append a reading with the current timestamp."""
        reading = TemperatureReading(
            timestamp=time(),
            temperature=temperature,
            target=target,
        )
        self.readings.append(reading)
        if len(self.readings) > self.max_readings:
            self.readings.pop(0)

    def clear(self):
        """Discard all stored readings."""
        self.readings = []

    def _get_recent_readings(self, window_seconds: float = 60) -> List[TemperatureReading]:
        if not self.readings:
            return []
        current_time = time()
        return [r for r in self.readings if current_time - r.timestamp < window_seconds]

    # ---- stability method ----

    def check_stability(self, target_k: float, method: str = "custom",
                         settings: Optional[dict] = None) -> dict:
        """滚动 1 分钟均值稳定性检测，含三概念分离。

        三个独立概念：
          - trending_stable (条件2): |window₀−window₂| ≤ 0.2K (over 2 min) → 趋于平稳
          - in_target_zone  (条件3): |1min_avg−target| ≤ 0.5K → 进入目标区间
          - steady_state    (新):   3 分钟窗口 max−min ≤ 0.1K → 进入稳态

        ``stable`` = in_target_zone AND steady_state（两者并行，无先后关系）。
        ``ready_for_adjust`` = trending_stable（用于触发设定点过冲调整）。
        """
        if settings is None:
            from config import custom_stability_settings as settings

        avg_window = settings.get("avg_window_seconds", 60)
        avg_tolerance = settings.get("avg_tolerance_k", 0.5)
        delta_tolerance = settings.get("delta_tolerance_k", 0.3)
        final_band = settings.get("final_stable_band_k", 0.3)
        min_readings = settings.get("min_readings_required", 6)

        # 稳态判定参数
        from config import steady_state_max_min_k, steady_state_window_s
        ss_max_min = steady_state_max_min_k
        ss_window = steady_state_window_s

        current_time = time()

        # 回溯窗口内的读数
        all_recent = [r for r in self.readings if current_time - r.timestamp < 180]

        if len(all_recent) < min_readings:
            return {
                "stable": False,
                "method": "custom",
                "reason": f"Need at least {min_readings} readings, have {len(all_recent)}",
                "avg_temp": None,
                "avg_delta": None,
                "trending_stable": False,
                "in_target_zone": False,
                "steady_state": False,
                "max_min_3min": None,
                "in_final_band": False,
                "ready_for_adjust": False,
            }

        # ---- 滚动 1 分钟均值窗口 ----
        minute_windows = []
        for i in range(3):
            window_start = current_time - (i + 1) * avg_window
            window_end = current_time - i * avg_window
            window_readings = [
                r for r in all_recent
                if window_start <= r.timestamp < window_end
            ]
            if len(window_readings) >= 3:
                window_avg = sum(r.temperature for r in window_readings) / len(window_readings)
                minute_windows.append({
                    "start": window_start,
                    "end": window_end,
                    "avg": window_avg,
                    "count": len(window_readings),
                })

        minute_windows.sort(key=lambda x: x["end"], reverse=True)

        if not minute_windows:
            return {
                "stable": False,
                "method": "custom",
                "reason": "No valid 1-minute windows",
                "avg_temp": None,
                "avg_delta": None,
                "trending_stable": False,
                "in_target_zone": False,
                "steady_state": False,
                "max_min_3min": None,
                "in_final_band": False,
                "ready_for_adjust": False,
            }

        latest_avg = minute_windows[0]["avg"]

        # ---- 条件 1: 粗判（1-min 均值在 ±avg_tolerance 内） ----
        condition1 = abs(latest_avg - target_k) <= avg_tolerance

        # ---- 条件 2: 趋于平稳（跨 2 分钟窗口均值变化 < delta_tolerance） ----
        condition2 = False
        avg_delta = None
        if len(minute_windows) >= 3:
            # 窗口 [0]=最新, [2]=2分钟前 → 跨 2 分钟的比较
            avg_delta = abs(minute_windows[0]["avg"] - minute_windows[2]["avg"])
            condition2 = avg_delta <= delta_tolerance

        # ---- 条件 3: 进入目标区间（1-min 均值在 ±final_band 内） ----
        condition3 = abs(latest_avg - target_k) <= final_band

        # ---- 稳态判定: 3 分钟窗口 max-min ≤ ss_max_min ----
        steady_readings = [
            r for r in self.readings
            if current_time - r.timestamp <= ss_window
        ]
        max_min_3min = None
        steady_state = False
        if len(steady_readings) >= 6:
            temps = [r.temperature for r in steady_readings]
            max_min_3min = max(temps) - min(temps)
            steady_state = max_min_3min <= ss_max_min

        # ---- 汇总 ----
        trending_stable = condition2
        in_target_zone = condition3
        is_stable = in_target_zone and steady_state

        reasons = []
        if not condition1:
            reasons.append(f"1-min avg {latest_avg:.3f}K not within ±{avg_tolerance}K of target")
        if not condition2 and avg_delta is not None:
            reasons.append(f"2 分钟窗口漂移 {avg_delta:.3f}K > {delta_tolerance}K（未趋于平稳）")
        if not condition3:
            reasons.append(f"未进入目标区间 ±{final_band}K（Δ={abs(latest_avg - target_k):.3f}K）")
        if not steady_state:
            if max_min_3min is not None:
                reasons.append(f"未进入稳态: 3min max-min={max_min_3min:.3f}K > {ss_max_min}K")
            else:
                reasons.append(f"稳态数据不足（需 ≥6 个读数在 {ss_window}s 内）")

        return {
            "stable": is_stable,
            "method": "custom",
            "avg_temp": latest_avg,
            "avg_delta": avg_delta,
            "trending_stable": trending_stable,
            "in_target_zone": in_target_zone,
            "steady_state": steady_state,
            "max_min_3min": max_min_3min,
            "in_final_band": in_target_zone,
            "ready_for_adjust": trending_stable,
            "reason": "Stable" if is_stable else f'Failed: {", ".join(reasons)}',
            "minute_windows": minute_windows,
        }

