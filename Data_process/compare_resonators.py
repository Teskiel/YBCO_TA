# -*- coding: utf-8 -*-
"""
五谐振器对比分析脚本。

对 merged 数据集固定 -25dBm / 0mW，追踪全部 5 个谐振器：
  - 跨温度追踪 f₀(T), Qi(T)
  - 6K 光学响应（0→9mW 激光）
  - 生成 4 张对比图 → output/merged/compare/
"""

import sys
import re
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
_otherwise_dir = _script_dir / "otherwise"
if str(_otherwise_dir) not in sys.path:
    sys.path.insert(0, str(_otherwise_dir))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter
import dataprocess as dp
import os as _os
from contextlib import redirect_stdout
from scipy.interpolate import UnivariateSpline
import io

# ============================================================
# 配置
# ============================================================
MERGED_DIR = _script_dir.parent / "Auto_Sweep" / "experiment_data" / "merged"
OUTPUT_DIR = _script_dir / "output" / "merged" / "compare"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FIXED_VNA_POWER = 25       # -25 dBm
FIXED_LASER_POWER = 0      #  0 mW (暗态)
LASER_POWERS = [0, 1, 3, 5, 7, 9]  # 光学响应扫描

# 寻峰参数（宽松，检测全部 5 个谐振器）
# phase_diff_snr_threshold 降至 1.5 —— R5 在 6-10K 时 SNR≈3，12K 后低于 3
# phase_window 扩大到 25 —— 高温谐振峰展宽后相位峰离幅度谷更远
PEAK_KWARGS = dict(
    min_prominence=1,
    distance=50,
    phase_window=25,
    phase_diff_snr_threshold=1.5,
    noise_inner_window=5,
    noise_outer_window=40,
    min_phase_diff_support_points=2,
    min_phase_diff_width=2,
    plot=False,
)

# 绘图风格 —— PPT 优化：白底、大字号、粗线条、高饱和配色
plt.rcParams.update({
    "figure.dpi": 200,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
    "font.size": 12,
    "axes.titlesize": 18,
    "axes.labelsize": 14,
    "legend.fontsize": 12,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#222222",
    "axes.labelcolor": "#111111",
    "text.color": "#111111",
    "xtick.color": "#222222",
    "ytick.color": "#222222",
    "grid.color": "#CCCCCC",
    "grid.alpha": 0.35,
    "axes.linewidth": 1.2,
    "xtick.major.width": 1.0,
    "ytick.major.width": 1.0,
    "lines.linewidth": 2.0,
    "lines.markersize": 8,
})

# 高饱和配色（Tableau 10 改编，适配 PPT 投影）
COLORS = ["#1F77B4", "#D62728", "#2CA02C", "#FF7F0E", "#9467BD"]
COLOR_CYCLE = plt.cycler(color=COLORS)

# ============================================================
# 数据加载
# ============================================================

def scan_temperatures():
    """扫描温度目录，返回排序后的 [(int_temp, dirname), ...] 列表。"""
    pattern = re.compile(r"^(\d+(?:\.\d+)?)K$")
    entries = []
    for subfolder in MERGED_DIR.iterdir():
        if subfolder.is_dir():
            m = pattern.match(subfolder.name)
            if m:
                entries.append((int(float(m.group(1))), subfolder.name))
    if not entries:
        raise FileNotFoundError(f"未找到温度子目录: {MERGED_DIR}")
    entries.sort(key=lambda x: x[0])
    return entries


def find_s2p(temp_dirname, power_dbm, laser_mw):
    """返回指定条件下的第一个 S2P 文件路径（或 None）。"""
    path = MERGED_DIR / temp_dirname / f"-{power_dbm}dBm" / f"{laser_mw:02d}mW"
    if not path.is_dir():
        return None
    for f in path.iterdir():
        if f.suffix == ".s2p":
            return str(f)
    return None


def load_resonances(s2p_path):
    """加载 S2P 并返回检测到的谐振峰列表 [(f0_Hz, dip_dB, bw_Hz, ql), ...]"""
    freq, s21 = dp.load_s_param(s2p_path)
    # 抑制 dataprocess 内部裸 print() 的输出
    with redirect_stdout(io.StringIO()):
        peaks, _, _ = dp.find_true_resonances(freq=freq, s21=s21, **PEAK_KWARGS)

    results = []
    for p in peaks:
        f0 = p["frequency"]
        dip = p["transmission"]  # dB
        idx = p["index"]

        # -3dB 带宽估算
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
            bw_hz = None
            ql = None
        else:
            bw_hz = delta_f
            ql = f0 / delta_f

        results.append((f0, dip, bw_hz, ql))

    # 过滤：dip 必须 < -1 dB（浅于 -1 dB 的"谐振峰"是噪声假阳性）
    results = [(f0, dip, bw, ql) for f0, dip, bw, ql in results if dip < -1.0]

    # 按频率升序排列（谐振器 1→5）
    results.sort(key=lambda x: x[0])
    return results


# ============================================================
# 图注
# ============================================================

def _add_caption(fig, text):
    """在图底部添加 SCI 规范的图注：'图X. 说明'"""
    fig.text(0.5, -0.02, text, ha="center", va="top", fontsize=11,
             fontstyle="italic", color="#555555")


# ============================================================
# 平滑拟合
# ============================================================

