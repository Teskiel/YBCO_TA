# 实验数据整合 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建三个模块（合并引擎、完整性检查器、处理脚本适配），实现拆分实验数据的统一整合管线。

**Architecture:** `experiment_merger.py` 扫描碎片目录→去重→硬链接合并；`completeness_checker.py` 分析完整性→分类缺失→生成补测清单；两模块独立可测，CLI 参数化。

**Tech Stack:** Python 3.12+ stdlib (dataclasses, pathlib, argparse, os), numpy (布尔矩阵), pytest (tmp_path fixtures)

**Spec:** `docs/superpowers/specs/2026-06-14-experiment-data-integration-design.md`

---

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| Create | `Data_process/experiment_merger.py` | 合并引擎：扫描→去重→硬链接合并 |
| Create | `Data_process/completeness_checker.py` | 完整性分析：矩阵构建→缺失分类→补测清单 |
| Create | `Data_process/tests/test_experiment_merger.py` | 合并引擎单元测试 |
| Create | `Data_process/tests/test_completeness_checker.py` | 完整性检查器单元测试 |
| Create | `Data_process/tests/__init__.py` | 测试包标记 |
| Modify | `Data_process/otherwise/process_data_single_pixel.py` | 适配扁平结构 (3处×~5行) |

---

### Task 1: 项目基础设施

**Files:**
- Create: `Data_process/tests/__init__.py`

- [ ] **Step 1: 创建 tests 目录和 `__init__.py`**

```bash
mkdir -p D:\YBCO\VNAMeas\Data_process\tests
```

```python
# Data_process/tests/__init__.py (空文件)
```

- [ ] **Step 2: 验证目录结构正确**

```bash
ls D:\YBCO\VNAMeas\Data_process\tests/
```

- [ ] **Step 3: Commit**

```bash
git add Data_process/tests/__init__.py
git commit -m "chore: create Data_process/tests package"
```

---

### Task 2: TDD scan_fragments — 碎片扫描

**Files:**
- Create: `Data_process/tests/test_experiment_merger.py` (fixture + 3 tests)
- Create: `Data_process/experiment_merger.py` (dataclasses + scan_fragments)

- [ ] **Step 1: 写测试 fixture + 3 个测试用例**

```python
# Data_process/tests/test_experiment_merger.py
# -*- coding: utf-8 -*-
"""experiment_merger.py 单元测试"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pathlib import Path
import experiment_merger as em


@pytest.fixture
def mock_two_fragments(tmp_path):
    """
    创建两个模拟碎片文件夹：
    frag1 (20260611): 6K 有 2 s2p (不完整), 8K 有 1 s2p
    frag2 (20260612): 6K 有 4 s2p (完整), 8K 有 4 s2p
    预期 most_complete 策略选中 frag2 的文件
    """
    frag1 = tmp_path / "20260611"
    frag2 = tmp_path / "20260612"

    # frag1: 6K 不完整 (只有 -25dBm 下 00mW 和 01mW)
    for laser in ["00mW", "01mW"]:
        d = frag1 / "6K" / "-25dBm" / laser
        d.mkdir(parents=True)
        (d / f"frag1_6K.s2p").write_text("frag1")

    # frag1: 8K 只有 1 个文件
    (frag1 / "8K" / "-25dBm" / "00mW").mkdir(parents=True)
    (frag1 / "8K" / "-25dBm" / "00mW" / "frag1_8K.s2p").write_text("frag1")

    # frag2: 6K 和 8K 各 4 文件 (2 VNA × 2 laser)
    for temp in ["6K", "8K"]:
        for vna in ["-25dBm", "-30dBm"]:
            for laser in ["00mW", "01mW"]:
                d = frag2 / temp / vna / laser
                d.mkdir(parents=True)
                (d / f"frag2_{temp}_{vna}_{laser}.s2p").write_text("frag2")

    return [frag1, frag2]


class TestScanFragments:
    """scan_fragments() 测试"""

    def test_finds_all_unique_combos(self, mock_two_fragments):
        """找到所有唯一的 (T, VNA, laser) 组合"""
        index = em.scan_fragments(mock_two_fragments)
        # 6K/-25dBm/00mW: frag1 + frag2 = 2
        # 6K/-25dBm/01mW: frag1 + frag2 = 2
        # 6K/-30dBm/00mW: frag2 only = 1
        # 6K/-30dBm/01mW: frag2 only = 1
        # 8K/-25dBm/00mW: frag1 + frag2 = 2
        # 8K/-25dBm/01mW: frag2 only = 1
        # 8K/-30dBm/00mW: frag2 only = 1
        # 8K/-30dBm/01mW: frag2 only = 1
        assert len(index) == 8
        assert len(index[(6, 25, 0)]) == 2  # 两个片段都有
        assert len(index[(6, 30, 0)]) == 1  # 仅 frag2

    def test_ignores_logs_and_discarded(self, tmp_path):
        """忽略 logs/ 和 discarded/ 目录"""
        frag = tmp_path / "frag"
        (frag / "6K" / "-25dBm" / "00mW").mkdir(parents=True)
        (frag / "6K" / "-25dBm" / "00mW" / "data.s2p").write_text("")
        (frag / "6K" / "logs").mkdir(parents=True)
        (frag / "6K" / "discarded").mkdir(parents=True)
        # 在 logs/ 和 discarded/ 下不应被扫描
        (frag / "6K" / "logs" / "ignored.s2p").write_text("")

        index = em.scan_fragments([frag])
        assert len(index) == 1
        assert (6, 25, 0) in index

    def test_empty_input_returns_empty_index(self):
        """空输入列表返回空索引"""
        index = em.scan_fragments([])
        assert index == {}

    def test_non_existent_dir_skipped(self, tmp_path):
        """不存在的目录被跳过"""
        frag = tmp_path / "exists"
        (frag / "6K" / "-25dBm" / "00mW").mkdir(parents=True)
        (frag / "6K" / "-25dBm" / "00mW" / "d.s2p").write_text("")
        non_exist = tmp_path / "nope"

        index = em.scan_fragments([frag, non_exist])
        assert len(index) == 1
```

- [ ] **Step 2: Run test to verify it fails (import error)**

```bash
cd D:\YBCO\VNAMeas\Data_process && python -m pytest tests/test_experiment_merger.py -x -q --tb=short
```
Expected: FAIL with `ModuleNotFoundError: No module named 'experiment_merger'`

- [ ] **Step 3: 实现 dataclasses + _parse_* helpers + scan_fragments**

