# 实验数据整合方案 — 设计文档

**日期**: 2026-06-14  
**状态**: 已确认  
**目标**: 将多次拆分运行的实验数据整合为统一目录，做完整性分析，生成补测建议，适配离线处理管线

---

## 背景

一次完整的 YBCO 谐振器温区扫描（6K → 80K，每 2K 一步，3 种 VNA 功率 × 6 种激光功率）因软件崩溃被拆分为 8 次独立运行。每次运行的计划温度列表相同（目标到 80K），但实际在中途崩溃，导致：

- 5 个温度点有跨文件夹重复（崩溃点处数据不完整）
- 原始目录结构缺少 `actual_{temp}K/` 中间层（实际温度编码在 S2P 文件名中）
- VNA 功率为 -25/-30/-45 dBm，与现有处理脚本默认的 -25/-35/-45 dBm 不同

## 设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 去重策略 | 取最完整的（S2P 文件数最多的那次运行） | 崩溃发生在温度中途，文件数少的 = 不完整 |
| 输出格式 | 扁平结构（无 `actual_` 中间层） | 简化目录结构，从文件名解析实际温度 |
| 工具定位 | 通用 CLI 工具，纳入 Data_process | 拆分运行是常态，需要可复用 |
| 缺失分析 | 带补测建议清单 | 诊断缺失原因 + 生成 Auto_Sweep 可消费的补测计划 |

---

## 架构

```
Data_process/
├── experiment_merger.py         ← 合并引擎
├── completeness_checker.py      ← 完整性分析 + 补测清单
├── tests/
│   ├── test_experiment_merger.py
│   └── test_completeness_checker.py
└── otherwise/
    └── process_data_single_pixel.py  ← 适配修改（去掉 actual_ 层）
```

### 数据流

```
accomplish/ (8 个碎片文件夹)
    │
    ▼
experiment_merger.py  ──→  merged/ (统一扁平目录)
    │
    ▼
completeness_checker.py  ──→  report.json (完整性报告 + 补测清单)
    │
    ▼
process_data_single_pixel.py  ──→  拟合结果 + 图表
```

---

## 模块 1: experiment_merger.py

### CLI

```bash
python experiment_merger.py \
    --input 20260611_115038 20260612_014432 ... \
    --output ../merged/20260611-14_6K-80K \
    --strategy most_complete \
    --dry-run
```

### 核心函数

```python
def scan_fragments(input_dirs: list[Path]) -> FragmentIndex
    """扫描所有输入目录，建立 (temp, vna_power, laser_power) -> [FileEntry] 索引"""

def resolve_conflicts(index: FragmentIndex, strategy: str) -> MergePlan
    """按策略去重，返回每个组合的最终文件路径"""

def execute_merge(plan: MergePlan, output_dir: Path, use_hardlink: bool = True) -> MergeReport
    """执行合并（默认硬链接节省空间），返回统计报告"""
```

### 去重逻辑 (`most_complete`)

对每个 `(temp, vna_power, laser_power)` 组合：
1. 如果只有 1 个片段有该文件 → 直接选用
2. 如果多个片段都有 → 选所在温度目录下 S2P 总数最多的片段
3. 如果总数相同 → 选时间最新的片段（按片段文件夹时间戳）

### 输出结构（扁平）

```
merged/
├── 6K/
│   ├── -25dBm/
│   │   ├── 00mW/ → YBCO_-25dBm_00mW_target_6K_actual_6.xxxK.s2p
│   │   ├── 01mW/
│   │   ├── 03mW/
│   │   ├── 05mW/
│   │   ├── 07mW/
│   │   └── 09mW/
│   ├── -30dBm/
│   └── -45dBm/
├── 8K/
...
```

### 合并方式

- 默认使用硬链接（`os.link`），不占用额外磁盘空间
- Windows 不支持硬链接时 fallback 到复制（`shutil.copy2`）
- `--dry-run` 模式仅打印合并计划，不执行实际文件操作

---

## 模块 2: completeness_checker.py

### CLI

```bash
python completeness_checker.py \
    --input ../merged/20260611-14_6K-80K \
    --temps-start 6 --temps-stop 80 --temps-step 2 \
    --vna-powers=-25,-30,-45 \
    --laser-powers 0,1,3,5,7,9 \
    --format json \
    --output report.json
```
> `--vna-powers=` 使用等号避免负号被 argparse 误解析为 flag；
> 温度范围由 start/stop/step 三元组生成 `range(start, stop+1, step)`。

### 核心函数

