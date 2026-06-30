# Design Spec: merged 数据集 YBCO KID 表征简报 PPT

**Date**: 2026-06-15
**Status**: approved
**Scope**: 单次生成，非持续维护

## 目标

基于 `Auto_Sweep/experiment_data/merged/` 的数据，生成一份 7 页中文简报 PPT（风格参照范例 `otherwise/数据处理初步-2.pptx`），展示：

- 谐振峰检测与 S21 温度演化
- f₀(T) / Qi(T) 温度响应
- 低温 & 高温下的光学响应（S21 vs 激光功率 + 频移 vs 激光功率）
- 响应率随温度变化
- 总结与展望

## 输入

| 来源 | 路径 |
|------|------|
| 图片根目录 | `Data_process/output/merged/`（已整编为 8 个子目录） |
| 范例 PPT | `Data_process/otherwise/数据处理初步-2.pptx`（风格参考） |
| 原始数据 | `Auto_Sweep/experiment_data/merged/`（不直接读取，仅引用） |

## 输出

`Data_process/output/YBCO_KID_merged_表征简报.pptx`

---

## Slide-by-Slide 设计

### Slide 1 — 封面

- **布局**: 居中标题 + 副标题列表
- **标题**: YBCO KID 微波-光学联合表征
- **副标题**（bullet）:
  - 样品：YBCO KID (merged 数据集)
  - 温度范围：6K → 76K（38 个温度点）
  - VNA 功率：-25 / -30 / -45 dBm
  - 激光功率：0, 1, 3, 5, 7, 9 mW
  - 分析日期：2026-06-15
- **配图**: 无

### Slide 2 — 谐振峰检测与全温 S21 叠加

- **布局**: 左图右文或上图下文（依图片比例决定）
- **标题**: 谐振器识别与全温 S21 叠加
- **要点** (bullet):
  - 采用幅度谷 + 相位差分峰联合判据自动寻峰，SNR ≥ 0.5
  - 选定谐振峰位于约 3.X GHz，Qi 在低温段约 X000
  - 全温 S21 叠加显示谐振峰随温度单调蓝移 → 超导动能电感效应
  - 峰形保持良好，器件在 6–76K 范围内稳定工作
- **配图**:
  - `01_resonance_detection/resonance_detection.jpg`（寻峰结果）
  - `04_S21_temperature_overlay/s21 vs - temp.jpg`（全温叠加）

### Slide 3 — f₀(T) 与 Qi(T)

- **布局**: 上下两图，各配要点
- **标题**: 谐振频率与内禀品质因子的温度响应
- **要点**:
  - f₀ 随温度升高单调下降约 X%（6→76K），符合动能电感 L_k ∝ λ²(T) 理论预期
  - Qi 低温段较高（~X000），随温度上升逐渐降低，归因于准粒子损耗增大
  - 三个 VNA 功率 (-25/-30/-45 dBm) 的 Qi 偏差较小，说明读出功率未引入显著非线性
- **配图**:
  - `02_f0_temperature/f0_versus_temp.jpg`
  - `03_Qi_temperature/qis_versus_temp.jpg`

### Slide 4 — 6K 光学响应

- **布局**: 4 张图网格排列（2×2）
- **标题**: 6K 下的光致谐振频移
- **要点**:
  - 展示 -25 / -30 / -45 dBm 三个 VNA 功率下 S21 曲线随 0→9 mW 激光功率的演化
  - 右上图为谐振频率偏移 vs 激光功率（3 个 VNA 功率各一条拟合线）
  - 频率响应率约 X Hz/W，频移与激光功率呈良好线性 → 准粒子退对机制
- **配图**: 选用 6K 附近一个完整温度点（如 5.991K）的 4 张图：
  - `05_optical_response_6K/s21 - 5.991K-25dBm.jpg`
  - `05_optical_response_6K/s21 - 5.991K-30dBm.jpg`
  - `05_optical_response_6K/s21 - 5.991K-45dBm.jpg`
  - `05_optical_response_6K/res shift - 5.991K.jpg`

### Slide 5 — 高温光学响应