```python
# Data_process/experiment_merger.py
# -*- coding: utf-8 -*-
"""
实验数据碎片合并引擎。

将多次拆分运行的温度扫描数据合并为统一扁平目录。
"""

import argparse
import os
import re
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass
class FileEntry:
    """单个 S2P 文件的元数据"""
    path: Path           # S2P 文件完整路径
    fragment_dir: Path   # 所属碎片文件夹根目录
    temp: int            # 温度 (K)
    vna_power: int       # VNA 功率 (正值, 如 25 表示 -25dBm)
    laser_power: int     # 激光功率 (mW)


# (temp, vna_power, laser_power) → [FileEntry, ...]
FragmentIndex = Dict[Tuple[int, int, int], List[FileEntry]]


def _parse_temp(dirname: str) -> int | None:
    """从目录名解析温度，如 '6K' → 6, '10K' → 10"""
    m = re.fullmatch(r"(\d+)K", dirname)
    return int(m.group(1)) if m else None


def _parse_vna_power(dirname: str) -> int | None:
    """从目录名解析 VNA 功率（返回正值），如 '-25dBm' → 25"""
    m = re.fullmatch(r"-(\d+)dBm", dirname)
    return int(m.group(1)) if m else None


def _parse_laser_power(dirname: str) -> int | None:
    """从目录名解析激光功率，如 '00mW' → 0, '03mW' → 3"""
    m = re.fullmatch(r"(\d+)mW", dirname)
    return int(m.group(1)) if m else None


def scan_fragments(input_dirs: List[Path]) -> FragmentIndex:
    """
    扫描所有输入目录，建立 (temp, vna_power, laser_power) → [FileEntry] 索引。
    忽略 logs/、discarded/ 目录以及非 .s2p 文件。
    """
    index: FragmentIndex = defaultdict(list)

    for fragment_dir in input_dirs:
        if not fragment_dir.is_dir():
            continue
        for temp_dir in sorted(fragment_dir.iterdir()):
            if not temp_dir.is_dir():
                continue
            temp = _parse_temp(temp_dir.name)
            if temp is None:
                continue  # 跳过 logs, discarded 等非温度目录

            for vna_dir in sorted(temp_dir.iterdir()):
                if not vna_dir.is_dir():
                    continue
                vna_power = _parse_vna_power(vna_dir.name)
                if vna_power is None:
                    continue

                for laser_dir in sorted(vna_dir.iterdir()):
                    if not laser_dir.is_dir():
                        continue
                    laser_power = _parse_laser_power(laser_dir.name)
                    if laser_power is None:
                        continue

                    for s2p_file in sorted(laser_dir.glob("*.s2p")):
                        entry = FileEntry(
                            path=s2p_file,
                            fragment_dir=fragment_dir,
                            temp=temp,
                            vna_power=vna_power,
                            laser_power=laser_power,
                        )
                        index[(temp, vna_power, laser_power)].append(entry)

    return dict(index)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:\YBCO\VNAMeas\Data_process && python -m pytest tests/test_experiment_merger.py -x -q --tb=short
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add Data_process/experiment_merger.py Data_process/tests/test_experiment_merger.py
git commit -m "feat: add scan_fragments — fragment directory scanner"
```

---

### Task 3: TDD resolve_conflicts — 去重策略

**Files:**
- Modify: `Data_process/tests/test_experiment_merger.py` (add 2 tests)
- Modify: `Data_process/experiment_merger.py` (add resolve_conflicts)

- [ ] **Step 1: 添加去重测试用例**

在 `test_experiment_merger.py` 末尾追加：

```python
class TestResolveConflicts:
    """resolve_conflicts() 测试"""

    def test_most_complete_picks_larger_fragment(self, mock_two_fragments):
        """重叠温度选 S2P 总数更多的片段"""
        index = em.scan_fragments(mock_two_fragments)
        plan = em.resolve_conflicts(index, strategy="most_complete")

        # 6K: frag1 有 2 s2p, frag2 有 4 s2p → 应选 frag2
        for key in [(6, 25, 0), (6, 25, 1)]:
            assert plan.mapping[key].fragment_dir == mock_two_fragments[1]

        # 8K/-25dBm/00mW: frag1 有 1 s2p(全在8K), frag2 有 4 s2p → 应选 frag2
        assert plan.mapping[(8, 25, 0)].fragment_dir == mock_two_fragments[1]

        # 确认冲突被记录
        overlapping_keys = {(6, 25, 0), (6, 25, 1), (8, 25, 0)}
        assert set(plan.conflicts) == overlapping_keys

    def test_single_fragment_no_conflicts(self, tmp_path):
        """单一片段无冲突"""
        frag = tmp_path / "frag"
        (frag / "6K" / "-25dBm" / "00mW").mkdir(parents=True)
        (frag / "6K" / "-25dBm" / "00mW" / "d.s2p").write_text("")

        index = em.scan_fragments([frag])
        plan = em.resolve_conflicts(index, strategy="most_complete")

        assert len(plan.conflicts) == 0
        assert len(plan.mapping) == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd D:\YBCO\VNAMeas\Data_process && python -m pytest tests/test_experiment_merger.py::TestResolveConflicts -x -q --tb=short
```
Expected: FAIL with `AttributeError: module 'experiment_merger' has no attribute 'resolve_conflicts'`

- [ ] **Step 3: 实现 resolve_conflicts**

在 `experiment_merger.py` 的 `scan_fragments` 之后追加：

```python
@dataclass
class MergePlan:
    """合并计划：每个测量组合的最终文件选择 + 冲突记录"""
    mapping: Dict[Tuple[int, int, int], FileEntry]
    conflicts: List[Tuple[int, int, int]]  # 存在多版本冲突的组合键


def resolve_conflicts(index: FragmentIndex, strategy: str = "most_complete") -> MergePlan:
    """
    按策略去重。

    most_complete 策略：
    1. 唯一版本 → 直接选用
    2. 多版本 → 比较所在温度下各片段的 S2P 总数，选最多的
    3. 总数相同 → 选片段文件夹修改时间最新的
    """
    mapping: Dict[Tuple[int, int, int], FileEntry] = {}
    conflicts: List[Tuple[int, int, int]] = []

    # 预计算每个片段在每个温度的 S2P 总数
    fragment_temp_counts: Dict[Tuple[Path, int], int] = defaultdict(int)
    for entries in index.values():
        for entry in entries:
            fragment_temp_counts[(entry.fragment_dir, entry.temp)] += 1

    for key, entries in sorted(index.items()):
        if len(entries) == 1:
            mapping[key] = entries[0]
        else:
            conflicts.append(key)
            if strategy == "most_complete":
                # 按 (所在温度S2P总数降序, 片段修改时间降序) 排序取最大值
                def _sort_key(e: FileEntry) -> Tuple[int, float]:
                    count = fragment_temp_counts.get((e.fragment_dir, e.temp), 0)
                    mtime = e.fragment_dir.stat().st_mtime
                    return (count, mtime)
                mapping[key] = max(entries, key=_sort_key)
            else:
                raise ValueError(f"未知去重策略: {strategy}")

    return MergePlan(mapping=mapping, conflicts=conflicts)
```