def smooth_spline(x, y, min_points=5):
    """三次样条平滑 + 迭代离群点剔除。返回 (xs, ys, mask_kept) 或 (None, None, None)。"""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < min_points:
        return None, None, None

    # 去重排序
    order = np.argsort(x)
    xu, idx = np.unique(x[order], return_index=True)
    yu = y[order][idx]
    if len(xu) < min_points:
        return None, None, None

    # 迭代剔除离群点
    keep = np.ones(len(xu), dtype=bool)
    for iteration in range(3):
        xk = xu[keep]; yk = yu[keep]
        if len(xk) < max(min_points, 4):
            break
        # 平滑因子正比于 y 跨度 —— 强平滑
        y_span = np.ptp(yk)
        s = len(xk) * 1.5 * (y_span if y_span > 0 else 1.0)
        k = min(3, len(xk) - 1)
        try:
            spl = UnivariateSpline(xk, yk, s=s, k=k)
        except Exception:
            break
        residuals = np.abs(yk - spl(xk))
        mad = np.median(residuals)
        if mad < 1e-12:
            break
        # 标记残差 > 5×MAD 的点为离群
        outliers = residuals > 5 * mad
        if not outliers.any():
            break
        keep[np.where(keep)[0][outliers]] = False

    xk = xu[keep]; yk = yu[keep]
    if len(xk) < min_points:
        return None, None, None

    y_span = np.ptp(yk)
    s_final = len(xk) * 1.0 * (y_span if y_span > 0 else 1.0)
    k_final = min(3, len(xk) - 1)
    try:
        spl = UnivariateSpline(xk, yk, s=s_final, k=k_final)
    except Exception:
        return None, None, None

    xs = np.linspace(xk.min(), xk.max(), 200)
    ys = spl(xs)
    # 映射回原始索引
    full_keep = np.zeros(len(x), dtype=bool)
    for i, ok in enumerate(keep):
        if ok:
            full_keep[order[idx[i]]] = True
    return xs, ys, full_keep


# ============================================================
# 跨温度谐振器追踪
# ============================================================

def match_resonators(prev_resonances, curr_resonances, max_shift_hz=200e6):
    """用最近邻将当前谐振峰匹配到前一个温度点。

    返回 [(prev_idx, curr_idx), ...] 匹配对列表。
    未匹配的标记为 None。

    首次调用时 prev_resonances 可为 None。
    """
    if prev_resonances is None:
        return [(i, i) for i in range(len(curr_resonances))]

    matches = []
    used_curr = set()

    for pi, (pf0, _, _, _) in enumerate(prev_resonances):
        best_idx = None
        best_dist = max_shift_hz
        for ci, (cf0, _, _, _) in enumerate(curr_resonances):
            if ci in used_curr:
                continue
            dist = abs(cf0 - pf0)
            if dist < best_dist:
                best_dist = dist
                best_idx = ci
        if best_idx is not None:
            used_curr.add(best_idx)
        matches.append((pi, best_idx))

    return matches


def track_all_resonators():
    """跨所有温度追踪 5 个谐振器，返回结构化数据。

    Returns:
        tracks: dict {res_id: {"temps": [...], "f0s": [...], "qis": [...], "dips": [...]}}
        num_resonators: int
    """
    temp_entries = scan_temperatures()
    print(f"Scanned {len(temp_entries)} T-points: {temp_entries[0][0]}K -> {temp_entries[-1][0]}K")

    prev_resonances = None
    res_to_track = {}  # {prev_idx: res_id}

    tracks = {}
    num_resonators = 0

    for int_t, dirname in temp_entries:
        s2p_path = find_s2p(dirname, FIXED_VNA_POWER, FIXED_LASER_POWER)
        if s2p_path is None:
            print(f"  [{int_t}K] skip: no S2P")
            continue

        curr = load_resonances(s2p_path)

        if prev_resonances is None:
            # 首次：初始化追踪
            num_resonators = len(curr)
            for i in range(num_resonators):
                tracks[i] = {"temps": [], "f0s": [], "qis": [], "dips": []}
                res_to_track[i] = i

        matches = match_resonators(prev_resonances, curr)

        for prev_idx, curr_idx in matches:
            if prev_idx not in res_to_track:
                continue
            res_id = res_to_track[prev_idx]

            if curr_idx is not None:
                f0, dip, bw, ql = curr[curr_idx]
                tracks[res_id]["temps"].append(int_t)
                tracks[res_id]["f0s"].append(f0 / 1e9)
                tracks[res_id]["dips"].append(dip)
                tracks[res_id]["qis"].append(ql)
            else:
                # 丢失追踪 — 填 NaN
                tracks[res_id]["temps"].append(int_t)
                tracks[res_id]["f0s"].append(np.nan)
                tracks[res_id]["dips"].append(np.nan)
                tracks[res_id]["qis"].append(np.nan)

        # 更新匹配映射
        new_mapping = {}
        for prev_idx, curr_idx in matches:
            if prev_idx in res_to_track and curr_idx is not None:
                new_mapping[curr_idx] = res_to_track[prev_idx]
        res_to_track = new_mapping
        prev_resonances = curr

    return tracks, num_resonators


# ============================================================
# 光学响应（6K）
# ============================================================

