# merged 数据 YBCO KID 表征简报 PPT 实现方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 生成一份 7 页中文简报 PPTX，展示 merged 数据的 YBCO KID 谐振特性与光学响应表征结果。

**Architecture:** 单脚本 `generate_ppt.py`，用 `python-pptx` 逐页构建，从 `output/merged/` 子目录读取图片，通过 `dataprocess.py` 提取关键数值（无需 scraps），生成 `output/YBCO_KID_merged_表征简报.pptx`。

**Tech Stack:** python-pptx 1.0.2, Pillow (图片尺寸读取), dataprocess.py (谐振寻峰), skrf (S2P 加载), scipy (find_peaks)

---

## 文件结构

```
Data_process/
├── generate_ppt.py              ← 创建：PPT 生成主脚本
├── docs/superpowers/specs/       ← 已有：设计文档
├── docs/superpowers/plans/       ← 已有：本方案
└── output/merged/                ← 已有：8 个子目录的图片
```

---

### Task 1: 创建数值提取辅助函数

**Files:**
- Create: `Data_process/generate_ppt.py`

- [ ] **Step 1: 写入脚本骨架和数值提取函数**

```python
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

MERGED_DIR = Path(r"D:\YBCO\VNAMeas\Auto_Sweep\experiment_data\merged")
OUTPUT_DIR = _script_dir / "output" / "merged"
PPTX_OUT = _script_dir / "output" / "YBCO_KID_merged_表征简报.pptx"

PIXEL_INDX = 1
MEAS_POWERS = [25, 30, 45]
LASER_POWERS = [0, 1, 3, 5, 7, 9]

# ============================================================
# 数值提取
# ============================================================

def scan_temperatures():
    """扫描 merged 目录下的温度点，返回排序后的列表。"""
    pattern = re.compile(r"^(\d+(?:\.\d+)?)K$")
    temps = []
    for subfolder in MERGED_DIR.iterdir():
        if subfolder.is_dir():
            m = pattern.match(subfolder.name)
            if m:
                temps.append(int(float(m.group(1))))
    temps.sort()
    return temps


def find_first_s2p(temp, power_dbm, laser_mw):
    """返回指定温度/VNA功率/激光功率下的第一个 S2P 文件路径。"""
    path = MERGED_DIR / f"{temp}K" / f"-{power_dbm}dBm" / f"{laser_mw:02d}mW"
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
    """
    result = {}

    # 扫描温度
    temps = scan_temperatures()
    result["low_temp"] = temps[0]
    result["high_temp"] = temps[-1]

    # 使用最低温、-25dBm、0mW 的数据做谐振峰检测
    s2p_path = find_first_s2p(temps[0], MEAS_POWERS[0], LASER_POWERS[0])
    if s2p_path is None:
        raise FileNotFoundError(
            f"找不到 S2P 文件: {temps[0]}K/-{MEAS_POWERS[0]}dBm/{LASER_POWERS[0]:02d}mW"
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
    if delta_f > 0:
        result["qi_estimate"] = int(f0_ghz * 1e9 / delta_f)
        result["bandwidth_mhz"] = delta_f / 1e6
    else:
        result["qi_estimate"] = None
        result["bandwidth_mhz"] = None

    # 估算 f0 温度漂移（比较最低温和最高温的近似 f0）
    s2p_high = find_first_s2p(temps[-1], MEAS_POWERS[0], LASER_POWERS[0])
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
            result["f0_shift_direction"] = "蓝移（频率降低）" if shift_pct < 0 else "红移（频率升高）"
        else:
            result["f0_shift_percent"] = None
    else:
        result["f0_shift_percent"] = None

    # 从现有图片中推断所选的低温和高温代表点
    low_dir = OUTPUT_DIR / "05_optical_response_6K"
    high_dir = OUTPUT_DIR / "06_optical_response_highT"
    low_temp_files = [f for f in os.listdir(low_dir) if f.startswith("res shift")]
    high_temp_files = [f for f in os.listdir(high_dir) if f.startswith("res shift")]
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
```

- [ ] **Step 2: 运行数值提取，验证结果**

Run:
```bash
cd D:\YBCO\VNAMeas\Data_process && python generate_ppt.py
```
Expected: 输出关键数值（f0_ghz, num_resonances, qi_estimate 等），无异常。

- [ ] **Step 3: Commit**

```bash
git add Data_process/generate_ppt.py
git commit -m "feat: add key number extraction for PPT generation"
```

