# -*- coding: utf-8 -*-
"""
实验数据完整性检查器。

分析合并后的数据目录，生成完整性报告和补测建议清单。
"""

from pathlib import Path
from typing import List
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
