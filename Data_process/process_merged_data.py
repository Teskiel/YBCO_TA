# -*- coding: utf-8 -*-
"""
适配 merged 数据目录的处理脚本。

基于 otherwise/process_data_single_pixel.py，针对 merged 数据目录
（无 actual_ 中间文件夹的扁平结构）进行调整。

merged 数据结构:
  merged/{temp}K/{power}dBm/{laser}mW/*.s2p

@author: Adapted from Jie Hu's process_data_single_pixel.py
"""

import sys
import os
from pathlib import Path

# 添加 otherwise 目录到 sys.path，以便导入 dataprocess
_script_dir = Path(__file__).resolve().parent
_otherwise_dir = _script_dir / "otherwise"
if str(_otherwise_dir) not in sys.path:
    sys.path.insert(0, str(_otherwise_dir))

import numpy as np
import matplotlib.pyplot as plt
import re
import dataprocess as dp

import scraps.resonator as scr
from scraps.fitsS21 import cmplxIQ_fit, cmplxIQ_params

import scraps.utility as ut

ut.SetDefaultPlotParam()


def fit_resonance(freq, s21, resfreq, span=20e6, temp=0, pwr=0):
    """拟合单个谐振峰（与原始脚本相同）。"""
    df = freq[1] - freq[0]
    index = np.argmin(np.abs(freq - resfreq))
    count = round(span / df)

    indx_start = index - count
    indx_stop = index + count

    freq_cut = freq[indx_start:indx_stop]
    s21_cut = s21[indx_start:indx_stop]

    indx_min = np.argmin(np.abs(s21_cut))
    index_min_all = indx_start + indx_min

    freq_cut = freq[index_min_all - count : index_min_all + count]
    s21_cut = s21[index_min_all - count : index_min_all + count]

    res = scr.Resonator(
        "name", temp, pwr, freq_cut, np.real(s21_cut), np.imag(s21_cut)
    )
    res.load_params(cmplxIQ_params)
    res.do_lmfit(cmplxIQ_fit)

    return res


# ============================================================
# 配置参数
# ============================================================

# merged 数据根目录
folder0 = r"D:\YBCO\VNAMeas\Auto_Sweep\experiment_data\merged"

# VNA 功率 (正值，代码中取负号: -25, -30, -45 dBm)
meas_powers = [25, 30, 45]

# 激光功率 (mW)
meas_laser_powers = [0, 1, 3, 5, 7, 9]

# 谐振峰选择（第几个检测到的峰，0-based）
pixel_indx = 1

# 寻峰参数
min_prominence = 3
phase_diff_prominence = None
distance = 10
phase_window = 10
phase_diff_snr_threshold = 0.5
noise_inner_window = 5
noise_outer_window = 40
min_phase_diff_support_points = 4
min_phase_diff_width = 4
max_phase_diff_width = None

# 拟合频率窗口 (Hz)
fit_span = 50e6

# 输出目录（放在 Data_process/output/ 下，用数据目录名区分）
merged_name = Path(folder0).name  # "merged"
output_dir = _script_dir / "output" / merged_name
os.makedirs(output_dir, exist_ok=True)

# ============================================================
# 扫描温度
# ============================================================

parent_folder = Path(folder0)
pattern = re.compile(r"^(\d+(?:\.\d+)?)K$")

temps = [
    int(float(match.group(1)))
    for subfolder in parent_folder.iterdir()
    if subfolder.is_dir()
    if (match := pattern.match(subfolder.name))
]
temps.sort()
print(f"发现温度点: {temps}")

# ============================================================
# 从 S2P 文件名中解析实际温度
# 文件名格式: YBCO_-25dBm_00mW_target_6K_actual_5.991K.s2p
# ============================================================

temp_meas_all = []
for temp in temps:
    path_temp = parent_folder / f"{temp}K"
    if not path_temp.is_dir():
        temp_meas_all.append(float(temp))  # fallback
        continue

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
        print(f"  ⚠ {temp}K: 无法从文件名解析实际温度，使用目标温度")
        temp_meas_all.append(float(temp))

# 打印温度映射
for t, tm in zip(temps, temp_meas_all):
    print(f"  {t}K → actual {tm:.3f}K")

# ============================================================
# 构建 S2P 文件路径矩阵 [temp][power][laser]
# 跳过数据不完整的温度点
# ============================================================

