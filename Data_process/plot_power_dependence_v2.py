# -*- coding: utf-8 -*-
"""
S21 随功率变化 — 全谱 + 五谐振子局部放大。

追踪策略 (v4):
  1. f0(T) 曲线驱动: scraps 数据 [6,22,38,54,70]K 为骨架 → 有限差分外推
  2. 双验证:
     a) 预测位置 ±50 MHz → 局部基线矫正 dip 检测
     b) 若失败 → find_true_resonances() 幅度+相位交叉验证基线图找谐振
  3. Zoom 窗口: T≤20K→±10MHz, T≥77K→±30MHz, 中间线性渐变
  4. 局部基线 = P90, dip_depth = dip_abs - baseline < -1 dB 判定存活

格式: skrf.Network, 红→紫渐变, figsize=(12,8), lw=3, alpha=0.8, Grid, Legend

输出: output/_power_dependence_v2/
"""
import os
import glob
import sys
from pathlib import Path
import numpy as np
import matplotlib
try:
    import IPython
    matplotlib.use("Qt5Agg")
except Exception:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
import skrf as rf

# dataprocess (find_true_resonances)
_script_dir = Path(__file__).resolve().parent
_otherwise = _script_dir / "otherwise"
if str(_otherwise) not in sys.path:
    sys.path.insert(0, str(_otherwise))
import dataprocess as dp

# ============================================================
# 配置
# ============================================================
DATA = Path(r"D:\YBCO\VNAMeas\Auto_Sweep\experiment_data\merged")
OUTPUT = _script_dir / "output" / "_power_dependence_v2"

# 图风格
FIG_SIZE = (12, 8)
LINE_ALPHA = 0.8
LINE_WIDTH = 3
CMAP = plt.cm.jet  # 深蓝(冷,0mW) → 青 → 绿 → 黄 → 红(热,9mW)
DPI = 150

# scraps 频率演化骨架: T = [6, 22, 38, 54, 70] K
SCRAPS_TEMPS = np.array([6, 22, 38, 54, 70])
SCRAPS_F0 = {
    "R1": np.array([3.8451, 3.8334, 3.8020, 3.7405, 3.5841]),
    "R2": np.array([4.0085, 3.9961, 3.9625, 3.8974, 3.7319]),
    "R3": np.array([4.4990, 4.4854, 4.4499, 4.3812, 4.2064]),
    "R4": np.array([4.9957, 4.9803, 4.9397, 4.8611, 4.6644]),
    "R5": np.array([5.2503, 5.2343, 5.1917, 5.0831, 4.6644]),
}

# 温度节点
LASER_TEMPS = [6, 10, 20, 40, 76]
VNA_TEMPS = [6, 10, 20, 40, 76]
FULL_SPEC_TEMP = 6
VNA_DBM_FOR_LASER = 25
LASER_MW_FOR_VNA = 0
ALL_LASER_POWERS = [0, 1, 3, 5, 7, 9]
ALL_VNA_POWERS = [25, 30, 45]

# find_true_resonances 参数 (同 generate_all_resonators_scraps.py 寻峰)
PEAK_KWARGS = dict(
    min_prominence=1, distance=50, phase_window=25,
    phase_diff_snr_threshold=1.5, noise_inner_window=5,
    noise_outer_window=40, min_phase_diff_support_points=2,
    min_phase_diff_width=2, plot=True,
)

# ============================================================
# 工具: Zoom 窗口 (温度自适应)
# ============================================================

def _zoom_mhz(temp_k: float) -> float:
    """T ≤ 20K → 10 MHz; T ≥ 77K → 30 MHz; 中间线性渐变。"""
    if temp_k <= 20:
        return 10.0
    if temp_k >= 77:
        return 30.0
    return 10.0 + (temp_k - 20.0) / (77.0 - 20.0) * 20.0


# ============================================================
# 核心: 有限差分外推 f0(T)
# ============================================================