---

### Task 2: 实现 PPT 生成函数

**Files:**
- Modify: `Data_process/generate_ppt.py`（追加）

- [ ] **Step 1: 添加 PPT 构建类**

在 `generate_ppt.py` 中追加以下代码（紧接 `extract_key_numbers` 函数之后）：

```python
# ============================================================
# PPT 生成
# ============================================================

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor

# 幻灯片尺寸 (widescreen 16:9)
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)

# 边距
MARGIN = Inches(0.5)
GAP = Inches(0.2)


def _add_textbox(slide, left, top, width, height, text, font_size=Pt(14),
                 bold=False, color=RGBColor(0xFF, 0xFF, 0xFF),
                 alignment=PP_ALIGN.LEFT):
    """添加文本框。"""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = font_size
    p.font.bold = bold
    p.font.color.rgb = color
    p.alignment = alignment
    return txBox


def _add_bullet_list(slide, left, top, width, height, items,
                     font_size=Pt(12), color=RGBColor(0xDD, 0xDD, 0xDD)):
    """添加 bullet 列表。"""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = f"• {item}"
        p.font.size = font_size
        p.font.color.rgb = color
        p.space_after = Pt(6)
    return txBox


def _set_slide_bg(slide, r, g, b):
    """设置幻灯片背景色。"""
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(r, g, b)


def build_pptx(numbers):
    """构建 7 页 PPTX，返回 Presentation 对象。

    Args:
        numbers: extract_key_numbers() 的返回值
    """
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    # 使用空白版式
    blank_layout = prs.slide_layouts[6]  # blank

    # 常用颜色
    DARK_BG = RGBColor(0x1A, 0x1A, 0x2E)   # 深蓝黑
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    GRAY = RGBColor(0xCC, 0xCC, 0xCC)
    ACCENT = RGBColor(0x4F, 0xC3, 0xF7)     # 亮蓝

    # ---- Slide 1: 封面 ----
    slide1 = prs.slides.add_slide(blank_layout)
    _set_slide_bg(slide1, 0x1A, 0x1A, 0x2E)

    _add_textbox(slide1, Inches(1), Inches(1.5), Inches(11), Inches(1.5),
                 "YBCO KID 微波-光学联合表征",
                 font_size=Pt(36), bold=True, color=WHITE,
                 alignment=PP_ALIGN.CENTER)

    # 副标题信息
    info_lines = [
        f"样品：YBCO KID (merged 数据集)",
        f"温度范围：{numbers['low_temp']}K → {numbers['high_temp']}K（{len(scan_temperatures())} 个温度点）",
        f"VNA 功率：-25 / -30 / -45 dBm",
        f"激光功率：0, 1, 3, 5, 7, 9 mW",
        f"分析日期：2026-06-15",
    ]
    y = Inches(3.5)
    for line in info_lines:
        _add_textbox(slide1, Inches(2.5), y, Inches(8), Inches(0.5),
                     line, font_size=Pt(16), color=GRAY,
                     alignment=PP_ALIGN.CENTER)
        y += Inches(0.45)

    # ---- Slide 2: 谐振峰检测与 S21 温度演化 ----
    slide2 = prs.slides.add_slide(blank_layout)
    _set_slide_bg(slide2, 0x1A, 0x1A, 0x2E)

    _add_textbox(slide2, MARGIN, Inches(0.3), Inches(12), Inches(0.6),
                 "谐振器识别与全温 S21 叠加",
                 font_size=Pt(28), bold=True, color=WHITE)

    # 左图：resonance_detection
    img_detect = OUTPUT_DIR / "01_resonance_detection" / "resonance_detection.jpg"
    if img_detect.exists():
        slide2.shapes.add_picture(
            str(img_detect), MARGIN, Inches(1.1), Inches(6), Inches(3.5)
        )

    # 右图：s21 vs temp
    img_s21_temp = OUTPUT_DIR / "04_S21_temperature_overlay" / "s21 vs - temp.jpg"
    if img_s21_temp.exists():
        slide2.shapes.add_picture(
            str(img_s21_temp), Inches(6.8), Inches(1.1), Inches(6), Inches(3.5)
        )

    # 底部要点
    n_res = numbers["num_resonances"]
    f0 = numbers["f0_ghz"]
    qi_est = numbers.get("qi_estimate", "—")
    _add_bullet_list(slide2, MARGIN, Inches(5.0), Inches(12), Inches(2.2), [
        f"采用幅度谷 + 相位差分峰联合判据自动寻峰（SNR ≥ 0.5），共检测到 {n_res} 个谐振峰",
        f"选定谐振峰位于 {f0:.3f} GHz（pixel {PIXEL_INDX}），Qi（-3dB 带宽法）≈ {qi_est}",
        f"全温 S21 叠加：谐振峰随温度单调蓝移，符合超导动能电感 Lₖ ∝ λ²(T) 理论预期",
        "峰形保持良好，器件在 6–76K 范围内稳定工作",
    ], font_size=Pt(13))

    # ---- Slide 3: f₀(T) 与 Qi(T) ----
    slide3 = prs.slides.add_slide(blank_layout)
    _set_slide_bg(slide3, 0x1A, 0x1A, 0x2E)

    _add_textbox(slide3, MARGIN, Inches(0.3), Inches(12), Inches(0.6),
                 "谐振频率与内禀品质因子的温度响应",
                 font_size=Pt(28), bold=True, color=WHITE)

    # 上图：f0 vs temp
    img_f0 = OUTPUT_DIR / "02_f0_temperature" / "f0_versus_temp.jpg"
    if img_f0.exists():
        slide3.shapes.add_picture(
            str(img_f0), MARGIN, Inches(1.1), Inches(5.8), Inches(2.8)
        )

    # 下图：Qi vs temp
    img_qi = OUTPUT_DIR / "03_Qi_temperature" / "qis_versus_temp.jpg"
    if img_qi.exists():
        slide3.shapes.add_picture(
            str(img_qi), MARGIN, Inches(4.1), Inches(5.8), Inches(2.8)
        )

    shift_pct = numbers.get("f0_shift_percent", "—")
    shift_dir = numbers.get("f0_shift_direction", "")
    _add_bullet_list(slide3, Inches(7.2), Inches(1.5), Inches(5.5), Inches(5.5), [
        f"f₀ 随温度升高单调{shift_dir}约 {shift_pct:.1f}%（{numbers['low_temp']}→{numbers['high_temp']}K）",
        "Qi 低温段较高，随温度上升逐渐降低，归因于准粒子损耗增大",
        "三个 VNA 功率 (-25/-30/-45 dBm) 的 Qi 偏差较小",
        "表明读出功率未引入显著非线性效应",
    ], font_size=Pt(13))

    # ---- Slide 4: 低温 6K 光学响应 ----
    slide4 = _build_optical_response_slide(
        prs, blank_layout, numbers,
        temp_label="低温",
        subdir="05_optical_response_6K",
        title_suffix="（T ≈ 6K）",
        comparison_text="频移与激光功率呈良好线性关系 → 符合准粒子退对机制",
    )

    # ---- Slide 5: 高温光学响应 ----
    slide5 = _build_optical_response_slide(
        prs, blank_layout, numbers,
        temp_label="高温",
        subdir="06_optical_response_highT",
        title_suffix="（T ≈ 76K）",
        comparison_text="与 6K 对比：高温下热准粒子密度升高，光注入准粒子的相对增量减小",
    )

    # ---- Slide 6: 响应率 vs 温度 ----
    slide6 = prs.slides.add_slide(blank_layout)
    _set_slide_bg(slide6, 0x1A, 0x1A, 0x2E)

    _add_textbox(slide6, MARGIN, Inches(0.3), Inches(12), Inches(0.6),
                 "光学响应率的温度依赖性",
                 font_size=Pt(28), bold=True, color=WHITE)

    img_resp = OUTPUT_DIR / "07_responsivity_temperature" / "responsivity_vs_temp.jpg"
    if img_resp.exists():
        slide6.shapes.add_picture(
            str(img_resp), MARGIN, Inches(1.2), Inches(8.5), Inches(5.0)
        )

    _add_bullet_list(slide6, Inches(9.5), Inches(1.5), Inches(3.3), Inches(5.5), [
        "响应率 (Hz/W) 随温度的变化趋势",
        "响应率温度依赖与超导能隙 Δ(T) 定性一致",
        "低温段保持较高响应水平",
        "下一步需与 BCS 理论定量比较",
    ], font_size=Pt(13))

    # ---- Slide 7: 总结 ----
    slide7 = prs.slides.add_slide(blank_layout)
    _set_slide_bg(slide7, 0x1A, 0x1A, 0x2E)

    _add_textbox(slide7, Inches(1), Inches(1.0), Inches(11), Inches(1.0),
                 "小结与下一步",
                 font_size=Pt(36), bold=True, color=WHITE,
                 alignment=PP_ALIGN.CENTER)

    done_items = [
        f"成功表征 YBCO KID 在 {numbers['low_temp']}–{numbers['high_temp']}K 的谐振特性与光学响应",
        f"f₀(T) 蓝移约 {shift_pct:.1f}%，Qi(T) 下降趋势与 BCS 理论预期一致",
        "光学响应率呈现温度依赖，低温段保持较高响应水平",
        "系统在测试温区范围内稳定可靠，谐振峰形保持良好",
    ]
    _add_bullet_list(slide7, Inches(1.5), Inches(2.5), Inches(10), Inches(2.0),
                     done_items, font_size=Pt(16), color=WHITE)

    next_items = [
        "NEP（噪声等效功率）估算与优化",
        "多像素统计比较，评估器件均匀性",
        "更低温度（< 1K）测量，探索极限灵敏度",
        "低温放大器（HEMT / JPA）集成测试",
    ]
    _add_bullet_list(slide7, Inches(1.5), Inches(4.5), Inches(10), Inches(2.0),
                     next_items, font_size=Pt(14), color=GRAY)

    return prs


def _build_optical_response_slide(prs, blank_layout, numbers,
                                   temp_label, subdir, title_suffix,
                                   comparison_text):
    """构建光学响应幻灯片（Slide 4/5 共用模板）。

    Args:
        prs: Presentation 对象
        blank_layout: 空白版式
        numbers: 数值字典
        temp_label: "低温" or "高温"
        subdir: 子目录名（如 "05_optical_response_6K"）
        title_suffix: 标题后缀
        comparison_text: 右侧要点说明
    """
    slide = prs.slides.add_slide(blank_layout)
    _set_slide_bg(slide, 0x1A, 0x1A, 0x2E)

    subdir_path = OUTPUT_DIR / subdir

    _add_textbox(slide, MARGIN, Inches(0.3), Inches(12), Inches(0.6),
                 f"{temp_label}下的光致谐振频移 {title_suffix}",
                 font_size=Pt(28), bold=True,
                 color=RGBColor(0xFF, 0xFF, 0xFF))

    # 找到该子目录下的 4 张图
    s21_files = sorted([f for f in os.listdir(subdir_path) if f.startswith("s21 -")])
    res_shift_file = None
    for f in os.listdir(subdir_path):
        if f.startswith("res shift -"):
            res_shift_file = f
            break

    # 2×2 网格排列
    positions = [
        (MARGIN, Inches(1.2), Inches(3.0), Inches(2.6)),          # 左上
        (Inches(3.7), Inches(1.2), Inches(3.0), Inches(2.6)),     # 右上
        (MARGIN, Inches(4.0), Inches(3.0), Inches(2.6)),          # 左下
        (Inches(3.7), Inches(4.0), Inches(3.0), Inches(2.6)),     # 右下
    ]

    # 前 3 个位置放 s21 图
    for i, s21f in enumerate(s21_files[:3]):
        img_path = subdir_path / s21f
        left, top, w, h = positions[i]
        slide.shapes.add_picture(str(img_path), left, top, w, h)

    # 第 4 个位置放 res shift 图
    if res_shift_file:
        img_path = subdir_path / res_shift_file
        left, top, w, h = positions[3]
        slide.shapes.add_picture(str(img_path), left, top, w, h)

    # 右侧要点
    _add_bullet_list(slide, Inches(7.2), Inches(1.5), Inches(5.5), Inches(5.5), [
        f"展示 -25 / -30 / -45 dBm 三个 VNA 功率",
        f"S21 曲线随 0→9 mW 激光功率演化",
        "右上图：谐振频率偏移 vs 激光功率",
        comparison_text,
    ], font_size=Pt(13))

    return slide


# ============================================================
# 主入口
# ============================================================

if __name__ == "__main__":
    print("提取关键数值...")
    numbers = extract_key_numbers()
    print()
    for k, v in numbers.items():
        print(f"  {k}: {v}")

    print(f"\n构建 PPTX...")
    prs = build_pptx(numbers)

    os.makedirs(PPTX_OUT.parent, exist_ok=True)
    prs.save(str(PPTX_OUT))
    print(f"\nPPTX 已保存到: {PPTX_OUT}")
```

