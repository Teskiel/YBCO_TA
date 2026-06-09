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

stable_hold_seconds = 60             # must stay stable this long before measuring
max_wait_seconds = 30 * 60           # 30-minute timeout per temperature point
temperature_poll_seconds = 10        # polling interval (~6 readings/min)

custom_stability_settings = {
    "avg_window_seconds": 60,        # 1-minute rolling window
    "avg_tolerance_k": 1.0,          # average within ±1.0 K of setpoint
    "delta_tolerance_k": 0.2,        # max drift over 2-minute span — 趋于平稳阈值
    "final_stable_band_k": 0.5,      # ±0.5 K 进入目标温度区间
    "min_readings_required": 10,     # 匹配 180s 回溯窗口
}

# ---- 稳态判定（与目标区间判定并行，无先后关系） ----
steady_state_max_min_k = 0.1         # 3 分钟窗口 max-min ≤ 0.1K = 进入稳态
steady_state_window_s = 180          # 稳态判定窗口（3 分钟）

# ---- 双阶段轮询间隔 ----
sparse_poll_seconds = 30             # Phase 1 低频读取（趋于平稳前）
fine_poll_seconds = 5                # Phase 2 高频读取（趋于平稳后，密集判稳态）

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
# 测量逻辑版本
# =========================================================================

MEASUREMENT_LOGIC_VERSION = "2026-06-08"  # 每次修改测量流程后更新，写入数据头部

# =========================================================================
# VNA 功率区间扫描默认值（与按钮网格并行使用）
# =========================================================================

vna_power_range_default_start_dbm = -55  # 功率区间起始 dBm
vna_power_range_default_stop_dbm = -45   # 功率区间终止 dBm
vna_power_range_default_step_db = 2      # 功率区间步长 dB