def _predict_f0_fd(f0_history: list, temp_k: float) -> float:
    """
    有限差分外推预测温度 temp_k 的 f0。

    - 若 temp_k 已在历史中 → 直接返回精确值
    - 否则取历史中温度 < temp_k 的最近 3-5 个点做有限差分外推

    f0_history: [(T1, f0_1), (T2, f0_2), ...] 按温度升序。
    """
    if not f0_history:
        return None

    # 精确匹配
    for tk, f0 in f0_history:
        if abs(tk - temp_k) < 0.5:
            return f0

    # 仅取温度低于目标的历史点
    below = [(tk, f0) for tk, f0 in f0_history if tk < temp_k]
    if not below:
        # 目标温度低于所有历史点 → 用最近点
        return f0_history[0][1]

    recent = below[-5:]
    f_vals = [f for _, f in recent]
    n = len(f_vals)

    if n == 1:
        # 只有一个低温点: 用最近温度差做线性外推
        # 找最接近目标温度的两个历史点 (可能一个低于, 一个高于)
        all_points = sorted(f0_history, key=lambda x: abs(x[0] - temp_k))
        if len(all_points) >= 2:
            t1, f1 = all_points[0]
            t2, f2 = all_points[1]
            if abs(t1 - t2) > 1:
                slope = (f2 - f1) / (t2 - t1)
                return f1 + slope * (temp_k - t1)
        return f_vals[0]
    elif n == 2:
        # 线性外推
        return f_vals[-1] + (f_vals[-1] - f_vals[-2])
    elif n == 3:
        f1, f2, f3 = f_vals
        return f3 + (f3 - f2) - (f3 - 2*f2 + f1)
    elif n == 4:
        f1, f2, f3, f4 = f_vals
        return f4 + (f4 - f3) - (f4 - 2*f3 + f2) + (f4 - 3*f3 + 3*f2 - f1)
    else:  # n >= 5
        f1, f2, f3, f4, f5 = f_vals[-5:]
        return (f5 + (f5 - f4) - (f5 - 2*f4 + f3)
                + (f5 - 3*f4 + 3*f3 - f2)
                - (f5 - 4*f4 + 6*f3 - 4*f2 + f1))


# ============================================================
# 核心: 局部基线矫正 dip 检测
# ============================================================

def _detect_dip_baseline(freq_ghz, s21_db, f0_pred, search_mhz=50):
    """
    在预测位置附近搜索 dip，局部基线矫正。

    返回 (f0_found, dip_depth, baseline) 或 (None, None, None)。
    """
    lo = f0_pred - search_mhz / 1000.0
    hi = f0_pred + search_mhz / 1000.0
    mask = (freq_ghz >= lo) & (freq_ghz <= hi)
    if mask.sum() < 20:
        return None, None, None

    f_win = freq_ghz[mask]
    s_win = s21_db[mask]

    baseline = float(np.percentile(s_win, 90))
    dip_abs = float(np.min(s_win))
    dip_depth = dip_abs - baseline
    idx_min = np.argmin(s_win)
    f_dip = float(f_win[idx_min])

    return f_dip, dip_depth, baseline


# ============================================================
# 核心: 双验证追踪单个谐振子
# ============================================================