在文件顶部的 `from dataclasses import dataclass` 之后不需要额外导入（`defaultdict` 和 `Tuple` 已在前面导入）。

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:\YBCO\VNAMeas\Data_process && python -m pytest tests/test_experiment_merger.py -x -q --tb=short
```
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add Data_process/experiment_merger.py Data_process/tests/test_experiment_merger.py
git commit -m "feat: add resolve_conflicts — most_complete dedup strategy"
```

---

### Task 4: TDD execute_merge — 合并执行

**Files:**
- Modify: `Data_process/tests/test_experiment_merger.py` (add 4 tests)
- Modify: `Data_process/experiment_merger.py` (add execute_merge + MergeReport)

- [ ] **Step 1: 添加合并执行测试用例**

在 `test_experiment_merger.py` 末尾追加：

```python
class TestExecuteMerge:
    """execute_merge() 测试"""

    @pytest.fixture
    def simple_plan(self, tmp_path):
        """创建一个简单合并计划：单个文件"""
        frag = tmp_path / "frag"
        src_dir = frag / "6K" / "-25dBm" / "00mW"
        src_dir.mkdir(parents=True)
        src_file = src_dir / "data.s2p"
        src_file.write_text("test data")
        return em.MergePlan(
            mapping={
                (6, 25, 0): em.FileEntry(
                    path=src_file, fragment_dir=frag,
                    temp=6, vna_power=25, laser_power=0,
                )
            },
            conflicts=[],
        )

    def test_creates_output_structure(self, simple_plan, tmp_path):
        """合并创建正确的输出目录结构和文件"""
        output_dir = tmp_path / "merged"
        report = em.execute_merge(simple_plan, output_dir)

        expected = output_dir / "6K" / "-25dBm" / "00mW" / "data.s2p"
        assert expected.exists()
        assert expected.read_text() == "test data"
        assert report.total_merged == 1
        assert report.conflicts_resolved == 0

    def test_dry_run_no_files_created(self, simple_plan, tmp_path):
        """dry_run 模式不创建任何文件"""
        output_dir = tmp_path / "merged"
        report = em.execute_merge(simple_plan, output_dir, dry_run=True)

        assert not output_dir.exists()
        assert report.skipped == 1

    def test_copy_fallback_when_hardlink_fails(self, simple_plan, tmp_path, monkeypatch):
        """硬链接失败时 fallback 到复制"""
        # 强制 os.link 失败
        def _fail_link(*args, **kwargs):
            raise OSError("cross-device link")
        monkeypatch.setattr(os, "link", _fail_link)

        output_dir = tmp_path / "merged"
        report = em.execute_merge(simple_plan, output_dir, use_hardlink=True)

        assert report.copies == 1
        assert report.hardlinks == 0
        expected = output_dir / "6K" / "-25dBm" / "00mW" / "data.s2p"
        assert expected.exists()

    def test_use_copy_directly(self, simple_plan, tmp_path):
        """--copy 模式直接复制"""
        output_dir = tmp_path / "merged"
        report = em.execute_merge(simple_plan, output_dir, use_hardlink=False)

        assert report.copies == 1
        assert report.hardlinks == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd D:\YBCO\VNAMeas\Data_process && python -m pytest tests/test_experiment_merger.py::TestExecuteMerge -x -q --tb=short
```
Expected: FAIL

- [ ] **Step 3: 实现 execute_merge + MergeReport**

在 `experiment_merger.py` 的 `resolve_conflicts` 之后追加：

```python
@dataclass
class MergeReport:
    """合并执行报告"""
    total_merged: int = 0
    conflicts_resolved: int = 0
    hardlinks: int = 0
    copies: int = 0
    skipped: int = 0


def execute_merge(
    plan: MergePlan,
    output_dir: Path,
    use_hardlink: bool = True,
    dry_run: bool = False,
) -> MergeReport:
    """
    执行合并计划。

    默认使用 os.link (硬链接) 节省空间，失败时 fallback 到 shutil.copy2。
    dry_run=True 时仅打印计划不创建文件。
    """
    report = MergeReport(
        total_merged=len(plan.mapping),
        conflicts_resolved=len(plan.conflicts),
    )

    for (temp, vna_power, laser_power), entry in sorted(plan.mapping.items()):
        dst_dir = output_dir / f"{temp}K" / f"-{vna_power}dBm" / f"{laser_power:02d}mW"
        dst = dst_dir / entry.path.name

        if dry_run:
            report.skipped += 1
            print(f"[DRY-RUN] {entry.path} → {dst}")
            continue

        dst_dir.mkdir(parents=True, exist_ok=True)

        if dst.exists():
            report.skipped += 1
            continue

        if use_hardlink:
            try:
                os.link(entry.path, dst)
                report.hardlinks += 1
            except OSError:
                shutil.copy2(entry.path, dst)
                report.copies += 1
        else:
            shutil.copy2(entry.path, dst)
            report.copies += 1

    return report
```

- [ ] **Step 4: Run all merger tests**

```bash
cd D:\YBCO\VNAMeas\Data_process && python -m pytest tests/test_experiment_merger.py -x -q --tb=short
```
Expected: 10 PASSED

- [ ] **Step 5: Commit**

```bash
git add Data_process/experiment_merger.py Data_process/tests/test_experiment_merger.py
git commit -m "feat: add execute_merge — hardlink merge executor"
```

---

### Task 5: experiment_merger CLI + 集成测试

**Files:**
- Modify: `Data_process/experiment_merger.py` (add main() + argparse)
- Modify: `Data_process/tests/test_experiment_merger.py` (add CLI integration test)

- [ ] **Step 1: 添加 CLI 集成测试**

在 `test_experiment_merger.py` 末尾追加：

```python
class TestCLI:
    """命令行端到端测试"""

    def test_dry_run_end_to_end(self, mock_two_fragments, tmp_path, capsys):
        """--dry-run 输出合并计划但不创建文件"""
        output_dir = tmp_path / "merged"
        args = [
            "--input", str(mock_two_fragments[0]), str(mock_two_fragments[1]),
            "--output", str(output_dir),
            "--dry-run",
        ]
        # 通过 sys.argv 模拟 CLI 调用
        import sys as _sys
        _sys.argv = ["experiment_merger.py"] + args

        # 把 main() 包装为可测试形式
        from argparse import Namespace
        ns = Namespace(
            input=mock_two_fragments,
            output=output_dir,
            strategy="most_complete",
            copy=False,
            dry_run=True,
        )
        index = em.scan_fragments(ns.input)
        plan = em.resolve_conflicts(index, ns.strategy)
        report = em.execute_merge(plan, ns.output,
                                  use_hardlink=not ns.copy,
                                  dry_run=ns.dry_run)

        assert not output_dir.exists()
        assert report.total_merged > 0
        captured = capsys.readouterr()
        # dry-run 模式应该打印了计划内容（来自 execute_merge 的 print）
        # 验证确实没有文件创建即可
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd D:\YBCO\VNAMeas\Data_process && python -m pytest tests/test_experiment_merger.py::TestCLI -x -q --tb=short
```
Expected: PASS (the test uses existing functions without CLI main())

