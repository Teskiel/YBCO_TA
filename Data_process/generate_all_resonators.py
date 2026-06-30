# -*- coding: utf-8 -*-
"""
五谐振器批量分析脚本。

对 merged 数据集，检测全部 5 个谐振器，逐个运行完整分析流水线，
输出到 output/merged/R{idx+1}_{freq}GHz/ 子文件夹。
"""

import sys
import os
import re
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
_otherwise_dir = _script_dir / "otherwise"
sys.path.insert(0, str(_otherwise_dir))

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

# 寻峰参数（宽松，检测全部 5 个谐振器）
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


def fit_resonance(freq, s21, resfreq, span=FIT_SPAN, temp=0, pwr=0):
    """拟合单个谐振峰。"""
    df = freq[1] - freq[0]
    index = np.argmin(np.abs(freq - resfreq))
    count = round(span / df)
    indx_start = max(0, index - count)
    indx_stop = min(len(freq), index + count)
    freq_cut = freq[indx_start:indx_stop]
    s21_cut = s21[indx_start:indx_stop]
    indx_min = np.argmin(np.abs(s21_cut))
    index_min_all = indx_start + indx_min
    freq_cut = freq[max(0, index_min_all - count): min(len(freq), index_min_all + count)]
    s21_cut = s21[max(0, index_min_all - count): min(len(freq), index_min_all + count)]
    res = scr.Resonator("name", temp, pwr, freq_cut, np.real(s21_cut), np.imag(s21_cut))
    res.load_params(cmplxIQ_params)
    res.do_lmfit(cmplxIQ_fit)
    return res


