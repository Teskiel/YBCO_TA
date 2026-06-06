# -*- coding: utf-8 -*-
"""
Experiment configuration constants.

All sweep parameters, instrument addresses, PID values, and stability
criteria live here so they can be changed in one place without touching
any instrument or algorithm code.

Dead code removed from the original power_sweep_auto.py:
  - TRACE_NAME         (declared but never referenced)
  - auto_adjust_pid    (never read by any code path)
  - diagnose_before_measure (never read by any code path)
"""

# =========================================================================
# Instrument resource addresses
# =========================================================================

resource_vna = "TCPIP0::localhost::hislip_PXI10_CHASSIS1_SLOT1_INDEX0::INSTR"
laser_resource = "TCPIP0::K-N7779C-00108::inst0::INSTR"
resource_lakeshore = "ASRL4::INSTR"

# =========================================================================
# Output paths
# =========================================================================

date = "20260529"
base_folder = rf"D:\YBCO\VNAMeas\data\{date}\-45dBm_temperature_sweep"

# =========================================================================
# Sweep ranges
# =========================================================================

power_levels_mw = [0, 1, 3, 5, 7, 9]

# Start from 26 K, step 2 K up to 100 K
temperature_levels_k = list(range(26, 101, 2))

# =========================================================================
# Temperature stability parameters
# =========================================================================

temperature_tolerance_k = 0.50       # only used by check_stability_simple
stable_hold_seconds = 60             # must stay stable this long before measuring
max_wait_seconds = 30 * 60           # 30-minute timeout per temperature point
temperature_poll_seconds = 10        # polling interval (~6 readings/min)

stability_method = "custom"          # "simple" | "v1" | "v2" | "v3" | "custom"

custom_stability_settings = {
    "avg_window_seconds": 60,        # 1-minute rolling window
    "avg_tolerance_k": 1.0,          # average within ±1.0 K of setpoint
    "delta_tolerance_k": 0.5,        # max drift between consecutive windows
    "final_stable_band_k": 0.5,      # 放宽标准：±0.5 K（原 0.2K）
    "min_readings_required": 10,     # 匹配 180s 回溯窗口 + 10s 轮询（最多 18 个读数）
}

# =========================================================================
# Setpoint adjustment (overshoot / undershoot compensation)
# =========================================================================

setpoint_adjust_settings = {
    "low_temp_threshold": 20.0,      # below 20 K: no overshoot, setpoint = target
    "medium_temp_threshold": 40.0,   # 20–40 K: apply limited overshoot
    "max_overshoot_k": 1.0,          # cap on overshoot amount
    "overshoot_factor": 0.5,         # multiplier on temperature error
}

# =========================================================================
# PID parameters (temperature-zone-dependent)
# =========================================================================

PID_PARAMS = {
    "low_temp":    {"p": 100.0, "i": 5.0, "d": 0.0, "max_temp": 20.0},
    "medium_temp": {"p": 100.0, "i": 0.0, "d": 0.0, "min_temp": 20.0, "max_temp": 40.0},
    "high_temp":   {"p": 150.0, "i": 0.0, "d": 0.0, "min_temp": 40.0},
}

# =========================================================================
# 自动重连设置
# =========================================================================

max_reconnect_attempts = 3          # 最大重连尝试次数
reconnect_delay_seconds = 2         # 重连前等待秒数

# =========================================================================
# 实验稳定性回退设置（简化版：固定PID + 仅调整设定点过冲）
# =========================================================================

# 各温区固定 PID 参数（永不调整）
FIXED_PID_ZONES = {
    "low":    {"max_temp": 20.0, "p": 100, "i": 5, "d": 0, "base_overshoot_k": 0.0},
    "medium": {"max_temp": 40.0, "p": 100, "i": 0, "d": 0, "base_overshoot_k": 1.5},
    "high":   {"max_temp": float("inf"), "p": 150, "i": 0, "d": 0, "base_overshoot_k": 2.0},
}

stability_fallback_settings = {
    "max_setpoint_adjustments": 2,   # 至多 2 次设定点过冲调整
    "good_enough_band_k": 0.5,       # ±0.5K "足够好"回退阈值
    "diagnostic_interval_s": 60,     # 状态推进间隔（秒）
    "max_overshoot_k": 10.0,         # 设定点过冲上限
}

# =========================================================================
# Diagnostics
# =========================================================================

enable_diagnostics = True
diagnostic_interval = 30            # seconds between diagnostic checks