def _track_one_resonator(freq_hz, s21_db, s21_complex, rname, temp_k,
                         f0_history, resonance_cache):
    """
    双验证追踪单个谐振子:

    验证 a) 有限差分预测 + 局部基线 dip 检测
    验证 b) 若 a 失败 → find_true_resonances() 幅度+相位交叉验证寻峰

    freq_hz: 频率数组 (Hz), s21_db: |S21| (dB), s21_complex: 复 S21
    返回 (f0_found_GHz, dip_depth) 或 (None, None)。
    """
    f0_pred = _predict_f0_fd(f0_history, temp_k)
    if f0_pred is None:
        return None, None

    freq_ghz = freq_hz / 1e9

    # 验证 a: 局部基线矫正 dip 检测
    f_dip, dip_depth, baseline = _detect_dip_baseline(freq_ghz, s21_db, f0_pred, search_mhz=50)

    if f_dip is not None and dip_depth < -1.0:
        deviation = abs(f_dip - f0_pred) * 1000
        if deviation < 100:
            return f_dip, dip_depth
        if dip_depth < -3.0:
            return f_dip, dip_depth

    # 验证 b: 用 find_true_resonances 在当前温度重新寻峰（幅度+相位交叉验证）
    if temp_k not in resonance_cache:
        try:
            peaks, fig, axes = dp.find_true_resonances(
                freq=freq_hz, s21=s21_complex, **{**PEAK_KWARGS, "plot": True})
            resonance_cache[temp_k] = (peaks, fig, axes)
        except Exception as e:
            print(f"    [!] find_true_resonances failed: {e}")
            resonance_cache[temp_k] = ([], None, None)

    peaks, fig, axes = resonance_cache[temp_k]

    # 从寻峰结果中找离预测位置最近的 dip (frequency 单位同 freq_hz 即 Hz)
    best_f0, best_dist = None, 999
    for p in peaks:
        pf_ghz = p["frequency"] / 1e9
        dist = abs(pf_ghz - f0_pred) * 1000  # MHz
        if dist < 80 and dist < best_dist:
            best_dist = dist
            best_f0 = pf_ghz

    if best_f0 is not None:
        _, dd, _ = _detect_dip_baseline(freq_ghz, s21_db, best_f0, search_mhz=10)
        return best_f0, dd if dd is not None else -99

    return None, None


# ============================================================
# 工具函数
# ============================================================

def _find_temp_dir(target_temp: int):
    for d in sorted(DATA.iterdir()):
        if d.is_dir() and d.name.endswith("K"):
            try:
                if int(d.name.rstrip("K")) == target_temp:
                    return d
            except ValueError:
                pass
    return None


def _collect_s2p(folder: Path):
    return sorted(glob.glob(os.path.join(str(folder), "**", "*.s2p"), recursive=True))


def _zoom_around(freq, s21_db, center_ghz, span_mhz):
    lo = center_ghz - span_mhz / 1000.0
    hi = center_ghz + span_mhz / 1000.0
    mask = (freq >= lo) & (freq <= hi)
    return freq[mask], s21_db[mask]


def _plot_overview(ax, s2p_files, title, legend_labels=None):
    n = len(s2p_files)
    for i, fp in enumerate(s2p_files):
        try:
            ntwk = rf.Network(fp)
            freq = ntwk.f / 1e9
            s21_db = 20 * np.log10(np.abs(ntwk.s[:, 1, 0]))
            color = CMAP(i / max(n, 1))
            label = legend_labels[i] if legend_labels and i < len(legend_labels) else os.path.basename(fp)
            ax.plot(freq, s21_db, color=color, linewidth=LINE_WIDTH, alpha=LINE_ALPHA, label=label)
        except Exception as e:
            print(f"  [!] 读取失败 {fp}: {e}")
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("|S21| (dB)")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=8)
    ax.grid(True)


def _plot_zoom(ax, s2p_files, center_ghz, zoom_mhz, title, legend_labels=None):
    n = len(s2p_files)
    for i, fp in enumerate(s2p_files):
        try:
            ntwk = rf.Network(fp)
            freq = ntwk.f / 1e9
            s21_db = 20 * np.log10(np.abs(ntwk.s[:, 1, 0]))
            fz, sz = _zoom_around(freq, s21_db, center_ghz, zoom_mhz)
            if len(fz) == 0:
                continue
            color = CMAP(i / max(n, 1))
            label = legend_labels[i] if legend_labels and i < len(legend_labels) else os.path.basename(fp)
            ax.plot(fz, sz, color=color, linewidth=LINE_WIDTH, alpha=LINE_ALPHA, label=label)
        except Exception as e:
            print(f"  [!] 读取失败 {fp}: {e}")
    ax.axvline(x=center_ghz, color="red", linestyle="--", alpha=0.5, linewidth=1)
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("|S21| (dB)")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=8)
    ax.grid(True)