def optical_response_6k():
    """提取 6K 下所有谐振器的光学响应。

    返回 dict: {res_id: {"laser_powers": [...], "f0s": [...], "dips": [...]}}
    """
    temp_entries = scan_temperatures()
    # 找最低温目录
    t6k_dir = temp_entries[0][1]  # 第一个是 6K

    # 先用 0mW 建立基线参考频率
    s2p_ref = find_s2p(t6k_dir, FIXED_VNA_POWER, 0)
    if s2p_ref is None:
        print("  [OptResp] Ref S2P not found")
        return {}
    ref_resonances = load_resonances(s2p_ref)
    n_res = len(ref_resonances)
    ref_freqs = [r[0] for r in ref_resonances]

    # 初始化结果
    result = {i: {"laser_powers": [], "f0s": [], "dips": []} for i in range(n_res)}

    for laser_mw in LASER_POWERS:
        s2p_path = find_s2p(t6k_dir, FIXED_VNA_POWER, laser_mw)
        if s2p_path is None:
            print(f"  [OptResp] 6K, {laser_mw}mW: no S2P")
            continue

        curr = load_resonances(s2p_path)
        curr_freqs = [r[0] for r in curr]

        # 最近邻匹配到参考谐振器
        for res_id, ref_f in enumerate(ref_freqs):
            best_idx = None
            best_dist = 200e6
            for ci, cf in enumerate(curr_freqs):
                dist = abs(cf - ref_f)
                if dist < best_dist:
                    best_dist = dist
                    best_idx = ci
            if best_idx is not None:
                f0, dip = curr[best_idx][0], curr[best_idx][1]
                result[res_id]["laser_powers"].append(laser_mw)
                result[res_id]["f0s"].append(f0 / 1e9)
                result[res_id]["dips"].append(dip)

    return result


# ============================================================
# 绘图
# ============================================================

def plot_spectrum_overview(tracks, num_res, temp_entries):
    """图 1：全谱指纹 —— 干净 S21 全景，无线条遮挡，无右侧表格。"""
    fig, ax = plt.subplots(figsize=(12, 5))
    t6k_dir = temp_entries[0][1]
    s2p_path = find_s2p(t6k_dir, FIXED_VNA_POWER, 0)
    freq, s21 = dp.load_s_param(s2p_path)
    amp = 20 * np.log10(np.abs(s21))

    ax.plot(freq / 1e9, amp, color=COLORS[0], linewidth=1.5, alpha=0.95)

    # 无遮挡标注：短虚线段在曲线上方，标签交错高度避免重叠
    y_base = amp.max() + 1.5
    for res_id in range(num_res):
        if tracks[res_id]["f0s"] and not np.isnan(tracks[res_id]["f0s"][0]):
            f0_g = tracks[res_id]["f0s"][0]
            dip = tracks[res_id]["dips"][0]
            c = COLORS[res_id % len(COLORS)]
            # 奇偶交错高度，避免 R1/R2、R4/R5 标签重叠
            y_tag = y_base + (1.2 if res_id % 2 == 0 else 0.0)
            ax.plot([f0_g, f0_g], [dip + 0.5, y_tag], color=c, linewidth=1.2,
                    alpha=0.5, linestyle=":")
            ax.annotate(f"R{res_id + 1}  {f0_g:.3f} GHz",
                        xy=(f0_g, y_tag),
                        fontsize=13, color=c, ha="center", va="bottom",
                        fontweight="bold")

    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("|S21| (dB)")
    ax.set_title("Full Spectrum: 5 Resonators on YBCO Feedline  (6 K, −25 dBm, 0 mW)",
                 fontweight="bold", fontsize=20)
    ax.grid(True, alpha=0.3)

    fig.tight_layout(rect=[0, 0.06, 1, 1])
    _add_caption(fig, "Fig. 1. Full-spectrum S21 of five hanger resonators on YBCO feedline (6 K, −25 dBm, 0 mW laser).")
    fig.savefig(str(OUTPUT_DIR / "01_spectrum_overview.jpg"), facecolor="white")
    fig.savefig(str(OUTPUT_DIR / "01_spectrum_overview.svg"), facecolor="white")
    plt.close(fig)
    print("  [Fig1] Spectrum overview -> 01_spectrum_overview.*")


def plot_f0_vs_temp(tracks, num_res, temp_entries):
    """图 2：f₀(T) 五线叠加。"""
    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.set_prop_cycle(COLOR_CYCLE)

    for res_id in range(num_res):
        t = np.array(tracks[res_id]["temps"])
        f = np.array(tracks[res_id]["f0s"])
        mask = ~np.isnan(f)
        if mask.sum() > 1:
            label = f"R{res_id + 1}: {f[mask][0]:.3f} GHz"
            c = COLORS[res_id % len(COLORS)]
            xs, ys, kept = smooth_spline(t[mask], f[mask])
            if xs is not None:
                ax.plot(xs, ys, "-", linewidth=2.5, color=c, label=label)
                tm, fm = t[mask], f[mask]
                ax.plot(tm[kept], fm[kept], "o", markersize=9, color=c, alpha=0.7)

    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel("Resonant Frequency f₀ (GHz)")
    ax.set_title("f₀(T) — All 5 Resonators (−25 dBm, 0 mW)", fontweight="bold", fontsize=20)
    ax.legend(loc="upper right", framealpha=0.8, facecolor="white",
              edgecolor="#999999", fontsize=12)
    ax.grid(True, alpha=0.3)

    fig.tight_layout(rect=[0, 0.06, 1, 1])
    _add_caption(fig, "Fig. 2. Resonant frequency vs temperature for all five resonators (−25 dBm, 0 mW). Solid curves: cubic spline with outlier rejection; markers: retained data points.")
    fig.savefig(str(OUTPUT_DIR / "02_f0_vs_temp_all.jpg"), facecolor="white")
    fig.savefig(str(OUTPUT_DIR / "02_f0_vs_temp_all.svg"), facecolor="white")
    plt.close(fig)
    print("  [Fig2] f0(T) comparison -> 02_f0_vs_temp_all.*")