def process_one_resonator(pixel_indx, output_dir, resfreqs, temps, temp_meas_all, s2p_file_matrix_temp):
    """处理单个谐振器，生成全部分析图。"""
    os.makedirs(output_dir, exist_ok=True)

    resfreq_fit_00 = resfreqs[pixel_indx]
    print(f"  谐振器 pixel_indx={pixel_indx}: {resfreq_fit_00/1e9:.4f} GHz")
    res_temp = resfreq_fit_00

    colors, sm = ut.GenColorMap(temp_meas_all)
    colors_power = ut.ColorCombinations(3)

    resfreq_all = []
    resfreq_fit = []
    responsivit_all = []
    reslist_all = []
    reslist_all_p2 = []
    reslist_all_p3 = []

    for indx, (temp, temp_meas) in enumerate(zip(temps, temp_meas_all)):
        if temp_meas > 80:
            continue

        temp_files = s2p_file_matrix_temp[indx]

        # 频率追踪外推
        if indx < 3:
            df = 0
        elif indx < 4:
            f1 = resfreq_all[indx - 3]
            f2 = resfreq_all[indx - 2]
            f3 = resfreq_all[indx - 1]
            df1 = f3 - f2
            df2 = f3 - f2 - (f2 - f1)
            res_temp = res_temp + df1 - df2
        elif indx < 5:
            f1, f2, f3, f4 = resfreq_all[indx - 4: indx]
            df1 = f4 - f3
            df2 = f4 - 2 * f3 + f2
            df3 = f4 - 3 * f3 + 3 * f2 - f1
            res_temp = res_temp + df1 - df2 + df3
        else:
            f1, f2, f3, f4, f5 = resfreq_all[indx - 5: indx]
            df1 = f5 - f4
            df2 = f5 - 2 * f4 + f3
            df3 = f5 - 3 * f4 + 3 * f3 - f2
            df4 = f5 - 4 * f4 + 6 * f3 - 4 * f2 + f1
            res_temp = res_temp + df1 - df2 + df3 - df4

        resfreqs_vs_power = []

        for i, meas_power in enumerate(MEAS_POWERS):
            s2p_file_matrix_mW = temp_files[i]
            reslist_meas_dBm = []

            for j, meas_laser_power in enumerate(MEAS_LASER_POWERS):
                file_path = s2p_file_matrix_mW[j]
                freq, s21 = dp.load_s_param(file_path)
                res = fit_resonance(freq, s21, res_temp, temp=temp_meas, pwr=meas_power)
                reslist_meas_dBm.append(res)

                if i == 0 and j == 0:
                    resfreq_fit.append(res.f0)
                    reslist_all.append(res)
                if i == 1 and j == 0:
                    reslist_all_p2.append(res)
                if i == 2 and j == 0:
                    reslist_all_p3.append(res)

            # S21 vs Laser Power 图
            fig, ax = plt.subplots()
            color_laser, sm2 = ut.GenColorMap(MEAS_LASER_POWERS)
            for count, r in enumerate(reslist_meas_dBm):
                ax.plot(r.freq / 1e9, 10 * np.log10(r.INorm**2 + r.QNorm**2),
                        color=color_laser[count], linewidth=2)
            ax.set_xlabel("Frequency (GHz)")
            ax.set_ylabel("$S_{21}$ (dB)")
            ax.set_title(f"T={temp_meas:.3f} K, $P_r=$-{meas_power} dBm")
            cbar = fig.colorbar(sm2, ax=ax)
            cbar.set_label("Laser Power (mW)")
            savepath = os.path.join(output_dir, f"s21 - {temp_meas:.3f}K-{meas_power}dBm.jpg")
            fig.savefig(savepath, dpi=300, bbox_inches="tight")
            plt.close(fig)

            f0s = ut.ExtractLmfitParams(reslist_meas_dBm, param="f0")
            resfreqs_vs_power.append(f0s)

        # 谐振频率 vs 激光功率（响应率）
        fig, ax = plt.subplots()
        for count2, f0s in enumerate(resfreqs_vs_power):
            f0s = np.array(f0s)
            ax.plot(MEAS_LASER_POWERS, (f0s - f0s[0]) / f0s[0] * 1e6, "s",
                    color=colors_power[count2], markersize=6,
                    label=f"$P_r$=-{MEAS_POWERS[count2]} dBm")
            a = np.polyfit(np.array(MEAS_LASER_POWERS), f0s, 1)
        responsivit_all.append([np.polyfit(np.array(MEAS_LASER_POWERS), np.array(f0s), 1)[0]
                                for f0s in resfreqs_vs_power])

        ax.set_xlabel("Laser power (mW)")
        ax.set_ylabel(r"$\delta f_r/f_r$ (ppm)")
        ax.set_title(f"T={temp_meas:.3f} K")
        ax.legend()
        savepath = os.path.join(output_dir, f"res shift - {temp_meas:.3f}K.jpg")
        fig.savefig(savepath, dpi=300, bbox_inches="tight")
        plt.close(fig)

        res_temp = res.f0
        resfreq_all.append(res_temp)
        if indx % 10 == 0:
            print(f"    T={temp}K ({temp_meas:.3f}K) done, f0={res.f0/1e9:.4f} GHz")

    # ---- 汇总图 ----
    resfreq_fit_arr = np.array(resfreq_fit)
    n_pts = min(len(temp_meas_all), len(resfreq_fit_arr))

    # f0 vs Temperature
    fig, ax = plt.subplots()
    ax.plot(temp_meas_all[:n_pts], (resfreq_fit_arr[:n_pts] - resfreq_fit_arr[0]) / resfreq_fit_arr[0] * 1e2,
            linewidth=2, color=colors_power[0])
    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel(r"$\delta f_r/f_r$ (%)")
    fig.savefig(os.path.join(output_dir, "f0_versus_temp.jpg"), dpi=300, bbox_inches="tight")
    plt.close(fig)

    # S21 vs Temperature 叠加
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
    plt.close(fig)

    # Qi vs Temperature
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
    plt.close(fig)

    # 响应率 vs Temperature
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
    # --- Step 1: 扫描温度和构建路径矩阵 ---
    print("Scanning temperatures...")
    pattern = re.compile(r"^(\d+(?:\.\d+)?)K$")
    temp_entries = []
    for subfolder in FOLDER0.iterdir():
        if subfolder.is_dir():
            m = pattern.match(subfolder.name)
            if m:
                temp_entries.append((int(float(m.group(1))), subfolder.name))
    temp_entries.sort(key=lambda x: x[0])
    temps = [t[0] for t in temp_entries]
    temp_names = [t[1] for t in temp_entries]

    # 解析实际温度
    temp_meas_all = []
    for temp, tname in zip(temps, temp_names):
        path_temp = FOLDER0 / tname
        found = False
        for vna_dir in sorted(path_temp.iterdir()):
            if not vna_dir.is_dir():
                continue
            for laser_dir in sorted(vna_dir.iterdir()):
                if not laser_dir.is_dir():
                    continue
                for f in laser_dir.iterdir():
                    if f.suffix == ".s2p":
                        match = re.search(r"actual_([\d.]+)K", f.name)
                        if match:
                            temp_meas_all.append(float(match.group(1)))
                            found = True
                        break
                if found:
                    break
            if found:
                break
        if not found:
            temp_meas_all.append(float(temp))

    # 检查完整性并构建矩阵
    valid_temps = []
    valid_temp_meas = []
    s2p_file_matrix_temp = []

    for temp, tname, temp_meas in zip(temps, temp_names, temp_meas_all):
        path_temp = FOLDER0 / tname
        complete = True
        s2p_matrix_dBm = []
        for meas_power in MEAS_POWERS:
            path_dBm = path_temp / f"-{meas_power}dBm"
            if not path_dBm.is_dir():
                complete = False
                break
            s2p_matrix_mW = []
            for meas_laser in MEAS_LASER_POWERS:
                path_mW = path_dBm / f"{meas_laser:02d}mW"
                if not path_mW.is_dir():
                    complete = False
                    break
                s2p_files = list(path_mW.glob("*.s2p"))
                if not s2p_files:
                    complete = False
                    break
                s2p_matrix_mW.append(str(s2p_files[0]))
            if not complete:
                break
            s2p_matrix_dBm.append(s2p_matrix_mW)
        if complete:
            valid_temps.append(temp)
            valid_temp_meas.append(temp_meas)
            s2p_file_matrix_temp.append(s2p_matrix_dBm)

    temps = valid_temps
    temp_meas_all = valid_temp_meas
    print(f"Valid temperatures: {len(temps)}")

    # --- Step 2: 检测全部谐振峰 ---
    print("\nDetecting resonance peaks...")
    file00 = s2p_file_matrix_temp[0][0][0]
    freq, s21 = dp.load_s_param(file00)
    peaks, fig, ax = dp.find_true_resonances(freq=freq, s21=s21, **PEAK_KWARGS, plot=True)

    # 保存寻峰图
    res_detect_dir = OUTPUT_BASE / "01_resonance_detection"
    res_detect_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(res_detect_dir / "resonance_detection.jpg"), dpi=300, bbox_inches="tight")
    plt.close(fig)

    resfreqs = [p["frequency"] for p in peaks]
    print(f"Detected {len(resfreqs)} resonators:")
    for i, f in enumerate(resfreqs):
        print(f"  R{i+1}: {f/1e9:.5f} GHz  dip={peaks[i]['transmission']:.2f} dB")

    if len(resfreqs) < 5:
        print(f"WARNING: only {len(resfreqs)} peaks detected, expected 5")

    # --- Step 3: 逐个处理谐振器 ---
    for pixel_indx in range(min(5, len(resfreqs))):
        freq_ghz = resfreqs[pixel_indx] / 1e9
        folder_name = f"R{pixel_indx+1}_{freq_ghz:.3f}GHz"
        output_dir = OUTPUT_BASE / folder_name
        print(f"\n{'='*60}")
        print(f"Processing {folder_name} (pixel_indx={pixel_indx})...")
        print(f"{'='*60}")
        process_one_resonator(pixel_indx, str(output_dir),
                              resfreqs, temps, temp_meas_all, s2p_file_matrix_temp)

    print(f"\nDone! Output: {OUTPUT_BASE}")
    print("Subfolders:", [d.name for d in sorted(OUTPUT_BASE.iterdir()) if d.is_dir()])


if __name__ == "__main__":
    main()