Wait — this test uses existing functions. Let me rewrite it to actually test the CLI via subprocess, OR I can just verify that the test passes as-is since it tests the end-to-end flow without CLI parsing.

Actually, let me restructure: the test should call the functions directly (unit-test style), and I should test the argparse separately. Let me keep the integration test as a function-level test and add a separate argparse test.

Let me revise:

```python
class TestCLI:
    """集成测试 (函数级别)"""

    def test_full_pipeline_dry_run(self, mock_two_fragments, tmp_path):
        """完整管线 dry-run: scan → resolve → execute(dry)"""
        output_dir = tmp_path / "merged"
        index = em.scan_fragments(mock_two_fragments)
        plan = em.resolve_conflicts(index, "most_complete")
        report = em.execute_merge(plan, output_dir, dry_run=True)

        assert not output_dir.exists()
        assert report.total_merged == 8
        assert len(plan.conflicts) == 3  # (6,25,0), (6,25,1), (8,25,0)

    def test_full_pipeline_real_merge(self, mock_two_fragments, tmp_path):
        """完整管线真实合并 → 验证输出结构"""
        output_dir = tmp_path / "merged"
        index = em.scan_fragments(mock_two_fragments)
        plan = em.resolve_conflicts(index, "most_complete")
        report = em.execute_merge(plan, output_dir)

        assert output_dir.is_dir()
        assert (output_dir / "6K" / "-25dBm" / "00mW").is_dir()
        assert report.total_merged == 8
        # 所有选中的文件应来自 frag2 (更完整)
        assert report.copies + report.hardlinks == 8
```

This is cleaner — no sys.argv manipulation needed.

Actually, I realize I should also add the argparse main() function. But that's hard to test without subprocess. Let me just write the main() and not add a separate test for it — instead verify manually.

- [ ] **Step 1: 添加集成测试**

在 `test_experiment_merger.py` 末尾追加：

```python
class TestPipeline:
    """集成测试：scan → resolve → execute 完整管线"""

    def test_dry_run_pipeline(self, mock_two_fragments, tmp_path):
        """dry-run 完整管线：不创建文件"""
        output_dir = tmp_path / "merged"
        index = em.scan_fragments(mock_two_fragments)
        plan = em.resolve_conflicts(index, "most_complete")
        report = em.execute_merge(plan, output_dir, dry_run=True)

        assert not output_dir.exists()
        assert report.total_merged == 8
        assert len(plan.conflicts) == 3

    def test_real_merge_pipeline(self, mock_two_fragments, tmp_path):
        """真实合并：创建正确的输出结构"""
        output_dir = tmp_path / "merged"
        index = em.scan_fragments(mock_two_fragments)
        plan = em.resolve_conflicts(index, "most_complete")
        report = em.execute_merge(plan, output_dir)

        assert output_dir.is_dir()
        assert (output_dir / "6K" / "-25dBm" / "00mW").is_dir()
        assert report.total_merged == 8
        # 验证合并的文件内容可读
        s2p_files = list(output_dir.rglob("*.s2p"))
        assert len(s2p_files) == 8
```

- [ ] **Step 2: Run test to verify it fails (no new code needed, should PASS)**

```bash
cd D:\YBCO\VNAMeas\Data_process && python -m pytest tests/test_experiment_merger.py -x -q --tb=short
```
Expected: 12 PASSED

- [ ] **Step 3: 添加 CLI main() 函数**

在 `experiment_merger.py` 末尾追加：

