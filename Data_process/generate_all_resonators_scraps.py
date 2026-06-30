# -*- coding: utf-8 -*-
"""
五谐振器完整分析 — 使用 scraps cmplxIQ 拟合。

为每个谐振器生成完整的 01-08 分析文件夹结构，
输出到 output/merged/R{idx+1}_{freq}GHz/。
"""

import sys
import os
import re
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
_otherwise_dir = _script_dir / "otherwise"
sys.path.insert(0, str(_otherwise_dir))
sys.path.insert(0, r"D:\YBCO\Measurement-System\Measurement-System")

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import dataprocess as dp
import scraps.resonator as scr
from scraps.fitsS21 import cmplxIQ_fit, cmplxIQ_params
import scraps.utility as ut

ut.SetDefaultPlotParam()

# ============================================================
# 配置
# ============================================================
FOLDER0 = Path(r"D:\YBCO\VNAMeas\Auto_Sweep\experiment_data\merged")
OUTPUT_BASE = _script_dir / "output" / "merged"
MEAS_POWERS = [25, 30, 45]
MEAS_LASER_POWERS = [0, 1, 3, 5, 7, 9]
FIT_SPAN = 50e6

# 寻峰参数
PEAK_KWARGS = dict(
    min_prominence=1, distance=50, phase_window=25,
    phase_diff_snr_threshold=1.5, noise_inner_window=5,
    noise_outer_window=40, min_phase_diff_support_points=2,
    min_phase_diff_width=2, plot=False,
)


def fit_resonance(freq, s21, resfreq, span=FIT_SPAN, temp=0, pwr=0):
    """cmplxIQ 复数拟合单个谐振峰。"""
    df = freq[1] - freq[0]
    idx_center = np.argmin(np.abs(freq - resfreq))
    count = round(span / df)
    i0 = max(0, idx_center - count)
    i1 = min(len(freq), idx_center + count)
    freq_cut = freq[i0:i1]
    s21_cut = s21[i0:i1]
    idx_min = np.argmin(np.abs(s21_cut))
    i0 = max(0, i0 + idx_min - count)
    i1 = min(len(freq), i0 + 2 * count)
    freq_cut = freq[i0:i1]
    s21_cut = s21[i0:i1]
    res = scr.Resonator("r", temp, pwr, freq_cut, np.real(s21_cut), np.imag(s21_cut))
    res.load_params(cmplxIQ_params)
    res.do_lmfit(cmplxIQ_fit)
    return res


