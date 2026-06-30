# -*- coding: utf-8 -*-
"""
五谐振器批量分析 v2 — 纯 dataprocess，无 scraps 依赖。

生成内容：
1. R1–R5 子文件夹，各含：f0_vs_T, Qi_vs_T, S21_overlay, responsivity_vs_T
2. 每个温度：res shift vs laser power (可选 per-temp S21)
3. 对比汇总图存于 merged/compare_v2/
"""

import sys
import re
import io
import os
from pathlib import Path
from contextlib import redirect_stdout

_script_dir = Path(__file__).resolve().parent
_otherwise_dir = _script_dir / "otherwise"
sys.path.insert(0, str(_otherwise_dir))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import dataprocess as dp
from scipy.interpolate import UnivariateSpline

# ============================================================
# 路径配置
# ============================================================
MERGED_DIR = Path(r"D:\YBCO\VNAMeas\Auto_Sweep\experiment_data\merged")
OUTPUT_BASE = _script_dir / "output" / "merged"

FIXED_VNA_POWER = 25       # -25 dBm
FIXED_LASER_POWER = 0      # 0 mW (暗态)
LASER_POWERS = [0, 1, 3, 5, 7, 9]
VNA_POWERS = [25, 30, 45]

# ============================================================
# 绘图风格 — PPT 优化白底
# ============================================================
plt.rcParams.update({
    "figure.dpi": 200,
    "savefig.dpi": 250,
    "savefig.bbox": "tight",
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
    "font.size": 13,
    "axes.titlesize": 16,
    "axes.labelsize": 14,
    "legend.fontsize": 11,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#333333",
    "axes.labelcolor": "#111111",
    "text.color": "#111111",
    "xtick.color": "#333333",
    "ytick.color": "#333333",
    "grid.color": "#DDDDDD",
    "grid.alpha": 0.4,
    "axes.linewidth": 1.2,
    "xtick.major.width": 1.0,
    "ytick.major.width": 1.0,
    "lines.linewidth": 2.2,
    "lines.markersize": 7,
})

COLORS = ["#1F77B4", "#D62728", "#2CA02C", "#FF7F0E", "#9467BD"]
COLOR_CYCLE = plt.cycler(color=COLORS)

# ============================================================
# 数据扫描
# ============================================================

def scan_temperatures():
    pattern = re.compile(r"^(\d+(?:\.\d+)?)K$")
    entries = []
    for subfolder in MERGED_DIR.iterdir():
        if subfolder.is_dir():
            m = pattern.match(subfolder.name)
            if m:
                entries.append((int(float(m.group(1))), subfolder.name))
    entries.sort(key=lambda x: x[0])
    return entries


def find_s2p(temp_dirname, power_dbm, laser_mw):
    path = MERGED_DIR / temp_dirname / f"-{power_dbm}dBm" / f"{laser_mw:02d}mW"
    if not path.is_dir():
        return None
    for f in path.iterdir():
        if f.suffix == ".s2p":
            return str(f)
    return None


def load_resonances(s2p_path):
    """返回检测到的谐振峰列表 [(f0_Hz, dip_dB, bw_Hz, ql), ...]"""
    freq, s21 = dp.load_s_param(s2p_path)
    with redirect_stdout(io.StringIO()):
        peaks, _, _ = dp.find_true_resonances(
            freq=freq, s21=s21,
            min_prominence=1, distance=50, phase_window=25,
            phase_diff_snr_threshold=1.5,
            noise_inner_window=5, noise_outer_window=40,
            min_phase_diff_support_points=2, min_phase_diff_width=2,
            plot=False,
        )
    results = []
    for p in peaks:
        f0 = p["frequency"]
        dip = p["transmission"]
        idx = p["index"]
        transmission = 20 * np.log10(np.abs(s21))
        dip_val = transmission[idx]
        half_level = dip_val + 3.0
        left = idx
        while left > 0 and transmission[left] < half_level:
            left -= 1
        right = idx
        while right < len(transmission) - 1 and transmission[right] < half_level:
            right += 1
        delta_f = freq[right] - freq[left]
        total_span = freq[-1] - freq[0]
        if delta_f <= 0 or delta_f > total_span * 0.5:
            bw_hz, ql = None, None
        else:
            bw_hz = delta_f
            ql = f0 / delta_f
        results.append((f0, dip, bw_hz, ql))
    results = [(f0, dip, bw, ql) for f0, dip, bw, ql in results if dip < -1.0]
    results.sort(key=lambda x: x[0])
    return results


