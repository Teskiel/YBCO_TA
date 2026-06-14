# -*- coding: utf-8 -*-
"""
生成 YBCO KID merged 数据集表征简报 PPTX。

从 output/merged/ 子目录读取图片，用 python-pptx 逐页构建。
关键数值通过 dataprocess.py（无需 scraps）从 S2P 数据中提取。
"""

import sys
import os
from pathlib import Path
import re

# 确保 otherwise 目录可导入
_script_dir = Path(__file__).resolve().parent
_otherwise_dir = _script_dir / "otherwise"
if str(_otherwise_dir) not in sys.path:
    sys.path.insert(0, str(_otherwise_dir))

import numpy as np
import dataprocess as dp

# ============================================================
# 配置
# ============================================================

MERGED_DIR = _script_dir.parent / "Auto_Sweep" / "experiment_data" / "merged"
OUTPUT_DIR = _script_dir / "output" / "merged"
PPTX_OUT = _script_dir / "output" / "YBCO_KID_merged_表征简报.pptx"

PIXEL_INDX = 1
MEAS_POWERS = [25, 30, 45]
LASER_POWERS = [0, 1, 3, 5, 7, 9]

# ============================================================
# 数值提取
# ============================================================

def scan_temperatures():
    """扫描 merged 目录下的温度点，返回排序后的列表（(整数温度, 原始目录名)）。"""
    pattern = re.compile(r"^(\d+(?:\.\d+)?)K$")
    entries = []
    for subfolder in MERGED_DIR.iterdir():
        if subfolder.is_dir():
            m = pattern.match(subfolder.name)
            if m:
                entries.append((int(float(m.group(1))), subfolder.name))
    if not entries:
        raise FileNotFoundError(f"MERGED_DIR 中没有找到匹配的温度子目录: {MERGED_DIR}")
    entries.sort(key=lambda x: x[0])
    return entries  # list of (int_temp, dirname)


def find_first_s2p(temp_dirname, power_dbm, laser_mw):
    """返回指定目录下的第一个 S2P 文件路径。

    Args:
        temp_dirname: 温度目录名（如 "6K"）
        power_dbm: VNA 功率 (dBm 数值，取负号)
        laser_mw: 激光功率 (mW)
    """
    path = MERGED_DIR / temp_dirname / f"-{power_dbm}dBm" / f"{laser_mw:02d}mW"
    if not path.is_dir():
        return None
    for f in path.iterdir():
        if f.suffix == ".s2p":
            return str(f)
    return None