def process_one_resonator(pixel_indx, output_dir, resfreqs, temps, temp_meas_all, s2p_matrix):
    """处理单个谐振器，生成完整分析图。"""
    os.makedirs(output_dir, exist_ok=True)
    resfreq_fit_00 = resfreqs[pixel_indx]
    print(f"  Resonator {pixel_indx}: f0={resfreq_fit_00/1e9:.4f} GHz")
    res_temp = resfreq_fit_00

    colors_power = ut.ColorCombinations(3)
    colors, sm = ut.GenColorMap(temp_meas_all)

    resfreq_all = []
    resfreq_fit = []
    responsivit_all = []
    reslist_all = []
    reslist_all_p2 = []
    reslist_all_p3 = []

    for indx, (temp, temp_meas) in enumerate(zip(temps, temp_meas_all)):
        if temp_meas > 80:
            continue
        temp_files = s2p_matrix[indx]

        # 频率追踪外推
        if indx < 3:
            pass
        elif indx < 4:
            f1, f2, f3 = resfreq_all[indx - 3:indx]
            res_temp += (f3 - f2) - (f3 - 2 * f2 + f1)
        elif indx < 5:
            f1, f2, f3, f4 = resfreq_all[indx - 4:indx]
            res_temp += (f4 - f3) - (f4 - 2 * f3 + f2) + (f4 - 3 * f3 + 3 * f2 - f1)
        else:
            f1, f2, f3, f4, f5 = resfreq_all[indx - 5:indx]
            res_temp += (f5 - f4) - (f5 - 2 * f4 + f3) + (f5 - 3 * f4 + 3 * f3 - f2) - (f5 - 4 * f4 + 6 * f3 - 4 * f2 + f1)

        resfreqs_vs_power = []

        for i, meas_power in enumerate(MEAS_POWERS):
            s2p_list = temp_files[i]
            reslist_dBm = []

            for j, meas_laser in enumerate(MEAS_LASER_POWERS):
                freq, s21 = dp.load_s_param(s2p_list[j])
                res = fit_resonance(freq, s21, res_temp, temp=temp_meas, pwr=meas_power)
                reslist_dBm.append(res)

                if i == 0 and j == 0:
                    # S21 温度追踪叠加图
                    plt.figure()
                    plt.plot(res.freq, 10 * np.log10(res.INorm**2 + res.QNorm**2), color=colors[indx])
                    plt.plot(res.freq, 10 * np.log10(res.resultINorm**2 + res.resultQNorm**2),
                             color=colors[indx], linestyle="--")
                    plt.title(f"temp = {temp}K")
                    plt.savefig(os.path.join(output_dir, f"s21_trace_{temp}K.jpg"), dpi=300, bbox_inches="tight")
                    plt.close()
                    resfreq_fit.append(res.f0)
                    reslist_all.append(res)

                if i == 1 and j == 0:
                    reslist_all_p2.append(res)
                if i == 2 and j == 0:
                    reslist_all_p3.append(res)

            # S21 vs Laser Power 图 (02_f0_temperature 对应)
            fig, ax = plt.subplots()
            color_laser, sm2 = ut.GenColorMap(MEAS_LASER_POWERS)
            for jj, r in enumerate(reslist_dBm):
                ax.plot(r.freq / 1e9, 10 * np.log10(r.INorm**2 + r.QNorm**2),
                        color=color_laser[jj], linewidth=2)
            ax.set_xlabel("Frequency (GHz)")
            ax.set_ylabel("$S_{21}$ (dB)")
            ax.set_title(f"T={temp_meas:.3f} K, $P_r=$-{meas_power} dBm")
            cbar = fig.colorbar(sm2, ax=ax)
            cbar.set_label("Laser Power (mW)")
            fig.savefig(os.path.join(output_dir, f"s21 - {temp_meas:.3f}K-{meas_power}dBm.jpg"),
                        dpi=300, bbox_inches="tight")
            plt.close(fig)

            f0s = ut.ExtractLmfitParams(reslist_dBm, param="f0")
            resfreqs_vs_power.append(f0s)

        # Res shift vs Laser Power
        fig, ax = plt.subplots()
        for jj, f0s in enumerate(resfreqs_vs_power):
            f0s = np.array(f0s)
            ax.plot(MEAS_LASER_POWERS, (f0s - f0s[0]) / f0s[0] * 1e6, "s",
                    color=colors_power[jj], markersize=6,
                    label=f"$P_r$=-{MEAS_POWERS[jj]} dBm")
            a = np.polyfit(np.array(MEAS_LASER_POWERS), f0s, 1)
        responsivit_all.append([np.polyfit(np.array(MEAS_LASER_POWERS), np.array(f0s), 1)[0]
                                for f0s in resfreqs_vs_power])
        ax.set_xlabel("Laser power (mW)")
        ax.set_ylabel(r"$\delta f_r/f_r$ (ppm)")
        ax.set_title(f"T={temp_meas:.3f} K")
        ax.legend()
        fig.savefig(os.path.join(output_dir, f"res shift - {temp_meas:.3f}K.jpg"),
                    dpi=300, bbox_inches="tight")
        plt.close(fig)

        res_temp = res.f0
        resfreq_all.append(res_temp)
        if indx % 8 == 0:
            print(f"    T={temp}K done, f0={res.f0/1e9:.4f} GHz")

    # ---- 汇总图 ----
    resfreq_fit_arr = np.array(resfreq_fit)
    n_pts = min(len(temp_meas_all), len(resfreq_fit_arr))

    # 02_f0_temperature: f0 vs Temperature
    fig, ax = plt.subplots()
    ax.plot(temp_meas_all[:n_pts], (resfreq_fit_arr[:n_pts] - resfreq_fit_arr[0]) / resfreq_fit_arr[0] * 1e2,
            linewidth=2, color=colors_power[0])
    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel(r"$\delta f_r/f_r$ (%)")
    fig.savefig(os.path.join(output_dir, "f0_versus_temp.jpg"), dpi=300, bbox_inches="tight")
    fig.savefig(os.path.join(output_dir, "f0_versus_temp.svg"), dpi=300, bbox_inches="tight")
    plt.close(fig)

    # 04_S21_temperature_overlay: S21 vs Temperature
    fig, ax = plt.subplots()
    color_s21, sm_s21 = ut.GenColorMap(temp_meas_all[:n_pts])
    for indx_r, res in enumerate(reslist_all[:n_pts]):
        ax.plot(res.freq / 1e9, 10 * np.log10(res.INorm**2 + res.QNorm**2),
                color=color_s21[indx_r], linewidth=1.5)
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("$S_{21}$ (dB)")
    cbar = fig.colorbar(sm_s21, ax=ax)
    cbar.set_label("Temperature (K)")
    fig.savefig(os.path.join(output_dir, "s21 vs - temp.jpg"), dpi=300, bbox_inches="tight")
    fig.savefig(os.path.join(output_dir, "s21 vs - temp.svg"), dpi=300, bbox_inches="tight")
    plt.close(fig)

    # 03_Qi_temperature: Qi vs Temperature
    fig, ax = plt.subplots()
    qis1 = ut.ExtractLmfitParams(reslist_all[:n_pts], param="qi")
    qis2 = ut.ExtractLmfitParams(reslist_all_p2[:n_pts], param="qi")
    qis3 = ut.ExtractLmfitParams(reslist_all_p3[:n_pts], param="qi")
    ax.plot(temp_meas_all[:len(qis1)], qis1, "s", color=colors_power[0], label="-25 dBm")
    ax.plot(temp_meas_all[:len(qis2)], qis2, "o", color=colors_power[1], label="-30 dBm")
    ax.plot(temp_meas_all[:len(qis3)], qis3, "d", color=colors_power[2], label="-45 dBm")
    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel("Qi")
    ax.legend()
    fig.savefig(os.path.join(output_dir, "qis_versus_temp.jpg"), dpi=300, bbox_inches="tight")
    fig.savefig(os.path.join(output_dir, "qis_versus_temp.svg"), dpi=300, bbox_inches="tight")
    plt.close(fig)

    # 07_responsivity: Responsivity vs Temperature
    b = np.array(responsivit_all)
    n_r = min(len(temp_meas_all), len(b))
    fig, ax = plt.subplots()
    ax.semilogx(temp_meas_all[:n_r], -b[:n_r, 2] * 1000, "s", color=colors_power[2])
    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel("Responsivity (Hz/W)")
    fig.savefig(os.path.join(output_dir, "responsivity_vs_temp.jpg"), dpi=300, bbox_inches="tight")
    plt.close(fig)

    return resfreq_fit_00


