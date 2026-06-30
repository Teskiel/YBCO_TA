# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概述

YBCO 超导谐振器测量数据**离线后处理**模块。与 `Auto_Sweep/`（在线测量自动化）互补——这里负责对已采集的 S2P 数据做谐振器拟合、频率追踪和响应率分析。

## 目录结构

```
Data_process/
├── CLAUDE.md                              ← 本文件
├── otherwise/
│   ├── dataprocess.py                     ← 谐振器寻峰库
│   ├── process_data_single_pixel.py       ← 单像素分析主脚本
│   └── 数据处理初步-2.pptx                 ← 初步结果展示
├── ppt_presentation/                      ← ★ 新子项目: PPT 简报生成器 (v9)
│   ├── README.md                          ← 物理意义详解 + 文献连接 + 使用指南
│   ├── CLAUDE.md                          ← 子项目上下文指南
│   ├── generate_ppt.py                    ← 唯一入口
│   └── output/                            ← PPTX 输出
├── docs/                                  ← 设计文档与规范
│   └── ppt-spec.md                        ← PPT 五段结构规范
├── output/                                ← 旧分析图 + 各版本 PPT
├── experiment_merger.py                   ← 实验碎片合并
├── completeness_checker.py                ← 数据完整性检查
└── [旧PPT脚本] generate_ppt*.py           ← v1-v8 历史版本 (保留参考)
```

## 依赖

| 包 | 用途 | 备注 |
|---|---|---|
| `scraps` | 超导谐振器拟合（`cmplxIQ_fit`, `cmplxIQ_params`, `resonator`） | **非公开包**，PMO 内部/自研，未发布到 PyPI |
| `skrf` (scikit-rf) | S2P 文件加载 (`rf.Network`) | |
| `scipy` | `find_peaks` 寻峰 | |
| `numpy` | 数值计算 | |
| `matplotlib` | 绘图 | |
| `pickle` | (未使用，import 残留) | |

## 架构

```
dataprocess.py  ← 纯函数库，无硬件依赖
    │
    ├── load_s_param(filename) → (freq, s21)
    ├── _robust_local_snr()    ← 局部 SNR + 半高宽验证（内部）
    └── find_true_resonances() ← 幅度谷 + 相位差分峰联合判据
            │
            └── process_data_single_pixel.py  ← 分析脚本
                    ├── fit_resonance()       ← 调用 scraps 做 cmplxIQ 拟合
                    ├── extract_res_and_fit() ← 批量拟合（未在主流程中使用）
                    └── 主流程: 遍历 T × P_r × P_laser → 拟合 → 追踪 f0(T) + 响应率
```

## 核心算法

### 谐振器寻峰 (`dataprocess.py`)

`find_true_resonances()` 使用**双判据**识别真实谐振：

1. **幅度谷** (transmission minima): `scipy.signal.find_peaks(-|S21|)`，按 prominence + distance 筛选
2. **相位差分峰** (diff(unwrapped phase) maxima): 同样 `find_peaks` 寻峰
3. **联合判据**: 幅度谷附近 `phase_window` 范围内必须存在相位差分峰，且该峰通过 `_robust_local_snr()` 的 SNR + 宽度验证

`_robust_local_snr()` 的宽松策略：
- SNR > 5 → 直接接受（跳过宽度检查）
- SNR < 10 → 需要足够支撑点 (`min_peak_support_points`)
- SNR ≤ 5 → 额外检查半高宽范围 (`min_phase_diff_width` ~ `max_phase_diff_width`)，默认 max=2×phase_window

### 频率追踪 (`process_data_single_pixel.py`)

通过有限差分外推预测下一温度点的谐振频率，避免温漂导致拟合丢失：

- 第 1-3 个温度点：直接用前一温度的拟合 f0 作为初值
- 第 4 个：2 阶差分外推
- 第 5 个：3 阶差分外推
- 第 6+ 个：4 阶差分外推

## 数据格式约定

脚本假设如下目录结构（由 `Auto_Sweep/` 实验生成）：

```
{folder0}/                          # 例: "20260606_092046"
├── {temp}K/                        # 例: "6K", "8K", "10K"
│   └── actual_{temp_meas}K/        # 例: "actual_6.123K"
│       ├── -25dBm/
│       │   ├── 00mW/  → *.s2p
│       │   ├── 01mW/  → *.s2p
│       │   └── ...
│       ├── -35dBm/
│       └── -45dBm/
└── pixel{pixel_indx}/              # 输出目录（脚本自动创建）
    ├── s21 - {temp}K-{power}dBm.jpg
    ├── res shift - {temp}K.jpg
    ├── f0_versus_temp.jpg / .svg
    ├── s21 vs - temp.jpg / .svg
    └── qis_versus_temp.jpg / .svg
```

## 关键参数

`process_data_single_pixel.py` 开头的硬编码参数：

| 变量 | 含义 | 当前值 |
|---|---|---|
| `folder0` | 数据根目录 | `"20260606_092046"` |
| `meas_powers` | VNA 功率 (dBm) | `[25, 35, 45]`（代码中取负号：-25, -35, -45） |
| `meas_laser_powers` | 激光功率 (mW) | `[0, 1, 3, 5, 7, 9]` |
| `pixel_indx` | 谐振器像素编号 | `1` |
| `min_prominence` | 寻峰 prominence | `3` |
| `phase_diff_snr_threshold` | 相位差分 SNR 阈值 | `0.5` |
| `span` | 拟合频率窗口 | `50e6` (50 MHz) |

## 已知问题

- `scraps` 包未安装在此环境，脚本需在配有该包的 Python 环境中运行
- `pickle` 被 import 但未使用（残留）
- `extract_res_and_fit()` 定义了但主流程未调用（注释掉的旧代码路径）
- `dataprocess.py` 底部有被注释掉的 example 代码块
- S2P 文件按 `.s2p` 后缀匹配，每个功率目录只取第一个匹配文件（遍历 `os.listdir` 结果）

## PPT 简报子项目 (`ppt_presentation/`)

2026-06-30 新建。详见 [ppt_presentation/README.md](ppt_presentation/README.md)。

**功能**: 整合出版级新图 (Auto_Sweep/draw/figures/) 和 scraps 分析旧图 (output/merged/)，生成 27 页五段式 PPT 简报。

**快速使用**:
```bash
cd Data_process/ppt_presentation
python generate_ppt.py
# → output/YBCO_KID_6-80K_表征简报_v9.pptx
```

**关键特性**:
- 遵循 `docs/ppt-spec.md` 五段结构 (Why→How→Results→Comparison→Extension)
- 连接 NotebookLM 笔记本中四篇文献 (Mazin/Arzeo/Fohmann/Haldar)
- 数据驱动幻灯片定义 (`_slide_content.py`)，调序无需改渲染代码
- 仅需 python-pptx + Pillow，不依赖 scraps/skrf/scipy