```python
def main():
    """命令行入口：实验数据碎片合并引擎"""
    parser = argparse.ArgumentParser(
        description="合并多次拆分运行的温度扫描数据")
    parser.add_argument("--input", nargs="+", type=Path, required=True,
                        help="碎片文件夹路径列表")
    parser.add_argument("--output", type=Path, required=True,
                        help="合并输出目录")
    parser.add_argument("--strategy", choices=["most_complete"],
                        default="most_complete",
                        help="去重策略 (默认: most_complete)")
    parser.add_argument("--copy", action="store_true",
                        help="强制复制 (默认使用硬链接节省空间)")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅显示合并计划，不创建文件")

    args = parser.parse_args()

    # 验证输入目录存在
    for d in args.input:
        if not d.is_dir():
            print(f"错误: 输入目录不存在: {d}", file=sys.stderr)
            sys.exit(1)

    print(f"扫描 {len(args.input)} 个碎片文件夹...")
    index = scan_fragments(args.input)
    n_files = sum(len(v) for v in index.values())
    print(f"  找到 {n_files} 个 S2P 文件，{len(index)} 个唯一 (T, Pr, Plaser) 组合")

    print(f"去重 (策略: {args.strategy})...")
    plan = resolve_conflicts(index, args.strategy)
    print(f"  冲突: {len(plan.conflicts)} 个组合有多个版本")

    print(f"合并到 {args.output}..." if not args.dry_run else "合并计划 (DRY-RUN):")
    report = execute_merge(plan, args.output,
                           use_hardlink=not args.copy,
                           dry_run=args.dry_run)

    if args.dry_run:
        print(f"\n=== 合并计划 ===")
    else:
        print(f"\n=== 合并完成 ===")
        print(f"  硬链接: {report.hardlinks}")
        print(f"  复制:   {report.copies}")
    print(f"  总文件: {report.total_merged}")
    print(f"  冲突:   {report.conflicts_resolved}")
    if report.skipped:
        print(f"  跳过:   {report.skipped}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 验证 CLI 帮助信息可用**

```bash
cd D:\YBCO\VNAMeas\Data_process && python experiment_merger.py --help
```
Expected: 输出 argparse 帮助文本

- [ ] **Step 5: Run all tests**

```bash
cd D:\YBCO\VNAMeas\Data_process && python -m pytest tests/test_experiment_merger.py -x -q --tb=short
```
Expected: 12 PASSED

- [ ] **Step 6: Commit**

```bash
git add Data_process/experiment_merger.py Data_process/tests/test_experiment_merger.py
git commit -m "feat: add experiment_merger CLI main + integration tests"
```

---

### Task 6: TDD build_completeness_matrix — 完整性矩阵

**Files:**
- Create: `Data_process/tests/test_completeness_checker.py` (fixture + 3 tests)
- Create: `Data_process/completeness_checker.py` (build_completeness_matrix)

- [ ] **Step 1: 写测试 fixture + 测试用例**

```python
# Data_process/tests/test_completeness_checker.py
# -*- coding: utf-8 -*-
"""completeness_checker.py 单元测试"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import numpy as np
from pathlib import Path
import completeness_checker as cc


@pytest.fixture
def mock_merged_dir(tmp_path):
    """
    创建模拟合并目录：
    6K, 8K, 10K × -25dBm, -30dBm × 00mW, 01mW, 03mW
    故意缺失:
      - 8K/-30dBm/01mW (isolated — 周围完整)
      - 10K/-30dBm/00mW, 01mW, 03mW (连续3个 → block)
    """
    data = tmp_path
    for temp, vna, laser in [
        (6, 25, 0), (6, 25, 1), (6, 25, 3),
        (6, 30, 0), (6, 30, 1), (6, 30, 3),
        (8, 25, 0), (8, 25, 1), (8, 25, 3),
        # 故意缺失: 8K/-30dBm/01mW
        (8, 30, 0), (8, 30, 3),
        (10, 25, 0), (10, 25, 1), (10, 25, 3),
        # 故意缺失全部: 10K/-30dBm/*
    ]:
        d = data / f"{temp}K" / f"-{vna}dBm" / f"{laser:02d}mW"
        d.mkdir(parents=True)
        (d / "data.s2p").write_text("")
    return data


class TestBuildCompletenessMatrix:
    """build_completeness_matrix() 测试"""

    def test_correct_shape(self, mock_merged_dir):
        """返回正确形状的 3D 布尔数组"""
        temps = [6, 8, 10]
        vna_powers = [25, 30]
        laser_powers = [0, 1, 3]
        matrix = cc.build_completeness_matrix(
            mock_merged_dir, temps, vna_powers, laser_powers)

        assert matrix.shape == (3, 2, 3)
        assert matrix.dtype == bool

    def test_found_and_missing_cells(self, mock_merged_dir):
        """正确标记存在和缺失的格子"""
        temps = [6, 8, 10]
        vna_powers = [25, 30]
        laser_powers = [0, 1, 3]
        matrix = cc.build_completeness_matrix(
            mock_merged_dir, temps, vna_powers, laser_powers)

        # 6K 全部完整
        assert matrix[0, :, :].all()
        # 8K/-30dBm/01mW 缺失
        assert matrix[1, 1, 0]     # 8K/-30dBm/00mW ✓
        assert not matrix[1, 1, 1] # 8K/-30dBm/01mW ✗
        assert matrix[1, 1, 2]     # 8K/-30dBm/03mW ✓
        # 10K/-30dBm 全部缺失
        assert matrix[2, 0, :].all()   # 10K/-25dBm 完整
        assert not matrix[2, 1, :].any()  # 10K/-30dBm 全缺

    def test_total_found_count(self, mock_merged_dir):
        """sum(matrix) 等于实际文件数"""
        temps = [6, 8, 10]
        vna_powers = [25, 30]
        laser_powers = [0, 1, 3]
        matrix = cc.build_completeness_matrix(
            mock_merged_dir, temps, vna_powers, laser_powers)

        n_expected = 3 * 2 * 3  # 18
        assert int(matrix.sum()) == 18 - 1 - 3  # 14 (缺4个)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd D:\YBCO\VNAMeas\Data_process && python -m pytest tests/test_completeness_checker.py -x -q --tb=short
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现 build_completeness_matrix**

```python
# Data_process/completeness_checker.py
# -*- coding: utf-8 -*-
"""
实验数据完整性检查器。

分析合并后的数据目录，生成完整性报告和补测建议清单。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict
import numpy as np


def build_completeness_matrix(
    data_dir: Path,
    temps: List[int],
    vna_powers: List[int],    # 正值, 如 25 表示 -25dBm
    laser_powers: List[int],
) -> np.ndarray:
    """
    构建完整性矩阵。

    遍历 data_dir/{temp}K/-{vna}dBm/{laser:02d}mW/，
    检查是否存在至少一个 .s2p 文件。
    返回 shape (len(temps), len(vna_powers), len(laser_powers)) 的 bool 数组。
    """
    n_t, n_v, n_l = len(temps), len(vna_powers), len(laser_powers)
    matrix = np.zeros((n_t, n_v, n_l), dtype=bool)

    for ti, temp in enumerate(temps):
        temp_dir = data_dir / f"{temp}K"
        if not temp_dir.is_dir():
            continue
        for vi, vna in enumerate(vna_powers):
            vna_dir = temp_dir / f"-{vna}dBm"
            if not vna_dir.is_dir():
                continue
            for li, laser in enumerate(laser_powers):
                laser_dir = vna_dir / f"{laser:02d}mW"
                if laser_dir.is_dir() and list(laser_dir.glob("*.s2p")):
                    matrix[ti, vi, li] = True

    return matrix
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:\YBCO\VNAMeas\Data_process && python -m pytest tests/test_completeness_checker.py -x -q --tb=short
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add Data_process/completeness_checker.py Data_process/tests/test_completeness_checker.py
git commit -m "feat: add build_completeness_matrix — 3D boolean matrix"
```

---

### Task 7: TDD diagnose_missing — 缺失分类

**Files:**
- Modify: `Data_process/tests/test_completeness_checker.py` (add 3 tests)
- Modify: `Data_process/completeness_checker.py` (add diagnose_missing)

- [ ] **Step 1: 添加缺失分类测试**

在 `test_completeness_checker.py` 末尾追加：

```python
class TestDiagnoseMissing:
    """diagnose_missing() 测试"""

    def test_classifies_isolated_edge_block(self, mock_merged_dir):
        """分类: isolated / edge / block"""
        temps = [6, 8, 10]
        vna_powers = [25, 30]
        laser_powers = [0, 1, 3]
        matrix = cc.build_completeness_matrix(
            mock_merged_dir, temps, vna_powers, laser_powers)
        missing = cc.diagnose_missing(matrix, temps, vna_powers, laser_powers)

        # 8K/-30dBm/01mW → isolated
        isolated = [m for m in missing if m.category == "isolated"]
        assert len(isolated) == 1
        assert isolated[0].temp == 8
        assert isolated[0].vna_power == 30
        assert isolated[0].laser_power == 1

        # 10K/-30dBm/* → block (连续3个)
        blocks = [m for m in missing if m.category == "block"]
        assert len(blocks) == 3

    def test_edge_temperature_classified_as_edge(self, tmp_path):
        """温度边缘缺失标记为 edge"""
        data = tmp_path
        # 只建 8K 的数据，6K 和 10K 完全缺失 → edge
        for vna in [25, 30]:
            for laser in [0, 1]:
                d = data / "8K" / f"-{vna}dBm" / f"{laser:02d}mW"
                d.mkdir(parents=True)
                (d / "d.s2p").write_text("")

        temps = [6, 8, 10]
        vna_powers = [25, 30]
        laser_powers = [0, 1]
        matrix = cc.build_completeness_matrix(data, temps, vna_powers, laser_powers)
        missing = cc.diagnose_missing(matrix, temps, vna_powers, laser_powers)

        edges = [m for m in missing if m.category == "edge"]
        # 6K 和 10K 缺失的点应全标记为 edge
        for m in edges:
            assert m.temp in [6, 10]

    def test_complete_dataset_returns_empty(self, tmp_path):
        """完全完整的数据返回空缺失列表"""
        for temp in [6, 8]:
            for vna in [25, 30]:
                for laser in [0, 1]:
                    d = tmp_path / f"{temp}K" / f"-{vna}dBm" / f"{laser:02d}mW"
                    d.mkdir(parents=True)
                    (d / "d.s2p").write_text("")

        temps = [6, 8]
        vna_powers = [25, 30]
        laser_powers = [0, 1]
        matrix = cc.build_completeness_matrix(tmp_path, temps, vna_powers, laser_powers)
        missing = cc.diagnose_missing(matrix, temps, vna_powers, laser_powers)

        assert len(missing) == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd D:\YBCO\VNAMeas\Data_process && python -m pytest tests/test_completeness_checker.py::TestDiagnoseMissing -x -q --tb=short