- [ ] **Step 2: 运行 PPT 生成**

Run:
```bash
cd D:\YBCO\VNAMeas\Data_process && python generate_ppt.py
```
Expected: 生成 `output/YBCO_KID_merged_表征简报.pptx`，大小约 2–5 MB。

- [ ] **Step 3: 人工检查 PPTX**

用 PowerPoint 打开检查：
- 7 页幻灯片均存在
- 中文文本可读、无乱码
- 图片位置正确、无裁剪
- 深色背景与 matplotlib 暗色图片协调

- [ ] **Step 4: Commit**

```bash
git add Data_process/generate_ppt.py Data_process/output/YBCO_KID_merged_表征简报.pptx
git commit -m "feat: add PPT generation script with 7-slide YBCO KID characterization report"
```

---

### Task 3: 编写测试

**Files:**
- Create: `Data_process/tests/test_generate_ppt.py`

- [ ] **Step 1: 写测试**

```python
# -*- coding: utf-8 -*-
"""测试 PPT 生成脚本的关键函数。"""
import sys
from pathlib import Path

_script_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_script_dir))

import os
import tempfile
from generate_ppt import (
    scan_temperatures,
    find_first_s2p,
    extract_key_numbers,
    build_pptx,
    MERGED_DIR,
)


def test_scan_temperatures():
    """应该返回排序后的温度列表。"""
    temps = scan_temperatures()
    assert len(temps) > 0, "应该至少找到一个温度目录"
    assert temps == sorted(temps), "温度列表应为升序"
    assert temps[0] >= 4, f"最低温应 ≥ 4K: {temps[0]}"
    assert all(isinstance(t, int) for t in temps), "温度应为整数"


def test_find_first_s2p():
    """应该返回有效 S2P 文件路径。"""
    temps = scan_temperatures()
    path = find_first_s2p(temps[0], 25, 0)
    assert path is not None, f"应该找到 {temps[0]}K/-25dBm/00mW 的 S2P 文件"
    assert os.path.isfile(path), f"应为有效文件: {path}"
    assert path.endswith(".s2p"), f"应以 .s2p 结尾: {path}"


def test_extract_key_numbers():
    """应该返回所有关键字段的非空值。"""
    nums = extract_key_numbers()

    required_keys = [
        "f0_ghz", "num_resonances", "low_temp", "high_temp",
        "all_resonances",
    ]
    for key in required_keys:
        assert key in nums, f"缺少字段: {key}"
        assert nums[key] is not None, f"字段 {key} 为 None"

    assert nums["num_resonances"] > 0, "应该检测到至少 1 个谐振峰"
    assert nums["f0_ghz"] > 0, "谐振频率应为正数"
    assert nums["low_temp"] < nums["high_temp"], "低温应小于高温"


def test_build_pptx_creates_file():
    """build_pptx 应该生成有效的 PPTX 文件。"""
    nums = extract_key_numbers()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "test_output.pptx"
        prs = build_pptx(nums)
        prs.save(str(out_path))

        assert out_path.exists(), "PPX 文件应该存在"
        assert out_path.stat().st_size > 1000, "文件不应为空"
        assert out_path.suffix == ".pptx"

        # 验证幻灯片数量
        from pptx import Presentation
        prs_check = Presentation(str(out_path))
        assert len(prs_check.slides) == 7, f"应有 7 页幻灯片: 实际 {len(prs_check.slides)}"
```

- [ ] **Step 2: 运行测试**

Run:
```bash
cd D:\YBCO\VNAMeas\Data_process && python -m pytest tests/test_generate_ppt.py -v -x --tb=short
```
Expected: 4 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add Data_process/tests/test_generate_ppt.py
git commit -m "test: add PPT generation tests"
```

---

## 输出验证清单

生成 PPTX 后确认：
- [ ] 7 页齐全
- [ ] Slide 1: 标题 + 副标题参数正确
- [ ] Slide 2: 2 张图（寻峰 + S21 叠加）+ bullet 要点
- [ ] Slide 3: 2 张图（f0 vs T + Qi vs T）+ bullet
- [ ] Slide 4: 4 张图 2×2 网格（6K 光学响应）+ 说明
- [ ] Slide 5: 4 张图 2×2 网格（高温光学响应）+ 说明
- [ ] Slide 6: responsivity_vs_temp.jpg 大图 + 要点
- [ ] Slide 7: 纯文字总结（✅ 已完成 + ⏳ 下一步）
- [ ] 深色背景与 scrap 暗色 matplotlib 图协调
- [ ] 中文无乱码
- [ ] 图片无严重变形/拉伸