def extract_key_numbers():
    """从数据中提取关键数值（仅用 dataprocess.py，不依赖 scraps）。

    Returns:
        dict with keys:
        - f0_ghz: 选定谐振峰频率 (GHz)
        - num_resonances: 检测到的谐振峰总数
        - f0_shift_percent: f0 从最低温到最高温的相对变化 (%)
        - qi_estimate: -3dB 带宽法估算的 Qi
        - low_temp: 最低温度 (K)
        - high_temp: 最高温度 (K)
        - all_resonances: 所有谐振峰频率列表 (GHz)
        - repr_low_temp: 低温代表点温度 (K) or None
        - repr_high_temp: 高温代表点温度 (K) or None
    """
    result = {}

    # 扫描温度
    temp_entries = scan_temperatures()
    temps = [t for t, _ in temp_entries]
    temp_dirs = [d for _, d in temp_entries]
    result["low_temp"] = temps[0]
    result["high_temp"] = temps[-1]

    # 使用最低温、-25dBm、0mW 的数据做谐振峰检测
    s2p_path = find_first_s2p(temp_dirs[0], MEAS_POWERS[0], LASER_POWERS[0])
    if s2p_path is None:
        raise FileNotFoundError(
            f"找不到 S2P 文件: {temp_dirs[0]}/-{MEAS_POWERS[0]}dBm/{LASER_POWERS[0]:02d}mW"
        )

    freq, s21 = dp.load_s_param(s2p_path)

    # 寻峰
    peaks, _, _ = dp.find_true_resonances(
        freq=freq, s21=s21,
        min_prominence=3, distance=10, phase_window=10,
        phase_diff_snr_threshold=0.5,
        noise_inner_window=5, noise_outer_window=40,
        min_phase_diff_support_points=4, min_phase_diff_width=4,
        plot=False,
    )

    result["num_resonances"] = len(peaks)
    all_freqs_ghz = [p["frequency"] / 1e9 for p in peaks]
    result["all_resonances"] = all_freqs_ghz

    if len(peaks) <= PIXEL_INDX:
        raise ValueError(
            f"pixel_indx={PIXEL_INDX} 超出检测到的谐振峰数 ({len(peaks)})"
        )

    selected_peak = peaks[PIXEL_INDX]
    f0_ghz = selected_peak["frequency"] / 1e9
    result["f0_ghz"] = f0_ghz

    # 估算 Qi：用 -3dB 带宽法
    # Qi ≈ f₀ / Δf_{-3dB}
    transmission = 20 * np.log10(np.abs(s21))
    peak_idx = selected_peak["index"]

    # 找到 |S21| 最小值作为 dip 底部
    dip_val = transmission[peak_idx]
    half_power_level = dip_val + 3.0  # -3dB above dip

    # 向左、右找 -3dB 交叉点
    left_idx = peak_idx
    while left_idx > 0 and transmission[left_idx] < half_power_level:
        left_idx -= 1
    right_idx = peak_idx
    while right_idx < len(transmission) - 1 and transmission[right_idx] < half_power_level:
        right_idx += 1

    delta_f = freq[right_idx] - freq[left_idx]
    # Guard: reject bandwidth that spans more than half the measurement range
    total_span = freq[-1] - freq[0]
    if delta_f <= 0 or delta_f > total_span * 0.5:
        result["qi_estimate"] = None
        result["bandwidth_mhz"] = None
    else:
        result["qi_estimate"] = int(f0_ghz * 1e9 / delta_f)
        result["bandwidth_mhz"] = delta_f / 1e6

    # 估算 f0 温度漂移（比较最低温和最高温的近似 f0）
    s2p_high = find_first_s2p(temp_dirs[-1], MEAS_POWERS[0], LASER_POWERS[0])
    if s2p_high:
        freq_high, s21_high = dp.load_s_param(s2p_high)
        # 在高温数据中重新寻峰
        peaks_high, _, _ = dp.find_true_resonances(
            freq=freq_high, s21=s21_high,
            min_prominence=3, distance=10, phase_window=10,
            phase_diff_snr_threshold=0.5,
            noise_inner_window=5, noise_outer_window=40,
            min_phase_diff_support_points=4, min_phase_diff_width=4,
            plot=False,
        )
        if len(peaks_high) > PIXEL_INDX:
            f0_high_ghz = peaks_high[PIXEL_INDX]["frequency"] / 1e9
            shift_pct = (f0_high_ghz - f0_ghz) / f0_ghz * 100
            result["f0_shift_percent"] = abs(shift_pct)
            result["f0_shift_direction"] = "红移（频率降低）" if shift_pct < 0 else "蓝移（频率升高）"
        else:
            result["f0_shift_percent"] = None
            result["f0_shift_direction"] = ""
    else:
        result["f0_shift_percent"] = None
        result["f0_shift_direction"] = ""

    # 从现有图片中推断所选的低温和高温代表点
    result["repr_low_temp"] = None
    result["repr_high_temp"] = None
    low_dir = OUTPUT_DIR / "05_optical_response_6K"
    high_dir = OUTPUT_DIR / "06_optical_response_highT"
    low_temp_files = [f for f in os.listdir(low_dir) if f.startswith("res shift")] if low_dir.is_dir() else []
    high_temp_files = [f for f in os.listdir(high_dir) if f.startswith("res shift")] if high_dir.is_dir() else []
    if low_temp_files:
        m = re.search(r"([\d.]+)K", low_temp_files[0])
        if m:
            result["repr_low_temp"] = float(m.group(1))
    if high_temp_files:
        m = re.search(r"([\d.]+)K", high_temp_files[0])
        if m:
            result["repr_high_temp"] = float(m.group(1))

    return result


if __name__ == "__main__":
    nums = extract_key_numbers()
    for k, v in nums.items():
        print(f"  {k}: {v}")