def plot_qi_vs_temp(tracks, num_res, temp_entries):
    """图 3：Qi(T) 五线叠加。"""
    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.set_prop_cycle(COLOR_CYCLE)

    for res_id in range(num_res):
        t = tracks[res_id]["temps"]
        q = tracks[res_id]["qis"]
        # Filter None/NaN: Qi is None when BW estimation fails, float otherwise
        valid = []
        for ti, qi in zip(t, q):
            if qi is None:
                continue
            if isinstance(qi, float) and np.isnan(qi):
                continue
            valid.append((ti, qi))
        if len(valid) > 1:
            tv, qv = zip(*valid)
            # Clip extreme Q values (from BW estimation errors)
            qv_clipped = np.array([min(qi, 20000) for qi in qv])
            c = COLORS[res_id % len(COLORS)]
            xs, ys, kept = smooth_spline(tv, qv_clipped)
            if xs is not None:
                ax.plot(xs, ys, "-", linewidth=2.5, color=c,
                        label=f"R{res_id + 1}")
                ax.plot(np.array(tv)[kept], qv_clipped[kept], "o", markersize=9, color=c, alpha=0.7)

    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel("Loaded Quality Factor QL")
    ax.set_title("QL(T) — All 5 Resonators (−25 dBm, 0 mW)", fontweight="bold", fontsize=20)
    ax.legend(loc="upper right", framealpha=0.8, facecolor="white",
              edgecolor="#999999", fontsize=12)
    ax.grid(True, alpha=0.3)

    fig.tight_layout(rect=[0, 0.06, 1, 1])
    _add_caption(fig, "Fig. 3. Loaded quality factor vs temperature (−25 dBm, 0 mW). QL estimated from −3 dB bandwidth; clipping at 20000.")
    fig.savefig(str(OUTPUT_DIR / "03_qi_vs_temp_all.jpg"), facecolor="white")
    fig.savefig(str(OUTPUT_DIR / "03_qi_vs_temp_all.svg"), facecolor="white")
    plt.close(fig)
    print("  [Fig3] Qi(T) comparison -> 03_qi_vs_temp_all.*")