# ============================================================
# 跨温度追踪
# ============================================================

def match_peaks_across_temps(all_temp_peaks, n_resonators=5):
    """
    all_temp_peaks: [(temp, [(f0, dip, bw, ql), ...]), ...]
    返回: tracking[n_res][n_temps] = (f0, dip, bw, ql) or None
    """
    if not all_temp_peaks:
        return []

    # 用第一个温度初始化
    first_peaks = all_temp_peaks[0][1]
    n_res = min(n_resonators, len(first_peaks))
    tracking = [[] for _ in range(n_res)]

    # 第一组：直接分配
    for r in range(n_res):
        tracking[r].append(first_peaks[r])

    # 后续温度：匹配最近的频率
    for temp, peaks in all_temp_peaks[1:]:
        used = set()
        for r in range(n_res):
            prev_f0 = tracking[r][-1][0]
            best_idx = None
            best_dist = float("inf")
            for i, p in enumerate(peaks):
                if i in used:
                    continue
                dist = abs(p[0] - prev_f0)
                if dist < best_dist and dist < 50e6:  # 50 MHz max jump
                    best_dist = dist
                    best_idx = i
            if best_idx is not None:
                used.add(best_idx)
                tracking[r].append(peaks[best_idx])
            else:
                tracking[r].append(None)  # 丢失
    return tracking


# ============================================================
# 主流程
# ============================================================

