# CLAUDE.md

YBCO 超导测量 monorepo。主体代码在 `Auto_Sweep/` 子目录中。

## 目录结构

```
D:\YBCO\VNAMeas\
├── Auto_Sweep/          ← 主项目（重构后的模块化生产代码）
│   └── CLAUDE.md        ← 详细文档入口，架构/配置/硬件信息
├── Data_process/        ← 离线数据处理（谐振器拟合、频率追踪）
│   └── CLAUDE.md        ← 数据处理文档
├── data/                ← 历史测量数据（~40 个日期文件夹，gitignore）
└── *.py                 ← 根级历史脚本（独立于 Auto_Sweep）
```

**详细文档见 [Auto_Sweep/CLAUDE.md](Auto_Sweep/CLAUDE.md)**，数据处理见 [Data_process/CLAUDE.md](Data_process/CLAUDE.md)。

## 根级历史脚本速览

根级 ~25 个 `.py` 脚本是重构前的遗留代码，**均不依赖 Auto_Sweep 模块**。它们共享 `Lakeshore335.py` 作为公共 LakeShore 驱动，分为以下几组：

| 分组 | 代表文件 | 状态 |
|------|----------|------|
| LakeShore 驱动/GUI | `Lakeshore335.py`, `Lakeshore335_interface*.py`, `Lakeshore335_auto_tune_PID.py` | 历史参考 |
| PowerSweep | `PowerSweep_auto_forKeysightVA.py`, `PowerTempSweep_auto2.py` | 部分仍在使用 |
| Read_VNA | `Read_VNA*.py`（9 个变体，基于 R&S ZNA 模板） | 历史 |
| 绘图分析 | `plot_result.py`, `Fitting_versus_temp_sweep_freq.py` | 按需使用 |
| 其他工具 | `VoltageMeterReader.py`, `temp_monitor.py`, `temperature_power_sweep.py` | 按需使用 |

两套 VNA 通信方案共存：`RsInstrument`（R&S ZNA）和 `pyvisa`（Keysight PXI）。

## 数据处理模块

`Data_process/` 目录为离线后处理模块，与 `Auto_Sweep/` 在线测量互补：

- **`dataprocess.py`** — 谐振器寻峰库：幅度谷 + 相位差分峰联合判据，SNR 验证
- **`process_data_single_pixel.py`** — 单像素分析脚本：遍历 T × P_r × P_laser 数据，调用 `scraps` 做 `cmplxIQ` 谐振器拟合，追踪 f0(T) 和响应率
- 依赖 `scraps`（PMO 内部超导谐振器拟合包，非公开）

详见 [Data_process/CLAUDE.md](Data_process/CLAUDE.md)。

## 绘图快速参考

**新工作流（两步，避免重复扫描）：**

```bash
# Step 1: 收集缓存 + 生成验证图
python Auto_Sweep/draw/_data_cache.py --data-dir "D:/.../experiment_data/{数据集名}"

# Step 2: 画图（从缓存读取，秒级启动）
python Auto_Sweep/draw/plot_all.py --cache "D:/.../output/_cache/_cache_{数据集}.pkl"
```

**Prompt 模板（省口舌）：**

| 场景 | 说法 |
|------|------|
| 新数据首次画图 | "用 `{数据集}` 画图，先收集缓存 + 验证，确认后画全部方案" |
| 改参数重画 | "基于 `{数据集}` 缓存，用 `{VNA功率}` 画方案 `{A/B/S21}`，仅拟合线" |
| 加新方案 | "基于已有缓存，追加画 `{方案}`" |
| 换数据集 | "用 `{新数据}` 代替，其余不变" |

**常用 VNA 功率选择：**

| 描述 | `--vna-powers` |
|------|----------------|
| 全部 16 级 (2dB 步) | 不传（默认全部） |
| 9 条低功率 (-55~-39) | `-55,-53,-51,-49,-47,-45,-43,-41,-39` |
| 6 条等间距 (6dB 步) | `-55,-49,-43,-37,-31,-25` |

详细文档: [Auto_Sweep/draw/CLAUDE.md](Auto_Sweep/draw/CLAUDE.md)

## 输出语言规则

- 所有面向用户的输出默认使用**简体中文**：PPT 简报、日志信息、图表标题、代码注释、CLAUDE.md 文档
- 代码内部标识符（变量名、函数名、类名）使用英文，遵循 PEP 8
- 对外技术文档和 API 文档可按需使用英文
- 图表中的技术术语（如 "f₀", "Qi", "S21", "SNR"）保留标准英文缩写

## Git 说明

- `.gitignore` 排除 `*.csv`, `*.s2p`, `data/`, `*.zip`, `__pycache__/`
- `Auto_Sweep/` 内的 `experiment_data/` 也应排除（实验输出，不提交）

## Claude Code 稳定性规则

**当前版本 2.1.162 存在 Bun runtime 崩溃 bug**（深嵌套 Agent 链 + ShellError 触发 SIGKILL）。以下规则必须遵守，防止闪退丢失工作：

### 启动方式
- **始终用 debug 模式启动**：`claude --debug --debug-file "$HOME/.claude/debug.log"`
- 这样崩溃后可查看 `~/.claude/debug.log` 定位原因

### 测试运行
- **禁止单次跑全量测试** (>50 个)，必须分批：
  - `python -m pytest tests/test_<module>.py -x -q --tb=short`（单文件，遇错即停）
  - `python -m pytest tests/ -x -q --tb=short`（全量但遇错即停）
  - 每批最多 30 个测试
- 优先用 `-x`（fail-fast），不要裸跑全量

### Agent/Sub-agent 深度
- 单个 session 中 Tool Call **嵌套深度不得超过 20**
- 发现自己在反复 spawn Agent 修改同一文件 → 立刻停止，手动 merge 改动，新开会话
- 大任务拆分为多个独立 session，不要在一个 session 中连续跑 Task 1→11

### Session 管理
- 每完成 2-3 个 git commit 后，**新开 session** 继续
- 任务量预估超过 5 个 commit → 提前拆分，在 plan 中明确 session 边界
- 不要在一句话中要求做超过 5 件独立的事情

### 崩溃恢复
- 查看日志：`cat ~/.claude/debug.log | tail -100`
- 查看 telemetry：`ls -lt ~/.claude/telemetry/ | head -5`
- 恢复代码后立即 `git commit`，不要依赖 Claude 的 memory 恢复