- **布局**: 同 Slide 4（2×2 网格）
- **标题**: 高温下的光致谐振频移（~76K）
- **要点**:
  - 与 6K 对比，高温下光学响应率显著变化
  - 高温下热准粒子密度升高 → 超导态对光注入准粒子的相对增量减小
  - 讨论响应率温度依赖是否与 Δ(T) 趋势一致
- **配图**: 选用 76K 附近一个完整温度点（如 76.204K）的 4 张图：
  - `06_optical_response_highT/s21 - 76.204K-25dBm.jpg`
  - `06_optical_response_highT/s21 - 76.204K-30dBm.jpg`
  - `06_optical_response_highT/s21 - 76.204K-45dBm.jpg`
  - `06_optical_response_highT/res shift - 76.204K.jpg`

### Slide 6 — 响应率 vs 温度

- **布局**: 大图居中 + 要点右侧或下方
- **标题**: 光学响应率的温度依赖性
- **要点**:
  - 响应率 (Hz/W) 从 6K 至 76K 的变化趋势
  - 响应率在低温段较高/稳定，在约 XX K 后开始下降/上升
  - 趋势与超导能隙 Δ(T) 的温度依赖定性一致
  - 最高响应率约 XXXX Hz/W @ XX K
- **配图**:
  - `07_responsivity_temperature/responsivity_vs_temp.jpg`

### Slide 7 — 总结

- **布局**: 纯文字，分栏或 bullet list
- **标题**: 小结与下一步
- **要点**:
  - ✅ 成功表征 YBCO KID 在 6–76K 的谐振特性与光学响应
  - ✅ f₀(T) 蓝移、Qi(T) 下降趋势与 BCS 理论预期一致
  - ✅ 光学响应率呈现温度依赖，最优值约 XXXX Hz/W
  - ⏳ 下一步：NEP 估算、多像素统计比较、低温放大器集成测试
- **配图**: 无（或复用 f0_versus_temp 缩略图作为装饰）

---

## 实现方法

### 方案：python-pptx 脚本（推荐）

用 `python-pptx` 库逐页构建 PPTX，从子目录读取图片、嵌入中文文本框。

**优势**：
- 完全可复现，后续换数据只需重跑
- 图片位置/大小精确可控
- 中文文本无编码问题（python-pptx 原生 Unicode）

**关键 API**：
```python
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN

prs = Presentation()
# 空白版式
slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
# 添加图片
slide.shapes.add_picture(path, left, top, width, height)
# 添加文本框
txBox = slide.shapes.add_textbox(left, top, width, height)
txBox.text_frame.paragraphs[0].text = "..."
```

**依赖**: `python-pptx`（需安装）、`Pillow`（已有）

### 替代方案：手动拼装

在 PowerPoint 中手动插入图片和文字。零开发成本但不可复现。不推荐。

---

## 关键数值提取

部分 Slide 的要点包含 "X.X GHz"、"XXXX Hz/W" 等占位符。这些数值需要从 `process_merged_data.py` 的输出日志中提取，或者重新运行精简版脚本仅输出关键数值（f₀ 范围、Qi 范围、响应率极值）。

**处理方式**（生成 PPT 时）：
1. 运行 `process_merged_data.py` 已有输出日志（终端 print）→ 手工提取关键数
2. 或者在生成 PPT 的脚本中直接 import `dataprocess` 和 `scraps` 做一次轻量计算
3. 推荐方案 1：先从已有日志中读取关键数值填入 PPT 文本

---

## 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| PPT 页数 | 7 页 | 与范例结构对齐 |
| 图片选用 | 每温度选 1 个完整温度点的全套 4 张 | 避免信息过载 |
| 文字语言 | 中文 | 内部组会简报需求 |
| 工具 | python-pptx | 可复现 |
| 配色/字体 | 继承 matplotlib 输出的 scraps 暗色主题 | 与现有图片一致 |

---

## 自检

- [x] 无 TBD/TODO 占位（除数值占位符 X.X，已说明提取方式）
- [x] Slide 结构内无矛盾
- [x] 范围聚焦：仅生成 1 个 PPTX，无后续维护需求
- [x] 图片路径均指向已有文件