# 先检查每个温度的完整性
valid_temps = []
valid_temp_meas = []

for temp, temp_meas in zip(temps, temp_meas_all):
    path_temp = parent_folder / f"{temp}K"
    complete = True
    missing = []

    for meas_power in meas_powers:
        path_dBm = path_temp / f"-{meas_power}dBm"
        if not path_dBm.is_dir():
            complete = False
            missing.append(f"-{meas_power}dBm")
            continue

        for meas_laser_power in meas_laser_powers:
            path_mW = path_dBm / f"{meas_laser_power:02d}mW"
            if not path_mW.is_dir():
                complete = False
                missing.append(f"-{meas_power}dBm/{meas_laser_power:02d}mW")
                continue

            # 检查是否有 .s2p 文件
            s2p_files = list(path_mW.glob("*.s2p"))
            if not s2p_files:
                complete = False
                missing.append(f"-{meas_power}dBm/{meas_laser_power:02d}mW (无.s2p)")

    if complete:
        valid_temps.append(temp)
        valid_temp_meas.append(temp_meas)
    else:
        print(f"  ⚠ {temp}K 数据不完整，跳过。缺失: {missing}")

temps = valid_temps
temp_meas_all = valid_temp_meas

print(f"\n有效温度点数: {len(temps)}")

# 构建路径矩阵
s2p_file_matrix_temp = []

for temp in temps:
    path_temp = parent_folder / f"{temp}K"

    s2p_file_matrix_dBm = []

    for meas_power in meas_powers:
        path_temp_dBm = path_temp / f"-{meas_power}dBm"

        s2p_file_matrix_mW = []

        for meas_laser_power in meas_laser_powers:
            path_temp_dBm_mW = path_temp_dBm / f"{meas_laser_power:02d}mW"

            for f in path_temp_dBm_mW.iterdir():
                if f.suffix == ".s2p":
                    s2p_file_matrix_mW.append(str(f))
                    break  # 每个目录只取第一个

        s2p_file_matrix_dBm.append(s2p_file_matrix_mW)

    s2p_file_matrix_temp.append(s2p_file_matrix_dBm)

# ============================================================
# 谐振峰检测（使用第一个温度、第一个功率、第一个激光功率的数据）
# ============================================================

file00_path = s2p_file_matrix_temp[0][0][0]
print(f"\n用于寻峰的文件: {file00_path}")

freq, s21 = dp.load_s_param(file00_path)

peaks, fig, ax = dp.find_true_resonances(
    freq=freq,
    s21=s21,
    min_prominence=min_prominence,
    phase_diff_prominence=phase_diff_prominence,
    distance=distance,
    phase_window=phase_window,
    phase_diff_snr_threshold=phase_diff_snr_threshold,
    noise_inner_window=noise_inner_window,
    noise_outer_window=noise_outer_window,
    min_phase_diff_support_points=min_phase_diff_support_points,
    min_phase_diff_width=min_phase_diff_width,
    max_phase_diff_width=max_phase_diff_width,
    plot=True,
)

# 保存寻峰图
os.makedirs(output_dir, exist_ok=True)
fig.savefig(os.path.join(output_dir, "resonance_detection.jpg"), dpi=300, bbox_inches="tight")
plt.close(fig)

resfreqs = [peak["frequency"] for peak in peaks]
print(f"检测到 {len(resfreqs)} 个谐振峰: {[f'{f/1e9:.4f} GHz' for f in resfreqs]}")

if len(resfreqs) <= pixel_indx:
    raise ValueError(
        f"pixel_indx={pixel_indx} 超出检测到的谐振峰数量 ({len(resfreqs)})。"
        f"可选的 pixel_indx: 0~{len(resfreqs)-1}"
    )

resfreq_fit_00 = resfreqs[pixel_indx]
print(f"选用谐振峰 pixel_indx={pixel_indx}: {resfreq_fit_00/1e9:.4f} GHz")

# 初始谐振频率
res_temp = resfreq_fit_00

# ============================================================
# 主循环：遍历所有温度，拟合谐振器
# ============================================================

colors, sm = ut.GenColorMap(temp_meas_all)

resfreq_all = []
resfreq_fit = []
responsivit_all = []
reslist_all = []
reslist_all_p2 = []
reslist_all_p3 = []

