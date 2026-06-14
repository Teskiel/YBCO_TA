# -*- coding: utf-8 -*-
"""
实验数据完整性检查器。

分析合并后的数据目录，生成完整性报告和补测建议清单。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List
import numpy as np


@dataclass
class MissingPoint:
    """单个缺失数据点"""
    temp: int
    vna_power: int       # 正值, 如 25 表示 -25dBm
    laser_power: int
    category: str        # "isolated" | "edge" | "block"


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


def _is_edge(ti: int, num_temps: int) -> bool:
    """温度索引是否在边缘 (首/尾)"""
    return ti == 0 or ti == num_temps - 1


def _is_laser_edge(li: int, num_lasers: int) -> bool:
    """激光功率索引是否在边缘 (首/尾)"""
    return li == 0 or li == num_lasers - 1


def _group_consecutive(indices: List[int]) -> List[List[int]]:
    """将索引列表按连续性分组"""
    if not indices:
        return []
    groups = []
    group = [indices[0]]
    for i in range(1, len(indices)):
        if indices[i] == indices[i - 1] + 1:
            group.append(indices[i])
        else:
            groups.append(group)
            group = [indices[i]]
    groups.append(group)
    return groups


def diagnose_missing(
    matrix: np.ndarray,
    temps: List[int],
    vna_powers: List[int],
    laser_powers: List[int],
) -> List[MissingPoint]:
    """
    分类缺失原因 (双维度扫描 + 优先级合并):
    - "block"    — 同一 (vna, laser) 沿温度轴连续缺失 >=3 个,
                    或同一 (temp, vna) 沿激光轴连续缺失 >=3 个
    - "edge"     — 温度边缘缺失 (首/尾温度)
    - "isolated" — 孤立偶发缺失
    优先级: block > edge > isolated
    """
    n_t, n_v, n_l = matrix.shape
    # 用字典累积每个缺失格子的最佳分类
    best: dict[tuple, str] = {}

    def _set(ti: int, vi: int, li: int, cat: str):
        key = (ti, vi, li)
        order = {"block": 3, "edge": 2, "isolated": 1}
        if key not in best or order[cat] > order[best[key]]:
            best[key] = cat

    # 维度1: 沿温度轴 — 对每个 (vna, laser) 扫描
    for vi in range(n_v):
        for li in range(n_l):
            missing_tis = [ti for ti in range(n_t) if not matrix[ti, vi, li]]
            for g in _group_consecutive(missing_tis):
                if len(g) >= 3:
                    cat = "block"
                elif _is_edge(g[0], n_t):
                    cat = "edge"
                else:
                    cat = "isolated"
                for ti in g:
                    _set(ti, vi, li, cat)

    # 维度2: 沿激光轴 — 对每个 (temp, vna) 扫描
    for ti in range(n_t):
        for vi in range(n_v):
            missing_lis = [li for li in range(n_l) if not matrix[ti, vi, li]]
            for g in _group_consecutive(missing_lis):
                if len(g) >= 3:
                    cat = "block"
                elif _is_laser_edge(g[0], n_l):
                    cat = "edge"
                else:
                    cat = "isolated"
                for li in g:
                    _set(ti, vi, li, cat)

    # 构建 MissingPoint 列表
    missing: List[MissingPoint] = []
    for (ti, vi, li), cat in best.items():
        missing.append(MissingPoint(
            temp=temps[ti],
            vna_power=vna_powers[vi],
            laser_power=laser_powers[li],
            category=cat,
        ))

    return missing