def main():
    # --- 扫描温度 ---
    temp_entries = scan_temperatures()
    print(f"Found {len(temp_entries)} temperature points")

    # --- 在第一温度检测参考谐振峰 ---
    first_temp_name = temp_entries[0][1]
    ref_s2p = find_s2p(first_temp_name, FIXED_VNA_POWER, FIXED_LASER_POWER)
    ref_peaks = load_resonances(ref_s2p)
    n_resonators = min(5, len(ref_peaks))
    print(f"Reference peaks: {n_resonators}")
    for i in range(n_resonators):
        print(f"  R{i+1}: {ref_peaks[i][0]/1e9:.5f} GHz  dip={ref_peaks[i][1]:.2f} dB")

    # --- 跨温度追踪所有谐振器 ---
    print("\nTracking resonators across temperatures...")
    all_temp_peaks = []
    for temp_int, temp_name in temp_entries:
        s2p = find_s2p(temp_name, FIXED_VNA_POWER, FIXED_LASER_POWER)
        if s2p is None:
            continue
        peaks = load_resonances(s2p)
        if len(peaks) >= n_resonators:
            all_temp_peaks.append((temp_int, peaks))

    tracking = match_peaks_across_temps(all_temp_peaks, n_resonators)
    n_temps = len(all_temp_peaks)
    temps_list = [t[0] for t in all_temp_peaks]

    for r in range(n_resonators):
        present = sum(1 for p in tracking[r] if p is not None)
        print(f"  R{r+1}: tracked {present}/{n_temps} temperatures")

    # --- 为每个谐振器创建输出文件夹 ---
    resonator_dirs = []
    for r in range(n_resonators):
        freq_ghz = ref_peaks[r][0] / 1e9
        folder_name = f"R{r+1}_{freq_ghz:.3f}GHz"
        res_dir = OUTPUT_BASE / folder_name
        res_dir.mkdir(parents=True, exist_ok=True)
        resonator_dirs.append(res_dir)
        print(f"  {folder_name}")

    # --- 生成寻峰总览图 ---
    print("\nGenerating overview images...")
    res_detect_dir = OUTPUT_BASE / "01_resonance_detection"
    res_detect_dir.mkdir(parents=True, exist_ok=True)

    freq_ref, s21_ref = dp.load_s_param(ref_s2p)
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(freq_ref / 1e9, 20 * np.log10(np.abs(s21_ref)), color="#333333", linewidth=1.5)
    for r in range(n_resonators):
        f0 = ref_peaks[r][0]
        dip = ref_peaks[r][1]
        ax.axvline(f0 / 1e9, color=COLORS[r], linestyle="--", linewidth=1.2, alpha=0.7)
        ax.annotate(f"R{r+1}\n{f0/1e9:.3f} GHz",
                     xy=(f0 / 1e9, dip), xytext=(0, -25 if r % 2 == 0 else -40),
                     textcoords="offset points", fontsize=9, color=COLORS[r],
                     ha="center", fontweight="bold")
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("$S_{21}$ (dB)")
    ax.set_title("YBCO KID Resonance Spectrum @ 6 K, -25 dBm, 0 mW")
    ax.grid(True, alpha=0.3)
    fig.savefig(str(res_detect_dir / "resonance_detection.jpg"), dpi=250, bbox_inches="tight")
    plt.close(fig)
    print("  resonance_detection.jpg OK")

    # --- 汇总对比图：f0 vs T (all 5) ---
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for r in range(n_resonators):
        t_vals, f0_vals = [], []
        for i, p in enumerate(tracking[r]):
            if p is not None:
                t_vals.append(temps_list[i])
                f0_vals.append(p[0] / 1e9)
        ax.plot(t_vals, f0_vals, "o-", color=COLORS[r], linewidth=2, markersize=5,
                label=f"R{r+1} ({ref_peaks[r][0]/1e9:.3f} GHz)")
    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel("$f_0$ (GHz)")
    ax.set_title("Resonance Frequency vs Temperature — All 5 Resonators")
    ax.legend(ncol=3, fontsize=10)
    ax.grid(True, alpha=0.3)
    compare_dir = OUTPUT_BASE / "compare_v2"
    compare_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(compare_dir / "f0_vs_temp_all.jpg"), dpi=250, bbox_inches="tight")
    plt.close(fig)
    print("  f0_vs_temp_all.jpg OK")

    # --- f0 归一化 ---
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for r in range(n_resonators):
        t_vals, f0_vals = [], []
        for i, p in enumerate(tracking[r]):
            if p is not None:
                t_vals.append(temps_list[i])
                f0_vals.append(p[0])
        if f0_vals:
            f0_arr = np.array(f0_vals)
            delta_f = (f0_arr - f0_arr[0]) / f0_arr[0] * 100
            ax.plot(t_vals, delta_f, "o-", color=COLORS[r], linewidth=2, markersize=5,
                    label=f"R{r+1}")
    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel(r"$\delta f_0 / f_0$ (%)")
    ax.set_title("Normalized Frequency Shift vs Temperature")
    ax.legend(ncol=3, fontsize=10)
    ax.grid(True, alpha=0.3)
    fig.savefig(str(compare_dir / "normalized_f0_vs_temp.jpg"), dpi=250, bbox_inches="tight")
    plt.close(fig)
    print("  normalized_f0_vs_temp.jpg OK")

    # --- Qi vs T (all 5) ---
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for r in range(n_resonators):
        t_vals, qi_vals = [], []
        for i, p in enumerate(tracking[r]):
            if p is not None and p[3] is not None:
                t_vals.append(temps_list[i])
                qi_vals.append(p[3])
        ax.plot(t_vals, qi_vals, "o-", color=COLORS[r], linewidth=2, markersize=5,
                label=f"R{r+1}")
    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel("$Q_i$")
    ax.set_title("Internal Quality Factor vs Temperature — All 5 Resonators")
    ax.legend(ncol=3, fontsize=10)
    ax.grid(True, alpha=0.3)
    fig.savefig(str(compare_dir / "qi_vs_temp_all.jpg"), dpi=250, bbox_inches="tight")
    plt.close(fig)
    print("  qi_vs_temp_all.jpg OK")

    # --- Dip vs T ---
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for r in range(n_resonators):
        t_vals, dip_vals = [], []
        for i, p in enumerate(tracking[r]):
            if p is not None:
                t_vals.append(temps_list[i])
                dip_vals.append(p[1])
        ax.plot(t_vals, dip_vals, "o-", color=COLORS[r], linewidth=2, markersize=5,
                label=f"R{r+1}")
    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel("Dip (dB)")
    ax.set_title("Resonance Dip Depth vs Temperature")
    ax.legend(ncol=3, fontsize=10)
    ax.grid(True, alpha=0.3)
    fig.savefig(str(compare_dir / "dip_vs_temp.jpg"), dpi=250, bbox_inches="tight")
    plt.close(fig)
    print("  dip_vs_temp.jpg OK")

    # --- 各谐振器独立 S21 vs T 叠加图 ---
    for r in range(n_resonators):
        fig, ax = plt.subplots(figsize=(10, 5))
        for i, (temp_int, temp_name) in enumerate(temp_entries):
            s2p_path = find_s2p(temp_name, FIXED_VNA_POWER, FIXED_LASER_POWER)
            if s2p_path is None:
                continue
            if i < len(tracking[r]) and tracking[r][i] is not None:
                f0_r = tracking[r][i][0]
                freq, s21 = dp.load_s_param(s2p_path)
                # 以追踪到的 f0 为中心，取 ±30 MHz
                mask = (freq > f0_r - 30e6) & (freq < f0_r + 30e6)
                t_norm = (temp_int - temps_list[0]) / max(1, (temps_list[-1] - temps_list[0]))
                color_idx = int(t_norm * (len(COLORS) - 1)) if len(temps_list) > 1 else 0
                # 使用 colormap
                from matplotlib.cm import viridis
                color = viridis(0.15 + 0.7 * t_norm)
                ax.plot(freq[mask] / 1e9, 20 * np.log10(np.abs(s21[mask])),
                        color=color, linewidth=1.0, alpha=0.7)
        ax.set_xlabel("Frequency (GHz)")
        ax.set_ylabel("$S_{21}$ (dB)")
        ax.set_title(f"R{r+1} ({ref_peaks[r][0]/1e9:.3f} GHz) — S21 vs Temperature")
        ax.grid(True, alpha=0.3)
        fig.savefig(str(resonator_dirs[r] / "s21_vs_temp.jpg"), dpi=250, bbox_inches="tight")
        plt.close(fig)
    print("  Per-resonator S21 vs T OK")

    # --- 各谐振器独立 f0 vs T + Qi vs T ---
    for r in range(n_resonators):
        # f0 vs T
        t_vals, f0_vals = [], []
        for i, p in enumerate(tracking[r]):
            if p is not None:
                t_vals.append(temps_list[i])
                f0_vals.append(p[0] / 1e9)
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(t_vals, f0_vals, "o-", color=COLORS[r], linewidth=2.5, markersize=6)
        ax.set_xlabel("Temperature (K)")
        ax.set_ylabel("$f_0$ (GHz)")
        ax.set_title(f"R{r+1} ({ref_peaks[r][0]/1e9:.3f} GHz) — Resonance Frequency")
        ax.grid(True, alpha=0.3)
        fig.savefig(str(resonator_dirs[r] / "f0_vs_temp.jpg"), dpi=250, bbox_inches="tight")
        plt.close(fig)

        # Qi vs T
        t_vals, qi_vals = [], []
        for i, p in enumerate(tracking[r]):
            if p is not None and p[3] is not None:
                t_vals.append(temps_list[i])
                qi_vals.append(p[3])
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(t_vals, qi_vals, "o-", color=COLORS[r], linewidth=2.5, markersize=6)
        ax.set_xlabel("Temperature (K)")
        ax.set_ylabel("$Q_i$")
        ax.set_title(f"R{r+1} ({ref_peaks[r][0]/1e9:.3f} GHz) — Internal Quality Factor")
        ax.grid(True, alpha=0.3)
        fig.savefig(str(resonator_dirs[r] / "qi_vs_temp.jpg"), dpi=250, bbox_inches="tight")
        plt.close(fig)
    print("  Per-resonator f0/Qi vs T OK")

    # --- 光学响应：逐温度、逐谐振器 ---
    print("\nGenerating optical response charts...")
    # 选取代表温度点
    rep_temps = [
        ("6K", [t for t in temp_entries if t[0] == 6]),
        ("8K", [t for t in temp_entries if t[0] == 8]),
        ("20K", [t for t in temp_entries if 19 <= t[0] <= 21]),
        ("40K", [t for t in temp_entries if 39 <= t[0] <= 41]),
        ("77K", [t for t in temp_entries if 75 <= t[0] <= 78]),
    ]

    # 为每个代表温度生成五谐振器光响应对比
    for label, t_entries in rep_temps:
        if not t_entries:
            continue
        temp_int, temp_name = t_entries[0]
        temp_idx = next((i for i, t in enumerate(all_temp_peaks) if t[0] == temp_int), None)
        if temp_idx is None:
            continue

        # 尝试读取实际温度
        s2p_test = find_s2p(temp_name, FIXED_VNA_POWER, 0)
        actual_temp = temp_int
        if s2p_test:
            m = re.search(r"actual_([\d.]+)K", s2p_test)
            if m:
                actual_temp = float(m.group(1))

        # 光响应图：五谐振器对比
        fig, axes = plt.subplots(2, 3, figsize=(14, 9))
        axes = axes.flatten()
        for r in range(n_resonators):
            ax = axes[r]
            f0s_per_laser = []
            for laser_mw in LASER_POWERS:
                s2p = find_s2p(temp_name, FIXED_VNA_POWER, laser_mw)
                if s2p is None:
                    f0s_per_laser.append(None)
                    continue
                peaks = load_resonances(s2p)
                # 匹配最近的谐振器
                if temp_idx < len(tracking[r]) and tracking[r][temp_idx] is not None:
                    ref_f0 = tracking[r][temp_idx][0]
                    matched = None
                    for p in peaks:
                        if abs(p[0] - ref_f0) < 30e6:
                            matched = p
                            break
                    if matched:
                        f0s_per_laser.append(matched[0])
                    else:
                        f0s_per_laser.append(None)
                else:
                    f0s_per_laser.append(None)

            valid = [(l, f) for l, f in zip(LASER_POWERS, f0s_per_laser) if f is not None]
            if len(valid) >= 3:
                l_vals, f_vals = zip(*valid)
                f_arr = np.array(f_vals)
                ax.plot(l_vals, (f_arr - f_arr[0]) / 1e3, "o-", color=COLORS[r],
                        linewidth=2, markersize=7)
                # 线性拟合
                if len(l_vals) >= 2:
                    coeff = np.polyfit(l_vals, f_arr, 1)
                    responsivity = coeff[0]  # Hz/mW → Hz/W = *1000
                    ax.plot(l_vals, (np.polyval(coeff, l_vals) - f_arr[0]) / 1e3,
                            "--", color=COLORS[r], linewidth=1, alpha=0.5)
                    ax.set_title(f"R{r+1}  {responsivity/1e3:.1f} kHz/(mW)", fontsize=11)
            ax.set_xlabel("Laser (mW)")
            ax.set_ylabel("Δf₀ (kHz)")
            ax.grid(True, alpha=0.3)

        # 第 6 个 subplot: 响应率柱状图
        ax = axes[5]
        responsivities = []
        labels_r = []
        for r in range(n_resonators):
            f0s_per_laser = []
            for laser_mw in LASER_POWERS:
                s2p = find_s2p(temp_name, FIXED_VNA_POWER, laser_mw)
                if s2p is None:
                    f0s_per_laser.append(None)
                    continue
                peaks = load_resonances(s2p)
                if temp_idx < len(tracking[r]) and tracking[r][temp_idx] is not None:
                    ref_f0 = tracking[r][temp_idx][0]
                    matched = None
                    for p in peaks:
                        if abs(p[0] - ref_f0) < 30e6:
                            matched = p
                            break
                    f0s_per_laser.append(matched[0] if matched else None)
                else:
                    f0s_per_laser.append(None)
            valid = [(l, f) for l, f in zip(LASER_POWERS, f0s_per_laser) if f is not None]
            if len(valid) >= 2:
                lv, fv = zip(*valid)
                resp = np.polyfit(lv, fv, 1)[0] / 1e3  # kHz/(mW)
            else:
                resp = 0
            responsivities.append(resp)
            labels_r.append(f"R{r+1}")
        bars = ax.bar(labels_r, responsivities, color=COLORS[:n_resonators])
        ax.set_ylabel("Responsivity (kHz/mW)")
        ax.set_title(f"Responsivity @ {actual_temp:.1f} K")
        ax.grid(True, alpha=0.3, axis="y")

        fig.suptitle(f"Optical Response at {actual_temp:.1f} K — All 5 Resonators",
                     fontsize=16, fontweight="bold", y=0.98)
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(str(compare_dir / f"optical_response_{label}.jpg"), dpi=250, bbox_inches="tight")
        plt.close(fig)
        print(f"  optical_response_{label}.jpg OK")

    # --- 响应率 vs 温度 (all 5) ---
    print("\nGenerating responsivity vs T...")
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for r in range(n_resonators):
        resp_vs_t = []
        t_valid = []
        for temp_idx, (temp_int, _) in enumerate(all_temp_peaks):
            temp_name_entry = next((tn for ti, tn in temp_entries if ti == temp_int), None)
            if temp_name_entry is None:
                continue
            f0s_per_laser = []
            for laser_mw in LASER_POWERS:
                s2p = find_s2p(temp_name_entry, FIXED_VNA_POWER, laser_mw)
                if s2p is None:
                    f0s_per_laser.append(None)
                    continue
                peaks = load_resonances(s2p)
                if temp_idx < len(tracking[r]) and tracking[r][temp_idx] is not None:
                    ref_f0 = tracking[r][temp_idx][0]
                    matched = None
                    for p in peaks:
                        if abs(p[0] - ref_f0) < 30e6:
                            matched = p
                            break
                    f0s_per_laser.append(matched[0] if matched else None)
                else:
                    f0s_per_laser.append(None)
            valid = [(l, f) for l, f in zip(LASER_POWERS, f0s_per_laser) if f is not None]
            if len(valid) >= 2:
                lv, fv = zip(*valid)
                resp = np.polyfit(lv, fv, 1)[0]  # Hz/mW
                resp_vs_t.append(resp)
                t_valid.append(temp_int)
        if len(t_valid) >= 3:
            ax.plot(t_valid, np.array(resp_vs_t) / 1e3, "o-", color=COLORS[r],
                    linewidth=2, markersize=5, label=f"R{r+1}")
    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel("Responsivity (kHz/mW)")
    ax.set_title("Optical Responsivity vs Temperature — All 5 Resonators")
    ax.legend(ncol=3, fontsize=10)
    ax.grid(True, alpha=0.3)
    fig.savefig(str(compare_dir / "responsivity_vs_temp.jpg"), dpi=250, bbox_inches="tight")
    plt.close(fig)
    print("  responsivity_vs_temp.jpg OK")

    # --- 各谐振器独立响应率 vs T ---
    for r in range(n_resonators):
        resp_vs_t = []
        t_valid = []
        for temp_idx, (temp_int, _) in enumerate(all_temp_peaks):
            temp_name_entry = next((tn for ti, tn in temp_entries if ti == temp_int), None)
            if temp_name_entry is None:
                continue
            f0s_per_laser = []
            for laser_mw in LASER_POWERS:
                s2p = find_s2p(temp_name_entry, FIXED_VNA_POWER, laser_mw)
                if s2p is None:
                    f0s_per_laser.append(None)
                    continue
                peaks = load_resonances(s2p)
                if temp_idx < len(tracking[r]) and tracking[r][temp_idx] is not None:
                    ref_f0 = tracking[r][temp_idx][0]
                    matched = None
                    for p in peaks:
                        if abs(p[0] - ref_f0) < 30e6:
                            matched = p
                            break
                    f0s_per_laser.append(matched[0] if matched else None)
                else:
                    f0s_per_laser.append(None)
            valid = [(l, f) for l, f in zip(LASER_POWERS, f0s_per_laser) if f is not None]
            if len(valid) >= 2:
                lv, fv = zip(*valid)
                resp = np.polyfit(lv, fv, 1)[0]
                resp_vs_t.append(resp)
                t_valid.append(temp_int)
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(t_valid, np.array(resp_vs_t) / 1e3, "o-", color=COLORS[r],
                linewidth=2.5, markersize=6)
        ax.set_xlabel("Temperature (K)")
        ax.set_ylabel("Responsivity (kHz/mW)")
        ax.set_title(f"R{r+1} ({ref_peaks[r][0]/1e9:.3f} GHz) — Optical Responsivity")
        ax.grid(True, alpha=0.3)
        fig.savefig(str(resonator_dirs[r] / "responsivity_vs_temp.jpg"), dpi=250, bbox_inches="tight")
        plt.close(fig)
    print("  Per-resonator responsivity vs T OK")

    print(f"\nDone! Output: {OUTPUT_BASE}")
    print("Resonator dirs:", [d.name for d in resonator_dirs])
    print("Compare dir:", compare_dir.name)


if __name__ == "__main__":
    main()