# ============================================================
# 主流程
# ============================================================
def main():
    print("Scanning temperatures...")
    pattern = re.compile(r"^(\d+(?:\.\d+)?)K$")
    temp_entries = []
    for sf in FOLDER0.iterdir():
        if sf.is_dir():
            m = pattern.match(sf.name)
            if m:
                temp_entries.append((int(float(m.group(1))), sf.name))
    temp_entries.sort(key=lambda x: x[0])
    temps = [t[0] for t in temp_entries]
    temp_names = [t[1] for t in temp_entries]

    # 解析实际温度 + 构建路径矩阵
    temp_meas_all = []
    s2p_matrix = []
    for temp, tname in zip(temps, temp_names):
        path_temp = FOLDER0 / tname
        # 解析实际温度
        actual = float(temp)
        for vna_dir in sorted(path_temp.iterdir()):
            if not vna_dir.is_dir():
                continue
            for laser_dir in sorted(vna_dir.iterdir()):
                if not laser_dir.is_dir():
                    continue
                for f in laser_dir.iterdir():
                    if f.suffix == ".s2p":
                        m2 = re.search(r"actual_([\d.]+)K", f.name)
                        if m2:
                            actual = float(m2.group(1))
                        break
                break
            break
        temp_meas_all.append(actual)

        # 构建 S2P 矩阵
        complete = True
        mat_dBm = []
        for mp in MEAS_POWERS:
            path_dBm = path_temp / f"-{mp}dBm"
            if not path_dBm.is_dir():
                complete = False; break
            mat_mW = []
            for ml in MEAS_LASER_POWERS:
                path_mW = path_dBm / f"{ml:02d}mW"
                s2p_files = list(path_mW.glob("*.s2p")) if path_mW.is_dir() else []
                if not s2p_files:
                    complete = False; break
                mat_mW.append(str(s2p_files[0]))
            if not complete:
                break
            mat_dBm.append(mat_mW)
        if complete:
            s2p_matrix.append(mat_dBm)
        else:
            s2p_matrix.append(None)

    # 过滤不完整的
    valid = [(t, ta, m) for t, ta, m in zip(temps, temp_meas_all, s2p_matrix) if m is not None]
    temps = [v[0] for v in valid]
    temp_meas_all = [v[1] for v in valid]
    s2p_matrix = [v[2] for v in valid]
    print(f"Valid temperatures: {len(temps)}")

    # 检测谐振峰
    print("Detecting peaks...")
    freq_ref, s21_ref = dp.load_s_param(s2p_matrix[0][0][0])
    peak_kwargs_plot = {**PEAK_KWARGS, "plot": True}
    peaks, fig, ax = dp.find_true_resonances(freq=freq_ref, s21=s21_ref, **peak_kwargs_plot)

    # 保存寻峰图
    detect_dir = OUTPUT_BASE / "01_resonance_detection"
    detect_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(detect_dir / "resonance_detection.jpg"), dpi=300, bbox_inches="tight")
    plt.close(fig)

    resfreqs = [p["frequency"] for p in peaks]
    n_res = min(5, len(resfreqs))
    print(f"Detected {n_res} resonators:")
    for i in range(n_res):
        print(f"  R{i+1}: {resfreqs[i]/1e9:.5f} GHz  dip={peaks[i]['transmission']:.2f} dB")

    # 逐个处理
    for pixel_indx in range(n_res):
        freq_ghz = resfreqs[pixel_indx] / 1e9
        folder_name = f"R{pixel_indx+1}_{freq_ghz:.3f}GHz"
        res_dir = OUTPUT_BASE / folder_name
        print(f"\n{'='*60}")
        print(f"Processing {folder_name}...")
        print(f"{'='*60}")
        process_one_resonator(pixel_indx, str(res_dir), resfreqs, temps, temp_meas_all, s2p_matrix)

    print(f"\nDone! Output: {OUTPUT_BASE}")


if __name__ == "__main__":
    main()