def _save_and_close(fig, outpath):
    fig.tight_layout()
    fig.savefig(outpath, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  [OK] {outpath.name}")


# ============================================================
# Group 1: S21 vs Laser Power
# ============================================================

def plot_laser_sweep(subdir: Path, baseline_dir: Path):
    vna_str = f"-{VNA_DBM_FOR_LASER}dBm"
    laser_labels = [f"{mw} mW" for mw in ALL_LASER_POWERS]

    # 全局谐振子追踪状态: {rname: [(T, f0), ...]}
    global_tracking = {r: [] for r in SCRAPS_F0}

    # 初始化: 从 scraps 骨架加载已知 f0(T) 点
    for rname in SCRAPS_F0:
        for tk, f0 in zip(SCRAPS_TEMPS, SCRAPS_F0[rname]):
            global_tracking[rname].append((float(tk), float(f0)))

    for temp in LASER_TEMPS:
        t_dir = _find_temp_dir(temp)
        if t_dir is None:
            print(f"  [SKIP] T={temp}K — no folder")
            continue
        vna_dir = t_dir / vna_str
        if not vna_dir.is_dir():
            print(f"  [SKIP] T={t_dir.name} — no {vna_str}")
            continue

        actual_k = float(t_dir.name.rstrip("K"))
        zoom_mhz = _zoom_mhz(actual_k)

        print(f"\n  --- Laser Sweep | T={t_dir.name} (zoom=+-{zoom_mhz:.0f}MHz) ---")

        # 收集 S2P 文件
        s2p_files = []
        for mw in ALL_LASER_POWERS:
            mw_dir = vna_dir / f"{mw:02d}mW"
            if mw_dir.is_dir():
                flist = _collect_s2p(mw_dir)
                s2p_files.append(flist[0] if flist else None)
            else:
                s2p_files.append(None)

        valid = [(i, fp) for i, fp in enumerate(s2p_files) if fp is not None]
        valid_files = [fp for _, fp in valid]
        valid_labels = [laser_labels[i] for i, _ in valid]
        if len(valid_files) < 2:
            print(f"  [SKIP] valid files < 2")
            continue

        # 用 laser=0mW 文件追踪/确认此温度下的 f0
        ref_fp = valid_files[0]
        ref_ntwk = rf.Network(ref_fp)
        ref_freq_hz = ref_ntwk.f              # Hz, 供 find_true_resonances
        ref_freq_ghz = ref_freq_hz / 1e9      # GHz, 供 dip 检测和画图
        ref_s21_complex = ref_ntwk.s[:, 1, 0]
        ref_s21_db = 20 * np.log10(np.abs(ref_s21_complex))

        # 逐谐振子双验证追踪
        resonance_cache = {}
        tracked_this_temp = {}
        need_baseline_plot = False

        # 先保存原始 FD 预测（在历史被污染前）
        fd_predictions = {}
        for rname in SCRAPS_F0:
            fd_predictions[rname] = _predict_f0_fd(global_tracking[rname], actual_k)

        for rname in SCRAPS_F0:
            history = global_tracking[rname]
            f0_found, dip_depth = _track_one_resonator(
                ref_freq_hz, ref_s21_db, ref_s21_complex, rname, actual_k, history, resonance_cache)

            if f0_found is not None:
                tracked_this_temp[rname] = (f0_found, dip_depth)
                # 如果这个温度点还不在追踪历史中，加入
                existing_temps = {t for t, _ in history}
                if actual_k not in existing_temps:
                    history.append((actual_k, f0_found))
                    history.sort(key=lambda x: x[0])
                print(f"    {rname}: f0={f0_found:.4f}GHz  depth={dip_depth:+.1f}dB  [OK]")
            else:
                f0_pred = _predict_f0_fd(history, actual_k)
                print(f"    {rname}: NOT FOUND (pred={f0_pred:.4f}GHz) -> baseline plot fallback")
                need_baseline_plot = True

        # 碰撞检测: 两个谐振子追踪到同一 dip → 扩大搜索窗口重新分离
        rnames = list(tracked_this_temp.keys())
        for i in range(len(rnames)):
            for j in range(i + 1, len(rnames)):
                ra, rb = rnames[i], rnames[j]
                fa, _ = tracked_this_temp[ra]
                fb, _ = tracked_this_temp[rb]
                if abs(fa - fb) < 0.010:  # < 10 MHz → 碰撞
                    print(f"    [COLLISION] {ra}({fa:.4f}) <-> {rb}({fb:.4f}) — re-search with +-150MHz")

                    # 在 3.0-6.0 GHz 全频段找所有 dip (局部基线 < -1 dB)
                    from scipy.signal import argrelextrema
                    all_dips = []
                    for order in [300, 150, 80]:  # 多尺度扫描
                        min_idx = argrelextrema(ref_s21_db, np.less, order=order)[0]
                        for mi in min_idx:
                            f_d = ref_freq_ghz[mi]
                            # 局部基线
                            lo = max(0, mi-800); hi = min(len(ref_s21_db), mi+800)
                            bl = float(np.percentile(ref_s21_db[lo:hi], 90))
                            dd = float(ref_s21_db[mi]) - bl
                            if dd < -0.8:
                                all_dips.append((f_d, dd))
                    # 按频率排序去重
                    all_dips.sort()
                    unique_dips = []
                    for fd, dd in all_dips:
                        if not unique_dips or abs(fd - unique_dips[-1][0]) > 0.005:
                            unique_dips.append((fd, dd))

                    print(f"      Found {len(unique_dips)} candidate dips in full band:")
                    for fd, dd in unique_dips:
                        print(f"        {fd:.4f} GHz  depth={dd:+.1f}dB")

                    # 最优分配: 最小化总偏差，强制保持频谱序 (R编号越大频率越高)
                    collided = [ra, rb]
                    # 确保 ra 编号 < rb (即 ra 应该在左边)
                    if int(ra[1]) > int(rb[1]):
                        collided = [rb, ra]  # ra=左边, rb=右边
                    r_left, r_right = collided

                    candidates = [(fd, dd) for fd, dd in unique_dips if dd < -0.8]
                    candidates.sort()  # 按频率升序

                    best_total = 999999
                    best_assign = {}
                    for fd_left, dd_left in candidates:
                        for fd_right, dd_right in candidates:
                            if fd_left >= fd_right:
                                continue  # 左边必须 < 右边
                            dist_left = abs(fd_left - fd_predictions.get(r_left, 0)) * 1000
                            dist_right = abs(fd_right - fd_predictions.get(r_right, 0)) * 1000
                            total = dist_left + dist_right
                            if total < best_total:
                                best_total = total
                                best_assign = {
                                    r_left: (fd_left, dd_left, dist_left),
                                    r_right: (fd_right, dd_right, dist_right),
                                }

                    for rn in collided:
                        if rn in best_assign:
                            best_fd, _, best_dist = best_assign[rn]
                            _, dd2, _ = _detect_dip_baseline(ref_freq_ghz, ref_s21_db, best_fd, search_mhz=10)
                            dd2 = dd2 if dd2 is not None else -99
                            tracked_this_temp[rn] = (best_fd, dd2)
                            hist = global_tracking[rn]
                            hist_temps = {t for t, _ in hist}
                            if actual_k not in hist_temps:
                                hist.append((actual_k, best_fd))
                                hist.sort(key=lambda x: x[0])
                            pred = fd_predictions.get(rn, 0)
                            print(f"      {rn}: pred={pred:.4f} -> assigned {best_fd:.4f}GHz (dist={best_dist:.0f}MHz)  depth={dd2:+.1f}dB")
                        else:
                            print(f"      {rn}: pred={fd_predictions.get(rn,0):.4f} -> no assignment")

        # 如果有谐振子未追踪到 → 保存基线图供人工核验
        if need_baseline_plot and actual_k in resonance_cache:
            _, fig, axes = resonance_cache[actual_k]
            if fig is not None:
                bp = baseline_dir / f"baseline_T{t_dir.name}.png"
                _save_and_close(fig, bp)

                # 从基线图重新提取漏掉的谐振子
                peaks, _, _ = resonance_cache[actual_k]
                for rname in SCRAPS_F0:
                    if rname in tracked_this_temp:
                        continue
                    history = global_tracking[rname]
                    f0_pred = _predict_f0_fd(history, actual_k)
                    if f0_pred is None:
                        continue
                    # 在基线图找到的谐振峰中搜索最近的
                    best = None
                    best_dist = 999
                    for p in peaks:
                        pf = p["frequency"] / 1e9
                        dist = abs(pf - f0_pred) * 1000
                        if dist < 100 and dist < best_dist:
                            best_dist = dist
                            best = pf
                    if best is not None:
                        _, dd, _ = _detect_dip_baseline(ref_freq_ghz, ref_s21_db, best, search_mhz=10)
                        tracked_this_temp[rname] = (best, dd if dd else -99)
                        history.append((actual_k, best))
                        history.sort(key=lambda x: x[0])
                        print(f"    {rname}: baseline recovery -> f0={best:.4f}GHz  [RECOVERED]")

        if not tracked_this_temp:
            print(f"  [SKIP] no resonators tracked")
            continue

        # 全谱图
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        _plot_overview(ax, valid_files,
                       f"T = {t_dir.name},  VNA = -{VNA_DBM_FOR_LASER} dBm  |  S21 vs Laser Power",
                       legend_labels=valid_labels)
        _save_and_close(fig, subdir / f"T{t_dir.name}_overview.png")

        # 每个谐振子 zoom (温度自适应窗口)
        for rname, (f0_actual, depth) in tracked_this_temp.items():
            fig, ax = plt.subplots(figsize=FIG_SIZE)
            _plot_zoom(ax, valid_files, f0_actual, zoom_mhz,
                       f"{rname}  f0 = {f0_actual:.4f} GHz  |  T = {t_dir.name},  "
                       f"VNA = -{VNA_DBM_FOR_LASER} dBm  |  zoom = +-{zoom_mhz:.0f} MHz",
                       legend_labels=valid_labels)
            _save_and_close(fig, subdir / f"T{t_dir.name}_{rname}_zoom.png")


# ============================================================
# Group 2: S21 vs VNA Power
# ============================================================

def plot_vna_sweep(subdir: Path):
    vna_labels = [f"-{mp} dBm" for mp in ALL_VNA_POWERS]

    for temp in VNA_TEMPS:
        t_dir = _find_temp_dir(temp)
        if t_dir is None:
            print(f"  [SKIP] T={temp}K")
            continue

        actual_k = float(t_dir.name.rstrip("K"))
        zoom_mhz = _zoom_mhz(actual_k)
        print(f"\n  --- VNA Sweep | T={t_dir.name} (zoom=+-{zoom_mhz:.0f}MHz) ---")

        s2p_files = []
        for mp in ALL_VNA_POWERS:
            mw_dir = t_dir / f"-{mp}dBm" / f"{LASER_MW_FOR_VNA:02d}mW"
            if mw_dir.is_dir():
                flist = _collect_s2p(mw_dir)
                s2p_files.append(flist[0] if flist else None)
            else:
                s2p_files.append(None)

        valid = [(i, fp) for i, fp in enumerate(s2p_files) if fp is not None]
        valid_files = [fp for _, fp in valid]
        valid_labels = [vna_labels[i] for i, _ in valid]
        if len(valid_files) < 2:
            print(f"  [SKIP] valid files < 2")
            continue

        # 用 laser=0mW, VNA=-25dBm 的追踪结果作为 zoom 中心
        # (复用 laser sweep 的 tracked f0 — 这里简化, 直接用第一个有效文件做双验证)
        ref_ntwk = rf.Network(valid_files[0])
        ref_freq = ref_ntwk.f / 1e9
        ref_s21_db = 20 * np.log10(np.abs(ref_ntwk.s[:, 1, 0]))

        # 用 scraps 外推 + 局部基线检测
        # 搜索窗口温度自适应: 近 Tc 频移加速, FD 预测偏差可达 ~100 MHz
        search_mhz = 80.0 if actual_k <= 50 else 80.0 + (200.0 - 80.0) * (actual_k - 50) / (76 - 50)
        tracked_f0s = {}
        for rname in SCRAPS_F0:
            history = [(float(tk), float(f0)) for tk, f0 in zip(SCRAPS_TEMPS, SCRAPS_F0[rname])]
            f0_pred = _predict_f0_fd(history, actual_k)
            if f0_pred is None:
                continue
            f_dip, dip_depth, _ = _detect_dip_baseline(ref_freq, ref_s21_db, f0_pred, search_mhz=search_mhz)
            if f_dip is not None and dip_depth < -1.0:
                tracked_f0s[rname] = (f_dip, dip_depth)

        if not tracked_f0s:
            print(f"  [SKIP] no resonators tracked")
            continue

        fig, ax = plt.subplots(figsize=FIG_SIZE)
        _plot_overview(ax, valid_files,
                       f"T = {t_dir.name},  Laser = {LASER_MW_FOR_VNA} mW  |  S21 vs VNA Power",
                       legend_labels=valid_labels)
        _save_and_close(fig, subdir / f"T{t_dir.name}_overview.png")

        for rname, (f0_actual, depth) in tracked_f0s.items():
            fig, ax = plt.subplots(figsize=FIG_SIZE)
            _plot_zoom(ax, valid_files, f0_actual, zoom_mhz,
                       f"{rname}  f0 = {f0_actual:.4f} GHz  |  T = {t_dir.name},  "
                       f"Laser = {LASER_MW_FOR_VNA} mW  |  zoom = +-{zoom_mhz:.0f} MHz",
                       legend_labels=valid_labels)
            _save_and_close(fig, subdir / f"T{t_dir.name}_{rname}_zoom.png")


# ============================================================
# Group 3: 全谱标注 (6K)
# ============================================================

def plot_full_spectrum(subdir: Path, baseline_dir: Path):
    t_dir = _find_temp_dir(FULL_SPEC_TEMP)
    if t_dir is None:
        print("[SKIP] no 6K data")
        return

    vna_dir = t_dir / f"-{VNA_DBM_FOR_LASER}dBm" / "00mW"
    s2p_files = _collect_s2p(vna_dir)
    if not s2p_files:
        print(f"[SKIP] no S2P: {vna_dir}")
        return

    actual_k = float(t_dir.name.rstrip("K"))
    zoom_mhz = _zoom_mhz(actual_k)
    print(f"\n  --- Full Spectrum | T={t_dir.name} (zoom=+-{zoom_mhz:.0f}MHz) ---")

    fp = s2p_files[0]
    ntwk = rf.Network(fp)
    freq_hz = ntwk.f
    freq_ghz = freq_hz / 1e9
    s21_complex = ntwk.s[:, 1, 0]
    s21_db = 20 * np.log10(np.abs(s21_complex))

    # 6K: 直接用 find_true_resonances() 做初始定位 + 保存基线图
    peaks, fig_baseline, axes = dp.find_true_resonances(
        freq=freq_hz, s21=s21_complex, **PEAK_KWARGS)

    if fig_baseline is not None:
        _save_and_close(fig_baseline, baseline_dir / "baseline_T6K.png")

    tracked_f0s = {}
    for rname in SCRAPS_F0:
        f0_ref = SCRAPS_F0[rname][0]  # 6K exact
        f_dip, dip_depth, _ = _detect_dip_baseline(freq_ghz, s21_db, f0_ref, search_mhz=20)
        if f_dip is not None and dip_depth < -1.0:
            tracked_f0s[rname] = (f_dip, dip_depth)
            print(f"    {rname}: {f_dip:.4f} GHz  depth={dip_depth:+.1f}dB")

    # 全谱 + 标注
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.plot(freq_ghz, s21_db, color="#1565C0", linewidth=1.5, alpha=0.9)
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("|S21| (dB)")
    ax.set_title(f"Full Spectrum  |  T = {t_dir.name},  VNA = -{VNA_DBM_FOR_LASER} dBm,  Laser = 0 mW")
    ax.grid(True)

    ymin, ymax = ax.get_ylim()
    for rname, (f0, _) in tracked_f0s.items():
        ax.axvline(x=f0, color="red", linestyle="--", alpha=0.4, linewidth=0.8)
        ax.annotate(f"{rname}\n{f0:.4f} GHz",
                   xy=(f0, ymin + 0.03 * (ymax - ymin)),
                   ha="center", va="bottom", fontsize=9,
                   bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.85))
    _save_and_close(fig, subdir / "full_spectrum_annotated.png")

    for rname, (f0, _) in tracked_f0s.items():
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        fz, sz = _zoom_around(freq_ghz, s21_db, f0, zoom_mhz)
        ax.plot(fz, sz, color="#1565C0", linewidth=2.0, alpha=0.9)
        ax.axvline(x=f0, color="red", linestyle="--", alpha=0.5, linewidth=1)
        ax.set_xlabel("Frequency (GHz)")
        ax.set_ylabel("|S21| (dB)")
        ax.set_title(f"{rname}  f0 = {f0:.4f} GHz  |  T = {t_dir.name}  |  zoom = +-{zoom_mhz:.0f} MHz")
        ax.grid(True)
        _save_and_close(fig, subdir / f"{rname}_zoom.png")