```
Expected: FAIL

- [ ] **Step 3: 实现 diagnose_missing**

在 `completeness_checker.py` 末尾追加：

```python
@dataclass
class MissingPoint:
    """单个缺失数据点"""
    temp: int
    vna_power: int       # 正值, 如 25 表示 -25dBm
    laser_power: int
    category: str        # "isolated" | "edge" | "block"


def _is_edge(ti: int, num_temps: int) -> bool:
    """温度索引是否在边缘 (首/尾)"""
    return ti == 0 or ti == num_temps - 1


def diagnose_missing(
    matrix: np.ndarray,
    temps: List[int],
    vna_powers: List[int],
    laser_powers: List[int],
) -> List[MissingPoint]:
    """
    分类缺失原因:
    - "block"    — 同一 (vna, laser) 连续缺失 ≥3 个温度
    - "edge"     — 温度边缘缺失
    - "isolated" — 孤立偶发缺失
    """
    n_t, n_v, n_l = matrix.shape
    missing: List[MissingPoint] = []

    for vi in range(n_v):
        for li in range(n_l):
            # 找出该 (vna, laser) 下所有缺失的温度索引
            missing_tis = [ti for ti in range(n_t) if not matrix[ti, vi, li]]
            if not missing_tis:
                continue

            # 分组连续缺失
            groups = []
            group = [missing_tis[0]]
            for i in range(1, len(missing_tis)):
                if missing_tis[i] == missing_tis[i - 1] + 1:
                    group.append(missing_tis[i])
                else:
                    groups.append(group)
                    group = [missing_tis[i]]
            groups.append(group)

            for g in groups:
                if len(g) >= 3:
                    category = "block"
                elif _is_edge(g[0], n_t):
                    category = "edge"
                else:
                    category = "isolated"

                for ti in g:
                    missing.append(MissingPoint(
                        temp=temps[ti],
                        vna_power=vna_powers[vi],
                        laser_power=laser_powers[li],
                        category=category,
                    ))

    return missing
```

- [ ] **Step 4: Run all tests**

```bash
cd D:\YBCO\VNAMeas\Data_process && python -m pytest tests/test_completeness_checker.py -x -q --tb=short
```
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add Data_process/completeness_checker.py Data_process/tests/test_completeness_checker.py
git commit -m "feat: add diagnose_missing — classify missing by pattern"
```

---

### Task 8: TDD report + CLI — 补测清单 + 格式化输出

**Files:**
- Modify: `Data_process/tests/test_completeness_checker.py` (add 4 tests)
- Modify: `Data_process/completeness_checker.py` (add report + CLI)

- [ ] **Step 1: 添加 report/格式化 CLI 测试**

在 `test_completeness_checker.py` 末尾追加：

```python
class TestReport:
    """报告生成和格式化测试"""

    def test_generate_retest_plan(self, mock_merged_dir):
        """补测清单按温度排序，列出所有缺失组合"""
        temps = [6, 8, 10]
        vna_powers = [25, 30]
        laser_powers = [0, 1, 3]
        matrix = cc.build_completeness_matrix(
            mock_merged_dir, temps, vna_powers, laser_powers)
        missing = cc.diagnose_missing(matrix, temps, vna_powers, laser_powers)
        report = cc.build_report(matrix, temps, vna_powers, laser_powers, missing)

        assert report.expected == 18
        assert report.found == 14
        assert report.missing == 4
        assert report.missing_breakdown == {"isolated": 1, "edge": 0, "block": 3}
        # 补测计划
        rp = report.retest_plan
        assert rp.temps == [8, 10]
        assert rp.vna_powers == [-30]
        assert len(rp.missing_combos) == 4

    def test_json_output_contains_all_sections(self, mock_merged_dir):
        """JSON 输出包含 summary, retest_plan, details"""
        temps = [6, 8, 10]
        vna_powers = [25, 30]
        laser_powers = [0, 1, 3]
        matrix = cc.build_completeness_matrix(
            mock_merged_dir, temps, vna_powers, laser_powers)
        missing = cc.diagnose_missing(matrix, temps, vna_powers, laser_powers)
        report = cc.build_report(matrix, temps, vna_powers, laser_powers, missing)

        output = cc.format_report_json(report)
        import json
        data = json.loads(output)

        assert "summary" in data
        assert "retest_plan" in data
        assert "details" in data
        assert data["summary"]["expected"] == 18

    def test_table_output_includes_headers(self, mock_merged_dir):
        """table 输出包含标题行"""
        temps = [6, 8, 10]
        vna_powers = [25, 30]
        laser_powers = [0, 1, 3]
        matrix = cc.build_completeness_matrix(
            mock_merged_dir, temps, vna_powers, laser_powers)
        missing = cc.diagnose_missing(matrix, temps, vna_powers, laser_powers)
        report = cc.build_report(matrix, temps, vna_powers, laser_powers, missing)

        output = cc.format_report_table(report, temps, vna_powers, laser_powers, matrix)

        assert "Temperature" in output
        assert "VNA Power" in output
        assert "Summary:" in output
        assert "Missing:" in output

    def test_complete_dataset_table(self, tmp_path):
        """完全完整的数据集表格输出不包含任何 ✗"""
        for temp in [6, 8]:
            for vna in [25]:
                for laser in [0]:
                    d = tmp_path / f"{temp}K" / f"-{vna}dBm" / f"{laser:02d}mW"
                    d.mkdir(parents=True)
                    (d / "d.s2p").write_text("")

        temps = [6, 8]
        vna_powers = [25]
        laser_powers = [0]
        matrix = cc.build_completeness_matrix(tmp_path, temps, vna_powers, laser_powers)
        missing = cc.diagnose_missing(matrix, temps, vna_powers, laser_powers)
        report = cc.build_report(matrix, temps, vna_powers, laser_powers, missing)

        output = cc.format_report_table(report, temps, vna_powers, laser_powers, matrix)
        assert "✗" not in output
        assert "0 missing" in output
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd D:\YBCO\VNAMeas\Data_process && python -m pytest tests/test_completeness_checker.py::TestReport -x -q --tb=short
```
Expected: FAIL