folder_save = str(output_dir)

for indx, (temp, temp_meas) in enumerate(zip(temps, temp_meas_all)):
    if temp_meas > 80:
        continue

    temp_files = s2p_file_matrix_temp[indx]

    # ---- 频率追踪外推 ----
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
        f1, f2, f3, f4 = resfreq_all[indx - 4 : indx]
        df1 = f4 - f3
        df2 = f4 - 2 * f3 + f2
        df3 = f4 - 3 * f3 + 3 * f2 - f1
        res_temp = res_temp + df1 - df2 + df3
    else:
        f1, f2, f3, f4, f5 = resfreq_all[indx - 5 : indx]
        df1 = f5 - f4
        df2 = f5 - 2 * f4 + f3
        df3 = f5 - 3 * f4 + 3 * f3 - f2
        df4 = f5 - 4 * f4 + 6 * f3 - 4 * f2 + f1
        res_temp = res_temp + df1 - df2 + df3 - df4

    resfreqs_vs_power = []

    for i, meas_power in enumerate(meas_powers):
        s2p_file_matrix_mW = temp_files[i]
        reslist_meas_dBm = []

        for j, meas_laser_power in enumerate(meas_laser_powers):
            file_path = s2p_file_matrix_mW[j]

            freq, s21 = dp.load_s_param(file_path)

            res = fit_resonance(
                freq, s21, res_temp, temp=temp_meas, pwr=meas_power, span=fit_span
            )

            reslist_meas_dBm.append(res)

            # ---- 收集第一个功率的谐振器用于温度追踪 ----
            if i == 0 and j == 0:
                plt.figure()
                plt.plot(
                    res.freq,
                    10 * np.log10(res.INorm**2 + res.QNorm**2),
                    color=colors[indx],
                )
                plt.title(f"temp = {temp}K")
                plt.plot(
                    res.freq,
                    10 * np.log10(res.resultINorm**2 + res.resultQNorm**2),
                    color=colors[indx],
                    linestyle="--",
                )

                os.makedirs(folder_save, exist_ok=True)
                resfreq_fit.append(res.f0)
                reslist_all.append(res)

            if i == 1 and j == 0:
                reslist_all_p2.append(res)

            if i == 2 and j == 0:
                reslist_all_p3.append(res)

        # ---- S21 vs Laser Power 图 ----
        fig, ax = plt.subplots()
        color_laser, sm2 = ut.GenColorMap(meas_laser_powers)

        for count, res in enumerate(reslist_meas_dBm):
            ax.plot(
                res.freq / 1e9,
                10 * np.log10(res.INorm**2 + res.QNorm**2),
                color=color_laser[count],
                linewidth=2,
            )

        ax.set_xlabel("Frequency (GHz)")
        ax.set_ylabel("$S_{21}$ (dB)")
        ax.set_title(f"T={temp_meas:.3f} K, $P_r=$-{meas_power} dBm")

        cbar = fig.colorbar(sm2, ax=ax)
        cbar.set_label("Laser Power (mW)")

        savefilename = os.path.join(
            folder_save, f"s21 - {temp_meas:.3f}K-{meas_power}dBm.jpg"
        )
        fig.savefig(savefilename, dpi=300, bbox_inches="tight")
        plt.close(fig)

        f0s = ut.ExtractLmfitParams(reslist_meas_dBm, param="f0")
        resfreqs_vs_power.append(f0s)

    # ---- 谐振频率 vs 激光功率（响应率） ----
    plt.figure()
    colors_power = ut.ColorCombinations(3)
    df_dP = []

    for count2, f0s in enumerate(resfreqs_vs_power):
        f0s = np.array(f0s)
        plt.plot(
            meas_laser_powers,
            (f0s - f0s[0]) / f0s[0] * 1e6,
            "s",
            color=colors_power[count2],
            markersize=6,
            label=f"$P_r$=-{meas_powers[count2]} dBm",
        )
        a = np.polyfit(np.array(meas_laser_powers), f0s, 1)
        df_dP.append(a[0])

    responsivit_all.append(df_dP)

    plt.xlabel("Laser power (mW)")
    plt.ylabel(r"$\delta f_r/f_r$ (ppm)")
    plt.title(f"T={temp_meas:.3f} K")
    plt.legend()

    savefilename = os.path.join(folder_save, f"res shift - {temp_meas:.3f}K.jpg")
    plt.savefig(savefilename, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"  ✓ T={temp}K (actual {temp_meas:.3f}K) 完成, f0={res.f0/1e9:.4f} GHz")

    res_temp = res.f0
    resfreq_all.append(res_temp)