```python
def build_completeness_matrix(
    data_dir: Path,
    temps: list[int],
    vna_powers: list[int],
    laser_powers: list[int],
) -> np.ndarray   # shape (T, P_r, P_laser), dtype=bool

def diagnose_missing(
    matrix, temps, vna_powers, laser_powers
) -> list[MissingPoint]
    """分类缺失原因:
       - "isolated" — 孤立的偶发缺失（周围温度点完整）
       - "edge"     — 温度范围边缘缺失
       - "block"    — 连续多温度缺失同一功率组合
    """

def generate_retest_plan(missing: list[MissingPoint]) -> RetestPlan
    """按温度→VNA功率→激光功率排序，合并同一温度下的缺失"""

def format_report(report: CompletenessReport, fmt: str) -> str
    """输出格式化: json | csv | table"""
```

### 输出格式

`--format table` 示例：
```
Temperature  VNA Power  Laser Power  Status
6K           -25dBm     00mW         ✓
6K           -30dBm     03mW         ✗ (missing — isolated)
...
────────────────────────────────────────
Summary: 684 expected, 655 found, 18 missing, 11 from-duplicates
Missing: 6 isolated, 8 edge, 4 block
Suggested retest: 6 temperature points
```

`--format json` 输出：
```json
{
  "summary": {
    "expected": 684,
    "found": 655,
    "missing": 18,
    "from_duplicates": 11,
    "missing_breakdown": {"isolated": 6, "edge": 8, "block": 4}
  },
  "retest_plan": {
    "temps": [6, 10, 72, 74, 78],
    "vna_powers": [-25, -30, -45],
    "laser_powers": [0, 1, 3, 5, 7, 9],
    "missing_combos": [
      {"temp": 6, "vna_power": -30, "laser_power": 3},
      "..."
    ]
  },
  "details": [
    {"temp": 6, "vna_power": -30, "laser_power": 3, "status": "missing", "category": "isolated"}
  ]
}
```

---

## 模块 3: process_data_single_pixel.py 适配

### 修改点

**1. VNA 功率默认值**（第 102 行）：
```python
# 修改前
meas_powers = [25, 35, 45]
# 修改后
meas_powers = [25, 30, 45]  # 匹配 accomplish 实际测量
```

**2. 去掉 `actual_{temp}K` 中间层**（第 120-134 行）：
```python
# 修改前：遍历 actual_{temp}K 子目录
for temp in temps:
    folder_temp = os.path.join(folder0, f'{temp}K')
    for folder in os.listdir(folder_temp):
        match = re.fullmatch(r"actual_(\d+(?:\.\d+)?)K", folder)
        if match:
            temp_meas_all.append(float(match.group(1)))

# 修改后：从 S2P 文件名解析实际温度
# 文件名格式: YBCO_-25dBm_00mW_target_6K_actual_6.123K.s2p
for temp in temps:
    path_temp = os.path.join(folder0, f'{temp}K')
    for vna_dir in sorted(os.listdir(path_temp)):
        vna_path = os.path.join(path_temp, vna_dir)
        if not os.path.isdir(vna_path): continue
        for laser_dir in sorted(os.listdir(vna_path)):
            laser_path = os.path.join(vna_path, laser_dir)
            if not os.path.isdir(laser_path): continue
            for f in os.listdir(laser_path):
                if f.endswith('.s2p'):
                    match = re.search(r"actual_([\d.]+)K", f)
                    if match:
                        temp_meas_all.append(float(match.group(1)))
                    break
            break
        break
```

**3. S2P 文件矩阵构建**（第 141 行）：
```python
# 修改前
path_temp = os.path.join(folder0, f'{temp}K', f'actual_{temp_meas:.3f}K')

# 修改后 — 扁平结构，直接拼接 temp/vna/laser
path_temp = os.path.join(folder0, f'{temp}K')
```

主循环逻辑不变。总共改动约 15 行。

---

## 测试策略

### test_experiment_merger.py

- 用 `tmp_path` 创建模拟碎片目录（包含正常文件 + 重复温度点 + 不完整温度点）
- 测试 `scan_fragments` 索引正确性
- 测试 `most_complete` 策略：选 S2P 总数最多的片段
- 测试 dry-run 模式不产生文件
- 测试硬链接 fallback 到复制
- 测试空输入、单输入等边缘情况

### test_completeness_checker.py

- 用模拟的合并目录测试完整性矩阵
- 测试缺失分类（isolated/edge/block）
- 测试 JSON/CSV/table 格式输出
- 测试完全完整的数据集返回零缺失
- 验证 retest_plan 按温度排序

---

## 约束与已知限制

- `scraps` 包非公开，`completeness_checker` 和 `experiment_merger` 不依赖它
- Windows 平台：硬链接需要 NTFS，fallback 到复制
- 仅处理 `.s2p` 文件，忽略其他格式
- 文件名中的实际温度精度为 3 位小数（`actual_6.123K` 格式）
- `discarded` 目录被忽略（现有数据中均为空）