# ============================================================
# 主流程
# ============================================================

def main():
    sub_laser = OUTPUT / "01_laser_sweep_VNA-25dBm"
    sub_vna = OUTPUT / "02_vna_sweep_laser0mW"
    sub_full = OUTPUT / "03_full_spectrum_T6K"
    sub_baseline = OUTPUT / "04_baseline_plots"
    for sd in [sub_laser, sub_vna, sub_full, sub_baseline]:
        sd.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("S21 功率依赖分析 v4 — f0(T)曲线驱动 + 双验证 + 自适应zoom")
    print(f"Zoom: T<=20K -> +-10MHz, T>=77K -> +-30MHz, 中间线性")
    print(f"输出: {OUTPUT}")
    print("=" * 60)

    print(f"\n[Group 1] S21 vs Laser Power (VNA=-{VNA_DBM_FOR_LASER}dBm)")
    print("-" * 40)
    plot_laser_sweep(sub_laser, sub_baseline)

    print(f"\n[Group 2] S21 vs VNA Power (Laser={LASER_MW_FOR_VNA}mW)")
    print("-" * 40)
    plot_vna_sweep(sub_vna)

    print(f"\n[Group 3] Full Spectrum (T={FULL_SPEC_TEMP}K)")
    print("-" * 40)
    plot_full_spectrum(sub_full, sub_baseline)

    total = 0
    for sd in [sub_laser, sub_vna, sub_full, sub_baseline]:
        pngs = sorted(sd.glob("*.png"))
        total += len(pngs)
        print(f"\n  {sd.name}/  ({len(pngs)} files)")
        for p in pngs:
            print(f"    {p.name}")

    print(f"\n{'='*60}")
    print(f"Done: {total} figures")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