# ============================================================
# 汇总图：f0 vs Temperature
# ============================================================

resfreq_fit = np.array(resfreq_fit)

plt.figure()
plt.plot(
    temp_meas_all[: len(resfreq_fit)],
    (resfreq_fit - resfreq_fit[0]) / resfreq_fit[0] * 1e2,
    linewidth=2,
    color=colors_power[0],
)
plt.xlabel("Temperature (K)")
plt.ylabel(r"$\delta f_r/f_r$ (%)")

savefilename = os.path.join(folder_save, "f0_versus_temp")
plt.savefig(savefilename + ".jpg", dpi=300, bbox_inches="tight")
plt.savefig(savefilename + ".svg", dpi=300, bbox_inches="tight")
plt.close()

# ============================================================
# 响应率 vs Temperature
# ============================================================

b = np.array(responsivit_all)
plt.figure()
plt.semilogx(
    temp_meas_all[: len(resfreq_fit)],
    -b[:, 2] * 1000,
    "s",
)
plt.xlabel("Temperature (K)")
plt.ylabel("Responsivity (Hz/W)")

savefilename = os.path.join(folder_save, "responsivity_vs_temp.jpg")
plt.savefig(savefilename, dpi=300, bbox_inches="tight")
plt.close()

# ============================================================
# S21 vs Temperature（叠加图）
# ============================================================

fig_s21_vs_temp, ax_s21 = plt.subplots()
color_s21_vs_temp, sm = ut.GenColorMap(temp_meas_all[: len(resfreq_fit)])

for indx, res in enumerate(reslist_all):
    ax_s21.plot(
        res.freq / 1e9,
        10 * np.log10(res.INorm**2 + res.QNorm**2),
        color=color_s21_vs_temp[indx],
        linewidth=1.5,
    )

ax_s21.set_xlabel("Frequency (GHz)")
ax_s21.set_ylabel("$S_{21}$ (dB)")
cbar = fig_s21_vs_temp.colorbar(sm, ax=ax_s21)
cbar.set_label("Temperature (K)")

savefilename = os.path.join(folder_save, "s21 vs - temp")
plt.savefig(savefilename + ".jpg", dpi=300, bbox_inches="tight")
plt.savefig(savefilename + ".svg", dpi=300, bbox_inches="tight")
plt.close()

# ============================================================
# Qi vs Temperature
# ============================================================

fig_q, ax_q = plt.subplots()
color_s21_vs_temp, sm = ut.GenColorMap(temp_meas_all[: len(resfreq_fit)])

qis = ut.ExtractLmfitParams(reslist_all, param="qi")
qis2 = ut.ExtractLmfitParams(reslist_all_p2, param="qi")
qis3 = ut.ExtractLmfitParams(reslist_all_p3, param="qi")

ax_q.plot(temp_meas_all[: len(resfreq_fit)], qis, "s", color=colors_power[0], label="-25 dBm")
ax_q.plot(temp_meas_all[: len(resfreq_fit)], qis2, "o", color=colors_power[1], label="-30 dBm")
ax_q.plot(temp_meas_all[: len(resfreq_fit)], qis3, "d", color=colors_power[2], label="-45 dBm")

ax_q.set_xlabel("Temperature (K)")
ax_q.set_ylabel("Qi")
ax_q.legend()

savefilename = os.path.join(folder_save, "qis_versus_temp")
plt.savefig(savefilename + ".jpg", dpi=300, bbox_inches="tight")
plt.savefig(savefilename + ".svg", dpi=300, bbox_inches="tight")
plt.close()

# ============================================================
# 保存结果数据
# ============================================================

print(f"\n所有结果已保存到: {output_dir}")
print(f"  - 处理温度点数: {len(resfreq_all)}")
print(f"  - 谐振频率范围: {resfreq_all[0]/1e9:.4f} ~ {resfreq_all[-1]/1e9:.4f} GHz")
