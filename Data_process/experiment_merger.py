# -*- coding: utf-8 -*-
"""
实验数据碎片合并引擎。

将多次拆分运行的温度扫描数据合并为统一扁平目录。
"""

import os
import re
import shutil
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
    if strategy != "most_complete":
        raise ValueError(f"未知去重策略: {strategy}")

    mapping: Dict[Tuple[int, int, int], FileEntry] = {}
    conflicts: List[Tuple[int, int, int]] = []

    # 预计算每个片段在每个温度的 S2P 总数
    fragment_temp_counts: Dict[Tuple[Path, int], int] = defaultdict(int)
    for entries in index.values():
        for entry in entries:
            fragment_temp_counts[(entry.fragment_dir, entry.temp)] += 1

    def _sort_key(e: FileEntry) -> Tuple[int, float]:
        count = fragment_temp_counts.get((e.fragment_dir, e.temp), 0)
        mtime = e.fragment_dir.stat().st_mtime
        return (count, mtime)

    for key, entries in sorted(index.items()):
        if len(entries) == 1:
            mapping[key] = entries[0]
        else:
            conflicts.append(key)
            mapping[key] = max(entries, key=_sort_key)

    return MergePlan(mapping=mapping, conflicts=conflicts)


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