def plot_optical_response(opt_data, num_res):
    """图 4：6K 光学响应 —— δf/f₀ vs 激光功率，纯散点无连线。"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    for res_id in range(num_res):
        if res_id not in opt_data or len(opt_data[res_id]["laser_powers"]) == 0:
            continue

        lp = opt_data[res_id]["laser_powers"]
        f0s = np.array(opt_data[res_id]["f0s"])
        dips = opt_data[res_id]["dips"]
        color = COLORS[res_id % len(COLORS)]
        f0_ref = f0s[0]

        # 左：δf/f₀ vs 激光功率，纯散点
        df_over_f = (f0s - f0_ref) / f0_ref * 1e6  # ppm
        ax1.scatter(lp, df_over_f, s=120, color=color, edgecolors="white", linewidth=0.8,
                    label=f"R{res_id + 1} ({f0_ref:.3f} GHz)", zorder=3)

        # 右：Dip vs 激光功率，纯散点
        ax2.scatter(lp, dips, s=120, color=color, edgecolors="white", linewidth=0.8,
                    label=f"R{res_id + 1}", zorder=3)

    ax1.set_xlabel("Laser Power (mW)")
    ax1.set_ylabel("δf / f₀  (×10⁻⁶, ppm)")
    ax1.set_title("Relative Frequency Shift vs Laser Power (6 K, −25 dBm)", fontweight="bold", fontsize=18)
    ax1.legend(loc="best", framealpha=0.8, facecolor="white", edgecolor="#999999", fontsize=11)
    ax1.grid(True, alpha=0.3)

    ax2.set_xlabel("Laser Power (mW)")
    ax2.set_ylabel("Dip Depth (dB)")
    ax2.set_title("Resonance Depth vs Laser Power (6 K, −25 dBm)", fontweight="bold", fontsize=18)
    ax2.legend(loc="best", framealpha=0.8, facecolor="white", edgecolor="#999999", fontsize=11)
    ax2.grid(True, alpha=0.3)

    fig.tight_layout(rect=[0, 0.06, 1, 1])
    _add_caption(fig, "Fig. 4. Relative frequency shift δf/f₀ vs laser power (6 K, −25 dBm). Scatter only; δf = f₀(P) − f₀(0 mW).")
    fig.savefig(str(OUTPUT_DIR / "04_optical_response_6k_all.jpg"), facecolor="white")
    fig.savefig(str(OUTPUT_DIR / "04_optical_response_6k_all.svg"), facecolor="white")
    plt.close(fig)
    print("  [Fig4] Optical response -> 04_optical_response_6k_all.*")


# ============================================================
# 新增图 5: QL vs VNA 读出功率
# ============================================================

def plot_ql_vs_power(temp_entries):
    """图 5：QL vs VNA 读出功率 (-45, -30, -25 dBm)，固定 T=6K, laser=0mW。"""
    t6k_dir = temp_entries[0][1]
    powers = [45, 30, 25]  # dBm (positive, negated in path)

    # 对每个功率检测谐振器
    all_res = {}  # {power: [(f0, dip, bw, ql), ...]}
    for pwr in powers:
        s2p_path = find_s2p(t6k_dir, pwr, 0)
        if s2p_path is None:
            all_res[pwr] = []
            continue
        cur = load_resonances(s2p_path)
        all_res[pwr] = cur

    # 用 -25dBm 的谐振器列表作为参考，匹配到其他功率
    ref = all_res[25]
    fig, ax = plt.subplots(figsize=(8, 5))

    for res_id, (f0_ref, dip_ref, bw_ref, ql_ref) in enumerate(ref):
        qls = []
        pwr_labels = []
        for pwr in powers:
            cur_list = all_res.get(pwr, [])
            # 最近邻匹配
            best = None
            best_dist = 200e6
            for cf0, cdip, cbw, cql in cur_list:
                d = abs(cf0 - f0_ref)
                if d < best_dist:
                    best_dist = d
                    best = (cf0, cdip, cbw, cql)
            if best is not None and best[3] is not None:
                qls.append(best[3])
                pwr_labels.append(-pwr)

        if len(qls) >= 2:
            c = COLORS[res_id % len(COLORS)]
            ax.plot(pwr_labels, qls, "o-", color=c, markersize=12, linewidth=2.5,
                    label=f"R{res_id + 1} ({f0_ref / 1e9:.3f} GHz)")

    ax.set_xlabel("VNA Readout Power (dBm)")
    ax.set_ylabel("Loaded Quality Factor QL")
    ax.set_title("QL vs Readout Power  (6 K, 0 mW Laser)", fontweight="bold", fontsize=20)
    ax.legend(loc="best", framealpha=0.8, facecolor="white", edgecolor="#999999", fontsize=12)
    ax.grid(True, alpha=0.3)
    # Reverse x-axis so -25 (highest power) is on the right
    ax.invert_xaxis()

    fig.tight_layout(rect=[0, 0.06, 1, 1])
    _add_caption(fig, "Fig. 5. Loaded quality factor vs VNA readout power (6 K, 0 mW laser).")
    fig.savefig(str(OUTPUT_DIR / "05_ql_vs_power.jpg"), facecolor="white")
    fig.savefig(str(OUTPUT_DIR / "05_ql_vs_power.svg"), facecolor="white")
    plt.close(fig)
    print("  [Fig5] QL vs Power -> 05_ql_vs_power.*")


# ============================================================
# 新增图 6: Δf/f₀ vs T（全温光学响应率）
# ============================================================

def compute_responsivity_all_t():
    """遍历所有温度点，计算每谐振器的 Δf/f₀ = [f0(9mW)-f0(0mW)]/f0(0mW)。

    Returns:
        responsivity: {res_id: {"temps": [...], "df_over_f": [...], "dips": [...]}}
    """
    temp_entries = scan_temperatures()
    # 用 6K 的 0mW 建立参考
    t6k_dir = temp_entries[0][1]
    s2p_ref = find_s2p(t6k_dir, FIXED_VNA_POWER, 0)
    ref_res = load_resonances(s2p_ref)
    ref_freqs = [r[0] for r in ref_res]
    n_res = len(ref_res)

    result = {i: {"temps": [], "df_over_f": [], "dips": []} for i in range(n_res)}

    for int_t, dirname in temp_entries:
        s2p_0 = find_s2p(dirname, FIXED_VNA_POWER, 0)
        s2p_9 = find_s2p(dirname, FIXED_VNA_POWER, 9)
        if s2p_0 is None or s2p_9 is None:
            continue

        res_0 = load_resonances(s2p_0)
        res_9 = load_resonances(s2p_9)

        for res_id, ref_f in enumerate(ref_freqs):
            # 在 0mW 中匹配
            best_0 = None
            best_d_0 = 200e6
            for f0, dip, bw, ql in res_0:
                d = abs(f0 - ref_f)
                if d < best_d_0:
                    best_d_0 = d
                    best_0 = (f0, dip, bw, ql)

            # 在 9mW 中匹配
            best_9 = None
            best_d_9 = 200e6
            for f0, dip, bw, ql in res_9:
                d = abs(f0 - ref_f)
                if d < best_d_9:
                    best_d_9 = d
                    best_9 = (f0, dip, bw, ql)

            if best_0 is not None and best_9 is not None:
                f0_dark = best_0[0]
                f0_lit = best_9[0]
                df_over_f = (f0_lit - f0_dark) / f0_dark
                result[res_id]["temps"].append(int_t)
                result[res_id]["df_over_f"].append(df_over_f)
                result[res_id]["dips"].append(best_0[1])

    return result


def plot_responsivity_vs_temp():
    """图 6：Δf/f₀ vs T，归一化光学响应率。"""
    resp = compute_responsivity_all_t()
    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.set_prop_cycle(COLOR_CYCLE)

    for res_id in range(len(resp)):
        t = resp[res_id]["temps"]
        df = np.array(resp[res_id]["df_over_f"]) * 1e6  # convert to ppm
        if len(t) > 1:
            c = COLORS[res_id % len(COLORS)]
            xs, ys, kept = smooth_spline(np.array(t), df)
            if xs is not None:
                ax.plot(xs, ys, "-", linewidth=2.5, color=c,
                        label=f"R{res_id + 1}")
                ta = np.array(t)
                ax.plot(ta[kept], df[kept], "o", markersize=9, color=c, alpha=0.7)

    ax.axhline(y=0, color="#333333", linewidth=1.0, alpha=0.3)
    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel("Δf / f₀  (×10⁻⁶, ppm)")
    ax.set_title("Normalized Optical Responsivity vs Temperature (9 mW Laser, −25 dBm)", fontweight="bold", fontsize=20)
    ax.legend(loc="best", framealpha=0.8, facecolor="white", edgecolor="#999999", fontsize=12)
    ax.grid(True, alpha=0.3)

    fig.tight_layout(rect=[0, 0.06, 1, 1])
    _add_caption(fig, "Fig. 6. Normalized optical responsivity δf/f₀ vs temperature (9 mW laser, -25 dBm). Curves truncate where resonance disappears.")
    fig.savefig(str(OUTPUT_DIR / "06_responsivity_vs_temp.jpg"), facecolor="white")
    fig.savefig(str(OUTPUT_DIR / "06_responsivity_vs_temp.svg"), facecolor="white")
    plt.close(fig)
    print("  [Fig6] Responsivity vs T -> 06_responsivity_vs_temp.*")


# ============================================================
# 图 7: Dip 深度 vs T（直观展示谐振消失过程）
# ============================================================

def plot_dip_vs_temp(tracks, num_res):
    """图 7：谐振谷深度 vs 温度。"""
    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.set_prop_cycle(COLOR_CYCLE)

    for res_id in range(num_res):
        t = np.array(tracks[res_id]["temps"])
        d = np.array(tracks[res_id]["dips"])
        mask = ~np.isnan(d)
        if mask.sum() > 1:
            c = COLORS[res_id % len(COLORS)]
            xs, ys, kept = smooth_spline(t[mask], d[mask])
            if xs is not None:
                ax.plot(xs, ys, "-", linewidth=2.5, color=c,
                        label=f"R{res_id + 1}")
                tm, dm = t[mask], d[mask]
                ax.plot(tm[kept], dm[kept], "o", markersize=9, color=c, alpha=0.7)

    ax.axhline(y=-1, color="red", linewidth=1.5, alpha=0.5, linestyle="--")
    ax.annotate("Detection limit (dip = −1 dB)", xy=(50, -1), fontsize=13,
                color="red", alpha=0.6, va="bottom")

    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel("Dip Depth (dB)")
    ax.set_title("Resonance Dip Depth vs Temperature", fontweight="bold", fontsize=20)
    ax.legend(loc="lower right", framealpha=0.8, facecolor="white", edgecolor="#999999", fontsize=12)
    ax.grid(True, alpha=0.3)

    fig.tight_layout(rect=[0, 0.06, 1, 1])
    _add_caption(fig, "Fig. 7. Resonance dip depth vs temperature. Dashed line: detection limit (dip = -1 dB).")
    fig.savefig(str(OUTPUT_DIR / "07_dip_vs_temp.jpg"), facecolor="white")
    fig.savefig(str(OUTPUT_DIR / "07_dip_vs_temp.svg"), facecolor="white")
    plt.close(fig)
    print("  [Fig7] Dip vs T -> 07_dip_vs_temp.*")


# ============================================================
# 图 8: 归一化 f₀ 偏移 vs T
# ============================================================

def plot_normalized_f0_vs_temp(tracks, num_res):
    """图 8：归一化 f₀ 偏移 (f₀(T)−f₀(6K))/f₀(6K) vs T。"""
    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.set_prop_cycle(COLOR_CYCLE)

    for res_id in range(num_res):
        t = np.array(tracks[res_id]["temps"])
        f = np.array(tracks[res_id]["f0s"])
        mask = ~np.isnan(f)
        if mask.sum() > 1:
            f0_6k = f[mask][0]  # first valid = 6K reference
            df_norm = (f[mask] - f0_6k) / f0_6k * 1e6  # ppm
            c = COLORS[res_id % len(COLORS)]
            xs, ys, kept = smooth_spline(t[mask], df_norm)
            if xs is not None:
                ax.plot(xs, ys, "-", linewidth=2.5, color=c,
                        label=f"R{res_id + 1} (f₀@6K={f0_6k:.3f} GHz)")
                tm, dm = t[mask], df_norm
                ax.plot(tm[kept], dm[kept], "o", markersize=9, color=c, alpha=0.7)

    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel("(f₀(T) − f₀(6K)) / f₀(6K)  (×10⁻⁶, ppm)")
    ax.set_title("Normalized Resonant Frequency Shift vs Temperature", fontweight="bold", fontsize=20)
    ax.legend(loc="lower left", framealpha=0.8, facecolor="white", edgecolor="#999999", fontsize=11)
    ax.grid(True, alpha=0.3)

    fig.tight_layout(rect=[0, 0.06, 1, 1])
    _add_caption(fig, "Fig. 8. Normalized resonant frequency shift (f₀(T)-f₀(6K))/f₀(6K) vs temperature. Coincident curves indicate uniform YBCO film quality.")
    fig.savefig(str(OUTPUT_DIR / "08_normalized_f0_vs_temp.jpg"), facecolor="white")
    fig.savefig(str(OUTPUT_DIR / "08_normalized_f0_vs_temp.svg"), facecolor="white")
    plt.close(fig)
    print("  [Fig8] Normalized f0 vs T -> 08_normalized_f0_vs_temp.*")


# ============================================================
# 图 9+10: 光学响应 2×2 复合图（δf/f₀ 散点 + 三功率 S21 局部放大）
# ============================================================

def _zoom_s21(ax, temp_dirname, power_dbm, laser_mw, f0_target, span_mhz=15):
    """在 ax 上绘制 S21 局部放大图（±span_mhz 窗口）。"""
    s2p_path = find_s2p(temp_dirname, power_dbm, laser_mw)
    if s2p_path is None:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes, fontsize=11)
        return
    freq, s21 = dp.load_s_param(s2p_path)
    amp = 20 * np.log10(np.abs(s21))
    mask = (freq > f0_target - span_mhz * 1e6) & (freq < f0_target + span_mhz * 1e6)
    if not mask.any():
        ax.text(0.5, 0.5, "Out of range", ha="center", va="center", transform=ax.transAxes, fontsize=11)
        return
    ax.plot(freq[mask] / 1e9, amp[mask], linewidth=1.5, color="#1F77B4")
    # 标记最低点
    idx_min = np.argmin(amp[mask])
    f_min = freq[mask][idx_min]
    a_min = amp[mask][idx_min]
    ax.plot(f_min / 1e9, a_min, "o", markersize=10, color="#D62728", zorder=3)
    ax.set_xlabel("Frequency (GHz)", fontsize=11)
    ax.set_ylabel("|S21| (dB)", fontsize=11)
    ax.set_title(f"−{power_dbm} dBm", fontsize=13, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.tick_params(labelsize=10)


def plot_optical_composite_6k(opt_data, temp_entries):
    """图 9：6K 光学响应 2×2 复合 —— 左大：δf/f₀ 散点，右三：S21 局部放大。"""
    t_dir = temp_entries[0][1]  # 6K
    # 用 R4 作 S21 局部放大参考（最深谐振器）
    f0_r4 = None
    for r in opt_data.get(3, {}).get("f0s", []):
        f0_r4 = r
        break

    fig = plt.figure(figsize=(13, 7.5))
    # 左大面板：δf/f₀ 散点
    ax_left = fig.add_axes([0.08, 0.12, 0.48, 0.78])

    for res_id in range(len(opt_data)):
        if res_id not in opt_data or len(opt_data[res_id]["laser_powers"]) == 0:
            continue
        lp = opt_data[res_id]["laser_powers"]
        f0s = np.array(opt_data[res_id]["f0s"])
        f0_ref = f0s[0]
        df_over_f = (f0s - f0_ref) / f0_ref * 1e6
        c = COLORS[res_id % len(COLORS)]
        ax_left.scatter(lp, df_over_f, s=100, color=c, edgecolors="white", linewidth=0.8,
                        label=f"R{res_id + 1} ({f0_ref:.3f} GHz)", zorder=3)

    ax_left.set_xlabel("Laser Power (mW)", fontsize=13)
    ax_left.set_ylabel("δf / f₀  (×10⁻⁶, ppm)", fontsize=13)
    ax_left.set_title("Optical Response @ 6 K", fontweight="bold", fontsize=18)
    ax_left.legend(loc="best", framealpha=0.8, facecolor="white", edgecolor="#999999", fontsize=11)
    ax_left.grid(True, alpha=0.3)
    ax_left.tick_params(labelsize=11)

    # 右三面板：S21 局部放大（-25/-30/-45 dBm, 0mW）
    if f0_r4 is not None:
        positions = [(0.62, 0.59, 0.34, 0.30), (0.62, 0.35, 0.34, 0.21), (0.62, 0.12, 0.34, 0.21)]
        for (l, b, w, h), pwr in zip(positions, [25, 30, 45]):
            ax = fig.add_axes([l, b, w, h])
            _zoom_s21(ax, t_dir, pwr, 0, f0_r4)
    else:
        fig.text(0.79, 0.5, "R4 not detected", ha="center", va="center", fontsize=13, color="red")

    _add_caption(fig, "Fig. 9. Optical response at 6 K. Left: δf/f₀ vs laser power for all 5 resonators. Right: S21 zoom (±15 MHz) of R4 at three readout powers (0 mW laser).")
    fig.savefig(str(OUTPUT_DIR / "09_optical_composite_6k.jpg"), facecolor="white", dpi=300)
    fig.savefig(str(OUTPUT_DIR / "09_optical_composite_6k.svg"), facecolor="white")
    plt.close(fig)
    print("  [Fig9] Optical composite 6K -> 09_optical_composite_6k.*")


def plot_optical_composite_hight(opt_data, temp_entries):
    """图 10：高温光学响应 2×2 复合 —— 用最高可测温度。"""
    # 找最高温有 R4 数据的温度点
    best_t_dir = None; best_t_int = 0; best_f0 = None
    for int_t, dirname in reversed(temp_entries):
        s2p_path = find_s2p(dirname, FIXED_VNA_POWER, 0)
        if s2p_path is None:
            continue
        res = load_resonances(s2p_path)
        r4_candidates = [r for r in res if 4.9e9 < r[0] < 5.1e9]
        if r4_candidates:
            best_t_dir = dirname; best_t_int = int_t; best_f0 = r4_candidates[0][0]
            break

    fig = plt.figure(figsize=(13, 7.5))

    # 左面板：δf/f₀ vs T（用 compute_responsivity_all_t 的数据）
    resp = compute_responsivity_all_t()
    ax_left = fig.add_axes([0.08, 0.12, 0.48, 0.78])
    for res_id in range(len(resp)):
        t = resp[res_id]["temps"]
        df = np.array(resp[res_id]["df_over_f"]) * 1e6
        if len(t) > 1:
            c = COLORS[res_id % len(COLORS)]
            ax_left.scatter(t, df, s=80, color=c, alpha=0.7, zorder=3)
            xs, ys, kept = smooth_spline(np.array(t), df)
            if xs is not None:
                ax_left.plot(xs, ys, "-", linewidth=2.5, color=c, label=f"R{res_id + 1}")
    ax_left.set_xlabel("Temperature (K)", fontsize=13)
    ax_left.set_ylabel("δf / f₀  (×10⁻⁶, ppm)", fontsize=13)
    ax_left.set_title(f"Optical Responsivity vs Temperature", fontweight="bold", fontsize=18)
    ax_left.legend(loc="best", framealpha=0.8, facecolor="white", edgecolor="#999999", fontsize=11)
    ax_left.grid(True, alpha=0.3)
    ax_left.tick_params(labelsize=11)

    # 右三面板：高温 S21 局部放大
    if best_t_dir is not None and best_f0 is not None:
        positions = [(0.62, 0.59, 0.34, 0.30), (0.62, 0.35, 0.34, 0.21), (0.62, 0.12, 0.34, 0.21)]
        for (l, b, w, h), pwr in zip(positions, [25, 30, 45]):
            ax = fig.add_axes([l, b, w, h])
            _zoom_s21(ax, best_t_dir, pwr, 0, best_f0)
        fig.text(0.79, 0.82, f"R4 @ {best_t_int} K", ha="center", fontsize=12,
                 fontweight="bold", color="#333333")
    else:
        fig.text(0.79, 0.5, "No resonance\ndetected at high T", ha="center", va="center", fontsize=13, color="red")

    _add_caption(fig, f"Fig. 10. Optical responsivity vs temperature (left) and S21 zoom of R4 at the highest detectable temperature ({best_t_int} K, right).")
    fig.savefig(str(OUTPUT_DIR / "10_optical_composite_hight.jpg"), facecolor="white", dpi=300)
    fig.savefig(str(OUTPUT_DIR / "10_optical_composite_hight.svg"), facecolor="white")
    plt.close(fig)
    print("  [Fig10] Optical composite high-T -> 10_optical_composite_hight.*")


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 60)
    print("YBCO 5-Resonator Comparison")
    print("=" * 60)

    # 1. 跨温度追踪
    print("\n[1/5] Tracking resonators across T...")
    temp_entries = scan_temperatures()
    tracks, num_res = track_all_resonators()

    print(f"  Tracked {num_res} resonators")
    for res_id in range(num_res):
        valid = sum(1 for f in tracks[res_id]["f0s"] if not np.isnan(f))
        f0_init = tracks[res_id]["f0s"][0] if tracks[res_id]["f0s"] else np.nan
        print(f"    R{res_id + 1}: f0 ~ {f0_init:.4f} GHz, valid T-points: {valid}")

    # 2. 光学响应
    print("\n[2/5] Extracting 6K optical response...")
    opt_data = optical_response_6k()
    for res_id, od in opt_data.items():
        print(f"    R{res_id + 1}: {len(od['laser_powers'])} laser power points")

    # 3-8. 绘图
    print("\n[3/5] Generating comparison figures...")
    plot_spectrum_overview(tracks, num_res, temp_entries)
    plot_f0_vs_temp(tracks, num_res, temp_entries)
    plot_qi_vs_temp(tracks, num_res, temp_entries)
    plot_optical_response(opt_data, num_res)
    plot_ql_vs_power(temp_entries)
    plot_responsivity_vs_temp()
    plot_dip_vs_temp(tracks, num_res)
    plot_normalized_f0_vs_temp(tracks, num_res)
    plot_optical_composite_6k(opt_data, temp_entries)
    plot_optical_composite_hight(opt_data, temp_entries)

    # 导出汇总表格
    print("\n[5/5] Exporting summary data...")
    _export_summary(tracks, num_res, opt_data)

    print(f"\nAll outputs saved to: {OUTPUT_DIR}")
    print("Done.")


def _export_summary(tracks, num_res, opt_data):
    """导出 CSV 汇总文件。"""
    csv_path = OUTPUT_DIR / "resonator_summary.csv"
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("resonator,f0_6K_GHz,dip_6K_dB,QL_6K")
        for lp in LASER_POWERS:
            f.write(f",delta_f0_{lp}mW_kHz")
        f.write("\n")

        for res_id in range(num_res):
            f0 = tracks[res_id]["f0s"][0] if tracks[res_id]["f0s"] else np.nan
            dip = tracks[res_id]["dips"][0] if tracks[res_id]["dips"] else np.nan
            qi = tracks[res_id]["qis"][0] if tracks[res_id]["qis"] else ""

            f.write(f"R{res_id + 1},{f0:.6f},{dip:.2f},{qi}")

            if res_id in opt_data and len(opt_data[res_id]["f0s"]) > 0:
                f0_ref = opt_data[res_id]["f0s"][0]
                for lp in LASER_POWERS:
                    if lp in opt_data[res_id]["laser_powers"]:
                        idx = opt_data[res_id]["laser_powers"].index(lp)
                        delta = (opt_data[res_id]["f0s"][idx] - f0_ref) * 1e6  # kHz
                        f.write(f",{delta:.2f}")
                    else:
                        f.write(",")
            else:
                f.write(",," * len(LASER_POWERS))
            f.write("\n")

    print(f"  Summary CSV -> {csv_path}")


if __name__ == "__main__":
    main()