- [ ] **Step 3: 实现 report 数据类 + 格式化函数 + CLI**

在 `completeness_checker.py` 末尾追加：

```python
@dataclass
class RetestPlan:
    """补测计划"""
    temps: List[int]
    vna_powers: List[int]       # 负值 (原始 VNA 功率)
    laser_powers: List[int]
    missing_combos: List[dict]


@dataclass
class CompletenessReport:
    """完整性分析报告"""
    expected: int
    found: int
    missing: int
    missing_breakdown: Dict[str, int]
    details: List[dict]
    retest_plan: RetestPlan


def generate_retest_plan(missing: List[MissingPoint]) -> RetestPlan:
    """从缺失列表生成补测计划，按温度→VNA功率→激光功率排序"""
    if not missing:
        return RetestPlan(temps=[], vna_powers=[], laser_powers=[], missing_combos=[])

    temps = sorted(set(m.temp for m in missing))
    vna_powers_pos = sorted(set(m.vna_power for m in missing))
    laser_powers = sorted(set(m.laser_power for m in missing))

    missing_combos = [
        {"temp": m.temp, "vna_power": -m.vna_power, "laser_power": m.laser_power}
        for m in sorted(missing, key=lambda m: (m.temp, m.vna_power, m.laser_power))
    ]

    return RetestPlan(
        temps=temps,
        vna_powers=[-v for v in vna_powers_pos],  # 转负值
        laser_powers=laser_powers,
        missing_combos=missing_combos,
    )


def build_report(
    matrix: np.ndarray,
    temps: List[int],
    vna_powers: List[int],
    laser_powers: List[int],
    missing: List[MissingPoint],
) -> CompletenessReport:
    """组装完整报告"""
    n_expected = len(temps) * len(vna_powers) * len(laser_powers)
    n_found = int(matrix.sum())

    breakdown: Dict[str, int] = {"isolated": 0, "edge": 0, "block": 0}
    for m in missing:
        breakdown[m.category] += 1

    details = [
        {
            "temp": m.temp,
            "vna_power": -m.vna_power,
            "laser_power": m.laser_power,
            "status": "missing",
            "category": m.category,
        }
        for m in sorted(missing, key=lambda m: (m.temp, m.vna_power, m.laser_power))
    ]

    return CompletenessReport(
        expected=n_expected,
        found=n_found,
        missing=n_expected - n_found,
        missing_breakdown=breakdown,
        details=details,
        retest_plan=generate_retest_plan(missing),
    )


def format_report_json(report: CompletenessReport) -> str:
    """JSON 格式输出"""
    import json
    return json.dumps({
        "summary": {
            "expected": report.expected,
            "found": report.found,
            "missing": report.missing,
            "missing_breakdown": report.missing_breakdown,
        },
        "retest_plan": {
            "temps": report.retest_plan.temps,
            "vna_powers": report.retest_plan.vna_powers,
            "laser_powers": report.retest_plan.laser_powers,
            "missing_combos": report.retest_plan.missing_combos,
        },
        "details": report.details,
    }, indent=2, ensure_ascii=False)


def format_report_table(
    report: CompletenessReport,
    temps: List[int],
    vna_powers: List[int],
    laser_powers: List[int],
    matrix: np.ndarray,
) -> str:
    """表格格式输出"""
    lines = []
    lines.append(f"{'Temperature':<13} {'VNA Power':<11} {'Laser Power':<13} Status")
    lines.append("-" * 58)

    for ti, temp in enumerate(temps):
        for vi, vna in enumerate(vna_powers):
            for li, laser in enumerate(laser_powers):
                if matrix[ti, vi, li]:
                    status = "✓"
                else:
                    cat = next(
                        (d["category"] for d in report.details
                         if d["temp"] == temp and d["vna_power"] == -vna
                         and d["laser_power"] == laser),
                        "unknown"
                    )
                    status = f"✗ (missing — {cat})"
                lines.append(
                    f"{temp}K           -{vna}dBm      {laser:02d}mW         {status}"
                )

    lines.append("-" * 58)
    lines.append(
        f"Summary: {report.expected} expected, {report.found} found, "
        f"{report.missing} missing"
    )
    cats = ", ".join(f"{k}: {v}" for k, v in report.missing_breakdown.items())
    lines.append(f"Missing: {cats}")
    if report.retest_plan.temps:
        lines.append(
            f"Suggested retest: {len(report.retest_plan.temps)} temperature points"
        )

    return "\n".join(lines)


def main():
    """命令行入口：实验数据完整性检查器"""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="分析合并后数据目录的完整性，生成补测建议")
    parser.add_argument("--input", type=Path, required=True,
                        help="合并后的数据目录")
    parser.add_argument("--temps-start", type=int, required=True,
                        help="起始温度 (K)")
    parser.add_argument("--temps-stop", type=int, required=True,
                        help="终止温度 (K)")
    parser.add_argument("--temps-step", type=int, required=True,
                        help="温度步长 (K)")
    parser.add_argument("--vna-powers", type=str, default="-25,-30,-45",
                        help="VNA 功率列表 (默认: -25,-30,-45)")
    parser.add_argument("--laser-powers", type=str, default="0,1,3,5,7,9",
                        help="激光功率列表 (默认: 0,1,3,5,7,9)")
    parser.add_argument("--format", choices=["json", "table"],
                        default="table", help="输出格式 (默认: table)")
    parser.add_argument("--output", type=Path,
                        help="输出文件路径 (默认: stdout)")

    args = parser.parse_args()

    temps = list(range(args.temps_start, args.temps_stop + 1, args.temps_step))
    # 存储正值 (内部使用)
    vna_powers = [abs(int(x.strip())) for x in args.vna_powers.split(",")]
    laser_powers = [int(x.strip()) for x in args.laser_powers.split(",")]

    if not args.input.is_dir():
        print(f"错误: 目录不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    matrix = build_completeness_matrix(args.input, temps, vna_powers, laser_powers)
    missing = diagnose_missing(matrix, temps, vna_powers, laser_powers)
    report = build_report(matrix, temps, vna_powers, laser_powers, missing)

    if args.format == "json":
        output = format_report_json(report)
    else:
        output = format_report_table(report, temps, vna_powers, laser_powers, matrix)

    if args.output:
        args.output.write_text(output, encoding="utf-8")
        print(f"报告已写入 {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run all completeness_checker tests**

```bash
cd D:\YBCO\VNAMeas\Data_process && python -m pytest tests/test_completeness_checker.py -x -q --tb=short
```
Expected: 10 PASSED

- [ ] **Step 5: 验证 CLI 帮助**

```bash
cd D:\YBCO\VNAMeas\Data_process && python completeness_checker.py --help
```
Expected: 输出 argparse 帮助文本

- [ ] **Step 6: Commit**

```bash
git add Data_process/completeness_checker.py Data_process/tests/test_completeness_checker.py
git commit -m "feat: add completeness_checker report generation + CLI"
```

---

### Task 9: 真实数据验证 — 对 accomplish 运行合并和完整性分析

**Files:**
- (不修改代码，仅运行验证)

- [ ] **Step 1: 对 accomplish 数据执行 dry-run 合并**

```bash
cd D:\YBCO\VNAMeas\Data_process && python experiment_merger.py \
    --input ../Auto_Sweep/experiment_data/accomplish/20260611_115038 \
           ../Auto_Sweep/experiment_data/accomplish/20260612_014432 \
           ../Auto_Sweep/experiment_data/accomplish/20260612_095452 \
           ../Auto_Sweep/experiment_data/accomplish/20260612_145605 \
           ../Auto_Sweep/experiment_data/accomplish/20260612_155002 \
           ../Auto_Sweep/experiment_data/accomplish/20260612_190601 \
           ../Auto_Sweep/experiment_data/accomplish/20260613_031259 \
           ../Auto_Sweep/experiment_data/accomplish/20260614_012513 \
    --output ../Auto_Sweep/experiment_data/merged \
    --dry-run
```

Expected: 输出合并计划，列出文件数、冲突数。

- [ ] **Step 2: 确认 dry-run 输出合理后，执行真实合并**

```bash
cd D:\YBCO\VNAMeas\Data_process && python experiment_merger.py \
    --input ../Auto_Sweep/experiment_data/accomplish/20260611_115038 \
           ../Auto_Sweep/experiment_data/accomplish/20260612_014432 \
           ../Auto_Sweep/experiment_data/accomplish/20260612_095452 \
           ../Auto_Sweep/experiment_data/accomplish/20260612_145605 \
           ../Auto_Sweep/experiment_data/accomplish/20260612_155002 \
           ../Auto_Sweep/experiment_data/accomplish/20260612_190601 \
           ../Auto_Sweep/experiment_data/accomplish/20260613_031259 \
           ../Auto_Sweep/experiment_data/accomplish/20260614_012513 \
    --output ../Auto_Sweep/experiment_data/merged
```

Expected: 合并完成，显示统计（硬链接/复制数，总文件数）。

- [ ] **Step 3: 对合并目录运行完整性分析**

```bash
cd D:\YBCO\VNAMeas\Data_process && python completeness_checker.py \
    --input ../Auto_Sweep/experiment_data/merged \
    --temps-start 6 --temps-stop 80 --temps-step 2 \
    --vna-powers=-25,-30,-45 \
    --laser-powers 0,1,3,5,7,9 \
    --format table
```

Expected: 输出完整性表格。

- [ ] **Step 4: 生成 JSON 格式补测清单**

```bash
cd D:\YBCO\VNAMeas\Data_process && python completeness_checker.py \
    --input ../Auto_Sweep/experiment_data/merged \
    --temps-start 6 --temps-stop 80 --temps-step 2 \
    --vna-powers=-25,-30,-45 \
    --laser-powers 0,1,3,5,7,9 \
    --format json \
    --output ../Auto_Sweep/experiment_data/completeness_report.json
```

Expected: 生成 JSON 报告文件。

- [ ] **Step 5: Commit (only if report files are tracked, otherwise just verify)**

No code to commit — this is a verification step.

---

### Task 10: 适配 process_data_single_pixel.py

**Files:**
- Modify: `Data_process/otherwise/process_data_single_pixel.py` (lines 102, 120-134, 141)

- [ ] **Step 1: 修改 VNA 功率默认值**

找到第 102 行附近：
```python
meas_powers = [25, 35, 45]
```
改为：
```python
meas_powers = [25, 30, 45]
```

- [ ] **Step 2: 修改温度解析 — 去掉 actual_ 中间层**

找到第 120-134 行：
```python
temp_meas_all = []
for temp in temps:
    folder_temp = os.path.join(folder0, f'{temp}K')
    folders = os.listdir(folder_temp)
    for folder in folders:
        match = re.fullmatch(r"actual_(\d+(?:\.\d+)?)K", folder)
        if match:
            temp_meas = float(match.group(1))
            temp_meas_all.append(temp_meas)
```

改为（从 S2P 文件名解析 actual 温度）：
```python
temp_meas_all = []
for temp in temps:
    path_temp = os.path.join(folder0, f'{temp}K')
    if not os.path.isdir(path_temp):
        continue
    # 从第一个可用的 S2P 文件名中解析实际温度
    # 文件名格式: YBCO_-25dBm_00mW_target_6K_actual_6.123K.s2p
    found = False
    for vna_dir in sorted(os.listdir(path_temp)):
        vna_path = os.path.join(path_temp, vna_dir)
        if not os.path.isdir(vna_path):
            continue
        for laser_dir in sorted(os.listdir(vna_path)):
            laser_path = os.path.join(vna_path, laser_dir)
            if not os.path.isdir(laser_path):
                continue
            for f in os.listdir(laser_path):
                if f.endswith('.s2p'):
                    match = re.search(r"actual_([\d.]+)K", f)
                    if match:
                        temp_meas_all.append(float(match.group(1)))
                        found = True
                    break
            if found:
                break
        if found:
            break
```

- [ ] **Step 3: 修改 S2P 文件矩阵构建**

找到第 141 行：
```python
path_temp = os.path.join(folder0, f'{temp}K', f'actual_{temp_meas:.3f}K')
```
改为：
```python
path_temp = os.path.join(folder0, f'{temp}K')
```

- [ ] **Step 4: 验证语法正确**

```bash
cd D:\YBCO\VNAMeas\Data_process && python -c "import py_compile; py_compile.compile('otherwise/process_data_single_pixel.py', doraise=True); print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add Data_process/otherwise/process_data_single_pixel.py
git commit -m "feat: adapt process_data_single_pixel.py to flat directory structure"
```

---

## 验证清单 (全部完成后)

- [ ] `python -m pytest tests/test_experiment_merger.py -v` — 12 tests PASSED
- [ ] `python -m pytest tests/test_completeness_checker.py -v` — 10 tests PASSED
- [ ] `python experiment_merger.py --help` — 输出帮助
- [ ] `python completeness_checker.py --help` — 输出帮助
- [ ] 对 accomplish 真实数据完成合并 + 完整性分析
